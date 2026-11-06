"""Account-scoped chart projection and explicit broker-fill cache sync."""
import hashlib
import json
import re
from datetime import date
from . import brokers
from .broker_reconciliation import known_id, request_plan, amount, shares
from .provider import now_cn
from executor.trade import parse_result_message

CACHE_KIND='broker_filled_orders_v1'


def sync_filled_orders(store,day):
    """Read complete broker-side fills and replace only verified account caches."""
    date.fromisoformat(day)
    if day!=now_cn().date().isoformat():raise ValueError('只能同步券商账户今天的成交委托')
    accounts=store.query('SELECT * FROM broker_accounts WHERE enabled=1 ORDER BY created_at,id')
    saved=0;errors=[]
    for account in accounts:
        try:
            result=brokers.filled_orders(store,account['id'],day)
            store.cache('broker-account:'+account['id'],CACHE_KIND,day,result)
            saved+=len(result['rows'])
        except Exception as exc:
            errors.append(dict(account_id=account['id'],account_masked=brokers.mask_account(account['account']),error=str(exc) or type(exc).__name__))
    return dict(day=day,accounts=len(accounts),saved=saved,errors=errors,
                message=f'已缓存 {saved} 条券商当日成交委托'+(f'；{len(errors)} 个账户未更新，已保留旧缓存' if errors else ''))


def _cached_fills(store,code,day,automatic):
    raw_code=code[2:]
    named=store.query('SELECT name FROM instruments WHERE code=?',(code,))
    target_name=named[0]['name'] if len(named)==1 else ''
    points=[]
    accounts=store.query('SELECT * FROM broker_accounts WHERE enabled=1 ORDER BY created_at,id')
    for account in accounts:
        cached=store.getcache('broker-account:'+account['id'],CACHE_KIND,day)
        if not cached:continue
        payload=cached[0]['data']
        if (payload.get('account_id')!=account['id'] or payload.get('account_verified') is not True or
            payload.get('complete') is not True or payload.get('day')!=day or
            not isinstance(payload.get('observed_at'),str) or not payload['observed_at'].startswith(day+'T') or
            not isinstance(payload.get('rows'),list)):continue
        occurrences={}
        for row in payload['rows']:
            if not isinstance(row,dict):continue
            if row.get('date') not in (None,'',day):continue
            row_code=str(row.get('code',''))[-6:]
            if row_code!=raw_code and not (not row_code and target_name and row.get('name')==target_name):continue
            side=row.get('side');clock=str(row.get('time',''))
            if side not in ('buy','sell') or not re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?',clock):continue
            try:
                quantity=int(row.get('quantity') or row.get('filled'));filled=int(row.get('filled'))
                order_price=float(row.get('price')) if row.get('price') is not None else None
                fill_price=float(row.get('average')) if row.get('average') is not None else None
            except (ValueError,TypeError):continue
            if quantity<=0 or filled<=0 or filled>quantity or not ((fill_price and fill_price>0) or (order_price and order_price>0)):continue
            order_id=str(row.get('order_id') or '')
            time=clock[:5]
            duplicate=False
            for point in automatic:
                if point['account_id']!=account['id'] or point['side']!=side:continue
                if order_id and point.get('order_id')==order_id:duplicate=True;break
                if (not order_id and not point.get('order_id') and point.get('quantity')==quantity and
                    (point.get('ordered_at') or '')[11:16]==time and order_price is not None and
                    point.get('order_price') is not None and amount(point['order_price'])==amount(order_price)):
                    duplicate=True;break
            if duplicate:continue
            identity=json.dumps([account['id'],day,row_code or row.get('name'),side,clock,order_id,order_price,fill_price,quantity,filled],ensure_ascii=False)
            occurrence=occurrences.get(identity,0);occurrences[identity]=occurrence+1
            ident=hashlib.sha256((identity+'|'+str(occurrence)).encode()).hexdigest()
            status=row.get('status') if row.get('status') in ('partial','filled','cancelled') else 'filled'
            points.append(dict(id='broker-fill-'+ident,source='broker_cache',account_id=account['id'],
                broker_name=brokers._spec(account['broker']).name,account_masked=brokers.mask_account(account['account']),
                code=code,day=day,side=side,status=status,mode='broker',created_at=day+'T'+clock+("+08:00" if len(clock)==8 else ':00+08:00'),
                ordered_at=day+'T'+clock+("+08:00" if len(clock)==8 else ':00+08:00'),order_price=order_price,
                quantity=quantity,order_id=order_id,filled=filled,fill_price=fill_price,attempted=True,
                message='券商账户当日成交缓存',cache_observed_at=payload.get('observed_at'),broker_state=row.get('broker_state') or row.get('state')))
    return points


