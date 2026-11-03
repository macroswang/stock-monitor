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
               plan=dict(account_id=account,code='sz000981',side='buy',price='2.16',quantity=2300),price_checks=dict(before_submit=dict(checked_at=stamp)),message='测试回报')
  if verification:payload['verification']=verification
  self.store.execute('INSERT INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,account,'sz000981','buy','key-'+ident,day,status,json.dumps(payload),stamp,stamp))
  request=dict(account_id=account,code='000981',side='buy',price='2.16',quantity=2300,dry_run=False)
  self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+ident,account,json.dumps(request),status,json.dumps(dict(order_id='contract-'+ident)),stamp,stamp))
 def legacy(self,message='委托提交成功,合同号:142783',**extra):
  self.seed(status='unknown')
  ack=dict(submitted=False,status='unknown',confirm=dict(title='委托买入',code='000981',price='2.16',quantity='2300'),
           result=dict(kind='unknown',title='系统提示',message=message),**extra)
  self.store.execute('UPDATE broker_requests SET result=?',(json.dumps(ack),))
  return ack
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
 def test_legacy_native_success_is_displayed_without_rewriting_status_or_inferring_a_fill(self):
  self.legacy()
  before=self.store.query('SELECT * FROM trading_runs'),self.store.query('SELECT * FROM broker_requests')
  with patch('core.brokers.submit_order',side_effect=AssertionError('order IO')),patch('core.brokers.order_report',side_effect=AssertionError('device IO')):
   point=chart(self.store,'sz000981','2026-11-03')['points'][0]
  self.assertTrue(point['receipt_accepted']);self.assertEqual(point['order_id'],'142783')
  self.assertEqual(point['status'],'unknown');self.assertIsNone(point['fill_price']);self.assertIsNone(point['filled'])
  self.assertEqual(before,(self.store.query('SELECT * FROM trading_runs'),self.store.query('SELECT * FROM broker_requests')))
 def test_legacy_ack_requires_exact_account_day_stock_direction_price_and_quantity(self):
  self.legacy()
  request=json.loads(self.store.query('SELECT payload FROM broker_requests')[0]['payload'])
  for field,value in [('account_id','b'),('code','000982'),('side','sell'),('price','2.15'),('quantity',2200),('dry_run',True)]:
   with self.subTest(field=field):
    self.store.execute('UPDATE broker_requests SET payload=?',(json.dumps(dict(request,**{field:value})),))
    self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'][0]['receipt_accepted'])
  self.store.execute('UPDATE broker_requests SET payload=?,created_at=?',(json.dumps(request),'2026-11-02T13:37:57+08:00'))
  self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'][0]['receipt_accepted'])
 def test_legacy_receipt_never_overrides_missing_conflicting_or_mixed_evidence(self):
  ack=self.legacy()
  for message in ['合同号:142783','委托提交成功','委托提交成功,合同号:142783，网络超时','委托提交成功,合同号:142783，失败','委托提交成功,合同号:142783，委托号:142784']:
   with self.subTest(message=message):
    changed=dict(ack,result=dict(ack['result'],message=message))
    self.store.execute('UPDATE broker_requests SET result=?',(json.dumps(changed),))
    self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'][0]['receipt_accepted'])
  for changed in [dict(ack,order_id='different'),dict(ack,confirm=dict(ack['confirm'],price='2.15')),dict(ack,result=dict(ack['result'],kind='error'))]:
   self.store.execute('UPDATE broker_requests SET result=?',(json.dumps(changed),))
   self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'][0]['receipt_accepted'])
 def test_legacy_receipt_cannot_create_a_marker_for_skipped_or_trial_runs(self):
  self.legacy()
  self.store.execute("UPDATE trading_runs SET status='skipped'")
  self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'][0]['receipt_accepted'])
  self.store.execute("UPDATE trading_runs SET status='unknown',payload=json_set(payload,'$.mode','trial')")
  self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'][0]['receipt_accepted'])
