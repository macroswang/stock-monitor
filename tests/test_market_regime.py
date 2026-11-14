import tempfile, unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from core.market_regime import CODE, KIND, SOURCE, MarketRegime, parse
from core.provider import CN
from core.store import Store


def payload(rows):
    return {'data': {CODE: {'day': [[row['date'], row['open'], row['close'], row['high'], row['low'], row['volume']]
                                   for row in rows]}}}


def series(count=320, start=3000.0, step=1.0):
    rows, day = [], date(2024, 1, 2)
    for index in range(count):
        while day.weekday() > 4:
            day += timedelta(days=1)
        price = start + step * index
        rows.append(dict(date=day.isoformat(), open=price - 1, close=price, high=price + 2, low=price - 2, volume=1e9))
        day += timedelta(days=1)
    return rows


class MarketRegimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(self.tmp.name) + '/monitor.sqlite3')
        self.regime = MarketRegime(self.store)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_parse_rejects_broken_index_rows(self):
        rows = series(5)
        self.assertEqual([row['date'] for row in parse(payload(rows))], [row['date'] for row in rows])
        with self.assertRaises(ValueError):
            parse(payload(rows + [rows[-1]]))
        broken = series(5)
        broken[2]['high'] = broken[2]['low'] - 1
        with self.assertRaises(ValueError):
            parse(payload(broken))

    def test_above_map_uses_the_annual_line_and_keeps_early_dates_unknown(self):
        rising = series(320, 3000.0, 2.0)
        self.store.cache(CODE, KIND, 'latest', dict(rows=rising, collected_at='2026-11-13T16:00:00+08:00', source=SOURCE))
        mapping = self.regime.above_map()
        self.assertIsNone(mapping[rising[10]['date']])
        self.assertTrue(mapping[rising[-1]['date']])
        falling = series(320, 4000.0, -2.0)
        self.store.cache(CODE, KIND, 'latest', dict(rows=falling, collected_at='2026-11-13T16:00:00+08:00', source=SOURCE))
        self.assertFalse(self.regime.above_map()[falling[-1]['date']])

    def test_refresh_stores_one_snapshot_and_view_reports_it(self):
        rows = series(320, 3000.0, 1.0)
        with patch('core.market_regime.fetch', return_value=rows), \
             patch('core.market_regime.eligible_sessions', return_value=[rows[-1]['date']]):
            self.regime.refresh(datetime(2026, 11, 13, 16, 0, tzinfo=CN))
        view = self.regime.view()
        self.assertEqual(view['date'], rows[-1]['date'])
        self.assertTrue(view['above'])
        self.assertEqual(view['bars'], 320)
        self.assertEqual(len(self.store.getcache(CODE, KIND)), 1)
        with patch('core.market_regime.fetch', side_effect=ValueError('offline')), \
             patch('core.market_regime.eligible_sessions', return_value=['2026-11-16']):
            self.regime.refresh(datetime(2026, 11, 16, 16, 0, tzinfo=CN))
        self.assertIn('offline', self.regime.error)

    def test_missing_or_foreign_snapshot_is_not_used(self):
        self.assertEqual(self.regime.rows(), [])
        self.assertEqual(self.regime.above_map(), {})
        self.assertIsNone(self.regime.view()['date'])
        self.store.cache(CODE, KIND, 'latest', dict(rows=series(320), collected_at='2026-11-13T16:00:00+08:00', source='other'))
        self.assertEqual(self.regime.rows(), [])
        self.assertIsNone(self.regime.view()['date'])
        self.assertIsNone(self.regime.view()['ma250'])


if __name__ == '__main__':
    unittest.main()
