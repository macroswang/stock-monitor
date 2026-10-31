import hashlib
import json
import unittest

from scripts.research_cffex_coverage import parse_close
from scripts.research_pobo_option_history import OUT as POBO, summarize
from scripts.research_tenagent_pobo import OUT as TEN, compare


class DatedOptionHistoryTests(unittest.TestCase):
    def test_archived_tables_keep_unknown_volumes(self):
        report = json.loads((POBO / 'report.json').read_text())
        self.assertEqual(len(report['tables']), 9)
        for row in report['tables']:
            raw = (POBO / row['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            data = parse_close(raw, row['kind'], row['date'])
            self.assertEqual(len(data), row['contracts'])
            self.assertEqual(summarize(data), {k: row[k] for k in ('call', 'put')})
            self.assertGreater(sum(row[k]['missing_contracts'] for k in ('call', 'put')), 0)
            with self.assertRaises(ValueError):
                parse_close(raw, row['kind'], '2026-10-27')

    def test_crosscheck_preserves_empty_pobo_value(self):
        report = json.loads((TEN / 'report.json').read_text())
        raw = (TEN / 'tenagent.html').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), report['source_sha256'])
        for prefix in ('IO', 'MO'):
            pobo_raw = (POBO / f'2026-10-29-{prefix}.html').read_bytes()
            self.assertEqual(hashlib.sha256(pobo_raw).hexdigest(), report['groups'][prefix]['pobo_sha256'])
            rows = compare(raw, prefix, parse_close(pobo_raw, prefix, '2026-10-29'))
            self.assertEqual(rows, report['groups'][prefix]['rows'])
        mo = report['groups']['MO']['rows']
        row = next(r for r in mo if r['code'] == 'MO2703-P-8400')
        self.assertIsNone(row['pobo'])
        self.assertEqual(row['tenagent'], 0)


if __name__ == '__main__':
    unittest.main()
