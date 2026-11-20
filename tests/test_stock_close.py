import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from core.app import App
from core.history import analyze
from core.stock_close import SESSION, checked_group, close_reference


DAY = '2026-11-20'


def minute_group():
    return dict(date=DAY, source='tencent', volume_unit='shares', bars=[
        dict(time=time, close='10.00', volume=100, complete=True) for time in SESSION
    ])


def closed_daily(volume):
    return dict(date=DAY, source='tencent', adjustment='none', volume_unit='shares',
                close='10.00', volume=volume, cached_at=DAY+'T15:20:00+08:00')


class StockCloseTest(unittest.TestCase):
    def test_verified_cache_accepts_reconciled_revisions_and_late_quote_metadata(self):
        code = 'sh600100'
        with tempfile.TemporaryDirectory() as directory:
            app = App(directory, False)
            self.addCleanup(app.store.db.close)
            group = minute_group()
            daily = closed_daily(len(SESSION)*100)
            reference = close_reference(DAY, daily)
            app.cache_minutes(code, checked_group(group, DAY, reference))
            app.quotes[code] = dict(date=DAY, timestamp=DAY+'T15:01:00+08:00',
                                    limit_up='11', high='10', previous_close='10')
            app.cache_minutes(code, dict(group, bars=group['bars'][:-1]))
            cached = app.stock_close.cached(code, 'minute', DAY)
            self.assertEqual(cached['bars'], group['bars'])
            self.assertEqual(analyze(code, DAY, cached, None)['status'], 'ready')

            group['bars'][30]['close'] = '9.00'
            app.cache_minutes(code, group)
            revised = app.stock_close.cached(code, 'minute', DAY)
            self.assertEqual(revised['close_verified'], 'daily')
            self.assertEqual(revised['bars'][30]['close'], '9.00')
            group['bars'][-1]['volume'] += 100
            revision = app.store.cache_revision(code, 'minute')
            app.cache_minutes(code, group)
            self.assertEqual(app.store.cache_revision(code, 'minute'), revision)
            self.assertEqual(app.stock_close.cached(code, 'minute', DAY), revised)

            daily['volume'] += 100
            app.store.cache(code, 'daily', DAY, daily)
            app.cache_minutes(code, group)
            self.assertEqual(app.stock_close.cached(code, 'minute', DAY)['bars'], group['bars'])
            self.assertFalse(app.store.query('SELECT 1 FROM events'))
            self.assertFalse(app.store.query('SELECT 1 FROM broker_requests'))

    def test_close_requires_complete_session_and_does_not_fabricate_mismatched_volume(self):
        group = minute_group()
        reference = close_reference(DAY, closed_daily(len(SESSION)*100))
        self.assertEqual(checked_group(group, DAY, reference)['close_verified'], 'daily')
        missing = dict(group, bars=group['bars'][:50]+group['bars'][51:])
        self.assertIsNone(checked_group(missing, DAY, reference))
        group['bars'][-1]['complete'] = False
        self.assertIsNone(checked_group(group, DAY, reference))
        group['bars'][-1].update(complete=True, volume=0)
        checked = checked_group(group, DAY, reference)
        self.assertNotIn('close_verified', checked)
        self.assertEqual(checked['close_volume_difference'], -100)
        self.assertEqual(checked['bars'][-1]['volume'], 0)

    def test_sweep_fills_watch_and_pool_and_protects_confirmed_data(self):
        watched, pooled = 'sh600100', 'sh600101'
        with tempfile.TemporaryDirectory() as directory:
            app = App(directory, False)
            self.addCleanup(app.store.db.close)
            app.store.execute('DELETE FROM watch')
            app.store.execute('INSERT INTO watch(code) VALUES (?)', (watched,))
            app.store.execute("INSERT INTO pool(code,added_day,source,state) VALUES (?,?,'test','watch')", (pooled,DAY))
            group = minute_group()
            daily = closed_daily(len(SESSION)*100)
            app.store.cache(watched,'daily',DAY,daily)
            partial = dict(group,bars=group['bars'][:-1])
            app.store.cache(watched,'minute',DAY,partial)
            app.provider = Mock()
            app.provider.minutes.return_value = [group]
            app.provider.watch_quotes.return_value = {pooled: dict(date=DAY, timestamp=DAY+'T15:20:00+08:00',
                source='tencent', volume_unit='shares', price='10.00', volume=daily['volume'])}
            now = datetime.fromisoformat(DAY+'T15:22:00+08:00')
            with patch('core.stock_close.now_cn',return_value=now),patch.object(app.stop,'wait',return_value=False):
                app.stock_close.refresh(DAY)
                app.stock_close.refresh(DAY)
            self.assertEqual([call.args[0] for call in app.provider.minutes.call_args_list], [watched,pooled])
            app.cache_minutes(watched,partial)
            for code,source in [(watched,'daily'),(pooled,'quote')]:
                result = app.store.getcache(code,'minute',DAY)[0]['data']
                self.assertEqual(result['close_verified'],source)
                self.assertEqual(result['bars'][-1],group['bars'][-1])
            self.assertFalse(app.store.query('SELECT 1 FROM events'))
            self.assertFalse(app.store.query('SELECT 1 FROM broker_requests'))
