import unittest

from scripts.compare_author_trin_classifications import analyze
from scripts.trin_scope_diagnostics import compute


def row(code, up, is_st='0'):
    return {'date': '2026-10-28', 'code': code, 'isST': is_st, 'tradestatus': '1',
            'volume': '1000', 'amount': '10000', 'close': '11' if up else '9', 'preclose': '10'}


class ClassificationComparisonTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row('sh.600001', True, '1'), row('sh.600002', False),
                     row('sz.000001', True), row('sz.000002', False),
                     row('sh.688001', True), row('sh.688002', False),
                     row('sz.300001', True), row('sz.300002', False)]
        baseline = compute(self.rows, 'all', 'amount')
        self.history = [{'date': '2026-10-28', 'advance': baseline['advance'],
                         'decline': baseline['decline'], 'trin_amount': baseline['trin']}]
        self.payload = {'date': '2026-10-28', 'daily': self.rows}
        self.ref = [{'date': '2026-10-28', 'trin': .77}]

    def test_st_exclusion_is_separate_and_base_is_reconciled(self):
        report = analyze(self.ref, {'2026-10-28': self.payload}, self.history)
        values = {row['scope']: row for row in report['rows']}
        self.assertEqual(values['all']['advance'], 4)
        self.assertEqual(values['exclude_st']['advance'], 3)
        self.assertEqual(values['exclude_st']['decline'], 4)

    def test_missing_st_or_mismatched_baseline_is_rejected(self):
        broken = {'date': '2026-10-28', 'daily': [{**x, 'isST': ''} for x in self.rows]}
        with self.assertRaises(ValueError):
            analyze(self.ref, {'2026-10-28': broken}, self.history)
        with self.assertRaises(ValueError):
            analyze(self.ref, {'2026-10-28': self.payload}, [{**self.history[0], 'advance': 9}])


if __name__ == '__main__':
    unittest.main()
