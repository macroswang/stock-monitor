import hashlib
import json
import unittest

from scripts.research_cfachina_option_crosscheck import OUT as CFA_OUT
from scripts.research_cfachina_pobo_crosscheck import OUT, compare
from scripts.research_cffex_coverage import parse_close


class PoboCloseCrosscheckTests(unittest.TestCase):
    def test_archived_tables_match_dated_association_snapshot(self):
        report = json.loads((OUT / 'report.json').read_text())
        for prefix in ('IO', 'HO', 'MO'):
            raw = (OUT / f'{prefix}.html').read_bytes()
            cfa_raw = (CFA_OUT / f'{prefix}.json').read_bytes()
            entry = report['groups'][prefix]
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['close_sha256'])
            self.assertEqual(hashlib.sha256(cfa_raw).hexdigest(), entry['cfa_sha256'])
            actual = compare(prefix, raw, json.loads(cfa_raw))
            for key, value in actual.items():
                self.assertEqual(value, entry[key])
            self.assertFalse(actual['volume_mismatch'])
            self.assertFalse(actual['close_mismatch_on_nonblank_volume'])
            self.assertTrue(all(row['association_volume'] == 0 for row in actual['missing_close_volume']))

    def test_wrong_product_and_date_are_rejected(self):
        payload = (OUT / 'HO.html').read_bytes()
        with self.assertRaises(ValueError):
            parse_close(payload, 'MO')
        with self.assertRaises(ValueError):
            parse_close(payload.replace('2026年10月30日'.encode(), '2026年10月29日'.encode()), 'HO')


if __name__ == '__main__':
    unittest.main()
