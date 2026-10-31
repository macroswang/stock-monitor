import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.check_author_episode23 import analyze, rounded

ROOT = Path(__file__).resolve().parents[1]


class AuthorEpisode23Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = ROOT / 'docs/author-episode23-20261029'
        cls.tencent = json.loads((directory / 'tencent-index.json').read_text())
        cls.sina = json.loads((directory / 'sina-index.json').read_text())

    def test_seven_video_results_and_forward_statistics(self):
        result = analyze(self.tencent, self.sina)
        self.assertEqual(result['sample_count'], 7)
        self.assertEqual(result['source_rows'], 83)
        self.assertEqual(result['samples'][-1]['10']['end_date'], '2024-09-09')
        self.assertEqual(str(rounded(result['samples'][-1]['10']['tencent_return'])), '-4.17')
        self.assertEqual(result['samples'][-1]['20']['end_date'], '2024-09-25')
        self.assertEqual(str(rounded(result['samples'][-1]['20']['tencent_return'])), '1.43')
        self.assertEqual(result['aug26_20day_low_close']['date'], '2024-09-13')
        self.assertEqual(result['stats']['20']['wins'], 1)
        self.assertEqual(result['stats']['3']['wins'], 5)

    def test_cross_source_date_and_price_mismatches_are_rejected(self):
        wrong = deepcopy(self.sina)
        row = next(x for x in wrong if x['day'] == '2024-06-12')
        row['close'] = '9999'
        with self.assertRaisesRegex(ValueError, '收盘价'):
            analyze(self.tencent, wrong)
        wrong = [x for x in self.sina if x['day'] != '2024-06-12']
        with self.assertRaisesRegex(ValueError, '日期'):
            analyze(self.tencent, wrong)


if __name__ == '__main__':
    unittest.main()
