import json
import unittest
from unittest.mock import patch
from core.sector_members import fetch,SectorMembers

class MemberTests(unittest.TestCase):
 def test_complete_members_are_returned(self):
  rows=[{'symbol':'sz000001','name':'股票甲'},{'symbol':'sh600001','name':'股票乙'}]
  with patch('core.sector_members.get',side_effect=['"2"',json.dumps(rows),'"2"']):
   data=fetch('new_test');self.assertEqual([r['code'] for r in data['members']],['sz000001','sh600001'])
 def test_partial_duplicate_and_wrong_category_are_rejected(self):
  rows=[{'symbol':'sz000001','name':'股票甲'},{'symbol':'sz000001','name':'股票甲'}]
  with patch('core.sector_members.get',side_effect=['"2"',json.dumps(rows),'"2"']):
   with self.assertRaises(ValueError):fetch('new_test')
  with patch('core.sector_members.get',side_effect=['"2"','[]','"2"']):
   with self.assertRaises(ValueError):fetch('gn_test')
  with self.assertRaises(ValueError):fetch('BK1234')
 def test_no_foreign_taxonomy_fallback(self):
  self.assertIsNone(SectorMembers().view('BK1234')['data'])

if __name__=='__main__':unittest.main()
