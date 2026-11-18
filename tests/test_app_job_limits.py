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
 def test_slow_stock_pool_does_not_hold_back_watched_minutes(self):
  from unittest.mock import patch
  self.app.store.execute('DELETE FROM watch')
  self.app.store.execute("INSERT INTO watch(code,name) VALUES('sh603938','三孚股份')")
  self.app.store.execute("INSERT INTO pool(code,name,added_day,source,state) VALUES('sh603938','三孚股份','2026-11-18','test','观察')")
  self.app.store.setconfig('monitor',True);self.app.POLL_SECONDS=.01
  pool_started=threading.Event();release_pool=threading.Event();second_poll=threading.Event()
  def slow_batch(codes):
   pool_started.set()
   release_pool.wait(2)
   return {}
  self.app.pool._batch=slow_batch
  self.app.pool.refresh_fund_flows=lambda codes:{}
  calls=[]
  def poll_stock(code):
   calls.append(code)
   if len(calls)==2:second_poll.set()
  self.app.poll_one=poll_stock
  with patch('core.app.trading',return_value=True):
   pool=threading.Thread(target=self.app.pool_loop)
   watch=threading.Thread(target=self.app.loop)
   pool.start()
   try:
    self.assertTrue(pool_started.wait(1))
    watch.start()
    self.assertTrue(second_poll.wait(1.5))
    self.assertFalse(release_pool.is_set())
   finally:
    self.app.stop.set();release_pool.set();pool.join(2)
    if watch.ident is not None:watch.join(2)
