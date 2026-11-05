import json,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.live_trading import LiveTrading,DEFAULT_RULE
from core.trading_quantity import quantity,migrate_rule,buy_cash_required
from core.store import Store
from core.provider import CN

class QuantityCalculationTests(unittest.TestCase):
 def test_fixed_lots_repeat_without_shrinking_to_a_fraction_of_remaining_holding(self):
  rule={**DEFAULT_RULE,'buy_lots':1,'sell_lots':1}
  for position in (300,200,100):
   self.assertEqual(quantity('sh603938',position,position,'buy',rule),100)
   self.assertEqual(quantity('sh603938',position,position,'sell',rule),100)
 def test_percentage_uses_current_position_for_both_directions_and_caps_sellable(self):
  rule={**DEFAULT_RULE,'buy_mode':'position','sell_mode':'position','buy_percent':25,'sell_percent':50}
  self.assertEqual(quantity('sz000981',1200,900,'buy',rule),300)
  self.assertEqual(quantity('sz000981',2000,900,'buy',rule),500)
  self.assertEqual(quantity('sz000981',1200,900,'sell',rule),600)
  self.assertEqual(quantity('sz000981',1200,200,'sell',rule),200)
 def test_percent_rounds_down_instead_of_unexpectedly_buying_more_than_requested(self):
  rule={**DEFAULT_RULE,'buy_mode':'position','buy_percent':10}
  self.assertEqual(quantity('sh603938',300,300,'buy',rule),0)
  self.assertEqual(quantity('sz000981',1000000,1000000,'buy',{**rule,'buy_percent':50.01}),500100)
 def test_fixed_sell_never_silently_exceeds_or_changes_requested_size(self):
  with self.assertRaisesRegex(ValueError,'可卖'):quantity('sz000981',1200,100,'sell',{**DEFAULT_RULE,'sell_lots':2})
 def test_percentage_can_clear_sellable_odd_lots_and_star_minimum_is_preserved(self):
  self.assertEqual(quantity('sz000981',199,199,'sell',{**DEFAULT_RULE,'sell_mode':'position','sell_percent':100}),199)
  self.assertEqual(quantity('sh688001',499,499,'buy',{**DEFAULT_RULE,'buy_mode':'position','buy_percent':50}),249)
  self.assertEqual(quantity('sh688001',499,499,'buy',DEFAULT_RULE),0)
 def test_old_fraction_rule_becomes_equivalent_whole_lots_without_money_limits(self):
  old=dict(buy_enabled=True,sell_enabled=True,buy_ratio='1/4',sell_ratio='1/4',base_shares=10300,max_order_value=1000,daily_buy_value=3000,daily_orders=2,max_deviation_pct=.5,signal='shape-v1')
  migrated=migrate_rule('sz000981',old,dict(quantity=10300,sellable=7800),DEFAULT_RULE)
  self.assertEqual((migrated['buy_lots'],migrated['sell_lots']),(25,19))
  self.assertTrue(migrated['buy_enabled']);self.assertTrue(migrated['sell_enabled'])
  self.assertFalse({'buy_ratio','sell_ratio','base_shares','max_order_value','daily_buy_value'}&migrated.keys())

class QuantityServiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
  self.now=datetime(2026,11,2,10,1,5,tzinfo=CN)
  clock=patch('core.live_trading.now_cn',side_effect=lambda:self.now);clock.start();self.addCleanup(clock.stop)
  self.app=SimpleNamespace(store=self.store,quotes={'sh603938':dict(price='30',timestamp=self.now.isoformat())})
  self.service=LiveTrading(self.app);self.store.setconfig('monitor',True)
  self.snapshot=dict(account_id='a',account_verified=True,observed_at=self.now.isoformat(),complete=True,funds=dict(available='10000'),positions=[dict(code='sh603938',name='三孚股份',quantity=300,sellable=300,price=30)])
  for ident in ('a','b'):
   self.store.execute('INSERT INTO broker_accounts(id,broker,account) VALUES(?,?,?)',(ident,'ths','12345678'+ident))
   self.service.apply_snapshot(ident,{**self.snapshot,'account_id':ident})
 def arm(self):
  r=self.service.rule('a','sh603938');self.service.save_rule('a','sh603938',dict(buy_enabled=True,sell_enabled=True,daily_orders=10),r['revision'])
  self.service.configure(dict(paused=False));self.service.started_at=(self.now-timedelta(minutes=3)).isoformat()
  self.store.execute('UPDATE trading_rules SET armed_at=?',((self.now-timedelta(minutes=3)).isoformat(),))
 def observe(self,key):
  self.service.observe('sh603938',[dict(kind='bottom',key=key,time='10:01',price=30,liquidity=dict(meanShares=100000,currentShares=100000))],self.app.quotes['sh603938'],self.now,True)
 def test_one_hand_order_above_old_single_and_daily_caps_is_allowed(self):
  self.arm()
  with patch('core.live_trading.brokers.holdings',return_value=self.snapshot),patch('core.live_trading.brokers.submit_order') as submit:
   for key in ('one','two','three'):self.observe(key);self.service.drain()
  rows=self.store.query('SELECT * FROM trading_runs')
  self.assertEqual([r['status'] for r in rows],['trial']*3)
  self.assertEqual([json.loads(r['payload'])['plan']['quantity'] for r in rows],[100]*3)
  self.assertEqual(sum(json.loads(r['payload'])['plan']['value'] for r in rows),9000)
  submit.assert_not_called()
 def test_actual_account_cash_still_blocks_unaffordable_order(self):
  self.arm();snapshot={**self.snapshot,'funds':dict(available='1000')}
  with patch('core.live_trading.brokers.holdings',return_value=snapshot),patch('core.live_trading.brokers.submit_order') as submit:
   self.observe('one');self.service.drain()
  run=self.store.query('SELECT * FROM trading_runs')[0]
  self.assertEqual(run['status'],'skipped');self.assertIn('可用资金不足',json.loads(run['payload'])['message']);submit.assert_not_called()
 def test_configured_buy_and_sell_size_is_independent_of_minute_liquidity(self):
  self.arm()
  r=self.service.rule('a','sh603938')
  self.service.save_rule('a','sh603938',dict(buy_lots=2,sell_lots=2),r['revision'])
  self.store.execute('UPDATE trading_rules SET armed_at=?',((self.now-timedelta(minutes=3)).isoformat(),))
  with patch('core.live_trading.brokers.holdings',return_value=self.snapshot),patch('core.live_trading.brokers.submit_order') as submit:
   for side,kind in [('buy','bottom'),('sell','top')]:
    for liquidity in [dict(meanShares=32400,currentShares=16700),dict(meanShares=0,currentShares=0),{}]:
     self.store.execute('DELETE FROM trading_runs')
     event=dict(kind=kind,key=side+str(liquidity),time='10:01',price=30,liquidity=liquidity)
     self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,True)
     self.service.drain(reports=False)
     run=self.store.query('SELECT * FROM trading_runs')[0]
     with self.subTest(side=side,liquidity=liquidity):
      self.assertEqual(run['status'],'trial')
      self.assertEqual(json.loads(run['payload'])['plan']['quantity'],200)
  submit.assert_not_called()
 def test_input_validation_and_obsolete_money_fields(self):
  r=self.service.rule('a','sh603938')
  for changes in [dict(buy_mode='bad'),dict(buy_lots=0),dict(buy_lots=1.5),dict(buy_lots=True),dict(buy_percent=0),dict(buy_percent=101),dict(buy_percent=float('nan')),dict(max_order_value=1000),dict(daily_buy_value=3000)]:
   with self.subTest(changes=changes),self.assertRaises(ValueError):self.service.save_rule('a','sh603938',changes,r['revision'])
 def test_same_stock_different_accounts_keep_modes_separate(self):
  r=self.service.rule('a','sh603938');self.service.save_rule('a','sh603938',dict(buy_mode='position',buy_percent=100),r['revision'])
  self.assertEqual(self.service.plan('a','sh603938','buy')['quantity'],300)
  self.assertEqual(self.service.rule('b','sh603938')['buy_mode'],'lots')
  self.assertEqual(self.service.rule('b','sh603938')['buy_lots'],1)
 def test_view_keeps_funds_account_scoped_and_exposes_actual_cash_reserve(self):
  self.service.apply_snapshot('b',{**self.snapshot,'account_id':'b','funds':dict(available='1,000')})
  view=self.service.view()
  accounts={a['id']:a for a in view['accounts']}
  self.assertEqual(accounts['a']['funds']['available'],'10000')
  self.assertEqual(accounts['b']['funds']['available'],'1,000')
  reserve=view['cash_reserve']
  self.assertAlmostEqual(2936*(1+reserve['rate'])+reserve['fixed'],buy_cash_required(2936))
