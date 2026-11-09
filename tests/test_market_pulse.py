import json
import unittest
from datetime import datetime
from unittest.mock import patch

from core import market_pulse as mp
from core.provider import CN


def quote(code, price, previous, low, amount, day='2026-11-06'):
    return dict(code=code, price=str(price), previous_close=str(previous), day_low=str(low),
                amount_yuan=str(amount), timestamp=day + 'T10:30:00+08:00')


class FakeStore:
    def __init__(self):
        self.caches = {}

    def cache(self, code, kind, day, payload):
        self.caches[(code, kind, day)] = payload

    def getcache(self, code, kind, day=None):
        rows = []
        for (c, k, d), payload in sorted(self.caches.items(), key=lambda item: item[0][2]):
            if c == code and k == kind and (day is None or d == day):
                rows.append(dict(day=d, data=payload))
        return rows


def pool(day, rows, yesterday_limits, sealed=0.7, down=0, open_num=None):
    attempt = len(rows) + (open_num if open_num is not None else max(0, round(len(rows) * (1 / sealed - 1))))
    return dict(date=day, rows=rows, total=len(rows),
                limit_up=dict(today=len(rows), yesterday=yesterday_limits, attempt=attempt,
                              open_num=attempt - len(rows), sealed_rate=sealed if attempt else None),
                limit_down=dict(today=down, yesterday=0, attempt=down, open_num=0, sealed_rate=None),
                source=mp.LIMIT_UP_SOURCE, source_url='https://example.org/',
                captured_at=day + 'T15:30:00+08:00')


def row(code, name, boards, days, reason='', amount=1e8):
    return dict(code=('sh' if code.startswith('6') else 'sz') + code, raw_code=code, name=name,
                reason=reason, boards=boards, days=days, again=1, limit_type='换手板', order_amount=amount)


def flow(day, source, measure, sectors):
    return dict(date=day, source=source, measure=measure, sectors=sectors,
                quote_time=None, date_inferred=True)


class LimitUpParsing(unittest.TestCase):
    def payload(self, counts, rows, total, page=None):
        return dict(data=dict(date='20261106', page=page or dict(page=1, total=total, count=1, limit=100),
                              info=rows, limit_up_count=counts[0], limit_down_count=counts[1]))

    def test_board_encoding_and_counts(self):
        counts = (dict(today=dict(num=2, history_num=3, open_num=1, rate=2 / 3),
                       yesterday=dict(num=5, history_num=7, open_num=2, rate=5 / 7)),
                  dict(today=dict(num=1, history_num=1, open_num=0, rate=1.0),
                       yesterday=dict(num=0, history_num=1, open_num=1, rate=0.0)))
        rows = [dict(code='600001', name='甲', reason_type='光伏+储能', high_days='3天3板',
                     high_days_value=3 * 65536 + 3, is_again_limit=1, limit_up_type='换手板', order_amount=1e8),
                dict(code='300002', name='乙', reason_type='人形机器人', high_days='首板',
                     high_days_value=65537, is_again_limit=0, limit_up_type='T字板', order_amount=5e7)]
        parsed = mp.parse_limit_up_payload(self.payload(counts, rows, 2), '2026-11-06')
        self.assertEqual(parsed['limit_up']['today'], 2)
        self.assertEqual(parsed['limit_up']['yesterday'], 5)
        self.assertEqual(parsed['limit_up']['attempt'], 3)
        self.assertAlmostEqual(parsed['limit_up']['sealed_rate'], 2 / 3)
        self.assertEqual([(r['boards'], r['days']) for r in parsed['rows']], [(3, 3), (1, 1)])
        self.assertEqual(parsed['rows'][1]['code'], 'sz300002')

    def test_count_mismatch_is_rejected(self):
        counts = (dict(today=dict(num=2, history_num=4, open_num=1, rate=.5),
                       yesterday=dict(num=1, history_num=1, open_num=0, rate=1)),
                  dict(today=dict(num=0, history_num=0, open_num=0, rate=0),
                       yesterday=dict(num=0, history_num=0, open_num=0, rate=0)))
        rows = [dict(code='600001', name='甲', reason_type='', high_days='首板', high_days_value=65537,
                     is_again_limit=0, limit_up_type='换手板', order_amount=1)]
        with self.assertRaises(ValueError):
            mp.parse_limit_up_payload(self.payload(counts, rows, 1), '2026-11-06')
        with self.assertRaises(ValueError):
            mp.parse_limit_up_payload(self.payload(counts, rows, 1, page=dict(page=1, total=1, count=2, limit=100)), '2026-11-06')
        with self.assertRaises(ValueError):
            mp.parse_limit_up_payload(self.payload(counts, rows, 1), '2026-11-05')

    def test_missing_board_encoding_stays_unknown(self):
        parsed = mp.parse_limit_up_row(dict(code='600003', name='丙', reason_type='液冷', high_days=None,
                                            high_days_value=None, is_again_limit=0, limit_up_type='换手板',
                                            order_amount=1, change_tag='FIRST_LIMIT'), '2026-11-06')
        self.assertIsNone(parsed['boards'])
        self.assertEqual(parsed['name'], '丙')
        with self.assertRaises(ValueError):
            mp.parse_limit_up_row(dict(code='600004', name='丁', reason_type='', high_days='首板',
                                       high_days_value=None, is_again_limit=0, limit_up_type='换手板',
                                       order_amount=1, change_tag='FIRST_LIMIT'), '2026-11-06')


