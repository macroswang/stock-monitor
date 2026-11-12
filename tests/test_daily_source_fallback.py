import json,unittest
from unittest.mock import patch
from core.provider import Tencent

PAYLOAD=lambda code: json.dumps({'data':{code:{'day':[['2026-11-11','7.0','7.1','7.2','6.9','1000']]}}},ensure_ascii=False)

class DailySourceFallbackTest(unittest.TestCase):
 def test_primary_kline_path_is_used_without_old_endpoint(self):
  calls=[]
  def fake_get(url):
   calls.append(url)
   if 'fqkline' in url: raise ValueError('HTTP Error 501')
   return PAYLOAD('sh601398')
  with patch('core.provider.get',side_effect=fake_get):
   rows=Tencent().daily('sh601398','2026-11-01','2026-11-12')
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['date'],'2026-11-11')
  self.assertIn('kline/kline',calls[0])
  self.assertFalse(any('fqkline' in url for url in calls))
 def test_old_endpoint_is_fallback_when_kline_fails(self):
  calls=[]
  def fake_get(url):
   calls.append(url)
   if 'kline/kline' in url: raise ValueError('HTTP Error 501')
   return PAYLOAD('sh601398')
  with patch('core.provider.get',side_effect=fake_get):
   rows=Tencent().daily('sh601398','2026-11-01','2026-11-12')
  self.assertEqual(len(rows),1)
  self.assertIn('fqkline',calls[1])
 def test_both_paths_fail_raises_value_error(self):
  with patch('core.provider.get',side_effect=ValueError('HTTP Error 501')):
   with self.assertRaises(ValueError):Tencent().daily('sh601398','2026-11-01','2026-11-12')

class IndexTechnicalFallbackTest(unittest.TestCase):
 def test_index_daily_uses_kline_path(self):
  calls=[]
  row=['2026-11-12','3600','3650','3660','3590','1000']
  def fake_get(url):
   calls.append(url)
   if 'fqkline' in url: raise ValueError('HTTP Error 501')
   return json.dumps({'data':{'sh000001':{'day':[row]}}})
  with patch('core.index_technical.get',side_effect=fake_get):
   from core.index_technical import fetch_daily
   rows=fetch_daily('2026-11-12','2026-11-12')
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['date'],'2026-11-12')
  self.assertIn('kline/kline',calls[0])
