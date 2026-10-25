"""Acceptance of the actual native JSON-lines peer using an isolated temporary ledger."""
import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.store import Store
from core.provider import now_cn
from core.paper_session import trading_error

class Peer:
    def __init__(self,binary,directory):
        self.proc=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env={**os.environ,'STOCK_MONITOR_DATA':str(directory)})
        self.lines=queue.Queue()
        threading.Thread(target=lambda:[self.lines.put(line) for line in self.proc.stdout],daemon=True).start()
    def call(self,method,**args):
        self.proc.stdin.write(json.dumps(dict(method=method,args=args),ensure_ascii=False)+'\n');self.proc.stdin.flush()
        reply=json.loads(self.lines.get(timeout=20))
        if not reply['ok']:raise ValueError(reply['error'])
        return reply['data']
    def close(self):
        self.proc.stdin.close()
        try:self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        self.proc.stdout.close();self.proc.stderr.close()

def main(binary):
    with tempfile.TemporaryDirectory(prefix='stock-native-acceptance-') as tmp:
        path=Path(tmp);st=Store(path/'monitor.sqlite3')
        for key,value in dict(initialized=True,monitor=False,phone_enabled=False,sound=False).items():st.setconfig(key,value)
        st.remember('sh600000','中文测试股票')
        for day in ['2026-10-19','2026-10-20']:
            st.cache('sh600000','minute',day,dict(source='native-acceptance',volume_unit='shares',previous_close='10',bars=[dict(time=t,close=p,volume=10000,complete=True) for t,p in [('09:31','10'),('09:32','11'),('09:33','9.5'),('09:34','9.5')]]))
        st.db.close();peer=Peer(binary,path)
        if trading_error(now_cn()):
            try:
                a=peer.call('paper_create',name='休市管道验收',cash='12345.67');aid=a['id']
                q=peer.call('paper_quote',code='sh600000',stamp='2026-10-19 09:31')
                before=peer.call('paper_snapshot',account=aid)
                requests=[('paper_order',dict(account=aid,id='closed-order-001',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price=10)),('paper_advance',dict(account=aid,code=q['code'],stamp='2026-10-19 09:32'))]
                for method,args in requests:
                    try:peer.call(method,**args)
                    except ValueError as error:assert '禁止模拟委托和成交' in str(error)
                    else:raise AssertionError('Closed-session request was accepted')
                    assert peer.call('paper_snapshot',account=aid)==before
            finally:peer.close()
            peer=Peer(binary,path)
            try:assert peer.call('paper_snapshot',account=aid)==before
            finally:peer.close()
            print(json.dumps(dict(result='PASS',mode='actual closed wall-clock',checks=['UTF-8 IPC','historical order blocked','advance blocked','ledger unchanged','restart persistence'],temporary_data=True),ensure_ascii=False))
            return
        try:
            a=peer.call('paper_create',name='原生管道验收',cash='12345.67');aid=a['id']
            peer.call('paper_seed',account=aid,code='sh600000',shares=1000,cost='9')
            q=peer.call('paper_quote',code='sh600000',stamp='2026-10-19 09:31')
            args=dict(account=aid,id='native-sell-001',code=q['code'],stamp=q['stamp'],token=q['token'],side='sell',shares=200,limit_price=10)
            first=peer.call('paper_order',**args);assert first['status']=='open'
            assert peer.call('paper_order',**args)==first
            s=peer.call('paper_advance',account=aid,code=q['code'],stamp='2026-10-19 09:32')
            assert s['fill_count']==1 and s['orders'][0]['status']=='partial'
            assert s['day_pnl']['profit']==99444 and s['positions'][0]['shares']==900
            peer.call('paper_cancel',account=aid,id=first['id'])
            q=peer.call('paper_quote',code=q['code'],stamp='2026-10-19 09:33')
            peer.call('paper_order',account=aid,id='native-buy-0001',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price=10)
            s=peer.call('paper_advance',account=aid,code=q['code'],stamp='2026-10-19 09:34')
            assert s['fill_count']==2 and s['positions'][0]['available']==900
            assert s['profit']==s['account']['realized']+s['unrealized']
            assert len(peer.call('paper_export',account=aid,kind='fills'))==2
            chart=peer.call('paper_chart',account=aid,code=q['code'],start='2026-10-19',end='2026-10-19',daily=True,day='2026-10-19')
            assert {p['side'] for p in chart['points']}=={'buy','sell'} and len(chart['minute_points'])==2
            for method,args in [('paper_unknown',dict(account=aid)),('paper_quote',dict(code=q['code'],stamp='2026-10-19 09:99'))]:
                try:peer.call(method,**args)
                except ValueError:pass
                else:raise AssertionError('Invalid request accepted')
            before=peer.call('paper_snapshot',account=aid)
            assert before['fills']==s['fills'] and before['available_cash']>=0
        finally:peer.close()
        peer=Peer(binary,path)
        try:
            assert peer.call('paper_snapshot',account=aid)==before
            b=peer.call('paper_create',name='独立账户',cash=100)
            assert peer.call('paper_snapshot',account=b['id'])['positions']==[]
            assert peer.call('paper_snapshot',account=aid)=={**before,'accounts':peer.call('paper_snapshot',account=aid)['accounts']}
        finally:peer.close()
        print(json.dumps(dict(result='PASS',transport='native UTF-8 JSON-lines',checks=['manual cash','seed holdings','idempotence','partial fills','cancel remainder','buyback','T+1','day profit','cash and profit reconciliation','fill export','chart buy/sell','invalid request recovery','process restart persistence','account isolation'],temporary_data=True),ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('binary',type=Path);main(parser.parse_args().binary.resolve())
