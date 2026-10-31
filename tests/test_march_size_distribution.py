import json
import unittest

from scripts.research_march_size_distribution import HISTORY, SOURCE, analyze


class MarchSizeDistributionTests(unittest.TestCase):
    def test_matches_the_saved_breadth_cross_section(self):
        payload = json.loads(SOURCE.read_text())
        expected = next(r for r in json.loads(HISTORY.read_text()) if r['date']=='2026-03-23')
        result = analyze(payload, expected)
        self.assertEqual((result['eligible'], result['rising'], result['top_decile_size']), (5182, 290, 519))
        self.assertEqual(result['top_decile_rising'], 49)
        self.assertAlmostEqual(result['top_decile_rising_turnover_share_percent'], 43.5015825463)
        self.assertEqual(result['excluded_active'], [])

    def test_incomplete_active_data_is_not_used(self):
        payload = json.loads(SOURCE.read_text())
        expected = next(r for r in json.loads(HISTORY.read_text()) if r['date']=='2026-03-23')
        next(r for r in payload['daily'] if r['tradestatus']=='1')['turn'] = ''
        with self.assertRaises(ValueError):
            analyze(payload, expected)


if __name__ == '__main__':
    unittest.main()
