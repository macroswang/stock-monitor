import copy
import json
import unittest
from pathlib import Path
from scripts.validate_market_strategy import run

ROOT = Path(__file__).resolve().parents[1]


class MarketStrategyValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = json.loads((ROOT/'fixtures/market-validation-inputs.json').read_text())['days']
        rows = json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text())
        cls.breadth = {r['date']: r for r in rows}

    def test_previous_close_signals_and_full_accounting(self):
        result = run(self.days, self.breadth, '2026-03-24', '2026-10-29', 'breadth_trin')
        previous = {row['date']: self.days[i-1]['date'] for i,row in enumerate(self.days) if i}
        self.assertTrue(result['trades'])
        for trade in result['trades']:
            self.assertEqual(trade['signal_date'], previous[trade['date']])
            self.assertGreater(trade['units'], 0)
        self.assertEqual(result['closed_trades'], result['wins']+result['losses']+result['flat'])
        self.assertGreaterEqual(result['max_drawdown_percent'], 0)

    def test_missing_breadth_is_error_not_silent_signal(self):
        breadth = copy.deepcopy(self.breadth)
        del breadth['2026-03-23']
        with self.assertRaisesRegex(ValueError, '广度'):
            run(self.days, breadth, '2026-03-24', '2026-03-24', 'breadth_trin')

    def test_today_breadth_not_used_until_following_day(self):
        modified = copy.deepcopy(self.breadth)
        modified['2026-03-24']['trin_amount'] = 999
        before = run(self.days, self.breadth, '2026-03-24', '2026-03-24', 'breadth_trin')
        after = run(self.days, modified, '2026-03-24', '2026-03-24', 'breadth_trin')
        self.assertEqual(before, after)

    def test_cash_benchmark_and_duplicate_dates(self):
        result = run(self.days, self.breadth, '2026-03-24', '2026-03-31', 'cash')
        self.assertEqual((result['net_return_percent'], result['max_drawdown_percent']), (0,0))
        days = copy.deepcopy(self.days)
        days[2]['date'] = days[1]['date']
        with self.assertRaisesRegex(ValueError, '重复'):
            run(days, self.breadth, '2026-03-24', '2026-03-31', 'cash')


if __name__ == '__main__':
    unittest.main()
