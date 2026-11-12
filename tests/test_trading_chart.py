import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.store import Store
from core.live_trading import LiveTrading
from core.trading_chart import chart,sync_filled_orders,CACHE_KIND

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
 def test_manual_submission_is_visible_then_replaced_only_by_a_new_verified_fill_sync(self):
  day='2026-11-03';stamp=day+'T10:00:01+08:00'
  request=dict(account_id='a',code='000981',side='buy',price='2.20',quantity=100,dry_run=False)
  result=dict(status='unknown',submitted=True,receipt_pending=True,submitted_at=stamp)
  self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',('manual-buy-123456','a',json.dumps(request),'unknown',json.dumps(result),stamp,stamp))
  initial=chart(self.store,'sz000981',day)['points']
  self.assertEqual(len(initial),1);self.assertEqual(initial[0]['source'],'manual');self.assertEqual(initial[0]['ordered_at'],stamp)
  self.assertEqual(initial[0]['order_price'],'2.20');self.assertNotIn('fill_price',initial[0])
  cache=dict(account_id='a',account_verified=True,complete=True,day=day,observed_at=day+'T09:59:00+08:00',rows=[])
  self.store.cache('broker-account:a',CACHE_KIND,day,cache)
  self.assertEqual(chart(self.store,'sz000981',day)['points'][0]['source'],'manual')
  cache.update(observed_at=day+'T10:05:00+08:00',rows=[dict(code='000981',side='buy',date=day,time='10:03:02',order_id='actual123',filled=100,average='2.18')])
  self.store.cache('broker-account:a',CACHE_KIND,day,dict(cache,account_verified=False))
  self.assertEqual(chart(self.store,'sz000981',day)['points'][0]['source'],'manual')
  self.store.cache('broker-account:a',CACHE_KIND,day,cache)
  actual=chart(self.store,'sz000981',day)['points']
  self.assertEqual(len(actual),1);self.assertEqual(actual[0]['source'],'broker_cache');self.assertEqual(actual[0]['fill_price'],2.18)
  self.assertEqual(actual[0]['ordered_at'],day+'T10:03:02+08:00')
  self.store.cache('broker-account:a',CACHE_KIND,day,dict(cache,rows=[]))
  self.assertEqual(chart(self.store,'sz000981',day)['points'],[])
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
 def test_verified_broker_fill_cache_projects_manual_buy_and_sell_and_survives_read_only_chart(self):
  payload=dict(account_id='a',account_verified=True,complete=True,day='2026-11-03',observed_at='2026-11-03T15:05:00+08:00',rows=[
   dict(code='000981',name='山子高科',side='buy',date='2026-11-03',time='10:01:02',order_id='manual-1',filled=500,average='2.18',amount='1090'),
   dict(code='000981',name='山子高科',side='sell',date='2026-11-03',time='13:22:03',order_id='manual-2',filled=300,average='2.25',amount='675')])
  self.store.cache('broker-account:a',CACHE_KIND,'2026-11-03',payload)
  before=self.store.db.total_changes;points=chart(self.store,'sz000981','2026-11-03')['points']
  self.assertEqual(self.store.db.total_changes,before);self.assertEqual([p['side'] for p in points],['buy','sell'])
  self.assertTrue(all(p['source']=='broker_cache' and p['status']=='filled' and p['attempted'] for p in points))
  self.assertEqual((points[0]['filled'],points[0]['fill_price'],points[0]['order_id']),(500,2.18,'manual-1'))
 def test_cached_broker_fill_with_same_contract_as_automatic_order_is_not_duplicated(self):
  self.seed(verification=dict(origin='broker_auto',status='filled',filled=2300,average='2.15'),status='filled')
  payload=dict(account_id='a',account_verified=True,complete=True,day='2026-11-03',observed_at='2026-11-03T15:05:00+08:00',rows=[
   dict(code='000981',side='buy',date='2026-11-03',time='13:38:00',order_id='contract-one',filled=2300,average='2.15')])
  self.store.cache('broker-account:a',CACHE_KIND,'2026-11-03',payload)
  points=chart(self.store,'sz000981','2026-11-03')['points'];self.assertEqual(len(points),1);self.assertEqual(points[0]['source'],'automatic')
 def native_sell(self):
  from executor.ths_orders import order_key
  self.store.execute("UPDATE broker_accounts SET broker='ths' WHERE id='a'")
  native=dict(date='2026-11-03',time='13:44:21',name='山子高科',side='sell',price='2.16',quantity=2300)
  verification=dict(origin='broker_auto',source='ths_native_today_order',status='filled',filled=2300,average='2.18',native_order_key=order_key(native))
  self.seed(status='filled',verification=verification)
  self.store.execute("UPDATE trading_runs SET side='sell',payload=json_set(payload,'$.plan.side','sell','$.price_checks.before_submit.checked_at','2026-11-03T13:44:20+08:00')")
  self.store.execute("UPDATE broker_requests SET payload=json_set(payload,'$.side','sell'),result='{}'")
  row=dict(code='000981',date=native['date'],time=native['time'],name=native['name'],side='sell',order_id='1199281',filled=2300,average='2.18')
  payload=dict(account_id='a',account_verified=True,complete=True,day='2026-11-03',observed_at='2026-11-03T15:01:06+08:00',source='ths_native_contract_group',rows=[row])
  self.store.cache('broker-account:a',CACHE_KIND,'2026-11-03',payload)
  return row,payload
 def test_native_order_without_contract_merges_its_cached_contract_only_in_chart(self):
  self.native_sell();before=self.store.db.total_changes
  for _ in range(2):
   points=chart(self.store,'sz000981','2026-11-03')['points']
   self.assertEqual(len(points),1);self.assertEqual(points[0]['source'],'automatic');self.assertEqual(points[0]['order_id'],'1199281')
   self.assertEqual(points[0]['fill_price'],'2.18');self.assertEqual(points[0]['order_price'],'2.16')
  self.assertEqual(self.store.db.total_changes,before)
  self.assertEqual(json.loads(self.store.query('SELECT result FROM broker_requests')[0]['result']),{})
 def test_native_merge_preserves_separate_same_minute_orders_and_conflicting_fill_evidence(self):
  row,payload=self.native_sell()
  for change in [dict(time='13:44:22'),dict(average='2.19'),dict(filled=2200),dict(quantity=2400),dict(name='其他股票')]:
   with self.subTest(change=change):
    self.store.cache('broker-account:a',CACHE_KIND,'2026-11-03',dict(payload,rows=[dict(row,**change)]))
    points=chart(self.store,'sz000981','2026-11-03')['points'];self.assertEqual(len(points),2);self.assertEqual(points[0]['order_id'],'')
 def test_native_merge_never_hides_two_ambiguous_broker_contracts(self):
  row,payload=self.native_sell()
  self.store.cache('broker-account:a',CACHE_KIND,'2026-11-03',dict(payload,rows=[row,dict(row,order_id='1199282')]))
  points=chart(self.store,'sz000981','2026-11-03')['points'];self.assertEqual(len(points),3)
  self.assertEqual({p['order_id'] for p in points},{'','1199281','1199282'})
 def test_native_merge_is_account_scoped_and_rejects_missing_or_untrusted_identity(self):
  row,payload=self.native_sell()
  self.store.execute("UPDATE trading_runs SET payload=json_set(payload,'$.verification.native_order_key',NULL)")
  self.assertEqual(len(chart(self.store,'sz000981','2026-11-03')['points']),2)
  self.store.execute("DELETE FROM trading_runs");self.store.execute("DELETE FROM broker_requests");self.native_sell()
  self.store.execute("UPDATE broker_accounts SET broker='zhangle' WHERE id='a'")
  self.assertEqual(len(chart(self.store,'sz000981','2026-11-03')['points']),2)
  self.store.execute("UPDATE broker_accounts SET broker='ths' WHERE id='a'")
  self.store.cache('broker-account:a',CACHE_KIND,'2026-11-03',dict(payload,source='unverified'))
  self.assertEqual(len(chart(self.store,'sz000981','2026-11-03')['points']),2)
  self.store.execute("DELETE FROM cache WHERE code='broker-account:a'")
  self.store.cache('broker-account:b',CACHE_KIND,'2026-11-03',dict(payload,account_id='b'))
  self.assertEqual(len(chart(self.store,'sz000981','2026-11-03')['points']),2)
 def test_incomplete_wrong_account_and_unverified_cache_never_projects(self):
  base=dict(account_id='a',account_verified=True,complete=True,day='2026-11-03',rows=[dict(code='000981',side='buy',time='10:01:02',filled=100,average='2.18')])
  for change in [dict(account_id='b'),dict(account_verified=False),dict(complete=False),dict(day='2026-11-02')]:
   with self.subTest(change=change):
    self.store.cache('broker-account:a',CACHE_KIND,'2026-11-03',dict(base,**change))
    self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'])
 def test_sync_replaces_only_successful_account_cache_and_retains_failed_account_cache(self):
  old=dict(account_id='b',account_verified=True,complete=True,day='2026-11-03',observed_at='old',rows=[dict(code='000981',side='sell',time='10:00:00',filled=100,average='2.20')])
  self.store.cache('broker-account:b',CACHE_KIND,'2026-11-03',old)
  fresh=dict(account_id='a',account_verified=True,complete=True,day='2026-11-03',observed_at='new',rows=[dict(code='000981',side='buy',time='11:00:00',filled=200,average='2.18')])
  with patch('core.trading_chart.now_cn',return_value=__import__('datetime').datetime.fromisoformat('2026-11-03T15:10:00+08:00')),patch('core.trading_chart.brokers.filled_orders',side_effect=[fresh,ValueError('账户未登录')]):
   result=sync_filled_orders(self.store,'2026-11-03')
  self.assertEqual((result['saved'],len(result['errors'])),(1,1))
  self.assertEqual(self.store.getcache('broker-account:a',CACHE_KIND,'2026-11-03')[0]['data']['observed_at'],'new')
  self.assertEqual(self.store.getcache('broker-account:b',CACHE_KIND,'2026-11-03')[0]['data']['observed_at'],'old')
 def test_prepared_request_is_not_mislabeled_as_an_automatic_order_attempt(self):
  self.seed(status='pending');self.store.execute("UPDATE broker_requests SET status='prepared'")
  self.assertFalse(chart(self.store,'sz000981','2026-11-03')['points'][0]['attempted'])
 def test_chart_does_not_truncate_more_than_five_hundred_automatic_orders(self):
  stamp='2026-11-03T10:00:00+08:00';runs=[];requests=[]
  for n in range(501):
   ident=f'many-{n}';payload=dict(mode='live',reference_price=2.2,plan=dict(account_id='a',code='sz000981',side='buy',price='2.20',quantity=100),price_checks=dict(before_submit=dict(checked_at=stamp)))
   request=dict(account_id='a',code='000981',side='buy',price='2.20',quantity=100,dry_run=False)
   runs.append((ident,'a','sz000981','buy','signal-'+ident,'2026-11-03','accepted',json.dumps(payload),stamp,stamp))
   requests.append(('auto_'+ident,'a',json.dumps(request),'accepted','{}',stamp,stamp))
  with self.store.lock,self.store.db:
   self.store.db.executemany('INSERT INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',runs)
   self.store.db.executemany('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',requests)
  self.assertEqual(len(chart(self.store,'sz000981','2026-11-03')['points']),501)
 def test_conflicting_receipt_ids_stay_unknown(self):
  self.seed(status='unknown');self.store.execute('UPDATE broker_requests SET result=?',(json.dumps(dict(order_id='1',result=dict(order_id='2'))),))
  point=chart(self.store,'sz000981','2026-11-03')['points'][0];self.assertEqual(point['order_id'],'');self.assertEqual(point['status'],'unknown')
 def test_native_missing_result_keeps_chart_and_execution_records_readable(self):
  self.seed(status='unknown')
  for receipt in (None,[], 'invalid'):
   with self.subTest(receipt=receipt):
    self.store.execute('UPDATE broker_requests SET result=?',(json.dumps(dict(result=receipt)),))
    point=chart(self.store,'sz000981','2026-11-03')['points'][0]
    self.assertEqual(point['order_id'],'');self.assertEqual(point['receipt_message'],'');self.assertIsNone(point['fill_price'])
    run=self.service.view()['runs'][0];self.assertEqual(run['status'],'unknown');self.assertFalse(run['receipt_accepted'])
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

 def test_durable_accepted_receipt_survives_interrupted_run_without_waiting_for_fills(self):
  self.seed(status='unknown')
  ack=dict(status='accepted',submitted=True,confirm=dict(side='buy',code='000981',quantity=2300,price='2.16'))
  self.store.execute("UPDATE broker_requests SET status='accepted',result=?",(json.dumps(ack),))
  before=self.store.db.total_changes
  p=chart(self.store,'sz000981','2026-11-03')['points'][0]
  self.assertEqual(p['status'],'accepted');self.assertIsNone(p['fill_price']);self.assertIsNone(p['filled'])
  self.assertEqual(self.service.view()['runs'][0]['status'],'accepted')
  self.assertEqual(self.store.db.total_changes,before)
  self.assertEqual(self.store.query('SELECT status FROM trading_runs')[0]['status'],'unknown')

 def test_interrupted_sell_uses_its_accepted_native_receipt_for_both_sending_and_unknown(self):
  self.seed(status='sending')
  self.store.execute("UPDATE trading_runs SET side='sell',payload=json_set(payload,'$.plan.side','sell')")
  ack=dict(status='accepted',submitted=True,confirm=dict(title='委托卖出',code='000981',quantity='2300',price='2.16'))
  self.store.execute("UPDATE broker_requests SET status='accepted',payload=json_set(payload,'$.side','sell'),result=?",(json.dumps(ack),))
  for status in ('sending','unknown'):
   self.store.execute('UPDATE trading_runs SET status=?',(status,))
   p=chart(self.store,'sz000981','2026-11-03')['points'][0]
   self.assertEqual(p['status'],'accepted');self.assertEqual(p['side'],'sell');self.assertIsNone(p['filled'])

 def test_accepted_receipt_projection_never_crosses_account_plan_or_trial(self):
  self.seed(status='unknown')
  good=dict(status='accepted',submitted=True,confirm=dict(side='buy',code='000981',quantity=2300,price='2.16'))
  for change in [dict(submitted=False),dict(confirm=dict(good['confirm'],code='603938')),
                 dict(confirm=dict(good['confirm'],side='sell')),dict(confirm=dict(good['confirm'],price='2.15')),
                 dict(confirm=dict(good['confirm'],quantity=2200)),dict(order_id='A',result=dict(order_id='B'))]:
   with self.subTest(change=change):
    self.store.execute("UPDATE broker_requests SET status='accepted',result=?",(json.dumps(dict(good,**change)),))
    self.assertEqual(chart(self.store,'sz000981','2026-11-03')['points'][0]['status'],'unknown')
  self.store.execute("UPDATE broker_requests SET result=?",(json.dumps(good),))
  request=json.loads(self.store.query('SELECT payload FROM broker_requests')[0]['payload'])
  for field,value in [('account_id','b'),('code','000982'),('side','sell'),('price','2.15'),('quantity',2200),('dry_run',True)]:
   with self.subTest(field=field):
    self.store.execute('UPDATE broker_requests SET payload=?',(json.dumps(dict(request,**{field:value})),))
    self.assertEqual(chart(self.store,'sz000981','2026-11-03')['points'][0]['status'],'unknown')
  self.store.execute('UPDATE broker_requests SET payload=?,created_at=?',(json.dumps(request),'2026-11-02T13:37:57+08:00'))
  self.assertEqual(chart(self.store,'sz000981','2026-11-03')['points'][0]['status'],'unknown')
  self.store.execute("UPDATE broker_requests SET created_at='2026-11-03T13:37:57+08:00'")
  self.store.execute("UPDATE trading_runs SET payload=json_set(payload,'$.mode','trial')")
  self.assertEqual(chart(self.store,'sz000981','2026-11-03')['points'][0]['status'],'unknown')
