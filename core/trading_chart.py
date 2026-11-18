"""Account-scoped chart projection and explicit broker-fill cache sync."""
import hashlib
import json
import re
from datetime import date,datetime,timedelta
from . import brokers
from .broker_reconciliation import known_id, request_plan, amount, shares
from .provider import now_cn,CN
from executor.trade import parse_result_message

CACHE_KIND='broker_filled_orders_v1'


def _fill_cache(store, account_id, day):
    cached=store.getcache('broker-account:'+account_id,CACHE_KIND,day)
    payload=cached[0]['data'] if cached else {}
    if (isinstance(payload,dict) and payload.get('account_id')==account_id and payload.get('account_verified') is True and
        payload.get('complete') is True and payload.get('day')==day and
        isinstance(payload.get('observed_at'),str) and payload['observed_at'].startswith(day+'T') and
        isinstance(payload.get('rows'),list)):
        try:
            observed=datetime.fromisoformat(payload['observed_at'])
            if (observed.tzinfo is not None and observed.astimezone(CN).date().isoformat()==day and
                observed<=now_cn()+timedelta(seconds=5)):return payload
        except (ValueError,TypeError):pass
    return None


def _manual_submissions(store, code, day):
    points=[];owners=[]
    rows=store.query("SELECT b.*,a.broker,a.account FROM broker_requests b JOIN broker_accounts a ON a.id=b.account_id "
                     "WHERE b.request_id NOT LIKE 'auto_%' AND substr(b.created_at,1,10)=? AND a.enabled=1",(day,))
    for row in rows:
        try:
            plan,request_day=request_plan(row)
            result=json.loads(row['result'] or '{}')
            if request_day!=day or plan['code']!=code[2:] or result.get('submitted') is not True:
                continue
            submitted=result.get('submitted_at') or row['created_at']
            cached=_fill_cache(store,row['account_id'],day)
            try:order_id=known_id(result)
            except ValueError:order_id=''
            # 用户完整同步后，以券商实际成交点替换待同步的手动委托点。
            point=dict(id='manual-'+row['request_id'],source='manual',account_id=row['account_id'],
                broker_name=brokers._spec(row['broker']).name,account_masked=brokers.mask_account(row['account']),
                code=code,day=day,side=plan['side'],status=row['status'],mode='live',created_at=row['created_at'],
                ordered_at=submitted,order_price=plan['price'],quantity=plan['quantity'],order_id=order_id,
                attempted=True,message='手动委托已发送，待手动同步成交')
            owners.append(point)
            if not (cached and cached['observed_at']>=submitted):points.append(point)
        except (ValueError,TypeError,KeyError):
            continue
    return points,owners


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


def _native_cached_match(point,row,key,day):
    """Match an ID-less verified order by its exact native identity, not minute."""
    if (not isinstance(row,dict) or not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key) or
        point.get('order_id') or point.get('mode')!='live' or not point.get('attempted') or
        point.get('status') not in ('partial','filled','cancelled') or not row.get('order_id') or
        row.get('date') not in (None,'',day) or row.get('side')!=point['side'] or
        (row.get('code') and str(row['code'])[-6:]!=point['code'][2:])):return False
    try:
        filled=shares(row.get('filled'))
        if (filled<=0 or filled!=shares(point.get('filled')) or filled>shares(point.get('quantity')) or
            amount(row.get('average'))<=0 or amount(row['average'])!=amount(point.get('fill_price')) or
            (row.get('quantity') is not None and shares(row['quantity'])!=shares(point.get('quantity')))):return False
        from executor.ths_orders import order_key
        return order_key(dict(date=day,time=row['time'],name=row['name'],side=row['side'],
                              price=point['order_price'],quantity=point['quantity']))==key
    except (KeyError,ValueError,TypeError):return False


