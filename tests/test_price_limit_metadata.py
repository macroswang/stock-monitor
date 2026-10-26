import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from core.provider import Tencent
from core.app import App

class PriceLimitMetadataTests(unittest.TestCase):
 def test_quote_retains_market_supplied_upper_and_lower_prices(self):
  f=['0']*49
  for k,v in {1:'万向钱潮',2:'000559',3:'12.71',4:'11.55',5:'11.90',6:'100',30:'20261026111324',32:'10.04',33:'12.71',34:'11.90',47:'12.71',48:'10.40'}.items():f[k]=v
  with patch('core.provider.get',return_value='v_sz000559="'+'~'.join(f)+'";'):
   q=Tencent().quote('sz000559')
  self.assertEqual(q['limit_up'],'12.71');self.assertEqual(q['limit_down'],'10.40')
 def test_limits_follow_only_matching_day_quote_and_survive_minute_refresh(self):
  with tempfile.TemporaryDirectory() as tmp:
   app=App(Path(tmp),False)
   try:
    code='sz000559';day='2026-10-26';app.quotes[code]=dict(date=day,timestamp=day+'T11:13:24+08:00',limit_up='12.71',limit_down='10.40',previous_close='11.55')
    group=dict(date=day,source='tencent',bars=[]);app.cache_minutes(code,group);row=app.store.getcache(code,'minute',day)[0]['data'];self.assertEqual(row['limit_down'],'10.40')
    app.quotes[code]['date']='2026-10-27';app.quotes[code]['limit_down']='11';app.cache_minutes(code,group);row=app.store.getcache(code,'minute',day)[0]['data'];self.assertEqual(row['limit_down'],'10.40')
   finally:app.stop.set();app.store.db.close()
