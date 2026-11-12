import tempfile,unittest,json
from unittest.mock import patch,Mock
from core.app import App
from core import notify
class NotifyTest(unittest.TestCase):
 def test_pool_alerts_no_longer_enter_notification_queues(self):
  with tempfile.TemporaryDirectory() as d:
   a=App(d,False)
   self.addCleanup(a.store.db.close)
   self.assertFalse(a.store.event({'key':'pool|new','kind':'POOL_ALERT'},'live'))
   for table in ('events','messages','local_delivery','delivery'):
    self.assertFalse(a.store.query('SELECT * FROM '+table))
 def test_old_queued_pool_alerts_are_skipped_for_local_and_phone(self):
  with tempfile.TemporaryDirectory() as d:
   a=App(d,False)
   self.addCleanup(a.store.db.close)
   event={'key':'pool|legacy','kind':'POOL_ALERT'}
   a.store.execute('INSERT INTO events(key,payload,mode) VALUES(?,?,?)',(event['key'],json.dumps(event),'live'))
   a.store.execute('INSERT INTO local_delivery(key,status,next_try) VALUES(?,?,0)',(event['key'],'pending'))
   a.store.execute('INSERT INTO delivery(key,status,next_try) VALUES(?,?,0)',(event['key'],'retry'))
   self.assertEqual(a.call('local_pending',{})['events'],[])
   with patch('core.notify.bark') as send:notify.drain(a.store,True)
   send.assert_not_called()
   self.assertEqual(a.store.query('SELECT status FROM local_delivery')[0]['status'],'skipped')
   self.assertEqual(a.store.query('SELECT status FROM delivery')[0]['status'],'skipped')
   self.assertEqual(len(a.store.query('SELECT * FROM events')),1)
 def test_enabling_phone_does_not_flush_old_messages(self):
  with tempfile.TemporaryDirectory() as d:
   a=App(d,False);a.store.event(dict(key='x',symbol='603002',trading_date='2026-10-16',event_label='09:33',volumes=[100,80,70],candidate_time='09:31'),'live')
   a.call('config',{'phone_enabled':True})
   with patch('core.notify.bark') as send:notify.drain(a.store,True)
   send.assert_not_called();self.assertEqual(a.store.query('SELECT status FROM delivery')[0]['status'],'skipped');a.store.db.close()
 def test_secret_not_in_database(self):
  with tempfile.TemporaryDirectory() as d:
   a=App(d,False)
   with patch('core.notify.key') as key:a.call('secret',{'key':'test-device-key'});key.assert_called_once_with('test-device-key')
   self.assertNotIn('test-device-key',json.dumps(a.call('snapshot',{})))
   a.store.db.close()
 def test_bark_application_error_is_failure(self):
  response=Mock();response.read.return_value=b'{"code":400,"message":"invalid"}'
  context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
  with patch('core.notify.key',return_value='test-only'),patch('core.notify.urlopen',return_value=context):
   with self.assertRaises(ValueError):notify.bark('test','not a signal')