def _native_submission_evidence(row,payload,ack,day):
    """Recover only the time already proved by a durable native-order key.

    A contract-fill timestamp may be minutes later than the order timestamp.
    This is a display association, never a new execution/order binding.
    """
    try:
        verification=payload.get('verification',{})
        if known_id(ack):return None
        if (row['broker']!='ths' or payload.get('mode')!='live' or
            verification.get('origin')!='broker_auto' or verification.get('source')!='ths_native_today_order' or
            verification.get('status') not in ('accepted','partial','filled','cancelled') or row['status']!=verification.get('status') or
            verification!=ack.get('verification') or
            not re.fullmatch(r'[a-f0-9]{64}',str(verification.get('native_order_key',''))) or
            not re.fullmatch(r'[a-f0-9]{64}',str(verification.get('evidence_hash','')))):return None
        expected,request_day=request_plan(dict(payload=row['request_payload'],account_id=row['account_id'],created_at=row['request_at']))
        plan=payload.get('plan',{});confirm=(ack.get('acknowledgement') or ack).get('confirm',{})
        recovery=ack.get('receipt_recovery',{})
        if (request_day!=day or expected['code']!=row['code'][2:] or expected['side']!=row['side'] or
            recovery.get('method')!='native_order_list' or not confirm.get('name') or
            any(plan.get(k)!=v for k,v in dict(account_id=row['account_id'],code=row['code'],side=row['side']).items()) or
            confirm.get('code')!=expected['code'] or confirm.get('side')!=expected['side'] or
            shares(confirm.get('quantity'))!=expected['quantity'] or shares(plan.get('quantity'))!=expected['quantity'] or
            amount(confirm.get('price'))!=amount(expected['price']) or amount(plan.get('price'))!=amount(expected['price'])):return None
        submitted=datetime.fromisoformat(recovery['submitted_at']);observed=datetime.fromisoformat(verification['observed_at'])
        created=datetime.fromisoformat(row['request_at'])
        if datetime.fromisoformat(payload['price_checks']['before_submit']['checked_at'])!=submitted:return None
        executed=shares(verification.get('filled'))
        status=verification['status'];quantity=expected['quantity']
        if (not 0<=executed<=quantity or status=='accepted' and executed!=0 or
            status=='partial' and not 0<executed<quantity or status=='filled' and executed!=quantity or
            status=='cancelled' and executed>=quantity):return None
        if (any(t.tzinfo is None or t.astimezone(CN).date().isoformat()!=day for t in (created,submitted,observed)) or
            not created<=submitted<=observed<=now_cn()+timedelta(seconds=5)):return None
        from executor.ths_orders import order_key
        # The original reconciliation admits only this bounded submission window.
        for offset in range(-2,17):
            stamp=(submitted+timedelta(seconds=offset)).astimezone(CN).replace(microsecond=0)
            if not -2<=(stamp-submitted).total_seconds()<=15:continue
            identity=dict(date=day,time=stamp.strftime('%H:%M:%S'),name=confirm['name'],side=row['side'],price=expected['price'],quantity=expected['quantity'])
            if order_key(identity)==verification['native_order_key']:
                return dict(ordered_at=stamp,verified_at=observed,name=confirm['name'])
    except (ValueError,TypeError,KeyError,AttributeError):pass
    return None


