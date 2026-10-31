import hashlib
import json
import unittest
from pathlib import Path

from scripts.research_cffex_coverage import MONTHS, parse_chain, parse_close
from scripts.research_cffex_sina_probe import parse_dayline

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/author-trading-system-20261028/cffex-coverage-20261031'
PROBE = ROOT / 'docs/author-trading-system-20261028/cffex-sina-probe-20261031'


class CoverageTests(unittest.TestCase):
    def test_saved_inputs_reproduce_coverage_and_preserve_blank_volume(self):
        report = json.loads((DATA / 'report.json').read_text(encoding='utf-8'))
        for filename, expected in report['files_sha256'].items():
            self.assertEqual(hashlib.sha256((DATA / filename).read_bytes()).hexdigest(), expected)
        close = parse_close((DATA / 'pobo-20261030.html').read_bytes())
        chain = set()
        for month in MONTHS:
            codes = parse_chain((DATA / f'{month}.json').read_bytes(), month)
            self.assertFalse(chain & codes)
            chain.update(codes)
        self.assertEqual(len(close), 268)
        self.assertEqual(chain, set(close))
        self.assertEqual(len(report['missing_volume']), 19)
        self.assertTrue(all(close[code]['volume'] is None for code in report['missing_volume']))
        samples = json.loads((PROBE / 'report.json').read_text(encoding='utf-8'))
        for row, probe in zip(report['sample_comparison'], samples['rows']):
            actual = parse_dayline((PROBE / probe['file']).read_text(encoding='utf-8'), probe['symbol'])['2026-10-30']
            self.assertEqual(row['sina'], actual)
            self.assertEqual(row['pobo'], close[row['code']])
            self.assertTrue(row['close_equal'])
            self.assertFalse(row['volume_equal'])

    def test_close_parser_rejects_duplicate_contract_and_wrong_date(self):
        row = '<tr>' + ''.join(f'<td>{v}</td>' for v in ['IO2703-C-3600','1','1','1','1','1','1','1','1']) + '</tr>'
        head = '中国金融期货交易所10月30日IO期权收盘行情 2026年10月30日'
        with self.assertRaises(ValueError):
            parse_close((head + row + row).encode())
        with self.assertRaises(ValueError):
            parse_close(('中国金融期货交易所10月29日IO期权收盘行情 2026年10月29日' + row).encode())


if __name__ == '__main__':
    unittest.main()
