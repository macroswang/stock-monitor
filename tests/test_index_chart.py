import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from core.app import App
from core.index_chart import KIND
from core.index_technical import trading_day
from core.provider import CN


class IndexChartTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(self.temp.name, False)
        self.now = datetime(2026, 11, 20, 11, 40, tzinfo=CN)
        self.args = dict(code='sh000001', start='2023-11-20', end='2026-11-20')
        self.clock = patch('core.index_chart.now_cn', return_value=self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.app.stop.set()
        self.app.store.db.close()
        self.temp.cleanup()

    def source(self, url):
        code, _, lo, hi, *_ = parse_qs(urlparse(url).query)['param'][0].split(',')
        start, end = date.fromisoformat(lo), date.fromisoformat(hi)
        price = {'sh000001':3500, 'sz399001':10000, 'sz399006':2200}[code]
        rows = []
        while start <= end:
            if start.weekday() < 5 and trading_day(start) is not False:
                rows.append([str(start), str(price), str(price+1), str(price+2), str(price-1), '123'])
            start += timedelta(days=1)
        return json.dumps({'data':{code:{'day':rows}}})

    def test_reuses_cache_and_keeps_all_three_indices_out_of_stock_signals(self):
        before = self.app.store.query("SELECT count(*) AS n FROM cache WHERE kind='daily'")[0]['n']
        with patch('core.index_chart.get', side_effect=self.source) as network:
            for code in ('sh000001', 'sz399001', 'sz399006'):
                args = dict(self.args, code=code)
                first = self.app.index_chart.load(args)
                self.assertEqual(first, self.app.index_chart.load(args))
                self.assertEqual(first['code'], code)
                self.assertTrue(first['daily'][-1]['provisional'])
                self.assertEqual(first['daily'][-1]['volume'], 12300)
            self.assertEqual(network.call_count, 3)
            with patch('core.index_chart.now_cn', return_value=self.now+timedelta(seconds=70)):
                updated = self.app.index_chart.load(self.args)
            self.assertEqual(network.call_count, 4)
            params = parse_qs(urlparse(network.call_args.args[0]).query)['param'][0].split(',')
            self.assertEqual(params[2], str(self.now.date()-timedelta(days=90)))
            self.assertEqual(updated['daily'][0]['date'], self.args['start'])
        self.assertEqual(len(self.app.store.query('SELECT * FROM cache WHERE kind=?', (KIND,))), 3)
        for table in ('events', 'trading_runs', 'broker_requests'):
            self.assertEqual(self.app.store.query(f'SELECT count(*) AS n FROM {table}')[0]['n'], 0)
        self.assertEqual(self.app.store.query("SELECT count(*) AS n FROM cache WHERE kind='daily'")[0]['n'], before)
        self.assertEqual(self.app.store.query("SELECT count(*) AS n FROM cache WHERE kind='daily' AND code IN ('sh000001','sz399001','sz399006')")[0]['n'], 0)

    def test_long_weekly_warmup_splits_requests_and_preserves_real_dates(self):
        with patch('core.index_chart.get', side_effect=self.source) as network:
            result = self.app.index_chart.load(dict(self.args, start='2015-11-20'))
            self.assertEqual(network.call_count, 2)
        dates = [row['date'] for row in result['daily']]
        self.assertEqual(dates, sorted(set(dates)))
        self.assertEqual((dates[0], dates[-1]), ('2015-11-20', '2026-11-20'))
        self.assertTrue(all(row['volume'] == 12300 for row in result['daily']))

    def test_concurrent_reads_share_one_fetch_and_future_cache_is_not_reused(self):
        with patch('core.index_chart.get', side_effect=self.source) as network:
            with ThreadPoolExecutor(max_workers=2) as pool:
                values = list(pool.map(lambda _: self.app.index_chart.load(self.args), range(2)))
            self.assertEqual(values[0], values[1])
            self.assertEqual(network.call_count, 1)
            payload = self.app.store.getcache('sh000001', KIND, 'history')[0]['data']
            payload['cached_at'] = '2026-11-21T11:40:00+08:00'
            self.app.store.cache('sh000001', KIND, 'history', payload)
            self.app.index_chart.load(self.args)
            self.assertEqual(network.call_count, 2)

    def test_invalid_identity_future_range_and_bad_prices_never_enter_cache(self):
        for args in (dict(self.args, code='sz000001'), dict(self.args, end='2026-11-21')):
            with patch('core.index_chart.get') as network, self.assertRaises(ValueError):
                self.app.index_chart.load(args)
            network.assert_not_called()
        for payload in ({'data':{'sz399001':{'day':[]}}}, {'data':{'sh000001':{'day':[['2026-11-20',3500,3501,1,3499,123]]}}}):
            self.app.index_chart.failed.clear()
            with patch('core.index_chart.get', return_value=json.dumps(payload)), self.assertRaises(ValueError):
                self.app.index_chart.load(self.args)
        self.assertEqual(self.app.store.getcache('sh000001', KIND), [])
