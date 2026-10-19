import tempfile,unittest,json,time
from datetime import datetime,timedelta
from unittest.mock import patch
from core.app import App,CN

class LocalOutboxTest(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.a=App(self.tmp.name,False)
 def tearDown(self):self.a.store.db.close();self.tmp.cleanup()
 def event(self):
  from core.provider import now_cn
  now=now_cn()
  return dict(key='test-live|1',symbol='603002',trading_date=now.date().isoformat(),event_label=now.strftime('%H:%M:%S'),observed_at=now.isoformat(),candidate_time='09:31',confirmation_label='09:33',volumes=[100,80,70],kind='TWO_MINUTE_CONFIRMATION')
 def test_live_event_before_first_shell_poll_is_not_lost(self):
  e=self.event();self.a.store.event(e,'live')
  self.assertEqual([x['key'] for x in self.a.call('local_pending',{})['events']],[e['key']])
 def test_claim_once_and_persist_acceptance_across_restart(self):
  e=self.event();self.a.store.event(e,'live')
  another=App(self.tmp.name,False)
  self.assertEqual(len(another.call('local_pending',{})['events']),1)
  self.assertTrue(another.call('local_claim',{'key':e['key']}))
  self.assertFalse(self.a.call('local_claim',{'key':e['key']}))
  another.call('local_finish',{'key':e['key'],'status':'accepted','detail':'isolated test'})
  another.store.db.close()
  third=App(self.tmp.name,False)
  self.assertFalse(third.call('local_pending',{})['events'])
  self.assertEqual(third.call('snapshot',{})['events'][0]['local_delivery'],'accepted');third.store.db.close()
 def test_interrupted_submission_is_unknown_not_duplicated(self):
  e=self.event();self.a.store.event(e,'live');self.a.call('local_claim',{'key':e['key']})
  another=App(self.tmp.name,False)
  self.assertFalse(another.call('local_pending',{})['events'])
  self.assertEqual(another.call('snapshot',{})['events'][0]['local_delivery'],'unknown');another.store.db.close()
 def test_delayed_test_is_local_only(self):
  with patch('core.store.time.time',return_value=1000):r=self.a.call('test_local',{'delay':10})
  with patch('core.app.time.time',return_value=1009):self.assertFalse(self.a.call('local_pending',{})['events'])
  with patch('core.app.time.time',return_value=1010):self.assertEqual(len(self.a.call('local_pending',{})['events']),1)
  self.assertFalse(self.a.store.query('SELECT * FROM delivery'))
 def test_replay_and_recovered_events_never_queue_local(self):
  e=self.event();self.a.store.event(e,'recovered');self.a.call('replay',{'code':'sh603002','day':'2026-10-16'})
  self.assertFalse(self.a.call('local_pending',{})['events'])
 def test_expired_alert_is_not_sent_after_restart(self):
  e=self.event();e['observed_at']=(datetime.fromisoformat(e['observed_at'])-timedelta(minutes=4)).isoformat()
  self.a.store.event(e,'live');self.assertFalse(self.a.call('local_pending',{})['events'])
  self.assertEqual(self.a.call('snapshot',{})['events'][0]['local_delivery'],'expired')
 def test_failed_submission_has_visible_status(self):
  e=self.event();self.a.store.event(e,'live');self.a.call('local_claim',{'key':e['key']})
  self.a.call('local_finish',{'key':e['key'],'status':'failed','detail':'隔离测试模拟系统拒绝'})
  row=self.a.call('snapshot',{})['events'][0]
  self.assertEqual(row['local_delivery'],'failed');self.assertIn('系统拒绝',row['local_detail'])
