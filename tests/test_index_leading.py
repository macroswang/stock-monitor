import copy,json,tempfile,unittest
from datetime import datetime
from unittest.mock import patch
from core.index_leading import parse_leading
from core.provider import CN
from core.app import App

class IndexLeadingTest(unittest.TestCase):
 def payload(self):
  return dict(rc=0,data=dict(code='000001',market=1,preClose=3577.62,
   time=int(datetime(2026,11,20,9,31,20,tzinfo=CN).timestamp()),trends=[
    '2026-11-20 09:30,3527.30,3527.30,3527.30,3527.30,4450518,5774669056.00,3514.749',
    '2026-11-20 09:31,3526.84,3532.08,3534.15,3526.84,17051548,23971933952.00,3493.792',
    '2026-11-20 09:32,3531.81,3530.11,3532.22,3529.98,9887287,13521319168.00,3497.497']))
 def test_real_endpoint_columns_pending_minute_and_invalid_values(self):
  now=datetime(2026,11,20,9,31,30,tzinfo=CN);raw=self.payload()
  result=parse_leading(raw,'sh000001',now)
  self.assertEqual(result['bars'],[dict(time='09:30',close='3527.30',value='3514.749'),dict(time='09:31',close='3532.08',value='3493.792')])
  self.assertEqual(result['previous_close'],'3577.62')
  for invalid in ('NaN','Infinity','-1','0','-'):
   raw=self.payload();raw['data']['trends'][1]=raw['data']['trends'][1].rsplit(',',1)[0]+','+invalid
   self.assertEqual(len(parse_leading(raw,'sh000001',now)['bars']),1)
 def test_conflicting_identity_session_order_and_future_stamp_are_rejected(self):
  now=datetime(2026,11,20,9,31,30,tzinfo=CN)
  for change in ('code','market','date','order','future','base'):
   raw=copy.deepcopy(self.payload());data=raw['data']
   if change=='code':data['code']='399001'
   elif change=='market':data['market']=0
   elif change=='date':data['trends'][0]=data['trends'][0].replace('11-20','11-19')
   elif change=='order':data['trends'].reverse()
   elif change=='future':data['time']+=60
   else:data['preClose']=0
   with self.subTest(change=change),self.assertRaises(ValueError):parse_leading(raw,'sh000001',now)
 def test_shared_cache_separate_from_stock_data_and_failed_yellow_feed_keeps_blue(self):
  with tempfile.TemporaryDirectory() as td:
   app=App(td,False)
   try:
    def primary(code):return [dict(code=code,date='2026-11-20',previous_close='100',source='tencent',bars=[dict(time='09:31',close='101')])]
    def leading(code):return dict(code=code,date='2026-11-20',previous_close='100',source='eastmoney',bars=[dict(time='09:31',close='101',value='99')])
    with patch('core.market.quotes',return_value=[]),patch('core.market.minutes',side_effect=primary),patch('core.market.leading_minutes',side_effect=leading) as fetch:
     app.market.poll();self.assertEqual(fetch.call_count,3)
    with patch('core.market.get') as network:
     for code in ('sh000001','sz399001','sz399006'):
      with patch.object(app.store,'getcache',wraps=app.store.getcache) as reads:
       stock=app.call('index_minute',dict(code=code,day='2026-11-20'))
       self.assertNotIn('leading',stock)
       self.assertNotIn('market_leading',[call.args[1] for call in reads.call_args_list])
      result=app.call('index_minute',dict(code=code,day='2026-11-20',include_leading=True));self.assertEqual(result['leading']['code'],code)
     self.assertIsNone(app.market.index_view('sh000001','2026-11-19',include_leading=True)['leading']);network.assert_not_called()
    before=app.market.view('2026-11-20')
    self.assertNotIn('leading',before) # Stock MACD/market rules keep their original payload.
    with patch('core.market.quotes',return_value=[]),patch('core.market.minutes',side_effect=primary),patch('core.market.leading_minutes',side_effect=TimeoutError):app.market.poll()
    self.assertEqual(app.market.view('2026-11-20')['minute']['bars'],before['minute']['bars'])
    self.assertTrue(app.market.index_view('sh000001','2026-11-20',include_leading=True)['leading_error'])
    self.assertEqual(app.store.query('SELECT count(*) AS n FROM events')[0]['n'],0)
   finally:app.stop.set();app.store.db.close()
