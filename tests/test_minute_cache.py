import tempfile,unittest
from unittest.mock import Mock,patch
from datetime import datetime
from core.provider import CN
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
 def test_live_refresh_updates_cached_non_watch_stock_and_throttles_without_trading(self):
  code='sz300058';day='2026-11-12'
  self.a.store.cache(code,'minute',day,dict(date=day,bars=[dict(time='11:30',close='15.20',volume=100,complete=True)]))
  self.a.provider.minutes.return_value=[dict(date='2026-11-11',bars=[dict(time='15:00',close='13.00',volume=100,complete=True)]),dict(date=day,bars=[dict(time='13:01',close='14.56',volume=200,complete=True)])]
  with patch('core.minute_cache.now_cn',return_value=datetime(2026,11,12,14,0,tzinfo=CN)),patch('core.minute_cache.time.time',return_value=1000):
   self.a.minute_cache.ensure(code,day,refresh=True);self.a.minute_cache.ensure(code,day,refresh=True)
  self.a.provider.minutes.assert_called_once_with(code)
  self.assertEqual(self.a.store.getcache(code,'minute',day)[0]['data']['bars'][-1]['time'],'13:01')
  self.assertFalse(self.a.store.getcache(code,'minute','2026-11-11'))
  self.assertFalse(self.a.store.query('SELECT 1 FROM watch WHERE code=?',(code,)))
  self.assertFalse(self.a.store.query('SELECT 1 FROM events'))
  self.assertFalse(self.a.store.query('SELECT 1 FROM broker_requests'))
 def test_live_refresh_failure_preserves_cache_and_retries_after_cooldown(self):
  code='sz300058';day='2026-11-12';original=dict(date=day,bars=[dict(time='11:30',close='15.20',volume=100,complete=True)])
  self.a.store.cache(code,'minute',day,original)
  self.a.provider.minutes.side_effect=ValueError('offline')
  with patch('core.minute_cache.now_cn',return_value=datetime(2026,11,12,14,0,tzinfo=CN)),patch('core.minute_cache.time.time',return_value=1000):
   for _ in range(2):
    with self.assertRaises(ValueError):self.a.minute_cache.ensure(code,day,refresh=True)
  self.a.provider.minutes.assert_called_once()
  self.assertEqual(self.a.store.getcache(code,'minute',day)[0]['data']['bars'],original['bars'])
  self.a.provider.minutes.side_effect=None;self.a.provider.minutes.return_value=[dict(date=day,bars=[dict(time='13:02',close='14.56',volume=200,complete=True)])]
  with patch('core.minute_cache.now_cn',return_value=datetime(2026,11,12,14,0,tzinfo=CN)),patch('core.minute_cache.time.time',return_value=1031):
   self.a.minute_cache.ensure(code,day,refresh=True)
  self.assertEqual(self.a.store.getcache(code,'minute',day)[0]['data']['bars'][-1]['time'],'13:02')
 def test_live_refresh_pauses_outside_verified_sessions(self):
  for stamp in ('2026-11-12T09:19:59','2026-11-12T11:30:00','2026-11-12T12:59:59','2026-11-12T15:00:00','2026-11-14T10:00:00','2026-10-01T10:00:00'):
   now=datetime.fromisoformat(stamp).replace(tzinfo=CN)
   with self.subTest(stamp=stamp),patch('core.minute_cache.now_cn',return_value=now):
    self.assertEqual(self.a.minute_cache.ensure('sz300058',now.date().isoformat(),refresh=True)['status'],'paused')
  self.a.provider.minutes.assert_not_called()
  self.assertFalse(self.a.store.query("SELECT 1 FROM minute_requests WHERE code='sz300058'"))
  self.a.provider.minutes.return_value=[dict(date='2026-11-12',bars=[dict(time='09:20',close='14',volume=100,complete=True)])]
  with patch('core.minute_cache.now_cn',return_value=datetime(2026,11,12,9,20,tzinfo=CN)):
   self.assertEqual(self.a.minute_cache.ensure('sz300058','2026-11-12',refresh=True)['status'],'downloaded')
  self.a.provider.minutes.assert_called_once_with('sz300058')

 def test_after_close_refresh_completes_partial_same_day_cache(self):
  code='sh600103';day='2026-11-12'
  self.a.store.cache(code,'minute',day,dict(date=day,bars=[dict(time='11:30',close='3.61',volume=100,complete=True)]))
  self.a.provider.minutes.return_value=[dict(date=day,bars=[dict(time='11:30',close='3.61',volume=100,complete=True),dict(time='15:00',close='3.60',volume=200,complete=True)])]
  with patch('core.minute_cache.now_cn',return_value=datetime(2026,11,12,16,15,tzinfo=CN)),patch('core.minute_cache.time.time',return_value=2000):
   result=self.a.minute_cache.ensure(code,day,refresh=True)
  self.assertEqual(result['status'],'downloaded')
  self.assertEqual(self.a.store.getcache(code,'minute',day)[0]['data']['bars'][-1]['time'],'15:00')
  self.a.provider.minutes.assert_called_once_with(code)
 def test_after_close_complete_cache_returns_without_network(self):
  code='sh600103';day='2026-11-12'
  self.a.store.cache(code,'minute',day,dict(date=day,bars=[dict(time='09:31',close='3.6',volume=1,complete=True),dict(time='15:00',close='3.6',volume=1,complete=True)]))
  with patch('core.minute_cache.now_cn',return_value=datetime(2026,11,12,16,15,tzinfo=CN)),patch('core.minute_cache.time.time',return_value=2000):
   result=self.a.minute_cache.ensure(code,day,refresh=True)
  self.assertEqual(result['status'],'cached')
  self.a.provider.minutes.assert_not_called()
