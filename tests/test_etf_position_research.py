import unittest
from decimal import Decimal
from scripts.research_etf_position import compare, within_day, non_overlapping


class ETFResearchTest(unittest.TestCase):
    def test_non_overlapping_selection_uses_time_not_results(self):
        rows=[{'signal_date':'2026-03-19','buy_date':'2026-03-27'},
              {'signal_date':'2026-03-17','buy_date':'2026-03-25'},
              {'signal_date':'2026-03-25','buy_date':'2026-04-01'}]
        self.assertEqual([x['signal_date'] for x in non_overlapping(rows)],['2026-03-17','2026-03-25'])

    def test_costs_and_execution_are_applied_to_both_legs(self):
        r=compare('4.000','3.950')
        self.assertEqual(r['sell_price'],'3.999')
        self.assertEqual(r['buy_price'],'3.951')
        self.assertEqual(r['sell_fee'],'5.00')
        self.assertEqual(r['buy_fee'],'5.00')
        self.assertEqual(Decimal(r['difference_yuan']),Decimal('230.00'))

    def test_rising_market_makes_rebuy_more_expensive(self):
        self.assertLess(Decimal(compare('4.000','4.050')['difference_yuan']),0)
        with self.assertRaises(ValueError):compare('4','3.9',units=55)

    def test_fills_outside_observed_range_are_rejected(self):
        bar=['2026-01-20','4.000','4.010','4.030','3.990','1000']
        self.assertTrue(within_day('3.999',bar))
        self.assertFalse(within_day('3.989',bar))
        self.assertFalse(within_day('4.031',bar))


if __name__=='__main__':unittest.main()
