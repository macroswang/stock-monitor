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
  r=self.service.rule('a','sz000981');self.service.save_rule('a','sz000981',dict(buy_enabled=True,sell_enabled=True,buy_mode='position',buy_percent=50,sell_mode='position',sell_percent=50),r['revision'])
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

 def test_sanfu_1316_two_lots_reach_bound_gateway_despite_small_minute_volume(self):
  # Recorded 2026-11-05 incident, with synthetic accounts and a fake broker.
  # The old hidden 1% cap rejected 200 shares against 16,700 minute shares.
  self.now=datetime(2026,11,5,13,16,11,tzinfo=CN)
  code='sh603938'
  self.app.quotes[code]=dict(code=code,price='30.55',timestamp=self.now.isoformat())
  self.clients['a'].holdings.return_value=dict(complete=True,funds=dict(available='16639.06'),positions=[dict(code=code,name='三孚股份',quantity=200,sellable=200,price='30.57')])
  self.service.sync('a')
  r=self.service.rule('a',code)
  self.service.save_rule('a',code,dict(buy_enabled=True,buy_lots=2),r['revision'])
  armed=(self.now-timedelta(minutes=5)).isoformat()
  self.store.execute('UPDATE trading_rules SET armed_at=? WHERE account_id=? AND code=?',(armed,'a',code))
  self.service.started_at=armed
  event=dict(kind='bottom',time='13:16',key='confirmed-shape-v1|bottom|13:11|13:16',price=30.5,liquidity=dict(meanShares=32400,currentShares=16700))
  self.service.observe(code,[event],self.app.quotes[code],self.now,True)
  def refreshed(*args,**kwargs):
   self.now+=timedelta(seconds=19)
   self.app.quotes[code].update(price='30.56',timestamp=self.now.isoformat())
   return self.service.sync('a')
  with patch.object(self.service,'execution_sync',side_effect=refreshed):
   self.service.drain(reports=False)
  run=self.store.query('SELECT * FROM trading_runs')[0]
  self.assertEqual(run['status'],'accepted',json.loads(run['payload']).get('message'))
  request=self.store.query('SELECT * FROM broker_requests')[0]
  self.assertEqual((run['account_id'],run['code'],run['status']),('a',code,'accepted'))
  self.assertEqual((request['account_id'],request['status']),('a','accepted'))
  plan=json.loads(run['payload'])['plan']
  self.assertEqual((plan['quantity'],plan['price']),(200,'30.56'))
  self.assertTrue(json.loads(run['payload'])['price_checks']['before_submit']['allowed'])
  self.clients['a'].submit_order.assert_called_once()
  self.clients['b'].submit_order.assert_not_called()
  self.service.observe(code,[event],self.app.quotes[code],self.now,True)
  self.service.drain(reports=False)
  self.clients['a'].submit_order.assert_called_once()

 def test_rule_off_or_account_pause_blocks_before_gateway(self):
  self.service.pause_account('a',True);self.signal()
  self.clients['a'].submit_order.assert_not_called();self.assertFalse(self.store.query('SELECT * FROM broker_requests'))

 def test_both_journals_and_plan_are_durable_before_native_confirmation(self):
  def lost(*,before_confirm,**kwargs):
   before_confirm()
   run=self.store.query('SELECT * FROM trading_runs ORDER BY rowid DESC')[0]
   self.assertEqual(run['status'],'sending');self.assertEqual(json.loads(run['payload'])['plan']['account_id'],'a')
   self.assertEqual(self.store.query('SELECT status FROM broker_requests ORDER BY rowid DESC')[0]['status'],'sending')
   raise RuntimeError('模拟点击后断连')
  self.clients['a'].submit_order.side_effect=lost
  self.signal();self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'unknown')
  self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'unknown')
  self.signal('another');self.signal();self.assertEqual(self.clients['a'].submit_order.call_count,2)
  self.assertEqual([r['status'] for r in self.store.query('SELECT status FROM broker_requests')],['unknown','unknown'])

 def test_sell_price_change_before_confirm_keeps_configured_limit(self):
  clicked=[]
  def changed(*,before_confirm,**kwargs):
   self.app.quotes['sz000981']={**self.app.quotes['sz000981'],'price':'2.10'}
   before_confirm();clicked.append(True)
   return dict(status='accepted',submitted=True)
  self.clients['a'].submit_order.side_effect=changed
  self.signal(kind='top')
  self.assertEqual(clicked,[True])
  self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'accepted')
  run=self.store.query('SELECT * FROM trading_runs')[0];payload=json.loads(run['payload'])
  self.assertEqual(run['status'],'accepted');self.assertTrue(payload['price_checks']['before_submit']['allowed'])
  self.assertEqual(payload['price_checks']['before_submit']['quote_price'],'2.10')
  self.assertEqual(payload['price_checks']['before_submit']['order_price'],'2.13')

 def test_sell_price_improves_at_final_confirmation_and_account_stays_bound(self):
  confirmed=[]
  def improved(*,before_confirm,**kwargs):
   self.app.quotes['sz000981']={**self.app.quotes['sz000981'],'price':'2.20'}
   before_confirm();confirmed.append(True)
   return dict(status='accepted',submitted=True,order_id='contract-a')
  self.clients['a'].submit_order.side_effect=improved
  self.signal(kind='top')
  self.assertEqual(confirmed,[True]);self.clients['b'].submit_order.assert_not_called()
  request=self.store.query('SELECT * FROM broker_requests')[0]
  self.assertEqual(request['account_id'],'a');self.assertEqual(request['status'],'accepted')
  run=self.store.query('SELECT * FROM trading_runs')[0];payload=json.loads(run['payload'])
  self.assertTrue(payload['price_checks']['before_submit']['allowed'])
  self.assertEqual(payload['price_checks']['before_submit']['order_price'],'2.13')

 def test_actual_limit_does_not_have_an_additional_signal_price_boundary(self):
  self.app.quotes['sz000981']={**self.app.quotes['sz000981'],'price':'2.1194'}
  self.signal(kind='top')
  run=self.store.query('SELECT * FROM trading_runs')[0];payload=json.loads(run['payload'])
  self.assertTrue(payload['price_checks']['after_holdings']['allowed'])
  check=payload['price_checks']['before_submit'];self.assertTrue(check['allowed']);self.assertTrue(check['order_allowed'])
  self.assertEqual(check['order_price'],'2.11');self.assertEqual(run['status'],'accepted')
  self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'accepted')

 def test_final_expired_quote_never_crosses_sending_and_has_audit(self):
  clicked=[]
  def stale(*,before_confirm,**kwargs):
   self.now+=timedelta(seconds=31)
   before_confirm();clicked.append(True)
   return dict(status='accepted',submitted=True)
  self.clients['a'].submit_order.side_effect=stale
  self.signal(kind='top')
  self.assertEqual(clicked,[])
  self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'failed')
  run=self.store.query('SELECT * FROM trading_runs')[0];payload=json.loads(run['payload'])
  self.assertEqual(run['status'],'failed');self.assertIn('等待新报价',payload['message'])
  self.assertEqual(payload['price_checks']['before_submit']['quote_age_ms'],31000)
