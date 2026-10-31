import unittest
from unittest.mock import patch

from scripts.research_p250_history import before
from scripts.research_p250_quote_bridge import replay


class QuoteBridgeTest(unittest.TestCase):
    def test_current_previous_close_mismatch_is_not_silently_joined(self):
        days = before('2026-10-27', 249)
        raw = {'date': '2026-10-27', 'collected_at': '2026-10-27T16:00:00+08:00',
               'codes': ['sh600001'], 'suspended': [],
               'quotes': [{'code': 'sh600001', 'price': '11', 'previous_close': '9', 'volume': 100}]}
        summary = {'missing': 0, 'status': 'closed', 'first_quote': None, 'last_quote': None}
        rows = [{'symbol': '600001.SH', 'close': '10', 'pre_close': '10'}]
        with patch('scripts.research_p250_quote_bridge.summarize', return_value=summary):
            result, _ = replay(days, lambda _: rows, raw, 'closed')
        self.assertEqual(result['current_previous_close_mismatches'], 1)
        self.assertEqual(result['models']['unadjusted_all']['250']['above'], 1)
        self.assertEqual(result['models']['unadjusted_prevclose_checked']['250']['eligible'], 0)
        self.assertEqual(result['models']['reset_on_discontinuity']['250']['eligible'], 0)

    def test_missing_trading_day_fails(self):
        days = before('2026-10-27', 249)
        days[-2] = days[-3]
        with self.assertRaisesRegex(ValueError, 'trading-day gap'):
            replay(days, lambda _: [], {'date': '2026-10-27'}, 'closed')


if __name__ == '__main__':
    unittest.main()
