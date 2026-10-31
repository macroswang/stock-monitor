import unittest
from scripts.check_author_score_hypotheses import compare, metrics


class ScoreHypothesisTests(unittest.TestCase):
    def test_fixed_means_and_errors_use_author_values(self):
        rows = compare([{'date': '2026-10-22', 'score': 17}],
                       [{'date': '2026-10-22', 'p20': 11.5, 'p60': 15.3, 'p250': 11.3}])
        self.assertAlmostEqual(rows[0]['mean_two'], 13.4)
        self.assertAlmostEqual(rows[0]['mean_three'], 12.7)
        self.assertAlmostEqual(rows[0]['error_two'], -3.6)
        self.assertEqual(metrics(rows, 'error_two')['mae'], 3.6)

    def test_duplicate_or_mismatched_dates_are_rejected(self):
        s = [{'date': '2026-10-22', 'score': 17}]
        p = [{'date': '2026-10-22', 'p20': 11.5, 'p60': 15.3, 'p250': 11.3}]
        with self.assertRaisesRegex(ValueError, '重复'):
            compare(s * 2, p)
        with self.assertRaisesRegex(ValueError, '不一致'):
            compare(s, [])


if __name__ == '__main__':
    unittest.main()
