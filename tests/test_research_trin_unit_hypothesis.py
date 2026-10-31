import unittest

from scripts.research_trin_unit_hypothesis import trin


class UnitHypothesisTests(unittest.TestCase):
    def test_star_unit_hypotheses_change_volume_not_stock_counts(self):
        def row(code, close, volume):
            return {'code': code, 'tradestatus': '1', 'close': close, 'preclose': '10', 'volume': volume, 'amount': '1000'}
        rows = [row('sh.688001', '11', '100'), row('sh.600001', '9', '100')]
        self.assertEqual(trin(rows, 'shares')['trin'], 1)
        self.assertEqual(trin(rows, 'star_times_100')['trin'], .01)
        self.assertEqual(trin(rows, 'star_divided_by_100')['trin'], 100)
        for key in ('shares', 'star_times_100', 'star_divided_by_100', 'amount'):
            self.assertEqual((trin(rows, key)['advance'], trin(rows, key)['decline']), (1, 1))

    def test_invalid_scenario_and_empty_groups_are_rejected(self):
        with self.assertRaises(ValueError):
            trin([], 'unexpected')
        with self.assertRaises(ValueError):
            trin([], 'shares')


if __name__ == '__main__':
    unittest.main()
