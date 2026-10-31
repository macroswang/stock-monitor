import json
import unittest

from scripts.audit_trin_interpretation_differences import INPUTS, OUTPUT, chart_band, compare


class TrinInterpretationDifferenceTests(unittest.TestCase):
    def test_boundaries_match_current_chart(self):
        self.assertEqual(chart_band(.6999), '0.6至0.7')
        self.assertEqual(chart_band(.7), '0.7至0.9')
        self.assertEqual(chart_band(.9), '0.9至1.1')
        self.assertEqual(chart_band(1.1), '0.9至1.1')
        self.assertEqual(chart_band(1.1001), '高于1.1')
        with self.assertRaises(ValueError):
            chart_band(float('nan'))

    def test_report_reproduces_known_differences(self):
        rows = compare([json.loads(path.read_text())['rows'] for path in INPUTS])
        report = json.loads(OUTPUT.read_text())
        self.assertEqual(rows, report['rows'])
        self.assertEqual([r['date'] for r in rows if r['chart_band_differs']], ['2026-09-18', '2026-10-26'])
        self.assertEqual([r['date'] for r in rows if r['one_boundary_differs']], ['2026-10-23'])


if __name__ == '__main__':
    unittest.main()