def _cumulative_compatible(point,row,evidence,payload):
    """Compare cumulative snapshots; never add one snapshot to another."""
    try:
        filled=shares(row.get('filled'));average=amount(row.get('average'))
        previous=shares(point.get('filled') or 0);quantity=shares(point['quantity']);limit=amount(point['order_price'])
        money=amount(row['amount']);cached=datetime.fromisoformat(payload['observed_at'])
        stamp=datetime.fromisoformat(point['day']+'T'+row['time']).replace(tzinfo=CN)
        if (not 0<filled<=quantity or average<=0 or
            row.get('quantity') is not None and shares(row['quantity'])!=quantity or
            row.get('price') is not None and amount(row['price'])!=limit or
            abs(average*filled-money)>amount('.0005')*filled+amount('.01') or
            (point['side']=='buy' and average>limit) or (point['side']=='sell' and average<limit) or
            cached.tzinfo is None or not evidence['ordered_at']<=stamp<=cached<=now_cn()+timedelta(seconds=5)):
            return False
        if cached<evidence['verified_at']:
            if filled>previous:return False
        elif filled<previous:return False
        # A completed/cancelled order cannot acquire later fills. A cache which
        # contains no new shares cannot move its fill time past verification.
        if ((point['status'] in ('filled','cancelled') and filled>previous) or
            (filled<=previous and stamp>evidence['verified_at'])):return False
        if not previous:return point['status']=='accepted' and stamp>evidence['verified_at']
        previous_average=amount(point.get('fill_price'))
        if previous_average<=0:return False
        if filled==previous:return average==previous_average
        # An incremental fill must itself respect the original limit, including
        # the broker's rounded cumulative average. Checking only overall VWAP
        # would accept impossible changes hidden by earlier better prices.
        delta=filled-previous;cash=average*filled-previous_average*previous
        tolerance=amount('.0005')*(filled+previous)+amount('.01')
        if delta<0:delta=-delta;cash=-cash
        if cash<=0:return False
        return cash<=limit*delta+tolerance if point['side']=='buy' else cash+tolerance>=limit*delta
    except (ValueError,TypeError,KeyError):return False


def _delayed_native_cached_match(point,row,evidence,day,payload):
    if not evidence or not isinstance(row,dict) or point.get('order_id') or not row.get('order_id'):return False
    if (row.get('date')!=day or str(row.get('code',''))[-6:]!=point['code'][2:] or
        row.get('name')!=evidence['name'] or row.get('side')!=point['side'] or
        point.get('status') not in ('accepted','partial','filled','cancelled') or
        not re.fullmatch(r'\d{2}:\d{2}:\d{2}',str(row.get('time','')))):return False
    return _cumulative_compatible(point,row,evidence,payload)


def _possible_owner(point,row,day):
    """An unresolved competing submission must block an inferred contract.

    Different partial quantities/averages are not evidence of different orders.
    Exact known contracts are handled separately before inference.
    """
    if (point.get('order_id') or point.get('mode')!='live' or not point.get('attempted') or
        point.get('status') not in ('sending','accepted','unknown','partial','filled','cancelled') or
        point.get('side')!=row.get('side')):return False
    try:
        quantity=shares(point.get('quantity'));limit=amount(point.get('order_price'));average=amount(row.get('average'))
        submitted=datetime.fromisoformat(point['ordered_at'])
        stamp=datetime.fromisoformat(day+'T'+row['time']).replace(tzinfo=CN)
        return (0<shares(row['filled'])<=quantity and limit>0 and average>0 and
            (row.get('quantity') is None or shares(row['quantity'])==quantity) and
            (row.get('price') is None or amount(row['price'])==limit) and
            submitted.tzinfo is not None and stamp>=submitted-timedelta(seconds=2) and
            (average<=limit if point['side']=='buy' else average>=limit))
    except (ValueError,TypeError,KeyError):return False


def _same_tight_fill(point,row,day):
    """Same id-less fill within 0.5s; never merge a same-minute distinct order."""
    if (point.get('order_id') or point.get('mode')!='live' or not point.get('attempted') or
        point.get('status') not in ('partial','filled') or point.get('side')!=row.get('side') or
        not point.get('ordered_at') or not re.fullmatch(r'\d{2}:\d{2}:\d{2}',str(row.get('time','')))):return False
    try:
        filled=shares(point.get('filled'));row_filled=shares(row.get('filled'))
        fill=amount(point.get('fill_price'));average=amount(row.get('average'))
        if filled<=0 or filled!=row_filled or fill<=0 or fill!=average:return False
        quantity=shares(point.get('quantity'))
        if row.get('quantity') is not None and quantity!=shares(row['quantity']):return False
        stamp=datetime.fromisoformat(day+'T'+row['time']).replace(tzinfo=CN)
        ordered=datetime.fromisoformat(point['ordered_at'])
        return ordered.tzinfo is not None and abs((stamp-ordered).total_seconds())<=0.5
    except (ValueError,TypeError,KeyError):
        return False


