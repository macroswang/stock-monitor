import json
import unittest
from pathlib import Path
from unittest.mock import patch

from core import market_radar as radar
from core import market_pulse as mp

FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures' / 'opportunity'
DAY = '2026-11-06'


def fixture_pools():
    data = json.loads((FIXTURES / 'limit-up-pools-20261103-20261106.json').read_text(encoding='utf-8'))
    pools = {}
    for day in data['days']:
        rows = [mp.parse_limit_up_row(row, day['date']) for row in day['rows']]
        pools[day['date']] = dict(rows=rows, limit_up={}, limit_down={}, total=len(rows))
    return pools


class FakeStore:
    def __init__(self):
        self.caches = {}

    def cache(self, code, kind, day, payload):
        self.caches[(code, kind, day)] = payload

    def getcache(self, code, kind, day=None):
        return [dict(day=d, data=payload) for (c, k, d), payload in sorted(self.caches.items(), key=lambda item: item[0][2])
                if c == code and k == kind and (day is None or d == day)]


def quote(price, previous=10.0, low=None, amount=2e8):
    return dict(code='x', price=str(price), previous_close=str(previous),
                day_low=str(low if low is not None else min(price, previous) - .2),
                amount_yuan=str(amount), timestamp=DAY + 'T10:30:00+08:00')


class NameRadar(unittest.TestCase):
    def test_fixture_detects_east_and_zodiac_clusters(self):
        pools = fixture_pools()
        days = sorted(pools)[-5:]
        rows_by_day = {stamp: pools[stamp]['rows'] for stamp in days}
        quotes, names = {}, {}
        for group in rows_by_day.values():
            for row in group:
                quotes[row['code']] = dict(quote(11.0, 10.0), code=row['code'])
        # Non-limit-up name-family candidates used by the low-buy scan.
        for code, name in [('sz002249', '大洋电机'), ('sz300189', '神农种业'), ('sh600866', '星湖科技')]:
            names[code] = name
            quotes[code] = dict(quote(10.2, 10.0, 9.9, 3e8), code=code)
        names['sh600602'] = '云赛智联'
        stats = __import__('core.market_plan', fromlist=['quote_stats']).quote_stats(quotes, DAY)
        items = radar._name_radar(days, rows_by_day, names, [], None, stats)
        themes = {item['theme']: item for item in items}
        self.assertIn('东方', themes)
        self.assertEqual(themes['东方']['kind'], '名称类')
        self.assertEqual(themes['东方']['stage'], '加速/高潮')
        self.assertEqual(themes['东方']['limit_up_today'], 6)
        self.assertEqual(themes['东方']['max_board'], 8)
        self.assertEqual(themes['东方']['stocks'][0]['name'], '东方海洋')
        self.assertEqual(len({item['theme'] for item in items}), len(items))
        zodiac = next((item for item in items if item['kind'] == '生肖/玄学'), None)
        self.assertIsNotNone(zodiac)
        self.assertIn('羊年', zodiac['theme'])
        self.assertGreaterEqual(zodiac['limit_up_5d'], 20)

    def test_stage_rules(self):
        self.assertEqual(radar._stage([0, 0, 2], 1, None), '启动初期')
        self.assertEqual(radar._stage([2, 3, 3], 2, None), '发酵')
        self.assertEqual(radar._stage([1, 1, 6], 8, None), '加速/高潮')
        self.assertEqual(radar._stage([4, 4, 2], 2, None), '分歧')
        self.assertEqual(radar._stage([3, 2, 0], 2, None), '退潮')
        self.assertEqual(radar._stage([1, 0, 1], 1, None), '观察')


class EventRadar(unittest.TestCase):
    def test_news_only_theme_is_early(self):
        news = [dict(time=DAY + 'T10:00:00+08:00', title='算力需求回升，数据中心扩容', url='https://a'),
                dict(time=DAY + 'T10:30:00+08:00', title='英伟达发布新平台', url='https://b')]
        rows = []
        items = radar._event_radar(DAY, __import__('datetime').datetime(2026, 11, 8, 22), rows, news, None, [], {})
        ai = next(item for item in items if item['theme'] == 'AI硬件/算力')
        self.assertEqual(ai['stage'], '启动初期')
        self.assertEqual(ai['news_count'], 2)
        self.assertEqual(ai['stocks'], [])
        self.assertIn('先观察', ai['verdict'])

    def test_concept_members_make_it_ferment(self):
        news = [dict(time=DAY + 'T10:00:00+08:00', title='冰雪旅游预订热度翻倍', url='https://a')]
        concept = dict(sectors=[dict(code='gn_bx', name='冰雪经济', net_yuan=1e8, change_percent=2.0)])
        rows = [dict(code='sh601188', name='龙江交通', reason='冰雪旅游保障+高速公路运营',
                     boards=3, days=3, order_amount=2e8)]
        stats = {'sh601188': dict(price=3.81, previous=3.46, low=3.46, amount=2e8, pct=10.12)}
        items = radar._event_radar(DAY, __import__('datetime').datetime(2026, 11, 8, 22), rows, news, concept, [], stats)
        snow = next(item for item in items if item['theme'] == '冰雪经济')
        self.assertEqual(snow['stage'], '发酵')
        self.assertEqual(snow['stocks'][0]['name'], '龙江交通')
        self.assertIn('冰雪旅游保障', snow['evidence'][0]['value'] + snow['stocks'][0]['reason'])

    def test_single_tag_without_news_or_concept_is_dropped(self):
        rows = [dict(code='sh601188', name='龙江交通', reason='冰雪旅游保障', boards=1, days=1, order_amount=1e8)]
        items = radar._event_radar(DAY, __import__('datetime').datetime(2026, 11, 8, 22), rows, [],
                                   None, [], {'sh601188': dict(price=3.8, previous=3.46, low=3.4, amount=1e8, pct=9.9)})
        self.assertNotIn('冰雪经济', [item['theme'] for item in items])

    def test_news_noise_is_filtered(self):
        news = [dict(time=DAY + 'T10:00:00+08:00', title='黄金回收新手沟通话术', url='https://a')]
        self.assertEqual(radar._news_hits(news, ['黄金']), [])


class Build(unittest.TestCase):
    def test_build_returns_deduped_report(self):
        pools = fixture_pools()
        days = sorted(pools)[-5:]
        quotes = {}
        for group in pools.values():
            for row in group['rows']:
                quotes[row['code']] = dict(quote(11.0, 10.0), code=row['code'])
        names = {'sz002249': '大洋电机', 'sh600866': '星湖科技'}
        for code, name in names.items():
            quotes[code] = dict(quote(10.2, 10.0, 9.9, 3e8), code=code)
        sentiment = dict(_days=pools)
        summary = dict(date=DAY, status='closed')
        with patch.object(mp, 'name_universe', return_value=names):
            result = radar.build(FakeStore(), summary, quotes, None, [], sentiment, [], None)
        self.assertLessEqual(len(result['items']), 5)
        self.assertIn('识别', result['summary'])
        themes = [(item['kind'], item['theme']) for item in result['items']]
        self.assertEqual(len(themes), len(set(themes)))
        for item in result['items']:
            self.assertIn(item['stage'], radar.STAGE_ORDER)
            self.assertTrue(item['stage_note'] and item['verdict'] and item['risk'] and item['watch'])
            for stock in item['stocks']:
                self.assertIn(stock['role'], ('龙头', '跟风', '低吸候选'))
                self.assertLess(stock['entry']['stop'], stock['entry']['target1'])


if __name__ == '__main__':
    unittest.main()
