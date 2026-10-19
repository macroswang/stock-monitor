import json,tempfile,unittest
from datetime import datetime
from unittest.mock import patch
from core.app import App,ROOT
from core.provider import Tencent
from core.sources import daily_view

class HistoryMessagesTest(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.a=App(self.tmp.name,False)
 def tearDown(self):self.a.store.db.close();self.tmp.cleanup()
 def history(self,code='sh603002',day='2026-10-16'):
  return self.a.call('history',{'code':code,'start':day,'end':day})
 def event(self):
  return dict(key='2026-10-16|603002|09:31',symbol='603002',trading_date='2026-10-16',candidate_time='09:31',confirmation_label='09:33',event_label='09:33',volumes=[4384500,1461000,1957000],kind='TWO_MINUTE_CONFIRMATION',observed_at='2026-10-16T09:33:05+08:00')
 def test_all_verified_history_matches_are_read_only(self):
  total=0
  for w in self.a.call('snapshot',{})['watch']:
   h=self.history(w['code']);total+=len(h['events']);self.assertEqual(h['days'][0]['status'],'ready')
   self.assertTrue(all(e['name']!='未知名称' for e in h['events']))
  self.assertEqual(total,19)
  self.assertFalse(self.a.store.query('SELECT * FROM events'));self.assertFalse(self.a.store.query('SELECT * FROM messages'));self.assertFalse(self.a.store.query('SELECT * FROM local_delivery'))
 def test_date_range_returns_multiple_daily_candles(self):
  h=self.a.call('history',{'code':'sh603002','start':'2026-10-12','end':'2026-10-16'})
  self.assertEqual(len(h['daily']),5);self.assertEqual(len(h['days']),5)
  self.assertEqual(h['days'][0]['status'],'missing_minutes');self.assertNotEqual(h['days'][0]['status'],'ready')
 def test_unknown_historical_limit_not_reported_as_zero_signal(self):
  data=self.a.store.getcache('sh603002','minute','2026-10-16')[0]['data'];data={k:v for k,v in data.items() if k not in ('limit_up','day_high')}
  self.a.store.cache('sh603002','minute','2026-10-15',data)
  h=self.history(day='2026-10-15');self.assertEqual(h['days'][0]['status'],'missing_limit');self.assertIn('不能当作零触发',h['days'][0]['message'])
  self.a.call('history_reference',{'code':'sh603002','day':'2026-10-15','limit_up':'17.89'})
  h=self.history(day='2026-10-15');self.assertEqual(h['days'][0]['status'],'ready');self.assertEqual(len(h['events']),1)
  self.assertFalse(self.a.store.query('SELECT * FROM local_delivery'))
 def test_invalid_reference_does_not_mutate_cache(self):
  with self.assertRaises(ValueError):self.a.call('history_reference',{'code':'sh603002','day':'2026-10-16','limit_up':'1'})
  self.assertEqual(self.a.store.getcache('sh603002','minute','2026-10-16')[0]['data']['limit_up'],'17.89')
 def test_live_quote_reference_is_archived_for_matching_day_only(self):
  self.a.quotes['sh603002']={'date':'2026-10-15','limit_up':'17.5','high':'16','timestamp':'2026-10-15T15:00:00+08:00'}
  self.a.cache_minutes('sh603002',{'date':'2026-10-15','bars':[],'source':'tencent'})
  self.assertEqual(self.a.store.getcache('sh603002','minute','2026-10-15')[0]['data']['limit_up'],'17.5')
  self.a.cache_minutes('sh603002',{'date':'2026-10-14','bars':[],'source':'tencent'})
  self.assertNotIn('limit_up',self.a.store.getcache('sh603002','minute','2026-10-14')[0]['data'])
 def test_daily_volume_normalization_is_not_applied_twice(self):
  normal=daily_view('sh603002',{'volume':'752568','source':'tencent'})
  star=daily_view('sh688680',{'volume':'1377592','source':'tencent'})
  self.assertEqual(float(normal['volume']),75256800);self.assertEqual(float(star['volume']),1377592)
  self.assertEqual(daily_view('sh603002',normal)['volume'],normal['volume'])
 def test_daily_adapter_ordinary_and_star_units(self):
  for code,factor in [('sh603002',100),('sh688680',1)]:
   raw=(ROOT/'fixtures'/f'{code}-daily.json').read_text()
   with patch('core.provider.get',return_value=raw):rows=Tencent().daily(code,'2026-10-16','2026-10-16')
   original=next(r for r in json.loads(raw)['data'][code]['day'] if r[0]=='2026-10-16')
   self.assertEqual(float(rows[0]['volume']),float(original[5])*factor);self.assertEqual(rows[0]['volume_unit'],'shares')
 def test_name_and_notification_body_survive_removal_and_restart(self):
  e=self.event();self.a.store.event(e,'live');self.a.call('remove',{'code':'sh603002'})
  second=App(self.tmp.name,False)
  row=second.call('messages',{})['items'][0]
  self.assertIn('宏昌电子',row['title']);self.assertIn('438.45',row['body']);self.assertIn('万股',row['body'])
  self.assertEqual(second.event_rows()[0]['name'],'宏昌电子');second.store.db.close()
 def test_messages_deduplicate_and_read_state_persists(self):
  self.a.store.event(self.event(),'live');self.a.store.event(self.event(),'live')
  m=self.a.call('messages',{});self.assertEqual(m['total'],1)
  self.a.call('message_read',{'id':m['items'][0]['id']});self.assertEqual(self.a.call('messages',{'unread':True})['total'],0)
  other=App(self.tmp.name,False);self.assertEqual(other.call('messages',{})['total'],1);self.assertEqual(other.call('snapshot',{})['unread_messages'],0);other.store.db.close()
 def test_message_status_tracks_same_delivery_without_extra_push(self):
  e=self.event();self.a.store.event(e,'live');self.a.call('local_claim',{'key':e['key']});self.a.call('local_finish',{'key':e['key'],'status':'accepted','detail':'test'})
  row=self.a.call('messages',{})['items'][0];self.assertEqual(row['local_delivery'],'accepted')
  self.a.call('messages',{});self.assertEqual(self.a.store.query('SELECT attempts FROM local_delivery')[0]['attempts'],1)
 def test_push_test_failure_is_retained_without_secret(self):
  with patch('core.notify.bark',side_effect=ValueError('no key')):
   with self.assertRaises(ValueError):self.a.call('test_push',{})
  m=self.a.call('messages',{})['items'][0];self.assertEqual(m['payload']['status'],'failed');self.assertEqual(m['category'],'push_test');self.assertNotIn('no key',json.dumps(m))
 def test_historical_records_query_has_name_source_and_range(self):
  self.a.call('replay',{'code':'sh603002','day':'2026-10-16'})
  r=self.a.call('events',{'start':'2026-10-16','end':'2026-10-16'})
  self.assertEqual(r['total'],1);self.assertEqual(r['items'][0]['name'],'宏昌电子');self.assertEqual(r['items'][0]['source_name'],'腾讯行情')
  self.assertEqual(self.a.call('events',{'start':'2026-10-15','end':'2026-10-15'})['total'],0)
 def test_source_metadata_and_unavailable_switch(self):
  s=self.a.call('sources',{'code':'sh603002'});self.assertIn('sh603002',s['minute_url']);self.assertEqual(s['selected'],'tencent')
  with self.assertRaises(ValueError):self.a.call('config',{'provider':'sina'})
  self.assertEqual(self.a.call('sources',{'code':'sh603002'})['selected'],'tencent')
 def test_bad_range_rejected_before_download(self):
  with self.assertRaises(ValueError):self.a.call('history',{'code':'sh603002','start':'2026-10-18','end':'2026-10-01'})

class MigrationHistoryTest(unittest.TestCase):
 def test_old_delivered_notification_backfills_message_without_requeue(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as directory:
   from pathlib import Path
   db=sqlite3.connect(Path(directory)/'monitor.sqlite3')
   db.executescript('''CREATE TABLE watch(code TEXT PRIMARY KEY,name TEXT,enabled INTEGER DEFAULT 1);
   CREATE TABLE events(key TEXT PRIMARY KEY,payload TEXT,mode TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE local_delivery(key TEXT PRIMARY KEY,status TEXT,attempts INTEGER DEFAULT 0,next_try REAL DEFAULT 0,detail TEXT);
   CREATE TABLE config(key TEXT PRIMARY KEY,value TEXT);''')
   db.execute('INSERT INTO watch VALUES(?,?,?)',('sh603002','宏昌电子',1))
   e=dict(key='old-test',symbol='603002',candidate_time='09:31',event_label='09:33',trading_date='2026-10-16',volumes=[10000,8000,7000],kind='TWO_MINUTE_CONFIRMATION')
   db.execute('INSERT INTO events(key,payload,mode) VALUES(?,?,?)',(e['key'],json.dumps(e),'live'))
   db.execute('INSERT INTO local_delivery VALUES(?,?,?,?,?)',(e['key'],'accepted',1,0,'old'))
   db.execute('INSERT INTO config VALUES(?,?)',('initialized','true'));db.commit();db.close()
   a=App(directory,False);self.assertEqual(a.call('messages',{})['total'],1);self.assertEqual(a.call('messages',{})['items'][0]['local_delivery'],'accepted')
   self.assertFalse(a.call('local_pending',{})['events']);a.store.db.close()
   b=App(directory,False);self.assertEqual(b.call('messages',{})['total'],1);self.assertEqual(b.store.query('SELECT attempts FROM local_delivery')[0]['attempts'],1);b.store.db.close()