class Sentiment(unittest.TestCase):
    def test_metrics_from_five_pools(self):
        days = mp.recent_trading_days('2026-11-06', 5)
        today_rows = [row('600900', '涨停甲', 3, 3, '光伏+储能'), row('600901', '涨停乙', 2, 2, '光伏')]
        yesterday_rows = [row('600900', '涨停甲', 2, 2), row('600903', '昨停甲', 1, 1),
                          row('600904', '昨停乙', 1, 1), row('600905', '昨停丙', 1, 1)]
        pools = {}
        for index, day in enumerate(days):
            rows = today_rows if day == days[-1] else yesterday_rows if day == days[-2] else [row('60090' + str(index), '样本', 1, 1)]
            pools[day] = pool(day, rows, yesterday_limits=4 if day == days[-1] else 1,
                              sealed=0.7, down=(15 if day == days[-1] else 2))
        quotes = {'sh600900': quote('sh600900', 11.0, 10.0, 9.9, 1e8),
                  'sh600901': quote('sh600901', 12.0, 10.0, 9.9, 1e8),
                  'sh600903': quote('sh600903', 10.2, 10.0, 9.8, 1e7),
                  'sh600904': quote('sh600904', 9.9, 10.0, 9.8, 1e7),
                  'sh600905': quote('sh600905', 10.1, 10.0, 9.9, 1e7)}
        with patch.object(mp, 'limit_up_pool', side_effect=lambda store, day, now: pools[day]):
            result = mp.sentiment(FakeStore(), '2026-11-06', quotes)
        self.assertEqual(result['limit_up']['today'], 2)
        self.assertEqual(result['limit_up']['yesterday'], 4)
        self.assertEqual(result['max_board'], 3)
        self.assertEqual(result['max_board_name'], '涨停甲')
        self.assertEqual(result['ladder'], [dict(boards=3, count=1), dict(boards=2, count=1)])
        self.assertEqual(result['non_consecutive'], 0)
        performance = result['yesterday_performance']
        self.assertEqual((performance['count'], performance['checked']), (4, 4))
        self.assertEqual(performance['promote'], 1)
        self.assertEqual(performance['advance'], 3)
        self.assertEqual([item['name'] for item in result['hot_reasons']], ['光伏', '储能'])
        self.assertEqual(len(result['trend']), 5)
        self.assertEqual(result['temperature'], '退潮')
        # The live close is still open, so the market gate itself is not decided here.
        self.assertEqual(result['trend'][-1]['max_board'], 3)

    def test_missing_day_pool_is_reported_not_fabricated(self):
        days = mp.recent_trading_days('2026-11-06', 5)
        def fetch(store, day, now):
            if day == days[-2]:
                raise ValueError('offline')
            return pool(day, [row('600900', '甲', 1, 1)], yesterday_limits=1)
        with patch.object(mp, 'limit_up_pool', side_effect=fetch):
            result = mp.sentiment(FakeStore(), '2026-11-06', {})
        self.assertEqual(len(result['trend']), 4)
        self.assertIsNone(result['yesterday_performance'])
        self.assertTrue(result['warnings'])


