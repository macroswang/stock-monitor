"""Read-only, account-scoped chart projection. Receipts are not fills."""
import json
from datetime import date
from . import brokers
from .broker_reconciliation import known_id


def chart(store,code,day):
    date.fromisoformat(day)
    accounts=[]
    for r in store.query('SELECT r.account_id,r.payload,a.broker,a.account FROM trading_rules r JOIN broker_accounts a ON a.id=r.account_id WHERE r.code=?',(code,)):
        rule=json.loads(r['payload'])
        accounts.append(dict(id=r['account_id'],broker_name=brokers._spec(r['broker']).name,account_masked=brokers.mask_account(r['account']),
                             buy_enabled=rule.get('buy_enabled',False),sell_enabled=rule.get('sell_enabled',False)))
    points=[]
    rows=store.query('''SELECT r.*,a.broker,a.account,b.result AS broker_result,b.created_at AS request_at
        FROM trading_runs r LEFT JOIN broker_accounts a ON a.id=r.account_id
        LEFT JOIN broker_requests b ON b.request_id='auto_'||r.id AND b.account_id=r.account_id
        WHERE r.code=? AND r.day=? ORDER BY r.created_at,r.id LIMIT 500''',(code,day))
    for r in rows:
        p=json.loads(r['payload']);plan=p.get('plan',{});v=p.get('verification',{})
        ack=json.loads(r['broker_result'] or '{}');signal=p.get('signal',{})
        try:order_id=known_id(ack)
        except ValueError:order_id=''
        # Only the broker-validated execution average is an actual fill price.
        fill_price=v.get('average') if v.get('origin')=='broker_auto' and v.get('status') in ('partial','filled','cancelled') and v.get('filled',0)>0 else None
        sent=p.get('price_checks',{}).get('before_submit',{}).get('checked_at') or r['request_at']
        points.append(dict(id=r['id'],account_id=r['account_id'],broker_name=brokers._spec(r['broker']).name if r['broker'] else '已移除账户',
            account_masked=brokers.mask_account(r['account'] or ''),code=code,day=day,side=r['side'],status=r['status'],mode=p.get('mode','trial'),
            signal_key=signal.get('key'),signal_time=signal.get('time'),reference_price=p.get('reference_price',signal.get('price')),
            created_at=r['created_at'],ordered_at=sent,order_price=plan.get('price'),quantity=plan.get('quantity'),order_id=order_id,
            filled=v.get('filled'),fill_price=fill_price,message=p.get('message',''),reconciliation=p.get('reconciliation'),
            attempted=bool(r['request_at']),receipt_message=ack.get('result',{}).get('message',''),admission=p.get('admission')))
    return dict(code=code,day=day,accounts=accounts,points=points)
