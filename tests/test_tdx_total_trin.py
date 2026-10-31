import unittest
from scripts.research_tdx_total_trin import aggregate


class TdxTotalTrinTest(unittest.TestCase):
    def test_preserves_classification_and_includes_block_amount(self):
        rows={'920001BJ':{'open':'10','high':'10','low':'10','close':'10','pre_close':'9','amount':'10','vol':'10'},
              '920002BJ':{'open':'10','high':'10','low':'10','close':'10','pre_close':'11','amount':'10','vol':'10'}}
        bars={'920001BJ':(20260324,1000,1000,1000,1000,10000.0,1000,0),
              '920002BJ':(20260324,1000,1000,1000,1000,10500.0,1100,0)}
        r=aggregate(rows,bars,{'BJ'})
        self.assertEqual(r['money_trin_amount'],1)
        self.assertEqual(r['tdx_trin_amount'],1.05)
        self.assertEqual(r['amount_difference_count'],1)
        self.assertIsNone(aggregate(rows,{'920001BJ':bars['920001BJ']},{'BJ'})['tdx_trin_amount'])


if __name__=='__main__':unittest.main()