class Capital(unittest.TestCase):
    def test_history_sums_and_persistent(self):
        store = FakeStore()
        days = mp.recent_trading_days('2026-11-06', 5)
        for index, day in enumerate(days):
            store.cache(mp.INDUSTRY_CACHE, 'sector_flow_v1', day,
                        flow(day, '新浪行业资金流', '买卖方向净额',
                             [dict(code='new_dlhy', name='电力行业', net_yuan=1e8 * (index + 1), change_percent=1)]))
            store.cache(mp.CONCEPT_CACHE, 'sector_flow_v1', day,
                        flow(day, '新浪概念资金流', '买卖方向净额',
                             [dict(code='gn_gf', name='光伏', net_yuan=2e8 * (index + 1), change_percent=2),
                              dict(code='gn_rzrq', name='融资融券', net_yuan=3e8, change_percent=0.5)]))
        industry = store.getcache(mp.INDUSTRY_CACHE, 'sector_flow_v1', '2026-11-06')[-1]['data']
        concept = store.getcache(mp.CONCEPT_CACHE, 'sector_flow_v1', '2026-11-06')[-1]['data']
        result, warnings = mp.capital(store, '2026-11-06', industry, concept, closed=True)
        self.assertEqual(result['history_days'], 5)
        self.assertEqual(result['by_code']['new_dlhy']['net_5d'], sum(1e8 * (i + 1) for i in range(5)))
        self.assertEqual(result['by_code']['gn_gf']['days'], 5)
        names = [item['name'] for item in result['persistent']]
        self.assertIn('光伏', names)
        self.assertNotIn('融资融券', names)
        self.assertFalse([w for w in warnings if '不足' in w])

    def test_missing_history_is_null_not_zero(self):
        store = FakeStore()
        day = '2026-11-06'
        industry = flow(day, '新浪行业资金流', '买卖方向净额',
                        [dict(code='new_dlhy', name='电力行业', net_yuan=1e8, change_percent=1)])
        store.cache(mp.INDUSTRY_CACHE, 'sector_flow_v1', day, industry)
        concept = flow(day, '新浪概念资金流', '买卖方向净额',
                       [dict(code='gn_gf', name='光伏', net_yuan=1e8, change_percent=1)])
        store.cache(mp.CONCEPT_CACHE, 'sector_flow_v1', day, concept)
        result, warnings = mp.capital(store, day, industry, concept, closed=True)
        self.assertIsNone(result['by_code']['new_dlhy']['net_5d'])
        self.assertTrue(any('近 5 日累计不展示' in w for w in warnings))

    def test_intraday_cutoff_excludes_unfinished_session(self):
        store = FakeStore()
        days = mp.recent_trading_days('2026-11-06', 5)
        for index, day in enumerate(days):
            store.cache(mp.INDUSTRY_CACHE, 'sector_flow_v1', day,
                        flow(day, '新浪行业资金流', '买卖方向净额',
                             [dict(code='new_dlhy', name='电力行业', net_yuan=1e8, change_percent=1)]))
            store.cache(mp.CONCEPT_CACHE, 'sector_flow_v1', day,
                        flow(day, '新浪概念资金流', '买卖方向净额',
                             [dict(code='gn_gf', name='光伏', net_yuan=1e8, change_percent=1)]))
        industry = store.getcache(mp.INDUSTRY_CACHE, 'sector_flow_v1', '2026-11-06')[-1]['data']
        concept = store.getcache(mp.CONCEPT_CACHE, 'sector_flow_v1', '2026-11-06')[-1]['data']
        result, warnings = mp.capital(store, '2026-11-06', industry, concept, closed=False)
        self.assertEqual(result['by_code']['new_dlhy']['days'], 4)
        self.assertEqual(result['by_code']['new_dlhy']['net_5d'], 4e8)
        self.assertTrue(any('盘中不把未完成的当日资金' in w for w in warnings))

    def test_unknown_source_is_rejected(self):
        store = FakeStore()
        day = '2026-11-06'
        industry = flow(day, '某未知榜单', '未知口径',
                        [dict(code='BK0427', name='公用事业', net_yuan=1e8, change_percent=1)])
        result, warnings = mp.capital(store, day, industry, None, closed=True)
        self.assertIsNone(result['industry'])
        self.assertTrue(any('行业' in w for w in warnings))

    def test_eastmoney_snapshot_is_used_but_history_stays_same_source(self):
        store = FakeStore()
        day = '2026-11-06'
        industry = flow(day, '东方财富行业板块资金流', '大单及超大单净额',
                        [dict(code='BK0427', name='公用事业', net_yuan=1e8, change_percent=1)])
        store.cache(mp.INDUSTRY_CACHE, 'sector_flow_v1', day, industry)
        for previous in mp.recent_trading_days(mp.previous_trading_day(day), 5):
            store.cache(mp.INDUSTRY_CACHE, 'sector_flow_v1', previous,
                        flow(previous, '新浪行业资金流', '买卖方向净额',
                             [dict(code='BK0427', name='公用事业', net_yuan=1e8, change_percent=1)]))
        result, warnings = mp.capital(store, day, industry, None, closed=True)
        self.assertEqual(result['industry']['measure'], '大单及超大单净额')
        self.assertEqual(result['by_code']['BK0427']['days'], 1)
        self.assertIsNone(result['by_code']['BK0427']['net_5d'])
        self.assertTrue(any('口径' in w for w in warnings))


