import gzip
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.breadth import Breadth, CODE, KIND
from core.store import Store


class RecordedCloseFallbackTests(unittest.TestCase):
    def test_recorded_live_snapshot_can_follow_reference_without_lookahead(self):
        fixture = Path(__file__).resolve().parents[1] / 'fixtures/market-core-rpc-20261030.json'
        recorded = json.loads(fixture.read_text())
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                store.cache(CODE, KIND, recorded['day']['date'], recorded['day'])
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat(recorded['finished_at'])):
                    view = Breadth(store).view()
                previous = next(x for x in view['days'] if x['date'] == '2026-10-29')
                current = next(x for x in view['days'] if x['date'] == '2026-10-30')
                self.assertEqual(current['status'], 'provisional')
                self.assertEqual(current['source'], previous['source'])
                self.assertFalse(current['adl_gap_before'])
                self.assertEqual(previous['ma_daily']['date'], '2026-10-29')
                self.assertNotIn('ma_daily', current)
            finally:
                store.db.close()

    def test_fresh_store_uses_one_recorded_close_without_writing_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-30T10:00:00+08:00')):
                    view = Breadth(store).view()
                row = next(x for x in view['days'] if x['date'] == '2026-10-29')
                self.assertEqual(row['status'], 'closed')
                self.assertEqual(row['covered'], 5222)
                self.assertIn('单来源', row['reconciliation_note'])
                self.assertAlmostEqual(row['ma_daily']['windows']['20']['percent'], 15.914351851851851)
                self.assertAlmostEqual(row['ma_daily']['windows']['60']['percent'], 14.137863698496387)
                self.assertEqual(store.query('SELECT * FROM cache'), [])
                self.assertEqual(store.query('SELECT * FROM watch'), [])
            finally:
                store.db.close()

    def test_future_or_corrupted_reference_is_not_shown(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-29T16:00:00+08:00')):
                    self.assertEqual(Breadth(store).view()['days'], [])
                bad = Path(directory) / 'bad.json.gz'
                bad.write_bytes(b'bad-data')
                bad.with_suffix('.sha256').write_text('0' * 64)
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.MA_CLOSE_REFERENCE', bad), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-30T10:00:00+08:00')):
                    self.assertEqual(Breadth(store).view()['days'], [])
            finally:
                store.db.close()

    def test_reference_does_not_bridge_a_later_missing_trading_day(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                store.cache('cn-ashare', 'breadth_raw_v1', '2026-11-03',
                            {'date': '2026-11-03', 'codes': ['sh600000'], 'suspended': [],
                             'collected_at': '2026-11-03T16:00:00+08:00',
                             'quotes': [{'code': 'sh600000', 'price': '11', 'previous_close': '10',
                                         'volume': 100, 'timestamp': '2026-11-03T15:00:00+08:00'}]})
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-11-04T10:00:00+08:00')):
                    view = Breadth(store).view()
                self.assertIn('缺少 2026-11-02', view['ma_note'])
                self.assertNotIn('2026-11-03', [row['date'] for row in view['days'] if row.get('ma_daily')])
            finally:
                store.db.close()

    def test_oct30_reference_only_after_collection_and_without_user_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                service = Breadth(store)
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T03:14:30+08:00')):
                    self.assertNotIn('2026-10-30', [r['date'] for r in service.view()['days']])
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T03:15:00+08:00')):
                    row = next(r for r in service.view()['days'] if r['date'] == '2026-10-30')
                self.assertEqual(row['ma_daily']['windows']['250']['above'], 387)
                self.assertEqual(row['ma_daily']['windows']['250']['eligible'], 4671)
                self.assertEqual(row['collected_at'], '2026-10-31T03:14:31.055070+08:00')
                self.assertEqual(store.query('SELECT * FROM cache'), [])
                self.assertEqual(store.query('SELECT * FROM watch'), [])
            finally:
                store.db.close()

    def test_oct30_incomplete_cache_uses_recorded_close_and_bad_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                store.cache(CODE, 'breadth_raw_v1', '2026-10-30',
                            {'date': '2026-10-30', 'codes': ['sh600000', 'sz000001'],
                             'suspended': [], 'collected_at': '2026-10-30T16:00:00+08:00',
                             'quotes': [{'code': 'sh600000', 'price': '11', 'previous_close': '10',
                                         'volume': 100, 'timestamp': '2026-10-30T15:00:00+08:00'}]})
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T04:00:00+08:00')):
                    row = next(r for r in Breadth(store).view()['days'] if r['date'] == '2026-10-30')
                self.assertEqual(row['ma_daily']['windows']['250']['above'], 387)
                bad = Path(directory) / 'bad.json.gz'
                bad.write_bytes(b'bad-data')
                bad.with_suffix('.sha256').write_text('0' * 64)
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.MA_CLOSE_REFERENCE_1030', bad), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T04:00:00+08:00')):
                    view = Breadth(store).view()
                self.assertNotIn('2026-10-30', [r['date'] for r in view['days']])
                self.assertIn('暂未更新', view['ma_note'])
            finally:
                store.db.close()

    def test_oct30_complete_cached_close_takes_precedence(self):
        fixture = Path(__file__).resolve().parents[1] / 'fixtures/ma-reference-2026-10-30.json.gz'
        with gzip.open(fixture, 'rt', encoding='utf-8') as stream:
            raw = json.load(stream)
        raw['collected_at'] = '2026-10-31T03:30:00+08:00'
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                store.cache(CODE, 'breadth_raw_v1', raw['date'], raw)
                with patch('core.breadth.HISTORY', Path('/missing-history.json')), \
                     patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T04:00:00+08:00')):
                    row = next(r for r in Breadth(store).view()['days'] if r['date'] == raw['date'])
                self.assertEqual(row['ma_daily']['collected_at'], raw['collected_at'])
            finally:
                store.db.close()


if __name__ == '__main__':
    unittest.main()
