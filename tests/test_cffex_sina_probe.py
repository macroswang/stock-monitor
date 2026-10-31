import hashlib
import json
import unittest
from pathlib import Path

from scripts.research_cffex_sina_probe import SYMBOLS, parse_dayline

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/author-trading-system-20261028/cffex-sina-probe-20261031'


class SinaOptionProbeTests(unittest.TestCase):
    def test_saved_responses_reproduce_report_and_have_unique_contracts(self):
        report = json.loads((DATA / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['errors'], [])
        self.assertEqual({r['symbol'] for r in report['rows']}, set(SYMBOLS))
        for row in report['rows']:
            raw = (DATA / row['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            self.assertEqual(parse_dayline(raw.decode('utf-8'), row['symbol']), row['days'])

    def test_reject_wrong_contract_missing_or_invalid_values(self):
        data = (DATA / 'io2703C3600.txt').read_text(encoding='utf-8')
        with self.assertRaises(ValueError):
            parse_dayline(data, 'io2703C3700')
        with self.assertRaises(ValueError):
            parse_dayline(data.replace('2026-10-30', '2026-10-31'), 'io2703C3600')
        with self.assertRaises(ValueError):
            parse_dayline(data.replace('"v":"58"', '"v":"-58"'), 'io2703C3600')


if __name__ == '__main__':
    unittest.main()
