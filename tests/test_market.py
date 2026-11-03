import json,tempfile,unittest
from unittest.mock import patch
from core.market import quotes,minutes,Market
from core.app import App

class MarketTest(unittest.TestCase):
 def test_index_quotes_do_not_need_stock_limit_up(self):
  f=['']*49
  for i,v in {1:'上证指数',2:'000001',3:'3718.61',4:'3716.28',30:'20261019131518',31:'2.33',32:'0.06'}.items():f[i]=v
  with patch('core.market.get',return_value='v_sh000001="'+'~'.join(f)+'";'):
   q=quotes()[0];self.assertEqual(q['code'],'sh000001');self.assertEqual(q['percent'],'0.06')
 def test_history_preserves_actual_date_and_previous_close(self):
  raw={'data':{'sh000001':{'data':[dict(date='20261016',prec='3700',data=['0930 3702 0 0','0931 3703 10 100'])]}}}
  with patch('core.market.get',return_value=json.dumps(raw)):g=minutes()[0]
  self.assertEqual(g['date'],'2026-10-16');self.assertEqual(g['previous_close'],'3700');self.assertEqual(g['bars'][1]['time'],'09:31')
 def test_cache_is_date_specific_and_failure_retains_last_quote(self):
  with tempfile.TemporaryDirectory() as td:
   app=App(td,False);q=dict(code='sh000001',timestamp='2026-10-19T13:15:18+08:00',price='3718')
   group=dict(date='2026-10-16',previous_close='3700',bars=[])
   with patch('core.market.quotes',return_value=[q]),patch('core.market.minutes',return_value=[group]):app.market.poll()
   self.assertIsNone(app.call('market',{'day':'2026-10-19'})['minute'])
   self.assertEqual(app.call('market',{'day':'2026-10-16'})['minute']['date'],'2026-10-16')
   with patch('core.market.quotes',side_effect=ValueError()),patch('core.market.minutes',side_effect=ValueError()):app.market.poll()
   self.assertEqual(app.market.view('2026-10-16')['quotes'][0]['price'],'3718');app.store.db.close()
 def parse_volume(self,lines,code='sh000001'):
  raw={'data':{code:{'data':[dict(date='20261103',prec='3600',data=lines)]}}}
  with patch('core.market.get',return_value=json.dumps(raw)):return minutes(code)[0]['bars']
 def test_actual_index_cumulative_lots_are_differenced_not_divided_by_100(self):
  for code in ('sh000001','sz399001','sz399006'):
   bars=self.parse_volume(['0930 3624.58 5974886 7682593279','0931 3613.59 23900726 31219088720','0932 3615.05 35289757 45381510324'],code)
   self.assertEqual([b['volume_lots'] for b in bars],[5974886,17925840,11389031])
   self.assertFalse(any('_cumulative_lots' in b for b in bars))
 def test_missing_minutes_and_bad_values_never_create_spikes_or_fake_zeros(self):
  bars=self.parse_volume(['0931 3600 100','0932 3601 140','0934 3601 200','0935 3602 230','0936 3603 NaN','0937 3604 280','0938 3604 300'])
  self.assertEqual([b.get('volume_lots') for b in bars],[None,40,None,30,None,None,20])
  for value in ('-1','1.5','Infinity','9007199254740992'):
   self.assertNotIn('volume_lots',self.parse_volume(['0930 3600 '+value])[0])
  self.assertEqual(self.parse_volume(['0930 3600 0','0931 3600 0'])[1]['volume_lots'],0)
  self.assertNotIn('volume_lots',self.parse_volume(['0930 3600'])[0])
 def test_lunch_snapshot_is_not_a_second_volume_bar_and_regressions_are_isolated_by_day(self):
  bars=self.parse_volume(['1129 3600 100','1130 3601 140','1300 3602 150','1301 3602 190'])
  self.assertEqual([b.get('volume_lots') for b in bars],[None,40,None,50])
  bars=self.parse_volume(['0930 3600 100','0931 3601 90','0932 3602 130','0933 3603 150'])
  self.assertEqual([b.get('volume_lots') for b in bars],[100,None,None,None])
  self.assertEqual(self.parse_volume(['0930 3600 10','0931 3601 30'])[1]['volume_lots'],20)
  bars=self.parse_volume(['0930 3600 100','0931 3601 NaN','0932 3602 80','0933 3603 90'])
  self.assertEqual([b.get('volume_lots') for b in bars],[100,None,None,None])

class MacdIndexFeedTests(unittest.TestCase):
 def test_all_three_feeds_are_shared_and_failure_is_isolated(self):
  from collections import Counter
  from core.market import CODES
  with tempfile.TemporaryDirectory() as td:
   app=App(td,False)
   def feed(code):
    if code=='sz399006':raise ValueError('unavailable')
    return [dict(date='2026-11-02',previous_close='100',bars=[dict(time='09:31',close='101')])]
   with patch('core.market.quotes',return_value=[]),patch('core.market.minutes',side_effect=feed) as fetch:
    app.market.poll()
   self.assertEqual(Counter(c.args[0] for c in fetch.call_args_list),Counter(CODES))
   sh=app.call('index_minute',dict(code='sh000001',day='2026-11-02'))
   sz=app.call('index_minute',dict(code='sz399001',day='2026-11-02'))
   self.assertEqual(sh['minute']['code'],'sh000001');self.assertEqual(sz['minute']['code'],'sz399001')
   self.assertEqual(sz['minute']['name'],'深证成指');self.assertFalse(sz['error'])
   self.assertIsNone(app.call('index_minute',dict(code='sz399006',day='2026-11-02'))['minute'])
   self.assertIsNone(app.call('index_minute',dict(code='sz399001',day='2026-10-30'))['minute'])
   app.store.db.close()
 def test_historical_date_does_not_depend_on_current_quote_or_fall_back_to_another_index(self):
  with tempfile.TemporaryDirectory() as td:
   app=App(td,False)
   app.store.cache('sz399001','market_minute','2026-10-16',dict(date='2026-10-16',previous_close='100',bars=[]))
   with patch('core.market.minutes') as fetch:
    result=app.call('index_minute',dict(code='sz399001',day='2026-10-16'));fetch.assert_not_called()
   self.assertEqual(result['minute']['date'],'2026-10-16');self.assertEqual(result['minute']['code'],'sz399001')
   self.assertIsNone(app.call('index_minute',dict(code='sh000001',day='2026-10-16'))['minute'])
   with self.assertRaises(ValueError):app.call('index_minute',dict(code='not-an-index',day='2026-10-16'))
   app.store.db.close()
