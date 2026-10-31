import unittest

from scripts.compare_author_trin_scopes import analyze


def row(code, close, previous, volume, amount):
    return {'trade_date': '20261028', 'symbol': code, 'close': str(close),
            'pre_close': str(previous), 'high': '12', 'low': '8',
            'vol': str(volume), 'amount': str(amount)}


class AuthorTrinScopeTests(unittest.TestCase):
    def test_exchange_scope_changes_totals_without_changing_formula(self):
        rows = [row('600000.SH', 10, 9, 100, 100),
                row('000001.SZ', 10, 11, 100, 100),
                row('830000.BJ', 10, 9, 100, 100)]
        report = analyze([{'date': '2026-10-28', 'trin': 0.77}], {'2026-10-28': rows})
        by_scope = {item['scope']: item for item in report['rows']}
        self.assertEqual(by_scope['shsz_ex_cdr']['counts']['up'], 1)
        self.assertEqual(by_scope['shszbj_ex_cdr']['counts']['up'], 2)
        self.assertEqual(by_scope['shsz_ex_cdr']['trin_amount'], 1.0)
        self.assertEqual(by_scope['shszbj_ex_cdr']['trin_amount'], 1.0)

    def test_duplicate_or_mismatched_date_is_rejected(self):
        one = row('600000.SH', 10, 9, 100, 100)
        ref = [{'date': '2026-10-28', 'trin': 0.77}]
        with self.assertRaises(ValueError):
            analyze(ref, {'2026-10-28': [one, one]})
        with self.assertRaises(ValueError):
            analyze(ref, {'2026-10-28': [{**one, 'trade_date': '20261027'}]})


if __name__ == '__main__':
    unittest.main()
