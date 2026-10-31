import hashlib
import json
import unittest

from scripts.research_cffex_official_history import OUT, compare, parse
from scripts.research_cffex_coverage import parse_close
from scripts.research_pobo_option_history import OUT as POBO


class ExchangeHistoryTests(unittest.TestCase):
    def test_saved_exchange_and_close_tables_reproduce_results(self):
        report = json.loads((OUT / 'report.json').read_text())
        for day in report['days']:
            raw = (OUT / f"{day['date']}.xml").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), day['sha256'])
            groups = parse(raw, day['date'])
            for prefix, entry in day['groups'].items():
                close = (POBO / f"{day['date']}-{prefix}.html").read_bytes()
                self.assertEqual(hashlib.sha256(close).hexdigest(), entry['pobo_sha256'])
                result = compare(groups[prefix], parse_close(close, prefix, day['date']))
                for key, value in result.items():
                    self.assertEqual(value, entry[key])
                self.assertFalse(result['volume_mismatch'])
                self.assertFalse(result['price_mismatch'])
                self.assertTrue(all(row['exchange_volume'] == 0 for row in result['pobo_blank']))

    def test_wrong_day_and_incomplete_product_are_rejected(self):
        raw = (OUT / '2026-10-29.xml').read_bytes()
        with self.assertRaises(ValueError):
            parse(raw, '2026-10-28')
        with self.assertRaises(ValueError):
            parse(raw.replace(b'<productid>MO</productid>', b'<productid>OTHER</productid>'), '2026-10-29')


if __name__ == '__main__':
    unittest.main()
