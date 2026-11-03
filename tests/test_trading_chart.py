import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.store import Store
from core.live_trading import LiveTrading
from core.trading_chart import chart

class TradingChartTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
  self.service=LiveTrading(SimpleNamespace(store=self.store))
  for ident,account in [('a','1111111001'),('b','2222222002')]:
   self.store.execute('INSERT INTO broker_accounts(id,broker,account) VALUES(?,?,?)',(ident,'zhangle',account))
   self.store.execute('INSERT INTO trading_rules VALUES(?,?,?,?,?)',(ident,'sz000981',json.dumps(dict(buy_enabled=True,sell_enabled=True)),1,'2026-11-02T09:00:00+08:00'))
 def seed(self,ident='one',account='a',day='2026-11-03',status='accepted',verification=None,mode='live'):
  stamp=day+'T13:37:57+08:00'
  payload=dict(mode=mode,signal=dict(key='confirmed-shape-v1|bottom|13:34|13:37',time='13:37',price=2.17),reference_price=2.17,
               plan=dict(price='2.16',quantity=2300),price_checks=dict(before_submit=dict(checked_at=stamp)),message='测试回报')
  if verification:payload['verification']=verification
  self.store.execute('INSERT INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,account,'sz000981','buy','key-'+ident,day,status,json.dumps(payload),stamp,stamp))
  self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+ident,account,'{}',status,json.dumps(dict(order_id='contract-'+ident)),stamp,stamp))
 def test_order_price_comes_from_plan_and_fill_is_not_inferred_from_acceptance(self):
  self.seed();p=chart(self.store,'sz000981','2026-11-03')['points'][0]
  self.assertEqual(p['order_price'],'2.16');self.assertEqual(p['reference_price'],2.17)
  self.assertIsNone(p['fill_price']);self.assertIsNone(p['filled']);self.assertEqual(p['order_id'],'contract-one')
 def test_verified_average_is_separate_from_limit_and_manual_notes_cannot_supply_it(self):
  self.seed(verification=dict(origin='broker_auto',status='filled',filled=2300,average='2.15'),status='filled')
  self.seed('two','b',verification=dict(origin='manual',status='filled',filled=2300,average='2.14'),status='filled')
  points=chart(self.store,'sz000981','2026-11-03')['points'];self.assertEqual(points[0]['fill_price'],'2.15');self.assertIsNone(points[1]['fill_price'])
 def test_accounts_dates_and_codes_are_scoped_and_full_accounts_never_leave_projection(self):
  self.seed();self.seed('two','b');self.seed('old','a','2026-11-02')
  view=chart(self.store,'sz000981','2026-11-03')
  self.assertEqual({p['account_id'] for p in view['points']},{'a','b'});self.assertEqual(len(view['points']),2)
  self.assertNotIn('1111111001',json.dumps(view));self.assertNotIn('2222222002',json.dumps(view))
  self.assertFalse(chart(self.store,'sh603938','2026-11-03')['points'])
 def test_chart_is_read_only_and_never_calls_device_or_order_gateway(self):
  self.seed()
  with patch('core.brokers.submit_order',side_effect=AssertionError('order IO')),patch('core.brokers.order_report',side_effect=AssertionError('device IO')):
   before=self.store.db.total_changes;chart(self.store,'sz000981','2026-11-03');self.assertEqual(self.store.db.total_changes,before)
 def test_conflicting_receipt_ids_stay_unknown(self):
  self.seed(status='unknown');self.store.execute('UPDATE broker_requests SET result=?',(json.dumps(dict(order_id='1',result=dict(order_id='2'))),))
  point=chart(self.store,'sz000981','2026-11-03')['points'][0];self.assertEqual(point['order_id'],'');self.assertEqual(point['status'],'unknown')
