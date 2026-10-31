import json
import unittest
from pathlib import Path

from scripts.compare_author_march_trin import compare


class AuthorMarchTrinTest(unittest.TestCase):
    def test_reference_matches_independent_history_and_missing_is_rejected(self):
        root=Path(__file__).resolve().parents[1]
        authors=json.loads((root/'fixtures/author-trin-march-reference.json').read_text())
        history=json.loads((root/'fixtures/breadth-history-verified.json').read_text())
        rows=compare(authors,history)
        self.assertEqual([r['author_trin_shown'] for r in rows],['0.31','3.04','1.4'])
        self.assertAlmostEqual(rows[1]['amount_trin'],3.1963001378190183)
        self.assertAlmostEqual(rows[2]['shares_trin'],1.4504815980203614)
        with self.assertRaises(ValueError):compare(authors,[])


if __name__=='__main__':unittest.main()