class DailyLevels(unittest.TestCase):
    def test_stock_rows_validate(self):
        rows = [['2026-11-05', '10', '10.5', '10.6', '9.9', '1000'], ['2026-11-06', '10.5', '10.8', '10.9', '10.4', '1200']]
        parsed = mp.parse_stock_rows(dict(data={'sz000001': {'day': rows}}), 'sz000001')
        self.assertEqual([r['date'] for r in parsed], ['2026-11-05', '2026-11-06'])
        with self.assertRaises(ValueError):
            mp.parse_stock_rows(dict(data={'sz000001': {'day': [['2026-11-06', '10', '10', '9', '10.5', '1']]}}), 'sz000001')

    def test_index_ma_and_ratio(self):
        dates = mp.recent_trading_days('2026-11-06', 30)
        bars = [dict(date=date, open=10, close=10 + offset * .1, high=10 + offset * .1 + .2,
                     low=10 + offset * .1 - .2, volume=1000 + offset) for offset, date in enumerate(dates)]
        live = {'sh000001': dict(price=12.9, previous=12.8, percent=.78, stamp='2026-11-06T15:00:00+08:00')}
        with patch.object(mp, 'fetch_index_daily', side_effect=lambda code: [dict(row) for row in bars]), \
             patch.object(mp, 'index_quotes', return_value=live):
            month = mp.index_trends(FakeStore(), '2026-11-06', datetime(2026, 11, 8, 19, tzinfo=CN), True)
        shanghai = next(row for row in month if row['code'] == 'sh000001')
        self.assertTrue(shanghai['above_ma20'])
        self.assertAlmostEqual(shanghai['ma5'], sum(10 + offset * .1 for offset in range(25, 30)) / 5, places=2)
        self.assertEqual(shanghai['price'], 12.9)
        self.assertAlmostEqual(shanghai['volume_ratio'], round(1029 / (sum(1000 + offset for offset in range(24, 29)) / 5), 2), places=2)