def _cache_rows(payload,code,day,target_name):
    """Validate once and deduplicate only identical cumulative contract rows."""
    rows=[];contracts={};conflicts=set()
    observed=datetime.fromisoformat(payload['observed_at'])
    for row in payload['rows']:
        if not isinstance(row,dict) or row.get('date') not in (None,'',day):continue
        raw_code=str(row.get('code',''))[-6:]
        if raw_code!=code[2:] and not (not raw_code and target_name and row.get('name')==target_name):continue
        clock=str(row.get('time',''))
        if row.get('side') not in ('buy','sell') or not re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?',clock):continue
        try:
            stamp=datetime.fromisoformat(day+'T'+clock).replace(tzinfo=CN)
            quantity=shares(row.get('quantity') or row.get('filled'));filled=shares(row.get('filled'))
            price=amount(row['price']) if row.get('price') is not None else 0
            average=amount(row['average']) if row.get('average') is not None else 0
            if stamp>observed or quantity<=0 or not 0<filled<=quantity or not (price>0 or average>0):continue
        except (ValueError,TypeError):continue
        ident=str(row.get('order_id') or '')
        if ident:
            if ident in contracts:
                if row!=contracts[ident]:conflicts.add(ident)
                continue  # Contract aggregates are snapshots, not fill fragments.
            contracts[ident]=row
        rows.append(row)
    return [row for row in rows if str(row.get('order_id') or '') not in conflicts]


def _enrich_native_point(point,row,evidence,payload):
    point['order_id']=str(row['order_id'])
    point['filled_at']=point['day']+'T'+row['time']+('+08:00' if len(row['time'])==8 else ':00+08:00')
    point['cache_observed_at']=payload['observed_at']
    if evidence and datetime.fromisoformat(payload['observed_at'])>=evidence['verified_at']:
        # Projection only: never persist these fresher display values into the
        # execution journal or use them for admission/reconciliation.
        previous=point['status'];filled=shares(row['filled'])
        point['filled']=filled;point['fill_price']=str(row['average'])
        if previous!='cancelled':point['status']='filled' if filled==shares(point['quantity']) else 'partial'
        if point['status']!=previous:point['execution_status']=previous