def receipt_status(row,payload,ack):
    """Project an already durable acceptance after an interrupted run update."""
    original=row['status']
    if original not in ('sending','unknown') or row.get('request_status')!='accepted' or payload.get('mode')!='live':return original
    try:
        if not isinstance(ack,dict) or ack.get('status')!='accepted' or ack.get('submitted') is not True:return original
        known_id(ack)  # Conflicting receipt numbers cannot prove acceptance.
        expected,day=request_plan(dict(payload=row['request_payload'],account_id=row['account_id'],created_at=row['request_at']))
        plan=payload.get('plan',{});confirm=ack.get('confirm') or {}
        if not isinstance(confirm,dict):return original
        title={'buy':'委托买入','sell':'委托卖出'}[row['side']]
        side=confirm.get('side') or {'委托买入':'buy','委托卖出':'sell'}.get(confirm.get('title'))
        if (day==row['day'] and expected['code']==row['code'][2:] and expected['side']==row['side']
            and plan.get('account_id')==row['account_id'] and plan.get('code')==row['code'] and plan.get('side')==row['side']
            and shares(plan.get('quantity'))==expected['quantity'] and amount(plan.get('price'))==amount(expected['price'])
            and side==row['side'] and confirm.get('title',title)==title and confirm.get('code')==expected['code']
            and shares(confirm.get('quantity'))==expected['quantity'] and amount(confirm.get('price'))==amount(expected['price'])):
            return 'accepted'
    except (ValueError,TypeError,KeyError):pass
    return original


def legacy_receipt_id(row, payload, ack):
    """Recover a display-only acknowledgement; never settle or rewrite a run."""
    if row['status'] != 'unknown' or row['request_status'] != 'unknown' or payload.get('mode') != 'live':
        return ''
    try:
        expected, day = request_plan(dict(payload=row['request_payload'], account_id=row['account_id'], created_at=row['request_at']))
        plan = payload.get('plan', {})
        confirm = ack.get('confirm') or {}
        if not isinstance(confirm,dict):return ''
        if (day != row['day'] or expected['code'] != row['code'][2:] or expected['side'] != row['side'] or
            plan.get('account_id') != row['account_id'] or plan.get('code') != row['code'] or plan.get('side') != row['side'] or
            shares(plan.get('quantity')) != expected['quantity'] or amount(plan.get('price')) != amount(expected['price']) or
            confirm.get('title') != {'buy':'委托买入', 'sell':'委托卖出'}[row['side']] or
            confirm.get('code') != expected['code'] or shares(confirm.get('quantity')) != expected['quantity'] or
            amount(confirm.get('price')) != amount(expected['price'])):
            return ''
        receipt = ack.get('result') or {}
        if not isinstance(receipt,dict):return ''
        if receipt.get('kind') not in ('unknown', 'success') or not isinstance(receipt.get('message'), str):return ''
        parsed = parse_result_message(receipt.get('message', ''), receipt.get('title', ''))
        ident = parsed.as_dict().get('order_id', '') if parsed and parsed.kind == 'success' else ''
        existing = known_id(ack)
        if not ident or (existing and existing != ident):return ''
        return ident
    except (ValueError, TypeError, KeyError):
        return ''


def chart(store,code,day):
    date.fromisoformat(day)
    accounts=[]
    for r in store.query('SELECT r.account_id,r.payload,a.broker,a.account FROM trading_rules r JOIN broker_accounts a ON a.id=r.account_id WHERE r.code=?',(code,)):
        rule=json.loads(r['payload'])
        accounts.append(dict(id=r['account_id'],broker_name=brokers._spec(r['broker']).name,account_masked=brokers.mask_account(r['account']),
                             buy_enabled=rule.get('buy_enabled',False),sell_enabled=rule.get('sell_enabled',False)))
    points=[]
    rows=store.query('''SELECT r.*,a.broker,a.account,b.result AS broker_result,b.created_at AS request_at,
        b.payload AS request_payload,b.status AS request_status
        FROM trading_runs r LEFT JOIN broker_accounts a ON a.id=r.account_id
        LEFT JOIN broker_requests b ON b.request_id='auto_'||r.id AND b.account_id=r.account_id
        WHERE r.code=? AND r.day=? ORDER BY r.created_at,r.id''',(code,day))
    for r in rows:
        p=json.loads(r['payload']);plan=p.get('plan',{});v=p.get('verification',{})
        ack=json.loads(r['broker_result'] or '{}');signal=p.get('signal',{})
        try:order_id=known_id(ack)
        except ValueError:order_id=''
        receipt_id=legacy_receipt_id(r,p,ack)
        receipt=ack.get('result')
        if not isinstance(receipt,dict):receipt={}
        # Only the broker-validated execution average is an actual fill price.
        fill_price=v.get('average') if v.get('origin')=='broker_auto' and v.get('status') in ('partial','filled','cancelled') and v.get('filled',0)>0 else None
        sent=p.get('price_checks',{}).get('before_submit',{}).get('checked_at') or r['request_at']
        points.append(dict(id=r['id'],account_id=r['account_id'],broker_name=brokers._spec(r['broker']).name if r['broker'] else '已移除账户',
            account_masked=brokers.mask_account(r['account'] or ''),code=code,day=day,side=r['side'],status=receipt_status(r,p,ack),mode=p.get('mode','trial'),
            signal_key=signal.get('key'),signal_time=signal.get('time'),reference_price=p.get('reference_price',signal.get('price')),
            created_at=r['created_at'],ordered_at=sent,order_price=plan.get('price'),quantity=plan.get('quantity'),order_id=order_id or receipt_id,
            filled=v.get('filled'),fill_price=fill_price,message=p.get('message',''),reconciliation=p.get('reconciliation'),
            attempted=r['request_status'] in ('sending','accepted','unknown','partial','filled','cancelled','rejected'),receipt_accepted=bool(receipt_id),receipt_message=receipt.get('message',''),admission=p.get('admission'),source='automatic'))
    points.extend(_cached_fills(store,code,day,points))
    return dict(code=code,day=day,accounts=accounts,points=points)