class SinaFallback(unittest.TestCase):
    def test_sina_rows_are_validated(self):
        rows = [dict(day='2026-11-05', open='10', high='10.6', low='9.9', close='10.5', volume='1000'),
                dict(day='2026-11-06', open='10.5', high='10.9', low='10.4', close='10.8', volume='1200')]
        parsed = mp.parse_sina_daily(rows)
        self.assertEqual([row['date'] for row in parsed], ['2026-11-05', '2026-11-06'])
        with self.assertRaises(ValueError):
            mp.parse_sina_daily([dict(day='2026-11-06', open='10', high='9', low='10.5', close='10', volume='1')])

    def test_index_daily_falls_back_and_caches_source(self):
        rows = [dict(date=date, open=10, close=10, high=10.2, low=9.8, volume=1000)
                for date in mp.recent_trading_days('2026-11-06', 25)]
        store = FakeStore()
        with patch.object(mp, 'fetch_index_daily', side_effect=OSError('waf')), \
             patch.object(mp, 'fetch_sina_daily', return_value=rows):
            fetched, source = mp.index_daily(store, 'sh000001', '2026-11-06', datetime(2026, 11, 8, 19, tzinfo=CN))
        self.assertEqual(source, mp.SINA_KLINE_SOURCE)
        self.assertEqual(len(fetched), 25)
        with patch.object(mp, 'fetch_index_daily', side_effect=OSError('should not refetch')), \
             patch.object(mp, 'fetch_sina_daily', side_effect=OSError('should not refetch')):
            cached, cached_source = mp.index_daily(store, 'sh000001', '2026-11-06', datetime(2026, 11, 8, 19, tzinfo=CN))
        self.assertEqual(cached_source, mp.SINA_KLINE_SOURCE)
        self.assertEqual(len(cached), 25)

    def test_stock_daily_falls_back_to_sina(self):
        rows = [dict(date=date, open=10, close=10, high=10.2, low=9.8, volume=1000)
                for date in mp.recent_trading_days('2026-11-06', 25)]
        store = FakeStore()
        with patch.object(mp, 'fetch_stock_daily', side_effect=OSError('waf')), \
             patch.object(mp, 'fetch_sina_daily', return_value=rows):
            fetched, failed = mp.stock_daily(store, ['sh600001'], '2026-11-06', datetime(2026, 11, 8, 19, tzinfo=CN))
        self.assertEqual(failed, [])
        self.assertEqual(len(fetched['sh600001']), 25)
        payload = store.getcache('sh600001', mp.LEVELS_KIND, '2026-11-06')[0]['data']
        self.assertEqual(payload['source'], mp.SINA_KLINE_SOURCE)

class TencentHosts(unittest.TestCase):
    def test_second_host_is_used_when_canonical_is_waf_limited(self):
        dates = mp.recent_trading_days('2026-11-06', 30)
        payload = {'data': {'sh000001': {'day': [[date, '10', '10.5', '10.6', '9.9', '100'] for date in dates]}}}
        def fake_get(url):
            if 'web.ifzq' in url:
                raise OSError('http 501')
            return json.dumps(payload)
        with patch.object(mp, 'get', side_effect=fake_get):
            rows = mp.fetch_index_daily('sh000001', 30)
        self.assertEqual([row['date'] for row in rows], dates)


class Hotspots(unittest.TestCase):
    def test_news_order_and_limit(self):
        feeds = [dict(region='domestic', time='2026-11-08T10:00:00+08:00', title='甲', url='https://a'),
                 dict(region='domestic', time='2026-11-08T12:00:00+08:00', title='乙', url='https://b')]
        result = mp.hotspots(feeds, dict(hot_reasons=[dict(name='光伏', count=2, stocks=[])]))
        self.assertEqual([item['title'] for item in result['news']], ['乙', '甲'])
        self.assertEqual(result['reasons'][0]['name'], '光伏')

    def test_same_article_from_two_feeds_is_one_row(self):
        feeds = [dict(region='domestic', time='2026-11-08T12:00:00+08:00', title='甲', url='https://a'),
                 dict(region='international', time='2026-11-08T12:00:00+08:00', title='甲', url='https://a')]
        result = mp.hotspots(feeds, None)
        self.assertEqual(len(result['news']), 1)


if __name__ == '__main__':
    unittest.main()
