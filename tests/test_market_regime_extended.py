import json
import unittest
from scripts.research_market_regime_extended import load_breadth, load_index, P250, ROOT


class ExtendedResearchTest(unittest.TestCase):
    def test_stock_overlap_is_matched_and_retains_quality_labels(self):
        rows, overlaps = load_breadth()
        collection=json.loads((P250/'baostock-collection.json').read_text())
        verified=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text())
        expected=sorted(set(collection['expected']) & {r['date'] for r in verified})
        self.assertEqual(overlaps,expected)
        self.assertTrue({'2026-03-23','2026-03-24','2026-03-25'}.issubset(overlaps))
        self.assertEqual((rows['2026-03-23']['advance'],rows['2026-03-23']['decline']),(290,4886))
        self.assertAlmostEqual(rows['2026-03-23']['trin'],0.31720385730179546)
        self.assertEqual(rows['2026-01-05']['source'],'BaoStock; TDX checked close only')

    def test_two_source_index_calendar_and_20_day_mean(self):
        rows=load_index()
        self.assertEqual(rows[0]['date'],'2025-09-01')
        self.assertEqual(rows[-1]['date'],'2026-10-29')
        self.assertIsNone(rows[18]['ma20'])
        self.assertAlmostEqual(rows[19]['ma20'],sum(r['close'] for r in rows[:20])/20)


if __name__=='__main__':unittest.main()
