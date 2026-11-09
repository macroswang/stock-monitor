"""The captured fixtures behind the data-layer checks; kept separate from synthetic cases."""
import json
import unittest
from pathlib import Path

from core import market_pulse as mp
from core import market_plan as plan

FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures' / 'opportunity'
DAY = '2026-11-06'


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


@unittest.skipUnless((FIXTURES / 'limit-up-pools-20261103-20261106.json').exists(), '涨停池 fixture 未提供')
class LimitUpFixture(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((FIXTURES / 'limit-up-pools-20261103-20261106.json').read_text(encoding='utf-8'))

    def test_every_captured_row_is_parsed_and_counts_reconcile(self):
        unknown = 0
        for day in self.data['days']:
            parsed = mp.split_counts(day['limit_up_count'])
            self.assertEqual(parsed['today'], day['page_total'])
            down = mp.split_counts(day['limit_down_count'])
            self.assertEqual(parsed['attempt'], parsed['today'] + parsed['open_num'])
            self.assertAlmostEqual(parsed['sealed_rate'], parsed['today'] / parsed['attempt'], places=9)
            rows = [mp.parse_limit_up_row(row, day['date']) for row in day['rows']]
            self.assertEqual(len(rows), day['page_total'])
            self.assertEqual(len({row['raw_code'] for row in rows}), len(rows))
            unknown += sum(1 for row in rows if row['boards'] is None)
            for row in rows:
                if row['boards'] is not None:
                    self.assertGreaterEqual(row['days'], row['boards'])
        # The source omitted the board encoding for a few names; they must stay unknown, never guessed.
        self.assertEqual(unknown, 3)

    def test_reason_tokens_from_real_captures(self):
        day = next(item for item in self.data['days'] if item['date'] == '2026-11-06')
        tokens = {}
        for row in day['rows']:
            for token in mp.reason_tokens(row['reason_type'] or ''):
                tokens[token] = tokens.get(token, 0) + 1
        self.assertEqual(tokens.get('东方'), 5)
        self.assertEqual(tokens.get('光伏'), 3)
        self.assertNotIn('次新股', tokens)


@unittest.skipUnless((FIXTURES / 'index-daily-20261108.json').exists(), '指数日线 fixture 未提供')
class IndexFixture(unittest.TestCase):
    def test_captured_bars_parse_and_latest_close_matches(self):
        data = json.loads((FIXTURES / 'index-daily-20261108.json').read_text(encoding='utf-8'))
        self.assertEqual(data['captured_at'][:10], '2026-11-08')
        for index in data['indices']:
            payload = {'data': {index['code']: {'day': [[row['date'], row['open'], row['close'], row['high'],
                                                       row['low'], row['volume']] for row in index['rows']]}}}
            parsed = mp._parse_index_rows(payload, index['code'])
            self.assertEqual(len(parsed), 60)
            self.assertEqual(parsed[-1]['date'], DAY)
        shanghai = next(item for item in data['indices'] if item['code'] == 'sh000001')
        self.assertEqual(shanghai['rows'][-1]['close'], 3649.18)


@unittest.skipUnless((FIXTURES / 'stock-daily-20261108.json').exists(), '个股日线 fixture 未提供')
class StockFixture(unittest.TestCase):
    def test_levels_are_computed_from_completed_bars(self):
        data = json.loads((FIXTURES / 'stock-daily-20261108.json').read_text(encoding='utf-8'))
        for stock in data['stocks']:
            payload = {'data': {stock['code']: {'day': [[row['date'], row['open'], row['close'], row['high'],
                                                       row['low'], row['volume']] for row in stock['rows']]}}}
            parsed = mp.parse_stock_rows(payload, stock['code'])
            self.assertEqual(parsed[-1]['date'], DAY)
            levels = plan._levels(parsed, DAY, True)
            closes = [row['close'] for row in parsed]
            self.assertAlmostEqual(levels['ma5'], round(sum(closes[-5:]) / 5, 2))
            self.assertAlmostEqual(levels['ma20'], round(sum(closes[-20:]) / 20, 2))
            self.assertEqual(levels['high20'], round(max(row['high'] for row in parsed[-20:]), 2))


@unittest.skipUnless((FIXTURES / 'sector-flow-history-20261030-20261106.json').exists(), '资金历史 fixture 未提供')
class CapitalFixture(unittest.TestCase):
    def test_five_day_sums_come_from_same_source_snapshots(self):
        data = json.loads((FIXTURES / 'sector-flow-history-20261030-20261106.json').read_text(encoding='utf-8'))
        store = FakeStore()
        blocks = {}
        for item in data['days']:
            if item['source'] == '新浪行业资金流':
                store.cache(mp.INDUSTRY_CACHE, 'sector_flow_v1', item['date'], item)
                blocks.setdefault(item['date'], {})['industry'] = item
            else:
                store.cache(mp.CONCEPT_CACHE, 'sector_flow_v1', item['date'], item)
                blocks.setdefault(item['date'], {})['concept'] = item
        latest = blocks[DAY]
        result, warnings = mp.capital(store, DAY, latest['industry'], latest['concept'], closed=True)
        self.assertEqual(result['history_days'], 5)
        self.assertEqual(len(latest['industry']['sectors']), 43)
        self.assertGreater(len(latest['concept']['sectors']), 100)
        days = sorted(blocks)[-5:]
        target = latest['industry']['sectors'][0]
        expected = 0
        for day in days:
            block = blocks[day].get('industry')
            if not block:
                continue
            match = next((row for row in block['sectors'] if row['code'] == target['code']), None)
            if match:
                expected += match['net_yuan']
        self.assertAlmostEqual(result['by_code'][target['code']]['net_5d'], expected, places=2)
        self.assertTrue(result['persistent'])
        self.assertNotIn('融资融券', [row['name'] for row in result['persistent']])


if __name__ == '__main__':
    unittest.main()
