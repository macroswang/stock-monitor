import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import analyze_p250_baostock as research


class SourceGateTest(unittest.TestCase):
    def test_substituted_date_cannot_pass_full_history_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / 'research'
            earlier = root / 'docs/author-mcl-history-20261029'
            later = root / 'docs/trin-sensitivity-20261028'
            for directory in (out, earlier, later):
                directory.mkdir(parents=True)
            expected = [f'day-{i}' for i in range(171)]
            records = {day: {} for day in expected}
            del records[expected[0]]
            records['different-day'] = {}
            (out / 'baostock-collection.json').write_text(json.dumps({
                'expected': expected, 'records': records, 'failures': {}}))
            (earlier / 'collection.json').write_text(json.dumps({'expected': [], 'failures': {}}))
            (later / 'summary.json').write_text(json.dumps({'results': [], 'failed': []}))
            with patch.object(research, 'OUT', out), patch.object(research, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'BaoStock history incomplete'):
                    research.main()
            self.assertFalse((out / 'baostock-comparison.json').exists())


if __name__ == '__main__':
    unittest.main()
