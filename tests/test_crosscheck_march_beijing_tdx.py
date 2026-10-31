import unittest
from scripts.crosscheck_march_beijing_tdx import compare


class BeijingTDXComparisonTest(unittest.TestCase):
    def test_float_rounding_and_price_volume_mismatches(self):
        row={'open':'15.01','high':'15.36','low':'14.90','close':'15.33',
             'pre_close':'14.85','vol':'7587.56','amount':'11488.228'}
        bar=(20260324,1501,1536,1490,1533,11488228.0,758756,65536)
        result=compare(row,bar,1485)
        self.assertEqual(result['fields'],[])
        self.assertFalse(result['previous_raw_close_differs'])
        different=compare({**row,'amount':'12000','vol':'8000'},bar,1480)
        self.assertEqual(different['fields'],['volume','amount'])
        self.assertTrue(different['previous_raw_close_differs'])


if __name__=='__main__':unittest.main()
