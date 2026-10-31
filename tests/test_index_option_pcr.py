import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from core.app import App
from core.index_option_pcr import IndexOptionPCR, parse_association, parse_exchange
from core.provider import CN

ROOT = Path(__file__).resolve().parent.parent
EXCHANGE = ROOT / 'docs/author-trading-system-20261028/cffex-official-history-20261031/2026-10-30.xml'
CFA = ROOT / 'docs/author-trading-system-20261028/cfachina-crosscheck-20261031'


class IndexOptionPCRTests(unittest.TestCase):
    def test_exchange_and_association_match_every_contract(self):
        groups = parse_exchange(EXCHANGE.read_bytes(), '2026-10-30')
        for product in ('IO', 'HO', 'MO'):
            payload = json.loads((CFA / f'{product}.json').read_text())
            self.assertEqual(parse_association(payload, product, '2026-10-30'), groups[product])
            with self.assertRaises(ValueError):
                parse_association(payload, product, '2026-10-29')
        with self.assertRaises(ValueError):
            parse_exchange(EXCHANGE.read_bytes(), '2026-10-29')

    def test_seed_matches_crosschecked_exchange_report(self):
        rows = json.loads((ROOT / 'fixtures/cffex-index-pcr-verified.json').read_text())
        report = json.loads((ROOT / 'docs/author-trading-system-20261028/cffex-20-crosscheck-20261031/report.json').read_text())
        days = {row['date']: row for row in report['days']}
        self.assertEqual(len(rows), 54)
        self.assertEqual(report['errors'], [])
        for row in rows:
            group = days[row['date']]['groups'][row['product']]
            self.assertEqual((row['call_volume'], row['put_volume'], row['contracts']),
                             (group['call'], group['put'], group['contracts']))
            self.assertEqual(row['exchange_sha256'], days[row['date']]['exchange_sha256'])
            self.assertEqual(row['pobo_sha256'], group['pobo_sha256'])

    def test_fixture_only_available_after_capture_and_errors_keep_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            app = App(directory, start_worker=False)
            service = IndexOptionPCR(app.store)
            before = datetime(2026,10,31,5,52,tzinfo=CN)
            after = datetime(2026,10,31,6,0,tzinfo=CN)
            self.assertEqual(service.view('IO', before)['days'], [])
            rows = service.view('IO', after)['days']
            self.assertEqual([r['date'] for r in rows], ['2026-10-28','2026-10-29','2026-10-30'])
            self.assertAlmostEqual(rows[-1]['pcr'], 0.6119273433)
            self.assertIsNone(rows[-1]['band_lower'])
            seed = json.loads((ROOT / 'fixtures/cffex-index-pcr-verified.json').read_text())
            capture = max(datetime.fromisoformat(row['collected_at']) for row in seed)
            self.assertEqual(len(service.view('IO', capture-timedelta(seconds=1))['days']), 3)
            verified = service.view('IO', capture+timedelta(seconds=1))['days']
            self.assertEqual(len(verified), 18)
            self.assertEqual(verified[0]['date'], '2026-09-30')
            self.assertIsNone(verified[-1]['band_lower'])
            with patch('core.index_option_pcr.collect', side_effect=ValueError('模拟核对失败')):
                service.refresh(after)
            self.assertEqual(service.view('IO', after)['error'], '模拟核对失败')
            self.assertEqual(service.view('IO', after)['days'], rows)
            with self.assertRaises(ValueError):
                service.view('other', after)
            app.store.db.close()

    def test_reject_mismatched_association_volume(self):
        payload = json.loads((CFA / 'IO.json').read_text())
        payload['data']['delayList'][0]['volume'] = '--'
        with self.assertRaises(ValueError):
            parse_association(payload, 'IO', '2026-10-30')


if __name__ == '__main__':
    unittest.main()
