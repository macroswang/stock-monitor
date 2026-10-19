import json,tempfile,unittest,time
from datetime import datetime
from unittest.mock import Mock,patch
from core.app import App,ROOT,CN
from core.archive import SinaHistory,quality
from core.validated_engine import MINUTES

BASE=ROOT.parent.parent/'ths_numeric_validation/ui_expanded/raw'
class SinaTest(unittest.TestCase):
 def test_saved_twelve_sources_have_valid_units_and_partial_prefix(self):
  if not BASE.exists():self.skipTest('External oracle unavailable')
  for path in sorted(BASE.glob('*-sina.json')):
   code=path.name.split('-')[0]
   with patch('core.archive.get',return_value='=('+path.read_text()+');'):
    groups=SinaHistory().minutes(code)
   self.assertTrue(groups);self.assertEqual(groups[0]['source'],'sina');self.assertFalse(groups[0]['rule_compatible'])
   if groups[0]['bars'][0]['time']!='09:31':self.assertTrue(all(b['average'] is None for b in groups[0]['bars']))
   last=groups[-1];self.assertEqual(quality(last),227 if code=='sh688680' else len(MINUTES))
   if quality(last)==len(MINUTES):self.assertTrue(last['bars'][-1]['average'])
   else:self.assertIsNone(last['bars'][-1]['average'])
 def test_invalid_units_and_duplicates_are_rejected(self):
  row=dict(day='2026-10-16 09:31:00',open='10',high='10',low='10',close='10',volume='100',amount='100000')
  for rows in ([row],[dict(row,amount='1000')]*2):
   with patch('core.archive.get',return_value=json.dumps(rows)),self.assertRaises(ValueError):SinaHistory().minutes('sh603002')
 def test_null_response_is_failure_not_success(self):
  with patch('core.archive.get',return_value='=(null);'),self.assertRaises(ValueError):SinaHistory().minutes('sh603002')

class ArchiveTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.a=App(self.tmp.name,False);self.a.provider=Mock();self.a.provider.minutes.return_value=[];self.a.archive.provider=Mock();self.a.archive.provider.minutes.return_value=[]
  self.clock=patch('core.archive.now_cn',return_value=datetime(2026,10,18,17,0,tzinfo=CN));self.clock.start()
 def tearDown(self):self.clock.stop();self.a.store.db.close();self.tmp.cleanup()
 def sample(self,day):return dict(date=day,source='sina',rule_compatible=False,bars=[dict(time=t,close='10',volume=100,complete=True) for t in MINUTES+['14:57','15:00']])
 def test_twenty_observed_trading_dates_and_no_deletion(self):
  r=self.a.archive.status('sh603002');self.assertEqual(len(r['items']),20);self.assertEqual(r['items'][-1]['date'],'2026-10-16');self.assertEqual(r['complete'],1)
  old=self.a.store.getcache('sh603002','daily');self.a.archive.update('sh603002');self.assertEqual(old,self.a.store.getcache('sh603002','daily'))
 def test_whole_day_backfill_preserves_tencent_and_no_notifications(self):
  old=self.a.store.getcache('sh603002','minute','2026-10-16')
  self.a.archive.provider.minutes.return_value=[self.sample('2026-10-09'),self.sample('2026-10-16')]
  self.a.archive.update('sh603002')
  self.assertEqual(old,self.a.store.getcache('sh603002','minute','2026-10-16'))
  self.assertEqual(self.a.store.getcache('sh603002','minute','2026-10-09')[0]['data']['source'],'sina')
  self.assertFalse(self.a.store.query('SELECT * FROM events'));self.assertFalse(self.a.store.query('SELECT * FROM messages'))
 def test_unverified_sina_never_claims_rule_matches(self):
  self.a.store.cache('sh603002','minute','2026-10-09',dict(self.sample('2026-10-09'),limit_up='20'))
  h=self.a.call('history',dict(code='sh603002',start='2026-10-09',end='2026-10-09'));self.assertEqual(h['days'][0]['status'],'source_unverified');self.assertEqual(h['events'],[])
  with self.assertRaises(ValueError):self.a.call('replay',dict(code='sh603002',day='2026-10-09'))
 def test_successful_and_failed_fetches_are_persistent_and_paced(self):
  self.a.archive.update('sh603002');self.a.archive.update('sh603002');self.assertEqual(self.a.archive.provider.minutes.call_count,1)
  self.a.store.db.close();self.a=App(self.tmp.name,False);self.a.archive.provider=Mock();self.a.provider=Mock();self.a.archive.update('sh603002');self.a.archive.provider.minutes.assert_not_called()
 def test_sina_failure_is_visible_and_not_retried_immediately(self):
  self.a.archive.provider.minutes.side_effect=ValueError('offline');self.a.archive.update('sh603002');self.a.archive.update('sh603002');self.assertEqual(self.a.archive.provider.minutes.call_count,1)
  self.assertTrue(next(r for r in self.a.archive.status('sh603002')['requests'] if r['source']=='sina')['error'])
 def test_trading_hours_no_archive_network(self):
  with patch('core.archive.now_cn',return_value=datetime(2026,10,19,10,0,tzinfo=CN)):self.a.archive.update('sh603002')
  self.a.provider.minutes.assert_not_called();self.a.archive.provider.minutes.assert_not_called()
 def test_partial_old_sina_is_not_downgraded(self):
  whole=self.sample('2026-10-09');self.a.store.cache('sh603002','minute','2026-10-09',whole)
  self.a.archive.provider.minutes.return_value=[dict(whole,bars=whole['bars'][20:])];self.a.archive.update('sh603002')
  self.assertEqual(quality(self.a.store.getcache('sh603002','minute','2026-10-09')[0]['data']),len(MINUTES))

 def test_new_close_bypasses_old_success_window(self):
  fn=Mock(return_value=[])
  morning=datetime(2026,10,19,7,0,tzinfo=CN)
  with patch('core.daily_cache.now_cn',return_value=morning),patch('core.archive.time.time',return_value=morning.timestamp()):self.a.archive.fetch('sh603002','sina',fn)
  self.a.archive.last_request=0
  close=datetime(2026,10,19,16,0,tzinfo=CN)
  with patch('core.daily_cache.now_cn',return_value=close),patch('core.archive.time.time',return_value=close.timestamp()):self.a.archive.fetch('sh603002','sina',fn)
  self.assertEqual(fn.call_count,2)
