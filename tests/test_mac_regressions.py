"""User-facing Mac audit regressions; all market sequences isolated from real monitoring."""
import tempfile,unittest,time,threading
from datetime import datetime,timedelta
from unittest.mock import patch
from core.app import App,CN
from core.provider import Tencent

def bar(t,v,p='9'):return dict(time=t,volume=v,close=p,complete=True)
def quote(at,p='9'):return dict(code='sh603002',name='宏昌电子',date=at.date().isoformat(),timestamp=at.isoformat(),price=p,limit_up='10',change='0')
def groups(*bars):return [dict(date='2026-10-16',bars=list(bars),source='tencent',volume_unit='shares')]
class MacRegression(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.a=App(self.tmp.name,False)
 def tearDown(self):self.a.store.db.close();self.tmp.cleanup()
 def test_future_quote_is_rejected(self):
  now=datetime(2026,10,16,9,32,50,tzinfo=CN)
  self.a.ingest('sh603002',quote(now+timedelta(minutes=1)),groups(bar('09:31',100),bar('09:32',80)),now)
  self.assertFalse(self.a.sessions)
 def test_stale_sample_breaks_continuity(self):
  t=datetime(2026,10,16,9,32,50,tzinfo=CN)
  g=groups(bar('09:31',100),bar('09:32',80))
  self.a.ingest('sh603002',quote(t),g,t)
  self.a.ingest('sh603002',quote(t-timedelta(minutes=1)),g,t+timedelta(seconds=5))
  t+=timedelta(seconds=15);g[0]['bars'].append(bar('09:33',70))
  self.a.ingest('sh603002',quote(t),g,t)
  self.assertEqual(self.a.store.query('SELECT mode FROM events')[0]['mode'],'recovered')
 def test_future_complete_bar_is_not_consumed(self):
  t=datetime(2026,10,16,9,32,50,tzinfo=CN)
  self.a.ingest('sh603002',quote(t),groups(bar('09:31',100),bar('09:32',80),bar('09:33',70)),t)
  self.assertFalse(self.a.store.query('SELECT * FROM events'))
 def test_added_stock_survives_history_failure_with_success_result(self):
  t=datetime(2026,10,16,16,tzinfo=CN)
  q=dict(quote(t),code='sh600519',name='贵州茅台')
  with patch.object(self.a.provider,'quote',return_value=q),patch.object(self.a.provider,'minutes',side_effect=OSError('offline')):
   result=self.a.call('add',{'code':'600519'})
  self.assertEqual(result['code'],'sh600519')
  self.assertEqual(len(self.a.store.query("SELECT * FROM watch WHERE code='sh600519'")),1)
 def test_wait_reopen_from_completed_close_is_seen_even_if_quote_resealed(self):
  t=datetime(2026,10,16,9,33,5,tzinfo=CN)
  g=groups(bar('09:31',100,'10'),bar('09:32',80,'10'),bar('09:33',70,'10'))
  self.a.ingest('sh603002',quote(t,'10'),g,t)
  # Continue observing, then a completed below-limit close proves a reopening.
  for seconds in (20,35,50):
   u=t.replace(second=seconds);self.a.ingest('sh603002',quote(u,'10'),g,u)
  t+=timedelta(minutes=1);g[0]['bars'].append(bar('09:34',60,'9.99'))
  self.a.ingest('sh603002',quote(t,'10'),g,t)
  self.assertEqual(len(self.a.store.query('SELECT * FROM events')),1)

if __name__=='__main__':unittest.main()

class ExtendedMacRegression(unittest.TestCase):
 setUp=MacRegression.setUp
 tearDown=MacRegression.tearDown
 def test_lunch_preserves_live_confirmation(self):
  from core.validated_engine import MINUTES
  bars=[bar(t,0) for t in MINUTES[:118]]+[bar('11:29',100),bar('11:30',80)]
  for clock in ['11:29:05','11:29:35','11:30:05','11:30:35','13:00:05','13:00:35','13:01:05']:
   at=datetime.fromisoformat('2026-10-16T'+clock).replace(tzinfo=CN)
   available=[b for b in bars if b['time']<=clock[:5]]
   if clock[:5]>='13:01':available.append(bar('13:01',70))
   self.a.ingest('sh603002',quote(at),groups(*available),at)
  event=self.a.call('snapshot',{})['events'][0]
  self.assertEqual(event['event_label'],'13:01');self.assertEqual(event['mode'],'live')
 def test_completed_minute_revision_is_recovery_not_live(self):
  t=datetime(2026,10,16,9,32,50,tzinfo=CN);g=groups(bar('09:31',100),bar('09:32',80))
  self.a.ingest('sh603002',quote(t),g,t)
  t+=timedelta(seconds=15);g[0]['bars'][0]['volume']=200;g[0]['bars'].append(bar('09:33',70))
  self.a.ingest('sh603002',quote(t),g,t)
  self.assertEqual(self.a.call('snapshot',{})['events'][0]['mode'],'recovered')
 def test_matched_reopen_state_is_not_lost_on_next_poll(self):
  g=groups(bar('09:31',100,'10'),bar('09:32',80,'10'))
  t=datetime(2026,10,16,9,32,50,tzinfo=CN);self.a.ingest('sh603002',quote(t,'10'),g,t)
  t+=timedelta(seconds=15);g[0]['bars'].append(bar('09:33',70,'10'))
  self.a.ingest('sh603002',quote(t,'9.99'),g,t)
  t+=timedelta(seconds=8);self.a.ingest('sh603002',quote(t,'10'),g,t)
  self.assertEqual(self.a.sessions['sh603002']['candidates'][0]['state'],'MATCHED_ONCE')
  self.assertEqual(len(self.a.call('snapshot',{})['events']),1)
 def test_missing_auction_point_blocks_volume_normalization(self):
  raw=dict(data={'sh603002':{'data':[{'date':'20261016','data':['0931 9 100 90000','0932 9 200 180000']}]}})
  import json
  with patch('core.provider.get',return_value=json.dumps(raw)):
   with self.assertRaisesRegex(ValueError,'09:30'):Tencent().minutes('sh603002')
 def test_remove_during_inflight_fetch_cannot_resurrect_stock(self):
  gate=threading.Event();started=threading.Event()
  def slow_quote(code):started.set();gate.wait(2);return quote(datetime(2026,10,16,9,33,5,tzinfo=CN))
  with patch.object(self.a.provider,'quote',side_effect=slow_quote),patch.object(self.a.provider,'minutes',return_value=groups(bar('09:31',100))):
   worker=threading.Thread(target=self.a.poll_one,args=('sh603002',));worker.start();started.wait(1)
   self.a.call('remove',{'code':'sh603002'});gate.set();worker.join(3)
  self.assertFalse(self.a.store.query("SELECT * FROM watch WHERE code='sh603002'"));self.assertNotIn('sh603002',self.a.quotes)

class ShutdownRegression(unittest.TestCase):
 setUp=MacRegression.setUp
 tearDown=MacRegression.tearDown
 def test_shutdown_discards_inflight_quote(self):
  started=threading.Event();gate=threading.Event()
  def slow(code):started.set();gate.wait(2);return quote(datetime(2026,10,16,9,33,5,tzinfo=CN))
  with patch.object(self.a.provider,'quote',side_effect=slow),patch.object(self.a.provider,'minutes',return_value=groups(bar('09:31',100))):
   worker=threading.Thread(target=self.a.poll_one,args=('sh603002',));worker.start();started.wait(1);self.a.stop.set();gate.set();worker.join(3)
  self.assertFalse(self.a.quotes);self.assertFalse(self.a.sessions)
 def test_consecutive_backups_do_not_overwrite(self):
  a=self.a.call('backup',{})['path'];b=self.a.call('backup',{})['path'];self.assertNotEqual(a,b)
