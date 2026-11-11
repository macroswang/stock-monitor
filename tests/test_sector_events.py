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

 def test_conflicting_duplicate_keeps_first_values_and_first_name(self):
  first=self.snap(-1,.5,200);later=self.snap(-1,99,99999)
  later['observations'][0]['name']='后来的名称'
  r=build_observations([first,later],self.now,'2026-10-30')
  group=r['series']['BK0001']
  self.assertEqual(group['name'],'测试板块')
  self.assertEqual(group['points'],[dict(time=(self.now-timedelta(minutes=1)).isoformat(),change=.5,net=200)])

 def test_overlapping_snapshots_sort_points_without_merging_sectors(self):
  late=self.snap(-1,.5,200);early=self.snap(-6,0,100)
  second=self.snap(-1,-.7,-300);second['observations'][0]['code']='BK0002'
  r=build_observations([late,second,early,early,late],self.now,'2026-10-30')
  self.assertEqual([p['time'] for p in r['series']['BK0001']['points']],[(self.now-timedelta(minutes=i)).isoformat() for i in (6,1)])
  self.assertEqual(len(r['series']['BK0002']['points']),1)
  self.assertEqual(r['events'][0]['label'],'启动观察')
  self.assertIsInstance(r['series']['BK0001']['points'],list)

 def test_invalid_rows_do_not_hide_later_valid_values(self):
  invalid=self.snap(-1,float('nan'),200);valid=self.snap(-1,.5,200)
  r=build_observations([invalid,valid],self.now,'2026-10-30')
  self.assertEqual(r['series']['BK0001']['points'][0]['change'],.5)

 def test_large_overlapping_history_keeps_every_unique_source_time(self):
  start=self.now.replace(hour=9,minute=30,second=0)
  snapshots=[]
  for minute in range(40):
   observations=[dict(code='BK0001',name='测试板块',source_time=(start+timedelta(minutes=minute,seconds=second)).isoformat(),change_percent=.1,net_yuan=10) for second in range(60)]
   snapshots.extend([dict(date='2026-10-30',source='东方财富行业板块资金流',observations=observations)]*8)
  r=build_observations(snapshots,self.now,'2026-10-30')
  self.assertEqual(len(r['series']['BK0001']['points']),2400)

if __name__=='__main__':unittest.main()
