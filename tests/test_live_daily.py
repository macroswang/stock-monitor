import tempfile,unittest
from unittest.mock import patch
from datetime import datetime
from core.app import App,CN

class LiveDailyTest(unittest.TestCase):
 def test_live_cache_and_final_replacement(self):
  with tempfile.TemporaryDirectory() as td:
   a=App(td,False)
   q=dict(date='2026-10-19',timestamp='2026-10-19T10:00:00+08:00',open='15',price='14',high='16',low='13',volume='12345')
   with patch('core.daily_cache.now_cn',return_value=datetime(2026,10,19,10,tzinfo=CN)):
    a.daily_cache.observe('sh603002',q)
    row=a.call('chart',dict(code='sh603002',kind='daily'))[-1]['data']
    self.assertTrue(row['provisional']);self.assertEqual(row['close'],'14');self.assertEqual(row['volume'],'12345')
    h=a.call('history',dict(code='sh603002',start='2026-10-19',end='2026-10-19'))
    self.assertEqual(h['daily'][0]['close'],'14')
    a.daily_cache.observe('sh603002',dict(q,price='15'))
    self.assertEqual(a.daily_cache.rows('sh603002')[-1]['data']['close'],'15')
    a.daily_cache.observe('sh603002',dict(q,date='2026-10-20'))
    self.assertEqual(a.daily_cache.rows('sh603002')[-1]['day'],'2026-10-19')
   a.store.cache('sh603002','daily','2026-10-19',dict(date='2026-10-19',close='15.5',cached_at='2026-10-19T15:16:00+08:00'))
   self.assertEqual(a.daily_cache.rows('sh603002')[-1]['data']['close'],'15.5')
   a.store.db.close()
