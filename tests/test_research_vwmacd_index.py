import unittest
from datetime import datetime

from core.option_pcr import eligible_sessions
from core.provider import CN
from scripts.research_vwmacd_index import compute


class ResearchVwMacdTests(unittest.TestCase):
    def test_equal_volume_linear_prices_produce_known_difference(self):
        dates = eligible_sessions(datetime(2026, 10, 30, 18, tzinfo=CN), 30)
        rows = [{'date': d, 'first_date': d, 'close': i, 'volume': 100} for i, d in enumerate(dates, 1)]
        result = compute(rows)
        self.assertEqual(len(result), 5)
        self.assertAlmostEqual(result[0]['dif'], 7)
        self.assertAlmostEqual(result[-1]['dea'], 7)
        self.assertAlmostEqual(result[-1]['histogram'], 0)

    def test_missing_session_resets_full_window(self):
        dates = eligible_sessions(datetime(2026, 10, 30, 18, tzinfo=CN), 30)
        rows = [{'date': d, 'first_date': d, 'close': i, 'volume': 100} for i, d in enumerate(dates, 1)]
        self.assertEqual(compute(rows[:15] + rows[16:]), [])


if __name__ == '__main__':
    unittest.main()
