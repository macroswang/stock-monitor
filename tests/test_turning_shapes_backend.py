import json,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.turning_shapes import signals
from core.turning_final import signals as final_signals
from core.turning_combined import SIGNAL
from core.turning_q1 import signals as q1_signals
from core.live_trading import LiveTrading,DEFAULT_RULE
from core.store import Store
from core.provider import CN

CASES=json.loads((Path(__file__).parent/'ui/fixtures/turning-shapes.json').read_text())
R1=json.loads((Path(__file__).parent/'fixtures/zhangle-reconstruction.json').read_text())

def case_bars(c):
 from core.turning_q1 import TIMES
 opening=dict(time='09:30',close=str(c['opening_price']),average=str(c['opening_price']),volume=0,complete=True)
 return [opening]+[dict(time=t,close=str(p),average=str(a),volume=v,complete=True) for t,p,a,v in zip(TIMES,c['prices'],c['averages'],c['volumes'])]


class ShapeParityTests(unittest.TestCase):
 def test_q1_remains_frozen_and_independent(self):
  for c in CASES:self.assertEqual(q1_signals(c['bars']),c['expectedQ1'])
 def test_complete_opening_quote_is_required_without_inventing_context(self):
  c=R1['cases'][0];rows=case_bars(c)
  self.assertTrue(signals(rows))
  self.assertEqual(signals(rows[1:]),[])
  self.assertEqual(signals(rows+[rows[0]]),[])
  for flag in [False,1,'true']:
   self.assertEqual(signals([dict(rows[0],complete=flag),*rows[1:]]),[])
 def test_price_signals_do_not_inherit_q1_size_or_cost_gates(self):
  c=R1['cases'][0];rows=case_bars(c)
  geometry=lambda ms:[(m['key'],m['time'],m['price']) for m in ms]
  self.assertEqual(geometry(signals([dict(b,volume=1) for b in rows])),geometry(signals(rows)))

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
  self.assertIn('观量 v2+Q1',upgraded.settings()['signal_notice'])
 def test_migration_does_not_repeat_or_rewrite_an_already_correct_rule(self):
  upgraded=LiveTrading(self.app);before=upgraded.rule('a','sz000981')
  self.store.setconfig('trading_paused',False)
  again=LiveTrading(self.app)
  self.assertEqual(again.rule('a','sz000981'),before);self.assertFalse(again.settings()['paused'])

class LabelledBottomDispatchTests(unittest.TestCase):
 def test_live_labelled_bottom_omitted_by_q1_generates_one_account_scoped_plan(self):
  c=next(c for c in R1['cases'] if c['code']=='sh603938' and c['day']=='2026-11-09');c=dict(c,bars=case_bars(c));mark=final_signals(c['bars'])[0]
  self.assertEqual((mark['kind'],mark['time']),('bottom','09:39'))
  self.assertNotIn(mark['key'],[m['key'] for m in q1_signals(c['bars'])])
  now=datetime.fromisoformat(c['day']+'T09:39:05+08:00')
  with tempfile.TemporaryDirectory() as directory:
   store=Store(Path(directory)/'test.sqlite3')
   try:
    with patch('core.live_trading.now_cn',return_value=now),patch('core.live_trading.brokers.submit_order') as submit:
     app=SimpleNamespace(store=store,quotes={});service=LiveTrading(app)
     store.execute("INSERT INTO broker_accounts(id,broker,account) VALUES('a','zhangle','123456789')")
     snapshot=dict(account_id='a',account_verified=True,observed_at=now.isoformat(),complete=True,funds=dict(available='100000'),positions=[dict(code=c['code'],name='山子高科',quantity=1000,sellable=1000,price=mark['price'])])
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
 def test_r1_buy_and_sell_reach_the_existing_gateway_once_at_emission(self):
  for kind,side,zero_previous in [('bottom','buy',False),('top','sell',False),('bottom','buy',True),('top','sell',True)]:
   with self.subTest(kind=kind,zero_previous=zero_previous),tempfile.TemporaryDirectory() as directory:
    c=next(c for c in R1['cases'] if c['code']=='sh603938' and c['day']==('2026-11-09' if kind=='bottom' else '2026-11-10'));c=dict(c,bars=case_bars(c))
    mark=next(m for m in final_signals(c['bars']) if m['kind']==kind)
    now=datetime.fromisoformat(c['day']+'T'+mark['time']+':05+08:00')
    store=Store(Path(directory)/'test.sqlite3')
    try:
     with patch('core.live_trading.now_cn',return_value=now) as clock:
      app=SimpleNamespace(store=store,quotes={});service=LiveTrading(app)
      store.execute("INSERT INTO broker_accounts(id,broker,account) VALUES('a','zhangle','123456789')")
      snapshot=dict(account_id='a',account_verified=True,observed_at=now.isoformat(),complete=True,funds=dict(available='100000'),positions=[dict(code=c['code'],name='山子高科',quantity=1000,sellable=1000,price=mark['price'])])
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
       self.assertEqual(gateway.call_args.args[1:6],('a',side,c['code'][2:],200,str(mark['price'])))
       run=store.query('SELECT * FROM trading_runs')[0];payload=json.loads(run['payload'])
       self.assertEqual(run['status'],'accepted');self.assertEqual(payload['signal']['time'],mark['time']);self.assertEqual(payload['signal']['candidateTime'],mark['candidateTime'])
       self.assertEqual(payload['reference_price'],mark['price'])
       later=now+timedelta(minutes=2);clock.return_value=later
       quote.update(timestamp=later.isoformat());service.ingest(c['code'],bars[:index+3],quote,later,True)
       service.drain(reports=False);gateway.assert_called_once()
       self.assertEqual(len(store.query('SELECT * FROM trading_runs')),1)
       restarted=LiveTrading(app)
       restarted.ingest(c['code'],bars[:index+3],quote,later,True)
       restarted.drain(reports=False);gateway.assert_called_once()
       self.assertEqual(len(store.query('SELECT * FROM trading_runs')),1)
    finally:store.db.close()
