import copy
import hashlib
import json
import unittest
from pathlib import Path

from scripts.research_cfachina_option_crosscheck import EAST, KINDS, OUT, compare, parse


class AssociationOptionCrosscheckTests(unittest.TestCase):
    def test_saved_responses_reproduce_the_crosscheck(self):
        report = json.loads((OUT / 'report.json').read_text())
        east_raw = EAST.read_bytes()
        self.assertEqual(hashlib.sha256(east_raw).hexdigest(), report['eastmoney_sha256'])
        rows = json.loads(east_raw)['list']
        for prefix in KINDS:
            raw = (OUT / f'{prefix}.json').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), report['groups'][prefix]['sha256'])
            association = parse(json.loads(raw), prefix, '2026-10-30')
            east = {row['dm']: row['vol'] for row in rows if row['dm'].startswith(prefix)}
            result = compare(association, east)
            for name, value in result.items():
                self.assertEqual(value, report['groups'][prefix][name])
            self.assertEqual(result['volume_mismatch'], [])

    def test_reject_wrong_date_duplicate_missing_and_non_numeric_volume(self):
        raw = json.loads((OUT / 'IO.json').read_text())
        for edit in ('date', 'duplicate', 'missing', 'volume'):
            sample = copy.deepcopy(raw)
            if edit == 'date':
                sample['data']['delayList'][0]['tradeDate'] = '2026-10-29'
            elif edit == 'duplicate':
                sample['data']['delayList'].append(sample['data']['delayList'][0])
            elif edit == 'missing':
                sample['data']['delayList'].pop()
            else:
                sample['data']['delayList'][0]['volume'] = '--'
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                parse(sample, 'IO', '2026-10-30')


if __name__ == '__main__':
    unittest.main()
