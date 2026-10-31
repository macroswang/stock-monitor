import hashlib
import json
import unittest
from pathlib import Path

from scripts.research_cffex_coverage import parse_close
from scripts.research_cffex_eastmoney_probe import compare, parse_snapshot

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/author-trading-system-20261028'
DATA = BASE / 'cffex-eastmoney-probe-20261031'


class EastmoneyOptionProbeTests(unittest.TestCase):
    def test_saved_snapshot_reproduces_cross_source_comparison(self):
        report = json.loads((DATA / 'report.json').read_text(encoding='utf-8'))
        raw = (DATA / 'eastmoney.json').read_bytes()
        close = (BASE / 'cffex-coverage-20261031/pobo-20261030.html').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), report['snapshot_sha256'])
        self.assertEqual(hashlib.sha256(close).hexdigest(), report['close_table_sha256'])
        actual = compare(parse_snapshot(raw), parse_close(close))
        for key, value in actual.items():
            self.assertEqual(value, report[key])
        self.assertEqual(actual['snapshot_count'], 268)
        self.assertEqual(actual['only_snapshot'], [])
        self.assertEqual(actual['only_close'], [])
        self.assertEqual(actual['volume_mismatches'], [])
        self.assertEqual(actual['price_mismatches_on_nonblank'], [])
        self.assertEqual(len(actual['blank_close_volume']), 19)
        self.assertTrue(all(item['snapshot_volume'] == 0 for item in actual['blank_close_volume']))

    def test_reject_incomplete_duplicate_and_invalid_volume(self):
        base = {'total': 1, 'list': [{'dm': 'IO2703-C-3600', 'sc': 221, 'vol': 70, 'p': 354.2}]}
        for value in (-1, True, None, '70'):
            changed = json.loads(json.dumps(base))
            changed['list'][0]['vol'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_snapshot(json.dumps(changed).encode())
        incomplete = {'total': 2, 'list': base['list']}
        duplicate = {'total': 2, 'list': base['list'] * 2}
        for data in (incomplete, duplicate):
            with self.assertRaises(ValueError):
                parse_snapshot(json.dumps(data).encode())


if __name__ == '__main__':
    unittest.main()
