import hashlib
import json
import unittest

from scripts.research_cffex_official_history import OUT as CHECKED, parse
from scripts.research_cffex_official_series import OUT, totals


class ExchangeSeriesTests(unittest.TestCase):
    def test_archive_reproduces_all_days_and_crosschecked_dates(self):
        report = json.loads((OUT / 'report.json').read_text())
        checked = json.loads((CHECKED / 'report.json').read_text())
        self.assertEqual(report['errors'], [])
        self.assertEqual(len(report['expected']), 30)
        self.assertEqual([r['date'] for r in report['records']], report['expected'])
        for record in report['records']:
            raw = (OUT / f"{record['date']}.xml").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
            self.assertEqual(totals(parse(raw, record['date'])), record['groups'])
        original = {day['date']: day for day in checked['days']}
        for record in report['records'][-3:]:
            for prefix, summary in record['groups'].items():
                verified = original[record['date']]['groups'][prefix]
                self.assertEqual((summary['call'], summary['put']), (verified['call'], verified['put']))


if __name__ == '__main__':
    unittest.main()
