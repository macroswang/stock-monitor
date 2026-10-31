import json
import unittest

from scripts.research_trin_balance_gap import DATA, OUT, analyze


class TrinBalanceGapTests(unittest.TestCase):
    def test_each_counterfactual_reproduces_the_displayed_ratio(self):
        row = next(r for r in json.loads(DATA.read_text())['days'] if r['date'] == '2026-10-23')
        result = analyze(row)
        self.assertAlmostEqual(result['local_trin'], 1.0660917324900157)
        up, down = result['counts']['up'], result['counts']['down']
        d = result['holding_counts_and_up_fixed']['down_target_yuan']
        u = result['holding_counts_and_down_fixed']['up_target_yuan']
        self.assertAlmostEqual(up*d/(down*result['up_amount_yuan']), .93)
        self.assertAlmostEqual(up*result['down_amount_yuan']/(down*u), .93)
        report = json.loads(OUT.read_text())
        self.assertEqual(result, {key: report[key] for key in result})

    def test_invalid_coverage_is_rejected(self):
        row = next(r for r in json.loads(DATA.read_text())['days'] if r['date'] == '2026-10-23')
        row['missing'] = 1
        with self.assertRaises(ValueError):
            analyze(row)


if __name__ == '__main__':
    unittest.main()
