import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.etf_option_pcr import CODE, KIND, ETFOptionPCR, parse_sse, parse_szse, valid
from core.provider import CN
from core.store import Store

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/author-trading-system-20261028'


class ETFOptionPCRTests(unittest.TestCase):
    def test_exchange_raw_samples_match_expected_totals(self):
        for day, sh, sz in [('2026-10-29', (2700191, 2594224), (1235126, 974791)),
                            ('2026-10-30', (3032822, 2786902), (1578181, 1139296))]:
            with self.subTest(day=day):
                compact = day.replace('-', '')
                payload = json.loads((DATA / f'sse-options-{compact}.json').read_text())
                self.assertEqual(parse_sse(payload, day), sh)
                self.assertEqual(parse_szse((DATA / f'szse-options-{compact}.xlsx').read_bytes()), sz)

    def test_missing_duplicate_wrong_date_and_inconsistent_totals_are_rejected(self):
        raw = json.loads((DATA / 'sse-options-20261030.json').read_text())
        cases = [copy.deepcopy(raw) for _ in range(4)]
        cases[0]['result'].pop()
        cases[1]['result'].append(cases[1]['result'][0])
        cases[2]['result'][0]['TRADE_DATE'] = '2026-10-29'
        cases[3]['result'][0]['TOTAL_VOLUME'] = '1'
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                parse_sse(case, '2026-10-30')

    def test_unpublished_szse_query_is_not_mistaken_for_a_daily_observation(self):
        response = (DATA / 'szse-options-unpublished-20261102.xlsx').read_bytes()
        with self.assertRaisesRegex(ValueError, '标的缺失'):
            parse_szse(response)

    def test_unpublished_szse_response_does_not_replace_previous_record(self):
        now = datetime(2026, 10, 31, 5, tzinfo=CN)
        sample = json.loads((ROOT / 'fixtures/etf-option-pcr-verified.json').read_text())[-1]
        payload = json.loads((DATA / 'sse-options-20261030.json').read_text())
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (DATA / 'szse-options-unpublished-20261102.xlsx').read_bytes()
        with tempfile.TemporaryDirectory() as tmp, patch('core.etf_option_pcr.HISTORY', Path(tmp) / 'none'):
            store = Store(Path(tmp) / 'db.sqlite3')
            try:
                store.cache(CODE, KIND, sample['date'], sample)
                service = ETFOptionPCR(store)
                with patch('core.etf_option_pcr.fetch_day', return_value=({}, payload)), patch('core.etf_option_pcr.urlopen', return_value=response):
                    service.refresh(now)
                self.assertIn('标的缺失', service.view(now)['error'])
                self.assertEqual(service.view(now)['days'][0]['pcr'], sample['pcr'])
            finally:
                store.db.close()

    def test_failure_preserves_verified_cache_and_recovery_updates_it(self):
        now = datetime(2026, 10, 31, 5, tzinfo=CN)
        sample = json.loads((ROOT / 'fixtures/etf-option-pcr-verified.json').read_text())[-1]
        with tempfile.TemporaryDirectory() as tmp, patch('core.etf_option_pcr.HISTORY', Path(tmp) / 'none'):
            store = Store(Path(tmp) / 'db.sqlite3')
            try:
                store.cache(CODE, KIND, sample['date'], sample)
                service = ETFOptionPCR(store)
                with patch('core.etf_option_pcr.collect', side_effect=[OSError('offline'), sample]):
                    service.refresh(now)
                    self.assertIn('获取失败', service.view(now)['error'])
                    self.assertEqual(service.view(now)['days'][0]['pcr'], sample['pcr'])
                    service.refresh(now)
                    self.assertEqual(service.view(now)['error'], '')
                    self.assertEqual(service.view(now)['days'][0]['date'], '2026-10-30')
            finally:
                store.db.close()

    def test_future_or_inconsistent_records_are_not_visible(self):
        sample = json.loads((ROOT / 'fixtures/etf-option-pcr-verified.json').read_text())[-1]
        now = datetime(2026, 10, 31, 5, tzinfo=CN)
        self.assertTrue(valid(sample, now))
        for change in ({'collected_at': '2026-10-31T06:00:00+08:00'},
                       {'collected_at': '2026-10-30T15:00:00+08:00'},
                       {'szse_call': 1}, {'pcr': 10}):
            self.assertFalse(valid({**sample, **change}, now))

    def test_corrupt_cache_does_not_mask_a_checked_fixture(self):
        now = datetime(2026, 10, 31, 5, tzinfo=CN)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db.sqlite3')
            try:
                store.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)', (CODE, KIND, '2026-10-30', 'null'))
                rows = ETFOptionPCR(store).view(now)['days']
                self.assertEqual(rows[-1]['date'], '2026-10-30')
                self.assertAlmostEqual(rows[-1]['pcr'], 0.8514845902290673)
            finally:
                store.db.close()

    def test_refresh_only_requests_the_latest_eligible_closed_day(self):
        rows = json.loads((ROOT / 'fixtures/etf-option-pcr-verified.json').read_text())
        with tempfile.TemporaryDirectory() as tmp, patch('core.etf_option_pcr.HISTORY', Path(tmp) / 'none'):
            store = Store(Path(tmp) / 'db.sqlite3')
            service = ETFOptionPCR(store)
            try:
                for now, sample, day in [(datetime(2026, 10, 30, 16, 29, tzinfo=CN), rows[0], '2026-10-29'),
                                         (datetime(2026, 10, 30, 16, 30, tzinfo=CN), rows[1], '2026-10-30')]:
                    recorded = {**sample, 'collected_at': f'{day}T16:30:00+08:00'}
                    with patch('core.etf_option_pcr.collect', return_value=recorded) as collector, patch('core.etf_option_pcr.now_cn', return_value=now):
                        service.refresh(now)
                        collector.assert_called_once_with(day, now)
                        self.assertEqual(service.view(now)['error'], '')
                        self.assertEqual(service.view(now)['days'][-1]['date'], day)
            finally:
                store.db.close()


if __name__ == '__main__':
    unittest.main()
