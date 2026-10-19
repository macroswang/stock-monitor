import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
from core.rules import Session
from core.app import App,ROOT,CN
from core.store import Store
from core.provider import Tencent

def bar(t,v,p='9',**kw): return dict(time=t,volume=v,close=p,complete=True,**kw)
class RulesTest(unittest.TestCase):
 def test_verified_12_stock_19_events(self):
  total=0
  for path in sorted((ROOT/'fixtures').glob('[s][hz]*-2026-10-16-tencent.json')):
   d=json.loads(path.read_text()); expected=json.loads(path.with_name('expected-'+path.name).read_text())
   s=Session(d['symbol'],d['trading_date'],d['limit_up'])
   for b in d['bars']: s.bar(b)
   sig=lambda es:[(e['key'],e['candidate_time'],e['confirmation_label'],e['event_label'],e['volumes'],e['kind']) for e in es]
   self.assertEqual(sig(s.events),sig(expected['matches']),path.name)
   self.assertEqual([c['candidate_time'] for c in s.candidates],[c['candidate_time'] for c in expected['candidates']])
   total+=len(s.events)
  self.assertEqual(total,19)
 def test_tie_resets_baseline(self):
  s=Session('a','2026-10-16','10')
  for b in [bar('09:31',100),bar('09:32',100),bar('09:33',80),bar('09:34',90)]:s.bar(b)
  self.assertEqual([e['candidate_time'] for e in s.events],['09:32'])
 def test_wait_reopen_no_extra_wait(self):
  s=Session('a','2026-10-16','10')
  s.bar(bar('09:31',100,'10'));s.bar(bar('09:32',80,'9'))
  self.assertFalse(s.tick('09:32:30','9'))
  s.bar(bar('09:33',70,'10'))
  self.assertFalse(s.events)
  self.assertEqual(len(s.tick('09:33:04','9.99')),1)
  self.assertFalse(s.tick('09:33:05','9.98'))
 def test_partial_and_gap(self):
  s=Session('a','2026-10-16','10');s.bar(bar('09:31',100))
  b=bar('09:32',999);b['complete']=False;s.bar(b)
  self.assertEqual(s.maximum,100)
  s.bar(bar('09:33',50));s.bar(bar('09:34',40));self.assertTrue(s.gap);self.assertFalse(s.events)
 def test_lunch_and_close(self):
  from core.validated_engine import MINUTES
  s=Session('a','2026-10-16','10')
  for t in MINUTES[:119]:s.bar(bar(t,0))
  for t,v in [('11:30',100),('13:01',80),('13:02',70)]:s.bar(bar(t,v))
  self.assertEqual(s.events[0]['event_label'],'13:02')
  s.bar(bar('13:03',200));s.expire();self.assertEqual(s.candidates[-1]['state'],'EXPIRED_AT_CLOSE')
 def test_reject_bad_units_and_prices(self):
  for b in [bar('09:31',1.5),bar('09:31',1,'11')]:
   with self.assertRaises(ValueError):Session('a','2026-10-16','10').bar(b)

class AppTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=App(self.tmp.name,False)
 def tearDown(self): self.app.store.db.close();self.tmp.cleanup()
 def test_replay_never_queues_notification_and_deduplicates(self):
  for _ in range(2): self.app.call('replay',{'code':'sh603002','day':'2026-10-16'})
  self.assertEqual(len(self.app.store.query('SELECT * FROM events')),1)
  self.assertFalse(self.app.store.query('SELECT * FROM delivery'))
 def test_restart_persists_watchlist_and_pause(self):
  self.app.call('toggle',{'code':'sh603002','enabled':False})
  self.app.call('remove',{'code':'sz000981'})
  another=App(self.tmp.name,False)
  rows=another.call('snapshot',{})['watch'];self.assertEqual(len(rows),11)
  self.assertEqual(next(r for r in rows if r['code']=='sh603002')['enabled'],0)
  another.store.db.close()
 def test_live_vs_recovery(self):
  code='sh603002';now=datetime(2026,10,16,9,32,5,tzinfo=CN)
  quote=dict(date='2026-10-16',timestamp=now.isoformat(),price='9',limit_up='10')
  groups=[dict(date='2026-10-16',bars=[bar('09:31',100),bar('09:32',80)])]
  self.app.ingest(code,quote,groups,now)
  now+=timedelta(seconds=60);quote['timestamp']=now.isoformat();groups[0]['bars'].append(bar('09:33',70))
  self.app.ingest(code,quote,groups,now)
  self.assertEqual(self.app.store.query('SELECT mode FROM events')[0]['mode'],'recovered')
 def test_live_fresh_event(self):
  code='sh603002';now=datetime(2026,10,16,9,32,50,tzinfo=CN)
  quote=dict(date='2026-10-16',timestamp=now.isoformat(),price='9',limit_up='10')
  groups=[dict(date='2026-10-16',bars=[bar('09:31',100),bar('09:32',80)])]
  self.app.ingest(code,quote,groups,now)
  now+=timedelta(seconds=15);quote['timestamp']=now.isoformat();groups[0]['bars'].append(bar('09:33',70))
  self.app.ingest(code,quote,groups,now)
  self.assertEqual(self.app.store.query('SELECT mode FROM events')[0]['mode'],'live')
  self.app.ingest(code,quote,groups,now)
  self.assertEqual(len(self.app.store.query('SELECT * FROM events')),1)
 def test_stale_quote_cannot_trigger(self):
  now=datetime(2026,10,16,9,33,5,tzinfo=CN)
  q=dict(date='2026-10-15',timestamp=(now-timedelta(days=1)).isoformat(),price='9',limit_up='10')
  self.app.ingest('sh603002',q,[],now)
  self.assertFalse(self.app.sessions)
 def test_backup_readable(self):
  import sqlite3
  p=self.app.call('backup',{})['path'];c=sqlite3.connect(p)
  self.assertEqual(c.execute('SELECT count(*) FROM watch').fetchone()[0],12);c.close()

class ProviderTest(unittest.TestCase):
 def test_saved_cumulative_unit_and_auction_normalization(self):
  # Raw saved sources are external read-only oracle, when available in this workspace.
  base=ROOT.parent.parent/'ths_numeric_validation/ui_expanded/raw'
  if not base.exists():self.skipTest('External raw oracle unavailable')
  for code in ['sh603002','sh688680']:
   raw=(base/f'{code}-tencent.json').read_text()
   with patch('core.provider.get',return_value=raw): groups=Tencent().minutes(code,datetime(2026,10,18,tzinfo=CN))
   actual=next(g for g in groups if g['date']=='2026-10-16')
   expected=json.loads((ROOT/'fixtures'/f'{code}-2026-10-16-tencent.json').read_text())
   self.assertEqual([(b['time'],b['volume']) for b in actual['bars']],[(b['time'],b['volume']) for b in expected['bars']])

if __name__=='__main__':unittest.main()

class DownloadTest(unittest.TestCase):
 def test_download_job_does_not_block_snapshot(self):
  import threading,time
  with tempfile.TemporaryDirectory() as d:
   a=App(d,False);gate=threading.Event()
   def slow(*args): gate.wait(2);return []
   with patch.object(a.provider,'minutes',side_effect=slow):
    task=a.call('download',{'code':'sh603002','kind':'minute','start':'2026-10-01','end':'2026-10-16'})
    before=time.monotonic();self.assertEqual(len(a.call('snapshot',{})['watch']),12)
    self.assertLess(time.monotonic()-before,.5)
    self.assertEqual(a.call('job',task)['status'],'running');gate.set()
    for _ in range(100):
     if a.call('job',task)['status']=='done':break
     time.sleep(.01)
    self.assertEqual(a.call('job',task)['status'],'done');a.store.db.close()

class CacheEvidenceTest(unittest.TestCase):
 def test_refresh_does_not_discard_verified_limit_metadata(self):
  with tempfile.TemporaryDirectory() as d:
   a=App(d,False)
   prior=a.store.getcache('sh603002','minute','2026-10-16')[0]['data']
   a.cache_minutes('sh603002',dict(date='2026-10-16',bars=prior['bars'],source='tencent',volume_unit='shares'))
   self.assertEqual(len(a.call('replay',{'code':'sh603002','day':'2026-10-16'})['matches']),1)
   a.store.db.close()
