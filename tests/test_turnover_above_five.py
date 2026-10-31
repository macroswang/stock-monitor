import unittest
from scripts.research_turnover_above_five import analyze


class TurnoverBreadthStudyTests(unittest.TestCase):
    def test_denominators_threshold_and_missing_values(self):
        def row(code, turn, status='1'):
            return {'date':'2026-10-22', 'code':code, 'turn':turn, 'tradestatus':status}
        payload={'date':'2026-10-22', 'fetched_at':'2026-10-28T10:00:00+08:00', 'daily':[
            row('sh.600001','5.000000'), row('sz.300001','6.000000'),
            row('sz.000001','1.000000'),row('sh.600002','', '0')]}
        result=analyze(payload)
        self.assertEqual((result['at_least_5_count'],result['above_5_count']),(2,1))
        self.assertAlmostEqual(result['active_share_percent'],200/3)
        self.assertEqual(result['listed_share_percent'],50)
        payload['daily'][2]['turn']=''
        self.assertIsNone(analyze(payload)['active_share_percent'])


if __name__ == '__main__':
    unittest.main()
