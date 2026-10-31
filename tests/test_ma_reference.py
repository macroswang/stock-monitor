import gzip
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.breadth import Breadth, _next_verified_trading_day, summarize
from core.ma_reference import calculate, load_seed
from core.store import Store


def quote(code, price, previous, day, time='15:00:00'):
    return {'code': code, 'price': str(price), 'previous_close': str(previous),
            'volume': 100, 'timestamp': f'{day}T{time}+08:00'}


def snapshot(day, quotes, clock='15:20:00', suspended=()):
    return {'date': day, 'quotes': quotes, 'codes': [q['code'] for q in quotes] + list(suspended),
            'suspended': list(suspended), 'collected_at': f'{day}T{clock}+08:00'}


class MaReferenceTests(unittest.TestCase):
    def setUp(self):
        reference = patch('core.breadth.MA_CLOSE_REFERENCE', new=Path('/nonexistent-close-reference.json.gz'))
        reference.start()
        self.addCleanup(reference.stop)
        reference_1030 = patch('core.breadth.MA_CLOSE_REFERENCE_1030', new=Path('/nonexistent-close-reference-1030.json.gz'))
        reference_1030.start()
        self.addCleanup(reference_1030.stop)
        self.seed = {'end_date': '2026-10-28', 'stocks': {
            'sh600000': [1000] * 249, 'sz000001': [1000] * 249,
            'sz000002': [1000] * 249}}

    def test_close_excludes_previous_close_mismatch(self):
        day = '2026-10-29'
        raw = snapshot(day, [quote('sh600000', 11, 10, day), quote('sz000001', 11, 9, day)], suspended=['sz000002'])
        result = calculate(self.seed, [raw], _next_verified_trading_day, summarize)
        self.assertEqual(result[0]['status'], 'closed')
        self.assertEqual(result[0]['previous_close_mismatches'], 1)
        self.assertEqual(result[0]['windows']['250'], {'eligible': 1, 'above': 1, 'percent': 100.0})
        self.assertEqual(len(self.seed['stocks']['sh600000']), 249)

    def test_seed_digest_failure_cannot_be_used(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'seed.json.gz'
            seed = {'version': 1, 'session_count': 249, 'end_date': '2026-10-28',
                    'stocks': {f'sh{600000 + i:06d}': [1000] for i in range(4000)}}
            path.write_bytes(gzip.compress(json.dumps(seed).encode()))
            path.with_suffix('.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(len(load_seed(path)['stocks']), 4000)
            path.with_suffix('.sha256').write_text('0' * 64)
            with self.assertRaisesRegex(ValueError, '校验失败'):
                load_seed(path)

    def test_provisional_and_gap_do_not_become_closed_history(self):
        day = '2026-10-29'
        provisional = snapshot(day, [quote('sh600000', 11, 10, day, '14:00:00')], clock='14:01:00')
        self.assertEqual(calculate(self.seed, [provisional], _next_verified_trading_day, summarize), [])
        result = calculate(self.seed, [provisional], _next_verified_trading_day, summarize, allow_provisional=True)
        self.assertEqual(result[0]['status'], 'provisional')
        gap = snapshot('2026-11-02', [quote('sh600000', 11, 10, '2026-11-02')])
        self.assertEqual(calculate(self.seed, [gap], _next_verified_trading_day, summarize), [])

    def test_invalid_later_snapshot_preserves_prior_result(self):
        day = '2026-10-29'
        valid = snapshot(day, [quote('sh600000', 11, 10, day)])
        broken = snapshot('2026-10-30', [quote('sh600000', 12, 11, '2026-10-30')])
        broken['codes'].append('sz000001')
        result = calculate(self.seed, [valid, broken], _next_verified_trading_day, summarize)
        self.assertEqual([r['date'] for r in result], [day])

    def test_future_collection_or_future_quote_cannot_become_close(self):
        day = '2026-10-29'
        raw = snapshot(day, [quote('sh600000', 11, 10, day)])
        now = datetime.fromisoformat('2026-10-29T14:00:00+08:00')
        self.assertEqual(calculate(self.seed, [raw], _next_verified_trading_day, summarize, as_of=now), [])
        raw['quotes'][0]['timestamp'] = '2026-10-29T15:30:00+08:00'
        self.assertEqual(calculate(self.seed, [raw], _next_verified_trading_day, summarize), [])

    def test_service_explains_missing_prior_session_is_not_backfilled(self):
        day = '2026-10-30'
        raw = snapshot(day, [quote('sh600000', 11, 10, day)])
        result = summarize(raw['quotes'], raw['codes'], day, raw['collected_at'], raw['suspended'])
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory + '/isolated.sqlite3')
            service = Breadth(store)
            with patch('core.ma_reference.load_seed', return_value=self.seed), \
                 patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T12:00:00+08:00')), \
                 patch('core.breadth.collect', return_value=(result, raw)):
                service.refresh(force=True)
                view = service.view()
                self.assertIn('2026-10-29', view['ma_note'])
                self.assertIn('不会自动补齐', view['ma_note'])
                self.assertNotIn('ma_daily', next(row for row in view['days'] if row['date'] == day))
            store.db.close()

    def test_service_exposes_close_but_never_promotes_provisional_snapshot(self):
        day = '2026-10-29'
        final = snapshot(day, [quote('sh600000', 11, 10, day), quote('sz000001', 9, 10, day)])
        result = summarize(final['quotes'], final['codes'], day, final['collected_at'], final['suspended'])
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory + '/isolated.sqlite3')
            service = Breadth(store)
            with patch('core.ma_reference.load_seed', return_value=self.seed), \
                 patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T12:00:00+08:00')), \
                 patch('core.breadth.collect', return_value=(result, final)):
                service.refresh(force=True)
                row = next(x for x in service.view()['days'] if x['date'] == day)
                self.assertEqual(row['ma_daily']['windows']['250']['eligible'], 2)
                self.assertEqual(row['ma_daily']['windows']['250']['percent'], 50.0)
                next_day = '2026-10-30'
                raw = snapshot(next_day, [quote('sh600000', 11, 11, next_day, '14:00:00')], clock='14:01:00')
                partial = summarize(raw['quotes'], raw['codes'], next_day, raw['collected_at'], raw['suspended'])
                with patch('core.breadth.collect', return_value=(partial, raw)):
                    service.refresh(force=True)
                view = service.view()
                rows = view['days']
                self.assertIn('ma_daily', next(x for x in rows if x['date'] == day))
                self.assertNotIn('ma_daily', next(x for x in rows if x['date'] == next_day))
                self.assertIn('暂未更新', view['ma_note'])
                self.assertEqual(store.query('SELECT * FROM watch'), [])
                self.assertEqual(store.query('SELECT * FROM events'), [])
            store.db.close()


if __name__ == '__main__':
    unittest.main()
