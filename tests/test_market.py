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