def _cached_fills(store,code,day,automatic,native_keys,native_evidence,owners):
    named=store.query('SELECT name FROM instruments WHERE code=?',(code,))
    target_name=named[0]['name'] if len(named)==1 else ''
    points=[]
    accounts=store.query('SELECT * FROM broker_accounts WHERE enabled=1 ORDER BY created_at,id')
    for account in accounts:
        payload=_fill_cache(store,account['id'],day)
        if not payload:continue
        rows=_cache_rows(payload,code,day,target_name)
        account_points=[p for p in automatic if p['account_id']==account['id']]
        account_point_ids={p['id'] for p in account_points}
        account_owners=[p for p in owners if p['account_id']==account['id']]
        known={(p['side'],str(p['order_id'])) for p in account_owners if p.get('order_id')}
        visible_known={(p['side'],str(p['order_id'])) for p in account_points if p.get('order_id')}
        inferred={};reverse={}
        if account['broker']=='ths' and payload.get('source')=='ths_native_contract_group':
            # Freeze the complete matching graph before enriching any point.
            # Traversal order must not turn an ambiguous match into a unique one.
            for index,row in enumerate(rows):
                if (row['side'],str(row.get('order_id') or '')) in known:continue
                possible=[p for p in account_owners if _possible_owner(p,row,day)]
                # A sub-second fill match is strong display evidence for the same
                # order even when the broker omitted its order id. Keep it far
                # tighter than the ambiguous same-minute case (2s+).
                tight=[p for p in possible if _same_tight_fill(p,row,day)]
                if len(tight)==1:
                    reverse[tight[0]['id']]=reverse.get(tight[0]['id'],0)+1
                    inferred[index]=tight[0]
                    continue
                matches=[p for p in possible if p['id'] in account_point_ids and
                    (_native_cached_match(p,row,native_keys.get(p['id']),day) or
                     _delayed_native_cached_match(p,row,native_evidence.get(p['id']),day,payload))]
                for point in matches:reverse[point['id']]=reverse.get(point['id'],0)+1
                if len(possible)==1 and len(matches)==1:
                    inferred[index]=matches[0]
        occurrences={}
        tight_matched=set()
        for index,row in enumerate(rows):
            order_id=str(row.get('order_id') or '');side=row['side'];clock=row['time']
            if (side,order_id) in visible_known:continue
            # Broker and local records can both omit an order id; a sub-second
            # identical fill is the same display execution, not a second order.
            tight=[p for p in account_owners if p['id'] not in tight_matched and _same_tight_fill(p,row,day)]
            if len(tight)==1:
                _enrich_native_point(tight[0],row,None,payload)
                tight_matched.add(tight[0]['id'])
                continue
            point=inferred.get(index)
            if point is not None and reverse[point['id']]==1:
                _enrich_native_point(point,row,native_evidence.get(point['id']),payload)
                continue
            quantity=shares(row.get('quantity') or row.get('filled'));filled=shares(row['filled'])
            order_price=float(row['price']) if row.get('price') is not None else None
            fill_price=float(row['average']) if row.get('average') is not None else None
            identity=json.dumps([account['id'],day,str(row.get('code','')) or row.get('name'),side,clock,order_id,order_price,fill_price,quantity,filled],ensure_ascii=False)
            occurrence=occurrences.get(identity,0);occurrences[identity]=occurrence+1
            ident=hashlib.sha256((identity+'|'+str(occurrence)).encode()).hexdigest()
            status=row.get('status') if row.get('status') in ('partial','filled','cancelled') else 'filled'
            points.append(dict(id='broker-fill-'+ident,source='broker_cache',account_id=account['id'],
                broker_name=brokers._spec(account['broker']).name,account_masked=brokers.mask_account(account['account']),
                code=code,day=day,side=side,status=status,mode='broker',created_at=day+'T'+clock+("+08:00" if len(clock)==8 else ':00+08:00'),
                ordered_at=day+'T'+clock+("+08:00" if len(clock)==8 else ':00+08:00'),order_price=order_price,
                quantity=quantity,order_id=order_id,filled=filled,fill_price=fill_price,attempted=True,
                message='券商账户当日成交缓存',cache_observed_at=payload['observed_at'],broker_state=row.get('broker_state') or row.get('state')))
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


def _archive_after(day,now):
    """Display cleanup starts on the next verified exchange session, not a weekday guess."""
    if day>=now.date().isoformat():return False
    from .breadth import _next_verified_trading_day
    following=_next_verified_trading_day(date.fromisoformat(day))
    return following is not None and following<=now.date()


