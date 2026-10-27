"""Exercise packaged live matching using a temporary ledger; never opens user databases."""
import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.verify_paper_ipc import Peer
from core.store import Store
from core.provider import now_cn
from core.paper_session import trading_error
from core.paper import Paper


def main(binary):
    now=now_cn();day=now.date().isoformat()
    with tempfile.TemporaryDirectory(prefix='stock-auto-sync-native-') as tmp:
        path=Path(tmp);store=Store(path/'monitor.sqlite3')
        for key,value in dict(initialized=True,monitor=False,phone_enabled=False,sound=False).items():store.setconfig(key,value)
        store.remember('sz000981','山子高科')
        bars=[dict(time='09:31',close='2.36',volume=100000,complete=True)]
        def cache():store.cache('sz000981','minute',day,dict(source='isolated-native-test',volume_unit='shares',bars=bars))
        cache();fixture=None
        if not trading_error(now) and now.strftime('%H:%M')>='09:36':
            # Seed an earlier acceptance in this TEMPORARY ledger. The positive
            # worker test must not pretend today's newly submitted order existed
            # at 09:31, or wait several real minutes just to generate a closed bar.
            paper=Paper(path/'paper.sqlite3',store)
            with patch('core.paper.now_cn',return_value=datetime.fromisoformat(day+'T09:32:01+08:00')):
                fixture=paper.call('paper_create',dict(cash=100000,name='早间确认时间夹具'))['id']
                q=paper.call('paper_quote',dict(code='sz000981',stamp=day+' 09:31'))
                paper.call('paper_order',dict(account=fixture,id='fixture-auto-buy',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=2000,limit_price='2.35'))
            paper.db.close()
        peer=Peer(binary,path)
        try:
            a=peer.call('paper_create',cash=100000,name='自动撮合隔离验收')['id']
            q=peer.call('paper_quote',code='sz000981',stamp=day+' 09:31')
            args=dict(account=a,id='native-auto-buy',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=2000,limit_price='2.35')
            closed=trading_error(now_cn())
            if closed:
                before=peer.call('paper_snapshot',account=a)
                try:peer.call('paper_order',**args)
                except ValueError as e:assert '禁止模拟委托和成交' in str(e)
                else:raise AssertionError('Closed session accepted an order')
                result=peer.call('paper_sync',account=a);assert result['sync']['status']=='closed'
                assert peer.call('paper_snapshot',account=a)==before
                print(json.dumps(dict(result='PASS',mode='closed wall-clock',temporary_data=True,checks=['sync endpoint packaged','closed order rejected','no ledger mutation']),ensure_ascii=False));return
            if fixture is None:raise ValueError('Not enough closed current-day minutes to run this native scenario')
            assert peer.call('paper_order',**args)['status']=='open'
            assert peer.call('paper_snapshot',account=a)['fill_count']==0
            bars.extend([dict(time='09:34',close='2.34',volume=10000,complete=True),dict(time='09:35',close='2.34',volume=300000,complete=True)])
            cache()
            deadline=time.monotonic()+12
            while True:
                snapshot=peer.call('paper_snapshot',account=fixture)
                if snapshot['orders'][0]['status']=='filled':break
                if time.monotonic()>deadline:raise AssertionError('Background matching did not execute the order')
                time.sleep(.2)
            assert snapshot['positions'][0]['shares']==2000 and snapshot['frozen_cash']==0
            assert {(f['price'],f['shares']) for f in snapshot['fills']}=={(234,100),(234,1900)}
            assert peer.call('paper_snapshot',account=a)['fill_count']==0 # Newly accepted order cannot use those old minutes.
            chart=peer.call('paper_chart',account=fixture,code='sz000981',start=day,end=day)
            assert len(chart['points'])==2 and {p['side'] for p in chart['points']}=={'buy'}
            assert len(chart['order_points'])==1 and chart['order_points'][0]['shares']==2000
            assert chart['order_points'][0]['stamp']==day+' 09:34' and chart['order_points'][0]['last_stamp']==day+' 09:35'
            # Only snapshots were polled: the executable's worker, not paper_sync/advance, filled it.
            before=peer.call('paper_snapshot',account=fixture);peer.call('paper_sync',account=fixture)
            assert peer.call('paper_snapshot',account=fixture)==before
            print(json.dumps(dict(result='PASS',mode='actual open wall-clock; synthetic earlier acceptance fixture',fixture_acceptance=day+'T09:32:01+08:00',time=now_cn().isoformat(),temporary_data=True,checks=['newly accepted order cannot use earlier minutes','native background matching of earlier-acceptance fixture','2.35 limit buys at later 2.34','partial then full fill','reserve released','one B for one order','idempotence'],fills=[dict(time=f['stamp'],price=f['price'],shares=f['shares']) for f in snapshot['fills']]),ensure_ascii=False))
        finally:peer.close();store.db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('binary',type=Path);main(p.parse_args().binary.resolve())
