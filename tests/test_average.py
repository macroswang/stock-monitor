import json,unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from core.provider import Tencent,CN
from core.app import ROOT

class AverageTest(unittest.TestCase):
 def test_saved_cash_divided_by_share_volume_matches_average(self):
  base=ROOT.parent.parent/'ths_numeric_validation/ui_expanded/raw'
  if not base.exists():self.skipTest('External raw oracle unavailable')
  for code in ('sh603002','sh688680'):
   raw=(base/(code+'-tencent.json')).read_text()
   with patch('core.provider.get',return_value=raw):groups=Tencent().minutes(code,datetime(2026,10,18,tzinfo=CN))
   source=json.loads(raw)['data'][code]['data']
   for g,day in zip(groups,source):
    for b,line in zip(g['bars'],day['data']):
     t,close,volume,cash,*_=line.split()
     if Decimal(volume)>0:self.assertEqual(Decimal(b['average']),Decimal(cash)/(Decimal(volume)*g['multiplier']))
 def test_zero_volume_and_invalid_cash_do_not_invent_average(self):
  rows=['0930 10 0 0','0931 10 100 100000','0932 10 200 NaN','0933 10 300 300000']
  raw=json.dumps({'data':{'sh603002':{'data':[{'date':'20261016','data':rows}]}}})
  with patch('core.provider.get',return_value=raw):g=Tencent().minutes('sh603002')[0]
  self.assertIsNone(g['bars'][0]['average']);self.assertIsNone(g['bars'][2]['average'])
  self.assertEqual(Decimal(g['bars'][1]['average']),Decimal(10));self.assertEqual(Decimal(g['bars'][3]['average']),Decimal(10))
 def test_twelve_observed_ths_average_points(self):
  base=ROOT.parent.parent/'ths_numeric_validation/ui_expanded/raw'
  if not base.exists():self.skipTest('External raw oracle unavailable')
  ledger=json.loads((ROOT/'docs/0.3.2/average-ledger.json').read_text())
  for code in sorted({r['code'] for r in ledger}):
   with patch('core.provider.get',return_value=(base/(code+'-tencent.json')).read_text()):groups=Tencent().minutes(code,datetime(2026,10,18,tzinfo=CN))
   bars={b['time']:b for g in groups if g['date']=='2026-10-16' for b in g['bars']}
   for row in ledger:
    if row['code']==code:self.assertEqual(round(float(bars[row['time']]['average']),2),row['ths_display'])
