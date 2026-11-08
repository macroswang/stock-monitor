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
CANDIDATES=json.loads((Path(__file__).parent/'ui/fixtures/turning-candidates.json').read_text())

class ShapeParityTests(unittest.TestCase):
 def test_exact_labelled_chart_engine_parity_including_q1_rejected_bottoms(self):
  for c in CASES:
   with self.subTest(code=c['code']):
    got=signals(c['bars'])
    self.assertEqual([[m['kind'],m['time'],m['price']] for m in got],CANDIDATES[c['code']])
    for m in got:
     self.assertEqual((m['time'],m['price']),(m['candidateTime'],m['candidatePrice']))
     self.assertEqual(m['key'],f"candidate-shape-v1|{m['kind']}|{m['time']}")
    self.assertEqual(q1_signals(c['bars']),c['expectedQ1'])
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
   mark=signals(c['bars'])[0];index=next(i for i,b in enumerate(c['bars']) if b['time']==mark['time'])
   for changed in [[dict(b,complete=False) if i==index else b for i,b in enumerate(c['bars'])],c['bars'][:index]+c['bars'][index+1:],c['bars']+[c['bars'][index]]]:
    self.assertNotIn(mark['key'],[m['key'] for m in signals(changed)])

 def test_candidate_is_immediate_and_does_not_move_or_repeat_after_future_bars(self):
  from core.turning_q1 import TIMES
  for kind,p,later in [('bottom',29.69,29.60),('top',30.50,30.60)]:
   bars=[dict(time=t,close=str(p if t=='13:16' else 30),average='29.95',volume=100000,complete=True) for t in TIMES if t<='13:16']
   first=signals(bars)
   self.assertEqual([(m['kind'],m['time'],m['price']) for m in first],[(kind,'13:16',p)])
   self.assertEqual(signals(bars+[dict(bars[-1],time='13:17',close=str(later)),dict(bars[-1],time='13:18',close=str(p))]),first)

 def test_zero_volume_previous_minute_does_not_block_candidate_but_invalid_data_does(self):
  from core.turning_q1 import TIMES
  for kind,p in [('bottom',29.69),('top',30.50)]:
   bars=[dict(time=t,close=str(p if t=='13:16' else 30),average='29.95',volume=0 if t=='13:15' else 100000,complete=True) for t in TIMES if t<='13:16']
   with self.subTest(kind=kind):
    self.assertEqual([(m['kind'],m['time'],m['price']) for m in signals(bars)],[(kind,'13:16',p)])
    for volume in [-1,float('nan'),float('inf')]:
     self.assertEqual(signals([dict(b,volume=volume) if b['time']=='13:15' else b for b in bars]),[])
    self.assertEqual(signals([b for b in bars if b['time']!='13:15']),[])
    self.assertEqual(signals([dict(b,complete=False) if b['time']=='13:15' else b for b in bars]),[])
    self.assertEqual(signals([dict(b,volume=0) if b['time']=='13:16' else b for b in bars]),[])

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
  c=next(c for c in CASES if c['code']=='sz000981');mark=signals(c['bars'])[0]
  self.assertEqual((mark['kind'],mark['time']),('bottom','09:58'))
  self.assertNotIn(mark['key'],[m['key'] for m in q1_signals(c['bars'])])
  now=datetime.fromisoformat('2026-11-02T09:58:05+08:00')
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

class CandidateLiveDispatchTests(unittest.TestCase):
 def test_candidate_buy_and_sell_reach_the_existing_gateway_once_before_confirmation(self):
  c=next(c for c in CASES if c['code']=='sz000981')
  for kind,side,zero_previous in [('bottom','buy',False),('top','sell',False),('bottom','buy',True),('top','sell',True)]:
   with self.subTest(kind=kind,zero_previous=zero_previous),tempfile.TemporaryDirectory() as directory:
    mark=next(m for m in signals(c['bars']) if m['kind']==kind)
    now=datetime.fromisoformat('2026-11-02T'+mark['time']+':05+08:00')
    store=Store(Path(directory)/'test.sqlite3')
    try:
     with patch('core.live_trading.now_cn',return_value=now) as clock:
      app=SimpleNamespace(store=store,quotes={});service=LiveTrading(app)
      store.execute("INSERT INTO broker_accounts(id,broker,account) VALUES('a','zhangle','123456789')")
      snapshot=dict(account_id='a',account_verified=True,observed_at=now.isoformat(),complete=True,funds=dict(available='10000'),positions=[dict(code=c['code'],name='山子高科',quantity=1000,sellable=1000,price=mark['price'])])
      service.apply_snapshot('a',snapshot);rule=service.rule('a',c['code'])
      service.save_rule('a',c['code'],{side+'_enabled':True,side+'_lots':2},rule['revision'])
      store.setconfig('trading_mode','live');store.setconfig('trading_paused',False);store.setconfig('monitor',True)
      earlier=(now-timedelta(minutes=5)).isoformat();service.started_at=earlier
      store.execute('UPDATE trading_rules SET armed_at=?',(earlier,))
      quote=dict(code=c['code'],price=mark['price'],timestamp=now.isoformat());app.quotes[c['code']]=quote
      index=next(i for i,b in enumerate(c['bars']) if b['time']==mark['time'])
      bars=[dict(b,volume=0) if zero_previous and i==index-1 else b for i,b in enumerate(c['bars'])]
      service.ingest(c['code'],bars[:index],quote,now-timedelta(minutes=1),False)
      service.ingest(c['code'],bars[:index+1],quote,now,True)
      service.ingest(c['code'],bars[:index+1],quote,now,True)
      def submit(*args,**kwargs):
       kwargs['authorize']()
       return dict(status='accepted',submitted=True,order_id='test-'+side)
      with patch('core.live_trading.brokers.holdings',return_value=snapshot),patch('core.live_trading.brokers.submit_order',side_effect=submit) as gateway:
       service.drain(reports=False);gateway.assert_called_once()
       self.assertEqual(gateway.call_args.args[1:6],('a',side,'000981',200,str(mark['price'])))
       run=store.query('SELECT * FROM trading_runs')[0];payload=json.loads(run['payload'])
       self.assertEqual(run['status'],'accepted');self.assertEqual(payload['signal']['time'],payload['signal']['candidateTime'])
       self.assertEqual(payload['reference_price'],mark['candidatePrice'])
       later=now+timedelta(minutes=2);clock.return_value=later
       quote.update(timestamp=later.isoformat());service.ingest(c['code'],bars[:index+3],quote,later,True)
       service.drain(reports=False);gateway.assert_called_once()
       self.assertEqual(len(store.query('SELECT * FROM trading_runs')),1)
    finally:store.db.close()
