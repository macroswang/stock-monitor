import json
import unittest
from pathlib import Path

from scripts.compare_author_trin_table import AUTHORS, ROOT, compare


class AuthorTrinComparisonTests(unittest.TestCase):
    def test_ten_cited_dates_compare_without_inventing_author_values(self):
        history=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text(encoding='utf-8'))
        rows=compare(history)
        self.assertEqual(len(rows),10)
        self.assertEqual([r['date'] for r in rows],[r['date'] for r in AUTHORS])
        r=next(x for x in rows if x['date']=='2026-09-21')
        self.assertEqual(r['author_trin'],1.69)
        self.assertAlmostEqual(r['shares_trin'],.942,places=3)
        self.assertAlmostEqual(r['amount_trin'],1.840,places=3)
        last=next(x for x in rows if x['date']=='2026-10-28')
        self.assertEqual(last['author_trin'],.77)
        self.assertAlmostEqual(last['shares_trin'],1.410,places=3)
        self.assertAlmostEqual(last['amount_trin'],.878,places=3)
        self.assertTrue(all(r['amount_error']<r['shares_error'] for r in rows))

    def test_missing_or_incomplete_cross_checked_day_is_rejected(self):
        history=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text(encoding='utf-8'))
        with self.assertRaises(KeyError):compare([x for x in history if x['date']!='2026-09-21'])
        modified=[dict(x,missing=1) if x['date']=='2026-09-21' else x for x in history]
        with self.assertRaises(ValueError):compare(modified)


if __name__=='__main__':unittest.main()
