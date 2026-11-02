"""Signal to durable gateway to contract-fill reconciliation; no device IO."""
import json,tempfile,unittest
from contextlib import nullcontext
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.store import Store
from core.live_trading import LiveTrading
from core.provider import CN
from executor.brokers.base import BrokerCredentials

class AutomaticFlowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
  self.now=datetime(2026,11,2,10,1,5,tzinfo=CN)
  for module in ('core.live_trading','core.brokers','core.broker_reconciliation'):
   clock=patch(module+'.now_cn',side_effect=lambda:self.now);clock.start();self.addCleanup(clock.stop)
  guard=patch('core.brokers.device_operation',side_effect=lambda *_a,**_k:nullcontext());guard.start();self.addCleanup(guard.stop)
  self.clients={};self.accounts={}
  for ident,account in [('a','123450001'),('b','987650002')]:
   self.store.execute('INSERT INTO broker_accounts(id,broker,account) VALUES(?,?,?)',(ident,'ths',account));self.accounts[ident]=account
   client=Mock();client.spec.supports_order=True;client.ensure_ready.return_value=dict(account_verified=True,account_display=account)
   client.holdings.return_value=dict(complete=True,funds=dict(available='10000'),positions=[dict(code='sz000981',name='山子高科',quantity=1200,sellable=1000,price='2.13')])
   def submit(*,side,code,quantity,price,before_confirm,ident=ident,**_):
    before_confirm();before_confirm()
    return dict(status='accepted',submitted=True,order_id='contract-'+ident,confirm=dict(side=side,code=code,quantity=quantity,price=price))
   client.submit_order.side_effect=submit
   client.order_report.side_effect=lambda oid,day,expected,ident=ident:dict(found=True,kind='contract_fills',source='ths_native_contract_group',date_source='broker_today_query',date=day,time='10:01:07',
       order_id=oid,code=expected['code'],side=expected['side'],filled=expected['quantity'],average=expected['price'],amount=str(float(expected['price'])*expected['quantity']),evidence_hash='b'*64)
   self.clients[ident]=client
  adapter=patch('core.brokers._adapter',side_effect=lambda _store,ident,_secrets=None:({},BrokerCredentials('ths',self.accounts[ident]),self.clients[ident]));adapter.start();self.addCleanup(adapter.stop)
  self.app=SimpleNamespace(store=self.store,quotes={'sz000981':dict(price='2.13',timestamp=self.now.isoformat())})
  self.service=LiveTrading(self.app);self.store.setconfig('monitor',True)
  for ident in ('a','b'):self.service.sync(ident)
  r=self.service.rule('a','sz000981');self.service.save_rule('a','sz000981',dict(buy_enabled=True,sell_enabled=True,buy_mode='position',buy_percent=50,sell_mode='position',sell_percent=50,daily_orders=10),r['revision'])
  self.store.execute("UPDATE trading_rules SET armed_at=? WHERE account_id='a'",((self.now-timedelta(minutes=2)).isoformat(),))
  self.service.configure(dict(mode='live',confirm_live=True));self.service.configure(dict(paused=False));self.service.started_at=(self.now-timedelta(minutes=2)).isoformat()

 def signal(self,key='one',kind='bottom'):
  signal=dict(key=key,kind=kind,time=self.now.strftime('%H:%M'),price=2.13,liquidity=dict(meanShares=100000,currentShares=100000))
  self.service.observe('sz000981',[signal],self.app.quotes['sz000981'],self.now,True);self.service.drain()

 def test_synced_stock_automatically_orders_and_reconciles_only_armed_account(self):
  self.signal();self.clients['a'].submit_order.assert_called_once();self.clients['b'].submit_order.assert_not_called()
  request=self.store.query('SELECT * FROM broker_requests')[0];run=self.store.query('SELECT * FROM trading_runs')[0]
  self.assertEqual(request['account_id'],'a');self.assertEqual(run['status'],'accepted')
  self.assertEqual(json.loads(request['payload'])['quantity'],600)
  self.assertIsNone(json.loads(request['payload'])['max_value'])
  self.assertIsNone(self.clients['a'].submit_order.call_args.kwargs['max_value'])
  self.now+=timedelta(seconds=65);self.service.drain()
  self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'filled')
  payload=json.loads(self.store.query('SELECT payload FROM trading_runs')[0]['payload'])
  self.assertEqual(payload['verification']['origin'],'broker_auto');self.assertEqual(payload['verification']['filled'],600)
  self.assertTrue(self.service.rule('a','sz000981')['buy_enabled']);self.assertFalse(self.service.rule('b','sz000981')['buy_enabled'])

 def test_duplicate_signal_never_submits_twice_without_human_steps(self):
  self.signal();self.signal()
  self.clients['a'].submit_order.assert_called_once();self.assertEqual(len(self.store.query('SELECT * FROM broker_requests')),1)

 def test_rule_off_or_account_pause_blocks_before_gateway(self):
  self.service.pause_account('a',True);self.signal()
  self.clients['a'].submit_order.assert_not_called();self.assertFalse(self.store.query('SELECT * FROM broker_requests'))

 def test_both_journals_and_plan_are_durable_before_native_confirmation(self):
  def lost(*,before_confirm,**kwargs):
   before_confirm()
   run=self.store.query('SELECT * FROM trading_runs')[0]
   self.assertEqual(run['status'],'sending');self.assertEqual(json.loads(run['payload'])['plan']['account_id'],'a')
   self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'sending')
   raise RuntimeError('模拟点击后断连')
  self.clients['a'].submit_order.side_effect=lost
  self.signal();self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'unknown')
  self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'unknown')
  self.signal('another');self.assertEqual(self.clients['a'].submit_order.call_count,1)
