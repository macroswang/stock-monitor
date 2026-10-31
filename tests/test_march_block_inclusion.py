import unittest
from scripts.research_march_block_inclusion import calculate


class MarchBlockInclusionTest(unittest.TestCase):
    def test_only_disclosed_block_amount_changes_group_ratio(self):
        rows=[{'symbol':'920001.BJ','close':'10','pre_close':'9','high':'10','low':'10','vol':'10','amount':'10'},
              {'symbol':'920002.BJ','close':'10','pre_close':'11','high':'10','low':'10','vol':'10','amount':'10'}]
        adjustment={'code':'920002','volume_matches':True,'amount_matches_within_32_yuan':True,
                    'volume_difference':'100','amount_difference_yuan':'500'}
        result=calculate(rows,[adjustment])
        self.assertEqual(result['base_trin_amount'],1)
        self.assertEqual(result['adjusted_trin_amount'],1.05)
        self.assertEqual(result['adjusted_trin_volume'],1.1)
        with self.assertRaises(ValueError):calculate(rows,[{**adjustment,'volume_matches':False}])


if __name__=='__main__':unittest.main()