def _verified_unfilled(row,payload,ack,day,now):
    """Never infer non-execution from an acknowledgement or a missing fill row.

    An intraday accepted/zero snapshot can still fill later. Only a post-close
    zero snapshot, or a terminal zero result, qualifies for display cleanup.
    This projection cannot change order status, paired cycles or durable evidence.
    """
    try:
        v=payload.get('verification',{});status=row['status']
        if (payload.get('mode')!='live' or status not in ('accepted','cancelled','rejected') or
            row.get('request_status')!=status or v.get('origin')!='broker_auto' or
            v.get('status')!=status or shares(v.get('filled'))!=0 or ack.get('verification')!=v or
            payload.get('reconciliation',{}).get('ok') is not True or ack.get('reconciliation',{}).get('ok') is not True or
            not v.get('source') or not re.fullmatch(r'[a-f0-9]{64}',v.get('evidence_hash',''))):return False
        expected,request_day=request_plan(dict(payload=row['request_payload'],account_id=row['account_id'],created_at=row['request_at']))
        plan=payload.get('plan',{})
        if (request_day!=day or expected['code']!=row['code'][2:] or expected['side']!=row['side'] or
            plan.get('account_id')!=row['account_id'] or plan.get('code')!=row['code'] or plan.get('side')!=row['side'] or
            shares(plan.get('quantity'))!=expected['quantity'] or amount(plan.get('price'))!=amount(expected['price'])):return False
        ident=known_id(ack)
        if ident:
            if v.get('order_id')!=ident:return False
        elif _native_submission_evidence(row,payload,ack,day) is None:return False
        observed=datetime.fromisoformat(v['observed_at']);checked=datetime.fromisoformat(v['at'])
        if observed.tzinfo is None or checked.tzinfo is None or not datetime.fromisoformat(row['request_at'])<=observed<=checked<=now:return False
        close=datetime.fromisoformat(day+'T15:00:00+08:00')
        return status in ('cancelled','rejected') or observed>=close
    except (KeyError,ValueError,TypeError):return False


def chart(store,code,day):
    date.fromisoformat(day)
    now=now_cn();archive=_archive_after(day,now)
    accounts=[]
    for r in store.query('SELECT r.account_id,r.payload,a.broker,a.account FROM trading_rules r JOIN broker_accounts a ON a.id=r.account_id WHERE r.code=?',(code,)):
        rule=json.loads(r['payload'])
        accounts.append(dict(id=r['account_id'],broker_name=brokers._spec(r['broker']).name,account_masked=brokers.mask_account(r['account']),
                             buy_enabled=rule.get('buy_enabled',False),sell_enabled=rule.get('sell_enabled',False)))
    points=[];native_keys={};native_evidence={}
    rows=store.query('''SELECT r.*,a.broker,a.account,b.result AS broker_result,b.created_at AS request_at,
        b.payload AS request_payload,b.status AS request_status
        FROM trading_runs r LEFT JOIN broker_accounts a ON a.id=r.account_id
        LEFT JOIN broker_requests b ON b.request_id='auto_'||r.id AND b.account_id=r.account_id
        WHERE r.code=? AND r.day=? ORDER BY r.created_at,r.id''',(code,day))
    for r in rows:
        p=json.loads(r['payload']);plan=p.get('plan',{});v=p.get('verification',{})
        ack=json.loads(r['broker_result'] or '{}');signal=p.get('signal',{})
        if v.get('origin')=='broker_auto' and v.get('source')=='ths_native_today_order':
            native_evidence[r['id']]=_native_submission_evidence(r,p,ack,day)
            # Retain exact-key support for old minimal records. A present but
            # invalid newer evidence chain must never fall back to this path.
            if (not ack and not v.get('observed_at') and not v.get('evidence_hash') and v.get('status')==r['status']):
                native_keys[r['id']]=v.get('native_order_key')
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
        if archive and _verified_unfilled(r,p,ack,day,now):points[-1]['archived_unfilled']=True
    manual,manual_owners=_manual_submissions(store,code,day)
    owners=points+manual_owners
    points.extend(manual)
    points.extend(_cached_fills(store,code,day,points,native_keys,native_evidence,owners))
    # New verified fills must always remain visible, even if a prior zero result
    # was eligible for cleanup before the fill cache was merged.
    for point in points:
        if point.get('archived_unfilled') and (point.get('filled')!=0 or point.get('status') not in ('accepted','cancelled','rejected')):
            point.pop('archived_unfilled',None)
    return dict(code=code,day=day,accounts=accounts,points=points)
