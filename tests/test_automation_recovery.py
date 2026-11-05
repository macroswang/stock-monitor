"""Regression boundaries: no real devices, credentials, orders or production writes."""
import json
import threading
import unittest
from datetime import timedelta
from unittest.mock import Mock,patch
from tests import test_trading_quantity_modes as fixtures
from executor import runtime

class AutomationRecoveryTests(unittest.TestCase):
 setUp=fixtures.QuantityServiceTests.setUp
 arm=fixtures.QuantityServiceTests.arm
 observe=fixtures.QuantityServiceTests.observe
 def test_busy_gateway_never_creates_unknown_or_blocks_account(self):
  self.service.configure(dict(mode='live',confirm_live=True));self.arm()
  serial='recovery-fake-device';guard=threading.Lock();guard.acquire();runtime._locks[serial]=guard
  adb=Mock(serial=serial);adb.devices.return_value=[serial]
  try:
   with patch('core.brokers.Adb',return_value=adb),patch('core.live_trading.brokers.holdings',return_value=self.snapshot),patch('core.brokers._adapter') as native:
    self.observe('one');self.service.drain()
    self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'pending')
    self.assertEqual(self.store.query('SELECT * FROM broker_requests'),[]);native.assert_not_called()
  finally:guard.release();runtime._locks.pop(serial,None)
  with patch('core.live_trading.brokers.holdings',return_value=self.snapshot),patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
   self.service.drain()
   self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'accepted');self.assertEqual(submit.call_count,1)
 def test_busy_signal_waits_for_fresh_quote_instead_of_expiring(self):
  self.arm()
  with patch('core.live_trading.brokers.holdings',side_effect=runtime.DeviceBusy('device busy')):
   self.observe('one');self.service.drain()
   self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'pending')
  self.now+=timedelta(seconds=46)
  with patch('core.live_trading.brokers.submit_order') as submit:
   self.service.drain();submit.assert_not_called()
  self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'pending')
 def test_verified_sync_cache_is_account_scoped_and_short_lived(self):
  with patch('core.live_trading.brokers.holdings',side_effect=lambda _,ident:{**self.snapshot,'account_id':ident,'observed_at':self.now.isoformat()}) as read:
   self.service.sync('a');self.service.sync('a',reuse_seconds=15);self.service.sync('b',reuse_seconds=15)
   self.assertEqual(read.call_count,2)
   self.now+=timedelta(seconds=16);self.service.sync('a',reuse_seconds=15);self.assertEqual(read.call_count,3)
 def test_clearance_keeps_fixed_lot_reentry_and_zeroes_stale_quantities(self):
  self.arm();self.service.apply_snapshot('a',{**self.snapshot,'positions':[]})
  p=json.loads(self.store.query("SELECT payload FROM trading_positions WHERE account_id='a'")[0]['payload'])
  self.assertEqual((p['quantity'],p['sellable']),(0,0));self.assertTrue(self.service.rule('a','sh603938')['buy_enabled'])
  self.assertEqual(self.service.plan('a','sh603938','buy')['quantity'],100)
  with self.assertRaises(ValueError):self.service.plan('a','sh603938','sell')
  r=self.service.rule('a','sh603938');self.service.save_rule('a','sh603938',{'buy_mode':'position'},r['revision'])
  with self.assertRaisesRegex(ValueError,'不足'):self.service.plan('a','sh603938','buy')
 def test_background_report_budget_yields_before_next_native_action(self):
  with runtime.budget(30,cancelled=lambda:True),self.assertRaises(runtime.OperationInterrupted):runtime.bound_timeout(20)
  self.assertEqual(runtime.bound_timeout(20),20)
 def test_prepare_syncs_before_starting_and_pause_cancels_it(self):
  self.arm();self.service.configure(dict(paused=True))
  def cancel(*args,**kwargs):
   self.service.configure(dict(paused=True))
   return self.snapshot
  with patch('core.live_trading.brokers.holdings',side_effect=cancel),self.assertRaisesRegex(ValueError,'取消'):self.service.prepare()
  self.assertTrue(self.service.settings()['paused'])
  with patch('core.live_trading.brokers.holdings',return_value=self.snapshot):self.service.prepare()
  self.assertFalse(self.service.settings()['paused'])
 def test_partial_sync_with_verified_configured_target_can_start(self):
  self.arm();self.service.configure(dict(paused=True))
  with patch('core.live_trading.brokers.holdings',return_value={**self.snapshot,'complete':False}):self.service.prepare()
  self.assertFalse(self.service.settings()['paused'])
 def test_partial_sync_without_valid_configured_target_cannot_start(self):
  self.arm();self.service.configure(dict(paused=True))
  invalid={**self.snapshot,'complete':False,'positions':[{**self.snapshot['positions'][0],'quantity':'--'}]}
  with patch('core.live_trading.brokers.holdings',return_value=invalid),self.assertRaisesRegex(ValueError,'无法核验'):self.service.prepare()
  self.assertTrue(self.service.settings()['paused'])

 def test_execution_refresh_updates_only_selected_stock_and_preserves_full_sync_time(self):
  with patch('core.live_trading.brokers.holdings',return_value=self.snapshot):self.service.sync('a')
  full=self.store.query("SELECT * FROM trading_sync WHERE account_id='a'")[0]
  self.now+=timedelta(seconds=31)
  fresh={**self.snapshot,'observed_at':self.now.isoformat(),'complete':False,'position_only':True,'funds':dict(available='9000'),'positions':[{**self.snapshot['positions'][0],'quantity':200,'sellable':100}]}
  with patch('core.live_trading.brokers.holdings',return_value=fresh) as read:
   self.service.execution_sync('a','sh603938');self.assertEqual(read.call_args.kwargs['target_code'],'sh603938')
  state=self.store.query("SELECT * FROM trading_sync WHERE account_id='a'")[0]
  self.assertEqual(state['last_success'],full['last_success']);self.assertEqual(state['status'],'complete')
  self.assertEqual(json.loads(state['payload'])['funds']['available'],'9000')
  a=json.loads(self.store.query("SELECT payload FROM trading_positions WHERE account_id='a'")[0]['payload'])
  b=json.loads(self.store.query("SELECT payload FROM trading_positions WHERE account_id='b'")[0]['payload'])
  self.assertEqual(a['quantity'],200);self.assertEqual(b['quantity'],300)
 def test_existing_outcomes_never_block_an_independent_signal_and_sync_is_fresh(self):
  self.service.configure(dict(mode='live',confirm_live=True));self.arm()
  with patch('core.live_trading.brokers.holdings',return_value=self.snapshot) as holdings,patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
   self.observe('one');self.service.drain(reports=False)
   original=self.store.query('SELECT * FROM trading_runs')[0]
   for status in ['accepted','unknown','partial']:
    self.store.execute('UPDATE trading_runs SET status=? WHERE id=?',(status,original['id']))
    self.observe('independent-'+status);self.service.drain(reports=False)
    self.assertEqual(self.store.query('SELECT status FROM trading_runs ORDER BY rowid DESC LIMIT 1')[0]['status'],'accepted')
   self.observe('independent-unknown');self.service.drain(reports=False)
   self.assertEqual(submit.call_count,4);self.assertEqual(holdings.call_count,4)
   self.assertTrue(all(call.args[1]=='a' for call in submit.call_args_list))
 def test_fresh_quote_after_long_native_preparation_is_allowed_within_original_deadline(self):
  self.arm();self.observe('one');self.now+=timedelta(seconds=50)
  self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
  with patch('core.live_trading.brokers.holdings',return_value={**self.snapshot,'observed_at':self.now.isoformat()}):self.service.drain()
  self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'trial')
 def test_waiting_past_old_deadline_uses_fresh_account_and_quote(self):
  self.arm();self.observe('one');self.now+=timedelta(seconds=91)
  self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
  with patch('core.live_trading.brokers.holdings',return_value={**self.snapshot,'observed_at':self.now.isoformat()}) as holdings,patch('core.live_trading.brokers.submit_order') as submit:
   self.service.drain();holdings.assert_called_once();submit.assert_not_called()
  self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'trial')

 def test_live_start_requires_order_support_but_not_a_report_reader(self):
  self.arm();self.service.configure(dict(mode='live',confirm_live=True))
  with patch('core.live_trading.brokers.list_accounts',return_value=[dict(id='a',supports_order=True,supports_order_report=False)]),patch.object(self.service,'view',return_value={}):
   self.service.configure(dict(paused=False))
  self.assertFalse(self.service.settings()['paused'])
  self.service.configure(dict(paused=True))
  with patch('core.live_trading.brokers.list_accounts',return_value=[dict(id='a',supports_order=False,supports_order_report=False)]),self.assertRaisesRegex(ValueError,'本机下单'):
   self.service.configure(dict(paused=False))
 def test_restart_closes_proven_unsubmitted_preparation_without_replaying_it(self):
  from core.live_trading import LiveTrading
  self.arm();self.observe('one');run=self.store.query('SELECT * FROM trading_runs')[0]
  self.store.execute("UPDATE trading_runs SET status='processing'")
  self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+run['id'],'a','{}','prepared',None,self.now.isoformat(),self.now.isoformat()))
  restored=LiveTrading(self.app)
  self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'failed')
  self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'skipped')
 def test_persisted_maintenance_requires_fresh_authentication_to_clear(self):
  from core import brokers
  from executor.brokers.base import BrokerCredentials
  self.store.execute('INSERT INTO broker_accounts(id,broker,account) VALUES(?,?,?)',('maintenance','zhangle','1234567890'))
  client=Mock();creds=BrokerCredentials('zhangle','1234567890')
  client.ensure_ready.return_value=dict(account_verified=True,account_display=creds.account,maintenance=True)
  self.assertTrue(brokers._verify_account(client,creds,self.store)['maintenance'])
  client.ensure_ready.return_value=dict(account_verified=True,account_display=creds.account)
  self.assertTrue(brokers._verify_account(client,creds,self.store)['maintenance'])
  client.ensure_ready.return_value=dict(account_verified=True,account_display=creds.account,authenticated_now=True)
  self.assertFalse(brokers._verify_account(client,creds,self.store).get('maintenance',False))
