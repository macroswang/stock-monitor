import unittest
from datetime import datetime,timedelta
from core.provider import CN
from core.sector_constituents import parse_quotes,SectorConstituents


def quote(code,price,previous,when):
 f=['']*33;f[2]=code[2:];f[3]=str(price);f[4]=str(previous);f[30]=when.strftime('%Y%m%d%H%M%S');return 'v_'+code+'="'+'~'.join(f)+'";'

class ConstituentTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,30,10,10,tzinfo=CN);self.members=[{'code':'sz000001','name':'A'},{'code':'sh600001','name':'B'},{'code':'sz000002','name':'C'}]
 def test_complete_timestamped_group(self):
  text=quote('sz000001',11,10,self.now)+quote('sh600001',9,10,self.now)+quote('sz000002',10,10,self.now)
  result=parse_quotes([text],self.members,self.now)
  self.assertEqual((result['advance'],result['decline'],result['flat']),(1,1,1));self.assertEqual(result['covered'],3);self.assertAlmostEqual(result['average'],0)
 def test_missing_future_stale_or_inconsistent_session_rejected(self):
  base=quote('sz000001',11,10,self.now)+quote('sh600001',9,10,self.now)
  for t in [self.now+timedelta(minutes=1),self.now-timedelta(minutes=4),self.now-timedelta(days=1)]:
   with self.subTest(t=t),self.assertRaises(ValueError):parse_quotes([base+quote('sz000002',10,10,t)],self.members,self.now)
 def test_closed_rejects_early_untouched_quote(self):
  now=datetime(2026,10,31,12,0,tzinfo=CN);last=datetime(2026,10,30,16,0,tzinfo=CN)
  text=quote('sz000001',11,10,last)+quote('sh600001',9,10,last)+quote('sz000002',10,10,last.replace(hour=9))
  with self.assertRaises(ValueError):parse_quotes([text],self.members,now)
 def test_missing_members_do_not_trigger_fetch(self):
  self.assertIsNone(SectorConstituents().view('new_test',None)['data'])

if __name__=='__main__':unittest.main()
