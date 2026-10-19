import tempfile,unittest
from datetime import date,datetime
from unittest.mock import Mock,patch
from core.app import App,CN

class DailyCacheTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.a=App(self.tmp.name,False);self.a.provider=Mock()
  self.clock=patch('core.daily_cache.now_cn',return_value=datetime(2026,10,19,16,0,tzinfo=CN));self.clock.start()
 def tearDown(self):self.clock.stop();self.a.store.db.close();self.tmp.cleanup()
 def test_incremental_update_not_repeated(self):
  self.a.provider.daily.return_value=[dict(date='2026-10-19',close='1')]
  self.a.daily_cache.update('sh603002');self.a.daily_cache.update('sh603002')
  self.a.provider.daily.assert_called_once_with('sh603002','2026-10-17','2026-10-19')
 def test_before_close_does_not_refetch_completed_cache(self):
  with patch('core.daily_cache.now_cn',return_value=datetime(2026,10,19,11,0,tzinfo=CN)):
   self.a.daily_cache.update('sh603002')
  self.a.provider.daily.assert_not_called()
 def test_duplicate_range_survives_restart(self):
  self.a.provider.daily.return_value=[];lo=date(2024,1,1);hi=date(2024,1,31)
  self.a.daily_cache.fetch('sh603002',lo,hi);self.a.store.db.close()
  self.a=App(self.tmp.name,False);self.a.provider=Mock()
  self.assertEqual(self.a.daily_cache.fetch('sh603002',lo,hi),[]);self.a.provider.daily.assert_not_called()
 def test_failed_range_cools_down(self):
  self.a.provider.daily.side_effect=ValueError('offline');lo=date(2024,1,1);hi=date(2024,1,31)
  with self.assertRaises(ValueError):self.a.daily_cache.fetch('sh603002',lo,hi)
  self.a.daily_cache.fetch('sh603002',lo,hi);self.a.provider.daily.assert_called_once()
  self.assertTrue(self.a.store.getcache('sh603002','daily'))
 def test_overlap_fetches_only_missing_range(self):
  self.a.provider.daily.return_value=[]
  self.a.daily_cache.fetch('sh603002',date(2024,1,1),date(2024,1,31));self.a.daily_cache.last_request=0
  self.a.daily_cache.fetch('sh603002',date(2024,1,15),date(2024,2,10))
  self.assertEqual(self.a.provider.daily.call_args.args,('sh603002','2024-02-01','2024-02-10'))
 def test_empty_response_not_retried_on_each_poll(self):
  self.a.provider.daily.return_value=[]
  for _ in range(4):self.a.daily_cache.update('sh603002')
  self.a.provider.daily.assert_called_once()
 def test_global_daily_request_pacing(self):
  self.a.provider.daily.return_value=[]
  self.a.daily_cache.fetch('sh603002',date(2024,1,1),date(2024,1,2))
  with patch.object(self.a.stop,'wait',return_value=False) as wait:
   self.a.daily_cache.fetch('sh688680',date(2024,1,1),date(2024,1,2))
   self.assertTrue(0<wait.call_args.args[0]<=1)
 def test_shutdown_cancels_daily_request(self):
  self.a.stop.set();self.a.daily_cache.fetch('sh603002',date(2024,1,1),date(2024,1,2));self.a.provider.daily.assert_not_called()

 def test_old_intraday_daily_candle_is_finalized_after_close(self):
  self.a.store.cache('sh603002','daily','2026-10-19',dict(date='2026-10-19',close='1',cached_at='2026-10-19T10:00:00+08:00'))
  self.a.provider.daily.return_value=[dict(date='2026-10-19',close='2')]
  self.a.daily_cache.update('sh603002')
  self.a.provider.daily.assert_called_once_with('sh603002','2026-10-19','2026-10-19')
  self.assertEqual(self.a.store.getcache('sh603002','daily')[-1]['data']['close'],'2')
 def test_recent_empty_response_can_retry_next_morning(self):
  self.a.provider.daily.return_value=[];self.a.daily_cache.update('sh603002')
  self.a.store.execute('UPDATE daily_requests SET attempt=attempt-46800');self.a.daily_cache.last_request=0
  self.a.daily_cache.update('sh603002');self.assertEqual(self.a.provider.daily.call_count,2)
