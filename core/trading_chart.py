"""Read-only, account-scoped chart projection. Receipts are not fills."""
import json
from datetime import date
from . import brokers
from .broker_reconciliation import known_id, request_plan, amount, shares
from executor.trade import parse_result_message


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
        WHERE r.code=? AND r.day=? ORDER BY r.created_at,r.id LIMIT 500''',(code,day))
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
            attempted=bool(r['request_at']),receipt_accepted=bool(receipt_id),receipt_message=receipt.get('message',''),admission=p.get('admission')))
    return dict(code=code,day=day,accounts=accounts,points=points)
