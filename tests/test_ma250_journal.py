import unittest
from scripts.report_ma250_journal import evaluate, mark, summary
from tests.test_ma250_pullback import bar, next_day, strong_case


class JournalReportTest(unittest.TestCase):
    def test_forward_outcomes_use_the_next_open_and_leave_pending_rows(self):
        bars, day = strong_case()
        for offset in range(1, 26):
            stamp = next_day(bars[-1]['date'])
            bars.append(bar(stamp, bars[-1]['close'] + 0.05 * offset))
        journal = [dict(code='sh600000', day=day,
                        data=dict(signal=dict(strong=True, strong_reasons=[]), market_above=True))]
        rows = evaluate(journal, {'sh600000': bars})
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['strong'])
        self.assertIsNotNone(rows[0]['forward']['20'])
        self.assertIsNone(rows[0]['forward']['60'])
        item = summary(rows)
        self.assertEqual(item['samples'], 1)
        self.assertEqual(item['pending'], 0)
        text = mark(rows)
        self.assertIn('强信号', text)
        self.assertIn('20日均值', text)

    def test_a_signal_without_a_future_bar_is_not_counted_as_zero(self):
        bars, day = strong_case()
        journal = [dict(code='sh600000', day=day,
                        data=dict(signal=dict(strong=True, strong_reasons=[]), market_above=True))]
        rows=evaluate(journal, {'sh600000': bars})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'pending_entry')
        self.assertEqual(summary(rows)['samples'],0)
        self.assertEqual(summary(rows)['pending'],1)


if __name__ == '__main__':
    unittest.main()
