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
