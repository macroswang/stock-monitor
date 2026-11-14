import json, tempfile, unittest
from pathlib import Path

from core.app import App

FIXTURE = Path(__file__).parent / 'fixtures' / 'ma250-pullback-603533.json'


def bars_until(stamp):
    bars = json.loads(FIXTURE.read_text(encoding='utf-8'))['bars']
    return bars[:next(index for index, bar in enumerate(bars) if bar['date'] == stamp) + 1]


class Ma250ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(self.tmp.name, False)
        self.code = 'sh600000'
        self.bars = bars_until('2026-11-02')
        for bar in self.bars:
            self.app.store.cache(self.code, 'daily', bar['date'],
                                 dict(bar, volume='0', volume_unit='shares', source='tencent', adjustment='none'))
        self.app.store.execute("INSERT OR REPLACE INTO watch(code,name,enabled) VALUES(?,?,1)", (self.code, '测试年线'))
        self.app.market_regime.above_map = lambda: {bar['date']: True for bar in self.bars}

    def tearDown(self):
        self.app.store.db.close()
        self.tmp.cleanup()

    def test_scan_lists_v1_and_labels_only_the_strong_signal(self):
        result = self.app.call('ma250_scan', dict(universe='watch', recent=1000))
        self.assertEqual(result['scanned'], 1)
        rows = {row['date']: row for row in result['rows']}
        self.assertIn('2026-11-02', rows)
        self.assertIn('2025-08-18', rows)
        self.assertTrue(rows['2025-08-18']['strong'])
        self.assertFalse(rows['2026-11-02']['strong'])
        self.assertIn('broke-line', rows['2026-11-02']['strong_reasons'])
        self.assertEqual(rows['2025-08-18']['name'], '测试年线')
        self.assertIsNotNone(rows['2025-08-18']['atr20_pct'])
        breakouts = [row for row in result['rows'] if row['kind'] == 'breakout']
        self.assertGreater(len(breakouts), 0)
        self.assertTrue(all(row['quality'] in (True, False) for row in breakouts))

    def test_scan_respects_universe_and_is_memoized_for_the_same_filters(self):
        first = self.app.call('ma250_scan', dict(universe='watch_pool', recent=5))
        second = self.app.call('ma250_scan', dict(universe='watch_pool', recent=5))
        self.assertEqual(first['rows'],second['rows'])
        self.assertEqual(first['coverage'],second['coverage'])
        self.assertGreaterEqual(first['codes'], 1)
        self.assertEqual(first['scanned'], 1)
        all_scan = self.app.call('ma250_scan', dict(universe='all', recent=5))
        self.assertEqual(len(first['trading_days']), 5)
        self.assertTrue(all(row['date'] in set(first['trading_days']) for row in first['rows']))
        self.assertGreaterEqual(all_scan['codes'], 1)

    def test_empty_universe_and_short_history_are_explicit(self):
        self.app.store.execute("DELETE FROM watch")
        self.app.store.execute("DELETE FROM pool")
        result = self.app.call('ma250_scan', dict(universe='watch_pool', recent=5))
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['scanned'], 0)


if __name__ == '__main__':
    unittest.main()
