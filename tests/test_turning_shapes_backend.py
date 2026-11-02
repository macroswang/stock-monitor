import json,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.turning_shapes import signals,SIGNAL
from core.turning_q1 import signals as q1_signals
from core.live_trading import LiveTrading,DEFAULT_RULE
from core.store import Store
from core.provider import CN

CASES=json.loads((Path(__file__).parent/'ui/fixtures/turning-shapes.json').read_text())

class ShapeParityTests(unittest.TestCase):
 def test_exact_labelled_chart_engine_parity_including_q1_rejected_bottoms(self):
  for c in CASES:
   with self.subTest(code=c['code']):
    got=signals(c['bars']);expected=c['expectedShapes']
    self.assertEqual([r['key'] for r in got],[r['key'] for r in expected])
    for actual,reference in zip(got,expected):
     self.assertEqual(actual.keys(),reference.keys())
     for key,value in reference.items():
      if isinstance(value,(float,int)):self.assertAlmostEqual(actual[key],value,places=9)
      else:self.assertEqual(actual[key],value)
  c=next(c for c in CASES if c['code']=='sz000981')
  self.assertTrue(any(m['kind']=='bottom' for m in signals(c['bars'])))
  self.assertFalse(any(m['kind']=='bottom' for m in q1_signals(c['bars'])))
 def test_q1_cost_volume_and_size_screen_do_not_filter_price_labels(self):
  for c in CASES:
   tiny=[dict(b,volume=1) for b in c['bars']]
   geometry=lambda result:[(m['key'],m['kind'],m['time'],m['price']) for m in result]
   self.assertEqual(geometry(signals(tiny)),geometry(signals(c['bars'])))
   self.assertEqual(q1_signals(tiny),[])
 def test_prefix_and_future_prices_cannot_rewrite_past_confirmations(self):
  for c in CASES:
   full=signals(c['bars'])
   for i in range(25,len(c['bars']),17):
    end=c['bars'][i]['time'];expected=[m for m in full if m['time']<=end]
    self.assertEqual(signals(c['bars'][:i+1]),expected)
    changed=[b if j<=i else dict(b,close='9999',average='1',volume=1) for j,b in enumerate(c['bars'])]
    self.assertEqual([m for m in signals(changed) if m['time']<=end],expected)
 def test_incomplete_duplicate_or_missing_confirmation_bars_do_not_trigger(self):
  for c in CASES:
   mark=c['expectedShapes'][0];index=next(i for i,b in enumerate(c['bars']) if b['time']==mark['time'])
   for changed in [[dict(b,complete=False) if i==index else b for i,b in enumerate(c['bars'])],c['bars'][:index]+c['bars'][index+1:],c['bars']+[c['bars'][index]]]:
    self.assertNotIn(mark['key'],[m['key'] for m in signals(changed)])

class SignalMigrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
  self.app=SimpleNamespace(store=self.store)
  self.service=LiveTrading(self.app)
  self.original=dict(signal='Q1',buy_enabled=True,sell_enabled=True,buy_ratio='1/3',sell_ratio='1/4',max_order_value=9876,daily_buy_value=3000,base_shares=1200,daily_orders=2,max_deviation_pct=.5)
  self.store.execute('INSERT INTO trading_rules VALUES(?,?,?,7,?)',('a','sz000981',json.dumps(self.original),'2026-11-02T09:30:00+08:00'))
  self.store.setconfig('trading_mode','live');self.store.setconfig('trading_paused',False)
 def test_migrate_preserves_switches_converts_sizes_and_requires_new_baseline(self):
  upgraded=LiveTrading(self.app);rule=upgraded.rule('a','sz000981')
  self.assertEqual(rule['signal'],SIGNAL)
  self.assertTrue(rule['buy_enabled']);self.assertTrue(rule['sell_enabled'])
  self.assertEqual(rule['buy_mode'],'lots');self.assertEqual(rule['buy_lots'],4)
  self.assertNotIn('max_order_value',rule);self.assertNotIn('daily_buy_value',rule)
  self.assertEqual(rule['revision'],8);self.assertEqual(rule['armed_at'],upgraded.started_at)
  self.assertTrue(upgraded.settings()['paused']);self.assertEqual(upgraded.settings()['mode'],'live')
  self.assertIn('金额上限已移除',upgraded.settings()['signal_notice'])
 def test_migration_does_not_repeat_or_rewrite_an_already_correct_rule(self):
  upgraded=LiveTrading(self.app);before=upgraded.rule('a','sz000981')
  self.store.setconfig('trading_paused',False)
  again=LiveTrading(self.app)
  self.assertEqual(again.rule('a','sz000981'),before);self.assertFalse(again.settings()['paused'])

class LabelledBottomDispatchTests(unittest.TestCase):
 def test_live_labelled_bottom_omitted_by_q1_generates_one_account_scoped_plan(self):
  c=next(c for c in CASES if c['code']=='sz000981');mark=c['expectedShapes'][0]
  self.assertEqual((mark['kind'],mark['time']),('bottom','10:00'))
  self.assertNotIn(mark['key'],[m['key'] for m in q1_signals(c['bars'])])
  now=datetime.fromisoformat('2026-11-02T10:00:05+08:00')
  with tempfile.TemporaryDirectory() as directory:
   store=Store(Path(directory)/'test.sqlite3')
   try:
    with patch('core.live_trading.now_cn',return_value=now),patch('core.live_trading.brokers.submit_order') as submit:
     app=SimpleNamespace(store=store,quotes={});service=LiveTrading(app)
     store.execute("INSERT INTO broker_accounts(id,broker,account) VALUES('a','zhangle','123456789')")
     snapshot=dict(account_id='a',account_verified=True,observed_at=now.isoformat(),complete=True,funds=dict(available='10000'),positions=[dict(code=c['code'],name='山子高科',quantity=1000,sellable=1000,price=mark['price'])])
     service.apply_snapshot('a',snapshot);rule=service.rule('a',c['code'])
     service.save_rule('a',c['code'],dict(buy_enabled=True,buy_mode='position',buy_percent=50),rule['revision'])
     service.configure(dict(paused=False));store.setconfig('monitor',True)
     earlier=(now-timedelta(minutes=5)).isoformat();service.started_at=earlier
     store.execute('UPDATE trading_rules SET armed_at=?',(earlier,))
     quote=dict(price=mark['price'],timestamp=now.isoformat());app.quotes[c['code']]=quote
     index=next(i for i,b in enumerate(c['bars']) if b['time']==mark['time'])
     service.ingest(c['code'],c['bars'][:index],quote,now-timedelta(minutes=1),False)
     service.ingest(c['code'],c['bars'][:index+1],quote,now,True)
     service.ingest(c['code'],c['bars'][:index+1],quote,now,True)
     with patch('core.live_trading.brokers.holdings',return_value=snapshot):service.drain()
     runs=store.query('SELECT * FROM trading_runs');self.assertEqual(len(runs),1)
     run=runs[0];payload=json.loads(run['payload'])
     self.assertEqual((run['account_id'],run['side'],run['status']),('a','buy','trial'))
     self.assertEqual(payload['signal']['key'],mark['key']);self.assertEqual(payload['signal_source'],SIGNAL)
     submit.assert_not_called()
   finally:store.db.close()
