import tempfile,threading,time,unittest
from core.app import App

class JobLimitTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.app=App(self.tmp.name,start_worker=False);self.addCleanup(self.app.store.db.close);self.addCleanup(self.app.stop.set)
 def wait(self,key):
  end=time.monotonic()+2
  while self.app.jobs[key]['status']=='running' and time.monotonic()<end:time.sleep(.001)
  self.assertEqual(self.app.jobs[key]['status'],'done')
 def test_finished_results_do_not_accumulate_without_limit(self):
  for _ in range(90):self.wait(self.app.start_job(lambda:'result')['job'])
  self.assertLessEqual(len(self.app.jobs),64)
 def test_concurrent_jobs_are_bounded_and_slots_recover(self):
  gate=threading.Event()
  try:
   jobs=[self.app.start_job(lambda:gate.wait(2))['job'] for _ in range(8)]
   with self.assertRaisesRegex(ValueError,'后台任务'):self.app.start_job(lambda:None)
  finally:gate.set()
  for key in jobs:self.wait(key)
  self.wait(self.app.start_job(lambda:True)['job'])
 def test_slow_symbol_does_not_hold_back_other_symbols_next_poll(self):
  from unittest.mock import patch
  self.app.store.execute('DELETE FROM watch')
  for code in ('sz000001','sz000002'):self.app.store.execute('INSERT INTO watch(code,name) VALUES(?,?)',(code,code))
  self.app.store.setconfig('monitor',True);self.app.POLL_SECONDS=.01
  gate=threading.Event();fast_twice=threading.Event();counts={}
  def poll(code):
   counts[code]=counts.get(code,0)+1
   if code=='sz000001':gate.wait(2)
   elif counts[code]>=2:fast_twice.set()
  self.app.poll_one=poll
  with patch('core.app.trading',return_value=True):
   thread=threading.Thread(target=self.app.loop);thread.start()
   try:self.assertTrue(fast_twice.wait(1.5));self.assertFalse(gate.is_set())
   finally:self.app.stop.set();gate.set();thread.join(2)
