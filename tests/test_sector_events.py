import unittest
from datetime import datetime,timedelta
from core.provider import CN
from core.sector_events import build_observations

class SectorEventTests(unittest.TestCase):
 def setUp(self):self.now=datetime(2026,10,30,10,10,tzinfo=CN)
 def snap(self,minutes,change,net,source='东方财富行业板块资金流'):
  t=self.now+timedelta(minutes=minutes)
  return dict(date='2026-10-30',source=source,observations=[dict(code='BK0001',name='测试板块',source_time=t.isoformat(),change_percent=change,net_yuan=net)])
 def test_direction_consistent_change_and_freshness(self):
  r=build_observations([self.snap(-6,0,100),self.snap(-1,.5,200)],self.now,'2026-10-30')
  self.assertEqual(r['events'][0]['label'],'启动观察')
  self.assertAlmostEqual(r['events'][0]['change'],.5)
  self.assertEqual(r['events'][0]['net'],100)
 def test_repeated_consistent_observations_change_to_sustained(self):
  rows=[self.snap(-8,0,100),self.snap(-6,.1,110),self.snap(-2,.4,150),self.snap(0,.7,200)]
  self.assertEqual(build_observations(rows,self.now,'2026-10-30')['events'][0]['label'],'持续走强')
 def test_missing_old_future_and_wrong_source_never_trigger(self):
  for snapshots in ([self.snap(-6,0,100),self.snap(-1,.5,200,'新浪行业资金流')],[self.snap(-20,0,100),self.snap(-1,.5,200)],[self.snap(-6,0,100),self.snap(2,.5,200)],[self.snap(-6,0,100),self.snap(-1,.5,50)]):
   with self.subTest(snapshots=snapshots):self.assertEqual(build_observations(snapshots,self.now,'2026-10-30')['events'],[])
 def test_no_signal_during_non_session_or_next_day(self):
  rows=[self.snap(-6,0,100),self.snap(-1,.5,200)]
  self.assertEqual(build_observations(rows,self.now.replace(hour=12),'2026-10-30')['events'],[])
  self.assertEqual(build_observations(rows,self.now+timedelta(days=1),'2026-10-30')['events'],[])
 def test_duplicate_source_time_does_not_duplicate_series(self):
  x=self.snap(-1,.5,200);r=build_observations([x,x],self.now,'2026-10-30')
  self.assertEqual(len(r['series']['BK0001']['points']),1)

 def test_overlapping_snapshots_keep_first_values_per_sector_and_sort_times(self):
  early=self.snap(-6,0,100);late=self.snap(-1,.5,200)
  conflict=self.snap(-1,99,9999)
  other=self.snap(-1,-.5,-200);other['observations'][0].update(code='BK0002',name='另一板块')
  result=build_observations([late,early,conflict,other,late],self.now,'2026-10-30')
  self.assertEqual(result,build_observations([early,late,other],self.now,'2026-10-30'))
  self.assertEqual(result['series']['BK0001']['points'][-1]['change'],.5)
  self.assertEqual(result['series']['BK0002']['points'][-1]['change'],-.5)

if __name__=='__main__':unittest.main()
