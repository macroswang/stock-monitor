import tempfile,unittest
from unittest.mock import Mock
from core.app import App

class MinuteCacheTest(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.a=App(self.tmp.name,False);self.a.provider=Mock()
 def tearDown(self):self.a.store.db.close();self.tmp.cleanup()
 def test_cached_day_never_downloads(self):
  self.assertEqual(self.a.minute_cache.ensure('sh603002','2026-10-16')['status'],'cached');self.a.provider.minutes.assert_not_called()
 def test_old_unavailable_day_does_not_hammer_endpoint(self):
  self.a.minute_cache.note('sh603002')
  r=self.a.minute_cache.ensure('sh603002','2020-01-02');self.assertEqual(r['status'],'outside_coverage');self.a.provider.minutes.assert_not_called()
 def test_recent_missing_day_is_downloaded_and_cached(self):
  self.a.provider.minutes.return_value=[dict(date='2026-10-15',bars=[dict(time='09:31',close='1',volume=100,complete=True)])]
  self.assertEqual(self.a.minute_cache.ensure('sh603002','2026-10-15')['status'],'downloaded')
  self.a.minute_cache.ensure('sh603002','2026-10-15');self.a.provider.minutes.assert_called_once()
  self.assertFalse(self.a.store.query('SELECT * FROM messages'))
 def test_missing_response_is_not_fetched_repeatedly(self):
  self.a.provider.minutes.return_value=[]
  self.a.minute_cache.ensure('sh603002','2026-10-15');self.a.minute_cache.ensure('sh603002','2026-10-14');self.a.provider.minutes.assert_called_once()
 def test_failure_keeps_cache_and_cools_down(self):
  self.a.provider.minutes.side_effect=ValueError('offline')
  with self.assertRaises(ValueError):self.a.minute_cache.ensure('sh603002','2026-10-15')
  self.assertEqual(self.a.minute_cache.ensure('sh603002','2026-10-15')['status'],'retry_later')
  self.assertTrue(self.a.store.getcache('sh603002','minute','2026-10-16'))
 def test_cooldown_survives_restart(self):
  self.a.provider.minutes.return_value=[];self.a.minute_cache.ensure('sh603002','2026-10-15');self.a.store.db.close()
  self.a=App(self.tmp.name,False);self.a.provider=Mock();self.a.minute_cache.ensure('sh603002','2026-10-15');self.a.provider.minutes.assert_not_called()
