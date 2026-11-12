import tempfile,unittest
from unittest.mock import Mock
from core.app import App


class WatchQuoteCacheTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=App(self.tmp.name,False)
 def tearDown(self):
  self.app.store.db.close();self.tmp.cleanup()
 def displayed(self):
  return next(w['quote'] for w in self.app.call('snapshot',{})['watch'] if w['code']=='sh603002')
 def test_quote_survives_minute_failure_restart_and_offline_fetch(self):
  quote=dict(code='sh603002',name='宏昌电子',date='2026-11-12',timestamp='2026-11-12T15:00:00+08:00',
             price='10.50',previous_close='10',open='10',high='10.80',low='9.80',volume='100',limit_up='11')
  self.app.provider=Mock();self.app.provider.quote.return_value=quote;self.app.provider.minutes.side_effect=OSError('offline')
  self.app.poll_one('sh603002')
  self.assertEqual(self.displayed()['price'],'10.50')
  self.assertIn('分时获取失败',self.app.health['sh603002'])
  self.app.store.db.close();self.app=App(self.tmp.name,False)
  self.assertFalse(self.app.quotes)  # Cached display cannot become live trading input.
  self.assertTrue(self.displayed()['cached'])
  self.app.provider=Mock();self.app.provider.quote.side_effect=OSError('offline')
  self.app.poll_one('sh603002')
  self.assertEqual({k:self.displayed()[k] for k in quote},quote)
  self.app.provider.minutes.assert_not_called()
  self.assertFalse(self.app.store.query('SELECT 1 FROM events'))
  self.assertFalse(self.app.store.query('SELECT 1 FROM broker_requests'))
 def test_legacy_candle_and_minute_metadata_restore_basic_fields_without_network(self):
  self.app.store.cache('sh603002','daily_live','2026-11-12',dict(close='10.50',open='10',high='10.80',low='9.80',volume='100',quote_time='2026-11-12T15:00:00+08:00'))
  self.app.store.cache('sh603002','minute','2026-11-12',dict(previous_close='10',bars=[]))
  self.app.store.db.close();self.app=App(self.tmp.name,False);self.app.provider=Mock()
  q=self.displayed()
  self.assertEqual([q[k] for k in ('price','previous_close','high','low')],['10.50','10','10.80','9.80'])
  self.assertEqual(float(q['change']),5)
  self.assertFalse(self.app.quotes);self.app.provider.quote.assert_not_called()
