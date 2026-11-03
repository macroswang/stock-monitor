"""Isolated IPC backend for browser integration tests. No real account/device IO."""
import json
import os
from datetime import timedelta
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.app import App
from core import brokers
from core.provider import now_cn
from executor.adb import Adb

tmp=tempfile.TemporaryDirectory()
os.environ['STOCK_MONITOR_DATA']=tmp.name
app=App(tmp.name,start_worker=False)
app.provider=Mock()
app.provider.quote.side_effect=lambda code:dict(code=code,name={'sz000981':'山子高科','sh603002':'宏昌电子'}.get(code,'未知'),price='2.13',timestamp=now_cn().isoformat())
app.quotes['sz000981']=app.provider.quote('sz000981')
for ident,broker,number in [('test-a','zhangle','1234561001'),('test-b','ths','9876542002')]:
    app.store.execute('INSERT INTO broker_accounts(id,broker,account,label) VALUES(?,?,?,?)',(ident,broker,number,'隔离测试账户'))
    brokers.SecretStore().set(broker,number,'password','fixture-only-password')

def holdings(_store,ident):
    positions=[dict(name='山子高科',code='sz000981',quantity=1200 if ident=='test-a' else 600,sellable=900 if ident=='test-a' else 600,price=2.13,cost=2.05)]
    if ident=='test-b':positions.append(dict(name='宏昌电子',quantity=500,sellable=500,price=2.13))
    return dict(account_id=ident,account_verified=True,observed_at=now_cn().isoformat(),complete=True,positions=positions,
                funds={'available':'25000' if ident=='test-a' else '1000','market_value':'2556' if ident=='test-a' else '2343','total_assets':'27556' if ident=='test-a' else '3343'})

sync_gate=threading.Event();sync_gate.set()
original_holdings=holdings
def delayed_holdings(*args):
    if not sync_gate.wait(10):raise ValueError("隔离测试同步超时")
    return original_holdings(*args)
brokers.holdings=delayed_holdings

broker_checks=[]
def ready(_store,ident,secrets=None):
    broker_checks.append(ident)
    return dict(account_verified=True,logged_in=True)
brokers.ensure_ready=ready
brokers.login=ready
brokers.holdings=holdings
def forbidden(*args,**kwargs):
    raise AssertionError('Integration test attempted real device/order IO')
Adb.run=forbidden
brokers.submit_order=forbidden
brokers.preview_order=forbidden
brokers.cancel=forbidden

def report(_store,account,ident,day,expected,secrets=None):
    if ident!='fixture-'+account:return dict(found=False,account_id=account,account_verified=True,observed_at=now_cn().isoformat())
    return dict(found=True,account_id=account,account_verified=True,observed_at=now_cn().isoformat(),order_id=ident,
                date=day,time=(now_cn()-timedelta(seconds=30)).strftime('%H:%M:%S'),date_source='broker_row',
                **expected,filled=expected['quantity'],status='filled',source='isolated_fixture',evidence_hash='a'*64)
brokers.order_report=report

def seed_reports():
    # Both fixture accounts use the report-capable protocol for isolation tests.
    app.store.execute("UPDATE broker_accounts SET broker='zhangle' WHERE id='test-b'")
    stamp=(now_cn()-timedelta(seconds=35)).isoformat()
    for account in ('test-a','test-b'):
        ident='report-'+account
        plan=dict(account_id=account,code='sz000981',side='sell',quantity=100,price='2.13',value=213)
        payload=dict(mode='live',plan=plan,signal_source='shape-v1',signal=dict(time='10:01',kind='top'))
        app.store.execute('INSERT OR REPLACE INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,account,'sz000981','sell','fixture-'+ident,now_cn().date().isoformat(),'accepted',json.dumps(payload),stamp,stamp))
        request=dict(account_id=account,code='000981',side='sell',quantity=100,price='2.13',dry_run=False)
        result=dict(status='accepted',order_id='fixture-'+account) if account=='test-a' else dict(status='accepted')
        payload['result']=result
        app.store.execute('UPDATE trading_runs SET payload=? WHERE id=?',(json.dumps(payload),ident))
        app.store.execute('INSERT OR REPLACE INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+ident,account,json.dumps(request),'accepted',json.dumps(result),stamp,stamp))
    return dict(seeded=True)

def seed_price_checks():
    stamp=now_cn().isoformat();ident='price-check-fixture'
    check=dict(policy='adverse-v1',allowed=False,reference_price='29.04',quote_price='28.89',signed_deviation_pct=-.516529,adverse_deviation_pct=.516529,maximum_pct=.5,boundary_price='28.90',quote_at=stamp,checked_at=stamp)
    payload=dict(mode='live',signal_source='shape-v1',signal=dict(time=stamp[11:16],kind='top'),reference_price=29.04,
                 message='卖出价低于信号价的允许范围：参考29.04元，校验28.89元，不利偏离0.517%（上限0.5%）',
                 price_checks={'before_holdings':dict(check,allowed=True,quote_price='29.08',adverse_deviation_pct=0), 'after_holdings':check},
                 timings=dict(queue_ms=300,holdings_ms=24324,gateway_ms=0,elapsed_ms=27897,holdings_scope='target'))
    app.store.execute('INSERT OR REPLACE INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,'test-a','sz000981','sell','fixture-top-price',stamp[:10],'skipped',json.dumps(payload),stamp,stamp))
    return dict(seeded=True)

for ident in ('test-a','test-b'):app.live_trading.apply_snapshot(ident,holdings(app.store,ident))
for line in sys.stdin:
    try:
        request=json.loads(line)
        if request['method']=='test_hold_sync':sync_gate.clear();result=True
        elif request['method']=='test_release_sync':sync_gate.set();result=True
        elif request['method']=='test_broker_checks':result=broker_checks
        elif request['method']=='test_seed_price_checks':result=seed_price_checks()
        elif request['method']=='test_seed_notice':
            app.store.setconfig('trading_signal_notice','测试：原买卖开关已保留，自动执行已暂停。')
            result=True
        else:result=seed_reports() if request['method']=='test_seed_reports' else app.call(request['method'],request.get('args',{}))
        print(json.dumps(dict(result=result),ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps(dict(error=str(exc)),ensure_ascii=False),flush=True)
app.stop.set()
app.store.db.close()
tmp.cleanup()
