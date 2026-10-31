import unittest
from decimal import Decimal

from scripts.research_low_trin_entry import evaluate, non_overlapping, summarize
from scripts.compare_low_trin_baseline import compare_groups


class EntryStudyTests(unittest.TestCase):
    def test_profit_is_net_of_both_costs_and_follows_signal(self):
        index = [{'date': f'2026-02-{i:02}'} for i in range(1, 9)]
        etf = {row['date']: [row['date'], '4.000', '4.000', '4.100', '3.900'] for row in index}
        etf['2026-02-07'][1] = '4.050'
        rows = [{'date': '2026-02-01', 'weak_low_trin': True, 'breadth': 10, 'trin': .5}]
        out = evaluate(rows, index, etf)
        event = out['events'][0]
        self.assertEqual((event['entry_date'], event['exit_date']), ('2026-02-02', '2026-02-07'))
        self.assertEqual(Decimal(event['net_yuan']), Decimal('230.00'))
        self.assertEqual(out['all']['positive'], 1)

    def test_nonoverlap_selection_and_empty_summary(self):
        events = [{'signal_date': '2026-01-01', 'exit_date': '2026-01-08'},
                  {'signal_date': '2026-01-05', 'exit_date': '2026-01-12'},
                  {'signal_date': '2026-01-08', 'exit_date': '2026-01-15'}]
        self.assertEqual(len(non_overlapping(events)), 2)
        self.assertIsNone(summarize([])['average_net_yuan'])

    def test_comparison_uses_identical_window_and_disjoint_weak_subgroups(self):
        index = [{'date': f'2026-02-{i:02}'} for i in range(1, 11)]
        etf = {row['date']: [row['date'], '4.000', '4.000', '4.100', '3.900'] for row in index}
        rows = [{'date': '2026-02-01', 'weak': True, 'trin': .5, 'breadth': 10},
                {'date': '2026-02-02', 'weak': True, 'trin': .8, 'breadth': 10},
                {'date': '2026-02-03', 'weak': False, 'trin': .5, 'breadth': 30}]
        groups = compare_groups(rows, index, etf)
        self.assertEqual(groups['all_dates']['all']['n'], 3)
        self.assertEqual(groups['weak_low_trin']['all']['n'], 1)
        self.assertEqual(groups['weak_other_trin']['all']['n'], 1)
        self.assertEqual(groups['not_weak']['all']['n'], 1)
        self.assertTrue(all(g['all']['average_net_yuan'] == '-20.00' for g in groups.values()))


if __name__ == '__main__':
    unittest.main()
