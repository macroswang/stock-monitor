import csv
import json
import unittest

from scripts.research_march_csi300 import MONEY, OUT, RAW, calculate, check_market


class MarchCSI300Tests(unittest.TestCase):
    def test_archived_members_and_prices_reproduce_the_observation(self):
        report = json.loads(OUT.read_text())
        data = json.loads(RAW.read_text())['daily']
        with MONEY.open(encoding='utf-8-sig',newline='') as stream:
            check = check_market(data,list(csv.DictReader(stream)))
        self.assertEqual(check,report['market_crosscheck'])
        self.assertEqual(check['stocks'],5182)
        result=calculate(report['members'],data)
        self.assertEqual(result,report['result'])
        self.assertEqual(result['member_count'],{'up':23,'down':277,'flat':0})
        self.assertAlmostEqual(result['member_share_percent']['up'],26.45865348)
        self.assertAlmostEqual(result['member_share_percent']['down'],27.95114218)

    def test_wrong_or_duplicate_members_are_rejected(self):
        report = json.loads(OUT.read_text())
        data = json.loads(RAW.read_text())['daily']
        members=report['members']
        members[1]=members[0]
        with self.assertRaises(ValueError):
            calculate(members,data)


if __name__ == '__main__':
    unittest.main()
