import json,tempfile,threading,unittest
from datetime import datetime,timedelta
from email.utils import format_datetime
from io import BytesIO
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from core.app import App
from core.provider import Tencent,eastmoney_watch_quotes


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

 def test_batch_updates_snapshot_while_formal_minutes_are_blocked(self):
  code='sh603002';now=datetime.fromisoformat('2026-11-18T14:00:00+08:00')
  formal=dict(code=code,date=now.date().isoformat(),timestamp=(now-timedelta(seconds=7)).isoformat(),price='10.50')
  fast=dict(formal,timestamp=now.isoformat(),price='10.65')
  self.app.store.setconfig('monitor',True)
  self.app.provider=Mock();self.app.provider.quote.return_value=formal
  waiting=threading.Event();release=threading.Event()
  def slow_minutes(_code):
   waiting.set();release.wait(3)
   raise OSError('minute feed unavailable')
  self.app.provider.minutes.side_effect=slow_minutes
  self.app.provider.watch_quotes.return_value={code:fast}
  with patch('core.app.now_cn',return_value=now):
   worker=threading.Thread(target=self.app.poll_one,args=(code,));worker.start()
   try:
    self.assertTrue(waiting.wait(2))
    self.assertTrue(self.app.refresh_display_quotes())
    self.app.provider.watch_quotes.assert_called_once()
    self.assertEqual(self.displayed(),fast)
    self.assertEqual(self.app.call('watch_quotes',{})['quotes'][code],fast)
    self.app.provider.watch_quotes.assert_called_once()
    self.assertEqual(self.app.quotes[code],formal)
    self.assertEqual(self.app.store.getcache(code,'watch_quote')[0]['data']['price'],'10.50')
   finally:
    release.set();worker.join(3)
  self.assertFalse(worker.is_alive())

 def test_batch_drops_future_stale_and_invalidated_entries(self):
  keep,removed,future,stale=[row['code'] for row in self.app.store.query('SELECT code FROM watch ORDER BY rowid LIMIT 4')]
  now=datetime.fromisoformat('2026-11-18T14:00:00+08:00')
  def quote(code,seconds):
   stamp=now+timedelta(seconds=seconds)
   return dict(code=code,date=stamp.date().isoformat(),timestamp=stamp.isoformat(),price='7.50')
  def batch(_codes):
   self.app.call('remove',{'code':removed})
   return {code:quote(code,seconds) for code,seconds in ((keep,-1),(removed,-1),(future,1),(stale,-16))}
  self.app.store.setconfig('monitor',True)
  self.app.provider=Mock();self.app.provider.watch_quotes.side_effect=batch
  with patch('core.app.now_cn',return_value=now):
   self.assertTrue(self.app.refresh_display_quotes())
  self.assertEqual(self.app.display_quotes,{keep:quote(keep,-1)})
  self.assertTrue(self.app.watch_display_quote(keep,now+timedelta(seconds=15))['cached'])
  self.assertIsNone(self.app.watch_display_quote(keep,now+timedelta(days=1)))
  self.app.quotes[keep]=quote(keep,0)
  self.assertEqual(self.app.watch_display_quote(keep,now),quote(keep,0))
  self.app.quotes[keep]=quote(keep,1)
  self.assertEqual(self.app.watch_display_quote(keep,now),quote(keep,-1))

 def test_batch_accepts_valid_rows_with_partial_or_wrong_symbol_reply(self):
  def row(code,reported):
   fields=['0']*49;fields[2]=reported;fields[3]='10';fields[30]='20261118140000';fields[47]='11'
   return 'v_'+code+'="'+'~'.join(fields)+'";'
  valid=row('sh603002','603002')
  mixed=valid+row('sz000981','000815')+row('sh600392','600392')+'v_sh688680="broken";'
  with patch('core.provider.get',return_value=mixed) as get:
   result=Tencent().watch_quotes(['sz000981','sh603002','sh688680'])
   get.assert_called_once_with('https://qt.gtimg.cn/q=sh603002,sh688680,sz000981','gb18030',timeout=3)
  with patch('core.provider.get',return_value=valid):
   self.assertEqual(result,{'sh603002':Tencent().quote('sh603002')})

 def test_batch_cooldown_honors_retry_after_and_timeout_keeps_short_backoff(self):
  now=datetime.fromisoformat('2026-11-18T14:00:00+08:00')
  retry_at=format_datetime(now+timedelta(minutes=25))
  def error(code,header=None):
   return HTTPError('',code,'',{'Retry-After':header} if header else {},None)
  for failure,wait in ((error(403),900),(error(429,'1200'),1200),(error(429,retry_at),1500),(error(429,'bad'),900)):
   self.assertEqual(self.app.display_quote_cooldown(failure,now),wait)
  with patch('core.app.now_cn',return_value=now),patch('core.app.time.monotonic',return_value=100):
   self.app.stop=Mock()
   self.app.stop.is_set.side_effect=[False,False,True]
   with patch.object(self.app,'refresh_display_quotes',side_effect=[TimeoutError(),True]):
    self.app.display_quote_loop()
   self.assertEqual([call.args[0] for call in self.app.stop.wait.call_args_list],[12,6])

 def test_batch_reuses_fresh_quote_and_switches_provider_until_cooldown_expires(self):
  code='sh603002';now=datetime.fromisoformat('2026-11-18T14:00:00+08:00')
  self.app.store.execute('DELETE FROM watch WHERE code<>?',(code,))
  self.app.store.setconfig('monitor',True)
  def quote(source,seconds=0,previous='10'):
   return dict(code=code,price='10.60',previous_close=previous,source=source,
               timestamp=(now+timedelta(seconds=seconds)).isoformat(),date=now.date().isoformat())
  self.app.provider=Mock()
  self.app.quotes[code]=quote('tencent',-2)
  with patch('core.app.now_cn',side_effect=lambda:now),patch('core.app.sys.stderr'), \
       patch('core.app.eastmoney_watch_quotes') as backup:
   self.assertTrue(self.app.refresh_display_quotes())
   self.app.provider.watch_quotes.assert_not_called();backup.assert_not_called()
   now+=timedelta(seconds=6)
   self.app.provider.watch_quotes.side_effect=HTTPError('',429,'',{'Retry-After':'1200'},None)
   backup.return_value={code:quote('eastmoney')}
   self.assertTrue(self.app.refresh_display_quotes())
   self.assertEqual(self.displayed()['source'],'eastmoney')
   self.assertEqual(self.app.quotes[code]['source'],'tencent')
   backup.assert_called_once_with([code])
   self.assertEqual(self.app.store.config()['display_quote_resume']['tencent'],now.timestamp()+1200)
   now+=timedelta(seconds=6)
   backup.return_value={code:quote('eastmoney',previous='9')}
   self.assertFalse(self.app.refresh_display_quotes())
   self.app.provider.watch_quotes.assert_called_once_with([code])
   self.assertEqual(self.displayed()['previous_close'],'10')
   now+=timedelta(seconds=1194)
   self.app.provider.watch_quotes.side_effect=None
   self.app.provider.watch_quotes.return_value={code:quote('tencent')}
   self.assertTrue(self.app.refresh_display_quotes())
   self.assertEqual(backup.call_count,2)
   self.assertEqual(self.displayed()['source'],'tencent')

 def test_eastmoney_batch_validates_market_price_and_source_time(self):
  stamp=datetime.fromisoformat('2026-11-18T14:00:00+08:00')
  valid=dict(f2=10.6,f12='603002',f13=1,f14='宏昌电子',f15=10.8,f16=9.9,f17=10.1,f18=10,f124=int(stamp.timestamp()))
  wrong_market=dict(valid,f13=0)
  malformed=dict(valid,f12='000981',f13=0,f124='--')
  wrong_price=dict(valid,f12='000815',f13=0,f2=12)
  body=json.dumps({'data':{'diff':[valid,wrong_market,malformed,wrong_price]}}).encode()
  with patch('core.provider.urlopen',return_value=BytesIO(body)) as fetch:
   quotes=eastmoney_watch_quotes(['sh603002','sz000981','sz000815'])
  fetch.assert_called_once()
  self.assertEqual(list(quotes),['sh603002'])
  self.assertEqual(quotes['sh603002']['timestamp'],stamp.isoformat())
  self.assertEqual(quotes['sh603002']['source'],'eastmoney')
