"""Test-only IPC peer: real App, signal engine, gateway, native page parsers and
reconciler; ONLY the external broker/Android device is simulated. Never imports
user accounts or credentials, and forbids every real ADB command.
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.app import App
from core.provider import CN
from executor.adb import Adb, Node, parse_nodes
from executor.brokers.base import BrokerAdapter
from executor.brokers.zhangle import SPEC as ZHANGLE
from executor.brokers.ths import SPEC as THS
from executor.identity import account_matches
from executor.trade import TradePage, CODE_ID, SUBMIT_ID, DIALOG_OK_ID, DIALOG_CANCEL_ID
from executor.ths_order import ThsOrderPage
from executor.zhangle import Zhangle
from tests.test_zhangle_preparation import InputDevice, poll
from tests.test_executor_trade import DialogTests, TRADE_FOCUS
from tests.test_executor_ths_order import form as ths_form, confirmation as ths_confirm, settings as ths_settings, n as ths_node

def forbidden(*_a,**_k):raise AssertionError('E2E simulator attempted real device IO')

class NativeBroker:
    def __init__(self,broker,number,clock,quantity):
        self.broker,self.number,self.clock,self.quantity=broker,number,clock,quantity
        self.orders=[];self.wrong_account=False;self.lose_receipt=False;self.gate=threading.Event();self.gate.set()
        self.device=ZhangleDevice(self) if broker=='zhangle' else ThsDevice(self)

    def accept(self,side,code,quantity,price):
        self.orders.append(dict(order_id=str((800000 if self.broker=='zhangle' else 900000)+len(self.orders)+1),
            side=side,code=code,quantity=int(quantity),price=str(price),filled=0,date=self.clock[0].date().isoformat(),time=self.clock[0].strftime('%H:%M:%S')))

    def positions(self):
        bought=sum(o['filled'] for o in self.orders if o['side']=='buy')
        sold=sum(o['filled'] for o in self.orders if o['side']=='sell')
        return [dict(name='山子高科',code='sz000981',quantity=self.quantity+bought-sold,sellable=self.quantity-sold,price=2.24,cost=2.10)]

class ZhangleDevice(InputDevice):
    def __init__(self,owner):
        super().__init__(drops=1);self.owner=owner;self.phase='form'
    def current_focus(self):return TRADE_FOCUS
    def nodes(self,**_kwargs):
        if self.phase=='confirm':
            xml=DialogTests.CONFIRM_XML.replace('委托卖出','委托买入' if self.side=='buy' else '委托卖出').replace('2.13',self.price).replace('100&#10;',self.quantity+'&#10;')
            return parse_nodes(xml)
        if self.phase=='receipt':
            if self.owner.lose_receipt:return []
            return parse_nodes(DialogTests.RESULT_ERROR_XML.replace('当前时间不允许委托','委托提交成功,合同号:'+self.owner.orders[-1]['order_id']))
        return super().nodes()
    def tap_node(self,node):
        suffix=node.resource_id.rsplit('/',1)[-1]
        if suffix==SUBMIT_ID:self.taps.append(suffix);self.phase='confirm'
        elif suffix==DIALOG_OK_ID:
            self.taps.append(suffix);self.owner.accept(self.side,self.code,self.quantity,self.price);self.phase='receipt'
        elif suffix==DIALOG_CANCEL_ID:self.phase='form'
        else:super().tap_node(node)

class ThsDevice:
    def __init__(self,owner):
        self.owner=owner;self.side='buy';self.code='';self.price='';self.quantity='';self.phase='form';self.focus='';self.search='';self.taps=[]
    def current_focus(self):return 'com.hexin.plat.android/trade.Form'
    def nodes(self,**_kwargs):
        if self.phase=='confirm':return ths_confirm(self.side,self.code,self.quantity,self.price)
        if self.phase=='receipt':
            if self.owner.lose_receipt:return [ths_node('系统信息','dialog_title')]
            return [ths_node('委托成功','dialog_title'),ths_node('合同号:'+self.owner.orders[-1]['order_id'],'dialog_message')]
        if self.phase=='settings':return ths_settings()+[ths_node('','iv_close')]
        nodes=ths_form(self.side)
        nodes[2]=replace(nodes[2],text=self.code);nodes[4]=replace(nodes[4],text=self.price);nodes[5]=replace(nodes[5],text=self.quantity)
        nodes += [ths_node('买 入' if self.side=='buy' else '卖 出',y=600),ths_node('','quick_setting_image'),
            ths_node('中国银河证券','page_title_view'),ths_node(self.owner.number,'account_info_view')]
        if self.phase=='search':nodes += [ths_node('','stock_search'),ths_node(self.search,'stockcode_tv',y=300)]
        return nodes
    def tap_node(self,node):
        suffix=node.resource_id.rsplit('/',1)[-1];self.taps.append(suffix)
        if suffix=='auto_stockcode':self.phase='search';self.focus='code'
        elif suffix=='stockcode_tv':self.code=self.search;self.price='2.24';self.phase='form'
        elif suffix=='btn':self.side='buy' if node.text=='买入' else 'sell'
        elif suffix=='quick_setting_image':self.phase='settings'
        elif suffix=='iv_close':self.phase='form'
        elif suffix=='btn_transaction':self.phase='confirm'
        elif suffix=='ok_btn':self.owner.accept(self.side,self.code,self.quantity,self.price);self.phase='receipt'
        elif suffix=='cancel_btn':self.phase='form'
        elif 'EditText' in node.class_name:self.focus='price' if node.bounds[1]==350 else 'quantity'
        else:raise AssertionError('Unsupported simulated tap: '+suffix)
    def clear_text(self,_length):
        if self.focus=='code':self.search=''
        else:setattr(self,self.focus,'')
    def input_text(self,text):
        if self.focus=='code':self.search=text
        else:setattr(self,self.focus,text)

class Adapter(BrokerAdapter):
    def __init__(self,owner):
        self.owner=owner;self.adb=owner.device;self.spec=ZHANGLE if owner.broker=='zhangle' else THS
    def ensure_ready(self,credentials):
        shown='9999999999' if self.owner.wrong_account else self.owner.number
        if self.owner.broker=='zhangle':
            header=Node(shown,'com.lphtsccft:id/title_bar_right','android.widget.TextView',(0,0,100,40),False,True,False,False)
            Zhangle.verify_trade_account([header],credentials.account)
        elif not account_matches(shown,credentials.account):raise ValueError('资金账户不一致')
        return dict(account_verified=True,account_display=shown,logged_in=True)
    login=ensure_ready
    def holdings(self,**_kwargs):return dict(complete=True,positions=self.owner.positions(),funds=dict(available='100000'))
    def submit_order(self,side,code,quantity,price=None,**kwargs):
        if not self.owner.gate.wait(10):raise AssertionError('Simulated device wait expired')
        device=self.adb;device.phase='form';device.code='';device.price='';device.quantity='';device.side=side
        page=TradePage(device) if self.owner.broker=='zhangle' else ThsOrderPage(device,expected_account=self.owner.number)
        return page.submit(side,code,quantity,price,**kwargs)
    def order_report(self,order_id,day,expected):
        orders=[o for o in self.owner.orders if o['order_id']==order_id]
        if not orders:return dict(found=False)
        row=dict(orders[0]);filled=row['filled']
        report=dict(row,found=True,filled=filled,status='filled' if filled==row['quantity'] else 'partial' if filled else 'accepted',
            date_source='broker_row',average=row['price'] if filled else None,amount=str(Decimal(row['price'])*filled),
            source='E2E_SIMULATED_BROKER',evidence_hash=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest())
        if self.owner.broker=='ths' and filled:
            report.update(kind='contract_fills',source='ths_native_contract_group')
        return report
    def discover_order_report(self,day,expected,submitted_at):
        from executor.ths_report import discover
        records=[dict(order_id=o['order_id'],code=o['code'],side=o['side'],name='山子高科',date=o['date'],time=o['time'],
                      filled=o['filled'],average=o['price'],amount=str(Decimal(o['price'])*o['filled']))
                 for o in self.owner.orders if o['filled']]
        with patch('executor.ths_report.contract_pages',return_value=iter([records])):
            return discover(self.adb,self.owner.number,day,expected,submitted_at,self.owner.clock[0])

class Harness:
    def __init__(self):
        from core import brokers
        self.tmp=tempfile.TemporaryDirectory(prefix='guanliang-order-e2e-');os.environ['STOCK_MONITOR_DATA']=self.tmp.name
        self.clock=[datetime(2026,11,4,9,55,0,tzinfo=CN)];self.patches=[]
        for name in ('core.app','core.live_trading','core.brokers','core.broker_reconciliation','core.store'):
            self.patches.append(patch(name+'.now_cn',side_effect=lambda:self.clock[0]))
        self.patches += [patch('executor.adb.Adb.run',side_effect=forbidden),patch('core.brokers.device_operation',side_effect=lambda *_a,**_k:nullcontext()),
            patch('executor.trade.wait_until',side_effect=poll),patch('executor.ths_order.wait_until',side_effect=poll)]
        for p in self.patches:p.start()
        self.app=App(self.tmp.name,start_worker=False)
        class PublicData:
            def quote(_self,code):return self.app.quotes.get(code,dict(code=code,name='山子高科',date='2026-11-04',price='2.24',timestamp=self.clock[0].isoformat(),limit_up='2.46'))
            def minutes(_self,code):return [r['data'] for r in self.app.store.getcache(code,'minute')]
            def daily(_self,code,start,end):return [r['data'] for r in self.app.store.getcache(code,'daily') if start<=r['day']<=end]
        self.app.provider=PublicData()
        self.owners={'zhangle':NativeBroker('zhangle','1234561001',self.clock,1200),'ths':NativeBroker('ths','9876542002',self.clock,600)}
        self.adapters={k:Adapter(v) for k,v in self.owners.items()}
        p=patch('executor.brokers.adapter',side_effect=lambda broker:self.adapters[broker]);p.start();self.patches.append(p)
        for ident,broker,account,lots in [('e2e-a','zhangle','1234561001',1),('e2e-b','ths','9876542002',2)]:
            self.app.store.execute('INSERT INTO broker_accounts(id,broker,account,label) VALUES(?,?,?,?)',(ident,broker,account,'隔离E2E'))
            brokers.SecretStore().set(broker,account,'password','TEST_ONLY')
            self.app.live_trading.sync(ident)
            rule=self.app.live_trading.rule(ident,'sz000981')
            self.app.live_trading.save_rule(ident,'sz000981',dict(buy_enabled=True,sell_enabled=True,buy_lots=lots,sell_lots=lots),rule['revision'])
        self.app.store.setconfig('monitor',True);self.app.live_trading.configure(dict(mode='live',confirm_live=True))
        self.bars=json.loads((Path(__file__).parent/'ui/fixtures/turning-shapes.json').read_text())[2]['bars']
    def tick(self,stamp):
        self.clock[0]=datetime.fromisoformat('2026-11-04T'+stamp+'+08:00');rows=[b for b in self.bars if b['time']<=stamp[:5]]
        quote=dict(code='sz000981',name='山子高科',date='2026-11-04',timestamp=self.clock[0].isoformat(),price=str(rows[-1]['close']),previous_close='2.24',limit_up='2.46',limit_down='2.02')
        self.app.ingest('sz000981',quote,[dict(date='2026-11-04',source='E2E_RECORDED_PUBLIC_FIXTURE',bars=rows)],self.clock[0])
        self.app.live_trading.drain(reports=False)
    def feed(self,kind):
        for stamp in (['09:59:20','09:59:50','10:00:05'] if kind=='bottom' else ['13:04:20','13:04:50','13:05:05']):self.tick(stamp)
        return self.state()
    def reconcile(self,fraction):
        self.clock[0]+=timedelta(seconds=5)
        for owner in self.owners.values():
            for row in owner.orders:row['filled']=max(row['filled'],int(row['quantity']*Decimal(str(fraction))))
        for row in self.app.store.query("SELECT * FROM broker_requests WHERE status IN ('accepted','partial','unknown')"):
            self.app.live_trading.reconciler.reconcile(row['account_id'],row['request_id'])
        return self.state()
    def state(self):
        view=self.app.live_trading.view()
        return dict(runs=view['runs'],orders={k:v.orders for k,v in self.owners.items()},
            chart=self.app.call('trading_chart',dict(code='sz000981',day='2026-11-04')),isolated=True,real_device_io=False)
    def call(self,method,args):
        if method=='e2e_feed':return self.feed(args['kind'])
        if method=='e2e_feed_async':return self.app.start_job(lambda:self.feed(args['kind']))
        if method=='e2e_hold_native':
            for owner in self.owners.values():owner.gate.clear()
            return True
        if method=='e2e_release_native':
            for owner in self.owners.values():owner.gate.set()
            return True
        if method=='e2e_reconcile':return self.reconcile(args['fraction'])
        if method=='e2e_state':return self.state()
        if method=='e2e_fault':
            owner=self.owners[args['broker']];setattr(owner,args['kind'],True);return True
        if method=='e2e_repeat':self.tick(self.clock[0].strftime('%H:%M:%S'));return self.state()
        return self.app.call(method,args)
    def close(self):
        self.app.stop.set();self.app.store.db.close()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

if __name__=='__main__':
    harness=Harness()
    try:
        for line in sys.stdin:
            try:
                r=json.loads(line);reply=dict(result=harness.call(r['method'],r.get('args',{})))
            except Exception as exc:reply=dict(error=str(exc))
            print(json.dumps(reply,ensure_ascii=False),flush=True)
    finally:harness.close()
