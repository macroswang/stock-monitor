import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.breadth import parse_quotes
from core.pool import (FUND_FLOW_SECONDS, SINA_FUND_FLOW_URL, Pool, _fund_flow_url,
                       _message_driver, _news_driver, _news_sentence, _parse_fund_flow_payload,
                       _parse_sina_fund_flow_payload, _radar_driver, _secid, _short_driver)
from core.provider import CN
from core.store import Store


def quote(code, price, previous, high=None, low=None, day='2026-11-09'):
    return dict(code=code, price=str(price), previous_close=str(previous),
                timestamp=day + 'T10:00:00+08:00',
                day_high=str(high if high is not None else price),
                day_low=str(low if low is not None else price),
                amount_yuan='100000000',
                turnover_rate=7.89, volume_ratio=1.03, amplitude=3.2, float_mcap_yi=123.4)


def pick(code, name, price=10.2, percent=1.2, chase=10.6, sector='智能穿戴', kind='概念',
         role='低吸候选', state='可考虑建仓'):
    return dict(code=code, name=name, sector=sector, sector_code='BK0001', sector_kind=kind,
                role=role, state=state, why='理由：资金净流入、回踩买点。', price=price, percent=percent,
                chase=chase, buy_low=round(price * 0.98, 2), buy_high=round(price * 1.01, 2),
                stop=round(price * 0.94, 2), target1=round(price * 1.1, 2), target2=round(price * 1.2, 2),
                trail=round(price * 0.97, 2), note='回踩分批。', sell_note='接近目标减半。')


def stock(code, name, price, percent, role='低吸候选', chase=None):
    return dict(code=code, name=name, role=role, price=price, percent=percent,
                entry=dict(buy_low=round(price * 0.98, 2), buy_high=round(price * 1.01, 2),
                           chase=round(chase if chase is not None else price * 1.03, 2),
                           stop=round(price * 0.94, 2), target1=round(price * 1.1, 2),
                           target2=round(price * 1.2, 2), trail=round(price * 0.97, 2),
                           note='', sell_note=''))


def tencent_line(code, fields=None):
    values = ['0'] * 60
    values[2] = code[2:]
    values[3] = '10'
    values[4] = '9.8'
    values[6] = '10000'
    values[30] = '20261109100000'
    values[33] = '10.2'
    values[34] = '9.8'
    values[37] = '1000'
    for index, value in (fields or {}).items():
        values[index] = value
    return 'v_' + code + '="' + '~'.join(values) + '";'


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class FakeApp:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.store = Store(str(Path(folder) / 'monitor.sqlite3'))


class PoolTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = FakeApp(self.tmp.name)
        self.addCleanup(self.app.store.db.close)
        self.pool = Pool(self.app)
        (self.app.dir / 'daily-outlook').mkdir(exist_ok=True)
        self.now = datetime(2026, 11, 13, 15, 0, tzinfo=CN)

    # ---------- helpers ----------
    def issue(self, day='2026-11-09', published=None, picks=None, directions=None, radar=None,
              version=9):
        return dict(quote_date=day, screen_version=version,
                    published_at=published or f'{day}T13:00:00+08:00',
                    native_slot=f'{day} 13:00',
                    top_picks=picks if picks is not None else [
                        pick('sh600001', '甲股份')],
                    directions=directions if directions is not None else [
                        dict(sector='AI硬件', sector_code='BK0002', sector_kind='概念', state='可考虑建仓',
                             why='板块资金净流入。', candidate=dict(code='sz000003', name='丙电子'),
                             stocks=[stock('sz000003', '丙电子', 30.0, 2.0)])],
                    radar=radar if radar is not None else [
                        dict(theme='军工订单', kind='事件/题材', stage='发酵', verdict='回踩低吸',
                             news_count=2,
                             stocks=[stock('sz000005', '戊航空', 15.0, 10.0, role='龙头', chase=15.3)]),
                        dict(theme='东方', kind='名称类', stage='加速/高潮', verdict='只观察，不追高',
                             stocks=[stock('sh600006', '东方一', 12.0, 9.9, role='龙头', chase=12.2)])])

    def sync(self, issue=None):
        with patch.object(self.pool, 'poll'):
            return self.pool.sync_issue(issue or self.issue(), fetch=False)

    def write_issue_file(self, day, stamp=None, code='sh600001'):
        issue = self.issue(day=day, published=stamp or f'{day}T13:00:00+08:00',
                           picks=[pick(code, '甲股份')], directions=[], radar=[])
        path = self.app.dir / 'daily-outlook' / f'{day}_130000_000001.json'
        path.write_text(json.dumps(issue, ensure_ascii=False), encoding='utf-8')
        return path

    def view_entry(self, moment=None, code='sh600001', **kwargs):
        with patch('core.pool.now_cn', return_value=moment or self.now):
            view = self.pool.view(limit=200, **kwargs)
        return next(item for item in view['entries'] if item['code'] == code), view

    # ---------- 行情字段 ----------
    def test_parse_quotes_quant_fields(self):
        text = tencent_line('sh600000', {38: '7.89', 43: '3.2', 44: '123.4', 49: '1.03'})
        parsed = parse_quotes(text, {'sh600000'})['sh600000']
        self.assertEqual(parsed['turnover_rate'], 7.89)
        self.assertEqual(parsed['amplitude'], 3.2)
        self.assertEqual(parsed['float_mcap_yi'], 123.4)
        self.assertEqual(parsed['volume_ratio'], 1.03)
        # Legacy fields stay byte-for-byte compatible.
        self.assertEqual(parsed['price'], '10')
        self.assertEqual(parsed['previous_close'], '9.8')
        self.assertEqual(parsed['volume'], 1000000)
        self.assertEqual(parsed['amount_yuan'], '10000000')
        self.assertEqual(parsed['day_low'], '9.8')
        self.assertEqual(parsed['day_high'], '10.2')

    def test_parse_quotes_quant_missing_is_none(self):
        values = ['0'] * 38
        values[2] = '600000'
        values[3] = '10'
        values[4] = '9.8'
        values[6] = '10000'
        values[30] = '20261109100000'
        values[33] = '10.2'
        values[34] = '9.8'
        values[37] = '1000'
        parsed = parse_quotes('v_sh600000="' + '~'.join(values) + '";', {'sh600000'})['sh600000']
        self.assertIsNone(parsed['turnover_rate'])
        self.assertIsNone(parsed['amplitude'])
        self.assertIsNone(parsed['float_mcap_yi'])
        self.assertIsNone(parsed['volume_ratio'])
        bad = tencent_line('sh600000', {38: '--', 43: 'NaN', 44: '', 49: 'abc'})
        parsed = parse_quotes(bad, {'sh600000'})['sh600000']
        self.assertIsNone(parsed['turnover_rate'])
        self.assertIsNone(parsed['amplitude'])
        self.assertIsNone(parsed['float_mcap_yi'])
        self.assertIsNone(parsed['volume_ratio'])

    def test_pool_day_quant_columns_and_history(self):
        self.sync()
        self.pool.quotes = {'sh600001': quote('sh600001', 10.5, 10.2, high=10.8, low=10.0)}
        self.pool._write_day('sh600001', '2026-11-09', quote('sh600001', 10.5, 10.2, high=10.8, low=10.0),
                             dict(high=10.8, low=10.0), datetime(2026, 11, 9, 14, 0, tzinfo=CN))
        row = self.app.store.query('SELECT turnover_rate,volume_ratio FROM pool_day '
                                   'WHERE code=? AND day=?', ('sh600001', '2026-11-09'))[0]
        self.assertEqual(row['turnover_rate'], 7.89)
        self.assertEqual(row['volume_ratio'], 1.03)
        self.pool.quotes = {}
        entry, _ = self.view_entry(moment=datetime(2026, 11, 9, 16, 0, tzinfo=CN))
        self.assertEqual(entry['quote']['basis'], 'last')
        self.assertEqual(entry['quant'], dict(turnover_rate=7.89, volume_ratio=1.03,
                                              amplitude=None, float_mcap_yi=None))
        self.assertEqual(entry['history'][-1]['turnover_rate'], 7.89)
        self.assertEqual(entry['history'][-1]['volume_ratio'], 1.03)

    # ---------- 库迁移 ----------
    def test_legacy_store_schema_is_migrated(self):
        path = Path(self.tmp.name) / 'legacy.sqlite3'
        legacy = sqlite3.connect(str(path))
        legacy.executescript('''
            CREATE TABLE pool(code TEXT PRIMARY KEY,name TEXT,added_day TEXT NOT NULL,added_price REAL,
              source TEXT NOT NULL,sector TEXT,role TEXT,reason TEXT,state TEXT NOT NULL,plan TEXT,
              updated_at TEXT,category TEXT,group_name TEXT,entry_tag TEXT,added_at TEXT,
              groups_json TEXT,archived INTEGER DEFAULT 0);
            CREATE TABLE pool_day(code TEXT,day TEXT,price REAL,percent REAL,high REAL,low REAL,state TEXT,
              hit_buy INTEGER DEFAULT 0,hit_stop INTEGER DEFAULT 0,hit_target INTEGER DEFAULT 0,
              collected_at TEXT,PRIMARY KEY(code,day));
            CREATE TABLE pool_episode(code TEXT NOT NULL,issue_id TEXT NOT NULL,published_at TEXT NOT NULL,
              quote_date TEXT,source TEXT,entry_tag TEXT,price REAL,plan TEXT,reason TEXT,sector TEXT,
              sector_kind TEXT,created_at TEXT,PRIMARY KEY(code,issue_id));
        ''')
        legacy.commit()
        legacy.close()
        store = Store(str(path))
        try:
            day_columns = {row['name'] for row in store.query('PRAGMA table_info(pool_day)')}
            self.assertTrue({'turnover_rate', 'volume_ratio'} <= day_columns)
            episode_columns = {row['name'] for row in store.query('PRAGMA table_info(pool_episode)')}
            self.assertTrue({'percent', 'category', 'group_name', 'groups_json', 'driver_short'}
                            <= episode_columns)
            with store.lock:
                store.db.execute(
                    'INSERT INTO pool_day(code,day,price,turnover_rate,volume_ratio) VALUES(?,?,?,?,?)',
                    ('sh600001', '2026-11-09', 10.0, 5.5, 1.2))
                store.db.execute(
                    'INSERT INTO pool_episode(code,issue_id,published_at,percent,category,group_name,groups_json) '
                    'VALUES(?,?,?,?,?,?,?)',
                    ('sh600001', '2026-11-09T13:00:00+08:00', '2026-11-09T13:00:00+08:00', 1.2, '概念', '智能穿戴', '[]'))
                store.db.commit()
            self.assertEqual(store.query('SELECT turnover_rate FROM pool_day')[0]['turnover_rate'], 5.5)
            self.assertEqual(store.query('SELECT category FROM pool_episode')[0]['category'], '概念')
        finally:
            store.db.close()

    # ---------- 入选事件 ----------
    def test_episodes_are_idempotent(self):
        first = self.sync()
        self.assertEqual(first['candidates'], 4)
        self.sync()
        rows = self.app.store.query('SELECT COUNT(*) AS n FROM pool_episode')
        self.assertEqual(rows[0]['n'], 4)
        entry, _ = self.view_entry(moment=datetime(2026, 11, 9, 16, 0, tzinfo=CN))
        self.assertEqual(entry['episodes'], dict(total=1, today=1,
                                                 first_at='2026-11-09T13:00:00+08:00',
                                                 last_at='2026-11-09T13:00:00+08:00'))

    def test_episodes_total_today_first_last(self):
        self.sync(self.issue(day='2026-11-09'))
        self.sync(self.issue(day='2026-11-10', published='2026-11-10T10:30:00+08:00'))
        entry, _ = self.view_entry(moment=datetime(2026, 11, 10, 15, 0, tzinfo=CN))
        self.assertEqual(entry['episodes']['total'], 2)
        self.assertEqual(entry['episodes']['today'], 1)
        self.assertEqual(entry['episodes']['first_at'], '2026-11-09T13:00:00+08:00')
        self.assertEqual(entry['episodes']['last_at'], '2026-11-10T10:30:00+08:00')

    def test_episode_total_counts_selection_days_not_issues(self):
        # 同一 code 同一天多期研判只算 1 天，episode 行仍分别保留。
        self.sync(self.issue(day='2026-11-09', published='2026-11-09T08:11:00+08:00',
                             picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        self.sync(self.issue(day='2026-11-09', published='2026-11-09T10:30:00+08:00',
                             picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        self.sync(self.issue(day='2026-11-10', published='2026-11-10T13:00:00+08:00',
                             picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        self.assertEqual(self.app.store.query('SELECT COUNT(*) AS n FROM pool_episode')[0]['n'], 3)
        entry, _ = self.view_entry(moment=datetime(2026, 11, 10, 15, 0, tzinfo=CN))
        self.assertEqual(entry['episodes'], dict(total=2, today=1,
                                                 first_at='2026-11-09T08:11:00+08:00',
                                                 last_at='2026-11-10T13:00:00+08:00'))
        later, _ = self.view_entry(moment=datetime(2026, 11, 11, 10, 0, tzinfo=CN))
        self.assertEqual((later['episodes']['total'], later['episodes']['today']), (2, 0))

    def test_episode_total_three_days_and_today_flag(self):
        for day in ('2026-11-09', '2026-11-10', '2026-11-11'):
            self.sync(self.issue(day=day, published=f'{day}T10:00:00+08:00',
                                 picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
            self.sync(self.issue(day=day, published=f'{day}T13:30:00+08:00',
                                 picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        self.assertEqual(self.app.store.query('SELECT COUNT(*) AS n FROM pool_episode')[0]['n'], 6)
        entry, _ = self.view_entry(moment=datetime(2026, 11, 11, 15, 0, tzinfo=CN))
        self.assertEqual(entry['episodes'], dict(total=3, today=1,
                                                 first_at='2026-11-09T10:00:00+08:00',
                                                 last_at='2026-11-11T13:30:00+08:00'))
        entry, _ = self.view_entry(moment=datetime(2026, 11, 12, 10, 0, tzinfo=CN))
        self.assertEqual((entry['episodes']['total'], entry['episodes']['today']), (3, 0))

    def test_pool_backtest_episodes_count_selection_days(self):
        for day, published in (('2026-11-09', '2026-11-09T08:11:00+08:00'),
                               ('2026-11-09', '2026-11-09T10:30:00+08:00'),
                               ('2026-11-10', '2026-11-10T13:00:00+08:00')):
            self.sync(self.issue(day=day, published=published, picks=[pick('sh600001', '甲股份')],
                                 directions=[], radar=[]))
        with patch('core.pool.now_cn', return_value=self.now):
            result = self.pool.pool_backtest()
        self.assertEqual([row['episodes'] for row in result['rows']], [2])

    def test_episodes_today_uses_previous_session_on_weekend(self):
        self.sync(self.issue(day='2026-11-13', published='2026-11-13T13:00:00+08:00'))
        entry, _ = self.view_entry(moment=datetime(2026, 11, 14, 10, 0, tzinfo=CN))
        self.assertEqual(entry['episodes']['total'], 1)
        self.assertEqual(entry['episodes']['today'], 1)
        self.assertEqual(entry['episodes']['last_at'], '2026-11-13T13:00:00+08:00')

    def test_legacy_episode_metadata_is_filled_in_place(self):
        issue = self.issue()
        with self.app.store.lock:
            self.app.store.db.execute(
                'INSERT INTO pool_episode(code,issue_id,published_at,quote_date,source,entry_tag,price,'
                'plan,reason,sector,sector_kind,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                ('sh600001', issue['published_at'], issue['published_at'], '2026-11-09', '建仓清单',
                 '可建仓', 10.2, '{}', '旧记录', '元件', '行业', '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        self.sync(issue)
        rows = self.app.store.query('SELECT COUNT(*) AS n FROM pool_episode WHERE code=?', ('sh600001',))
        self.assertEqual(rows[0]['n'], 1)
        row = self.app.store.query('SELECT category,group_name,percent,groups_json FROM pool_episode '
                                   'WHERE code=?', ('sh600001',))[0]
        self.assertEqual(row['category'], '概念')
        self.assertEqual(row['group_name'], '智能穿戴')
        self.assertEqual(row['percent'], 1.2)
        self.assertEqual(json.loads(row['groups_json']), ['概念'])

    def test_record_episodes_needs_published_at(self):
        issue = self.issue()
        issue.pop('published_at')
        self.assertEqual(self.pool.record_episodes(issue), dict(recorded=0, issue_id=None))
        self.assertEqual(self.app.store.query('SELECT COUNT(*) AS n FROM pool_episode')[0]['n'], 0)

    def test_backfill_episodes_uses_recent_limit_and_archives(self):
        for day in ('2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06', '2026-11-07'):
            self.write_issue_file(day)
        result = self.pool._backfill_episodes(limit=3)
        self.assertEqual(result['issues'], 3)
        issues = self.app.store.query('SELECT COUNT(DISTINCT issue_id) AS n FROM pool_episode')[0]['n']
        self.assertEqual(issues, 3)
        stamps = [row['published_at'] for row in
                  self.app.store.query('SELECT DISTINCT published_at FROM pool_episode ORDER BY published_at')]
        self.assertEqual(stamps, ['2026-11-05T13:00:00+08:00', '2026-11-06T13:00:00+08:00',
                                  '2026-11-07T13:00:00+08:00'])

    def test_bootstrap_backfills_all_archived_issues(self):
        for day in ('2026-11-03', '2026-11-06', '2026-11-09'):
            self.write_issue_file(day)
        with patch.object(self.pool, 'poll'):
            self.pool.bootstrap()
        issues = self.app.store.query('SELECT COUNT(DISTINCT issue_id) AS n FROM pool_episode')[0]['n']
        self.assertEqual(issues, 3)
        rows = self.app.store.query('SELECT COUNT(*) AS n FROM pool_episode')[0]['n']
        self.assertEqual(rows, 3)

    # ---------- view：tags / quant ----------
    def test_view_quant_and_tags_from_episodes(self):
        self.sync()
        self.pool.quotes = {'sh600001': quote('sh600001', 10.5, 10.2, high=10.8, low=10.0)}
        entries = {}
        with patch('core.pool.now_cn', return_value=datetime(2026, 11, 10, 15, 0, tzinfo=CN)):
            for entry in self.pool.view(limit=200)['entries']:
                entries[entry['code']] = entry
        self.assertEqual(entries['sh600001']['quant'], dict(turnover_rate=7.89, volume_ratio=1.03,
                                                            amplitude=3.2, float_mcap_yi=123.4))
        self.assertEqual(entries['sh600001']['tags'], dict(concept=['智能穿戴'], theme=[], event=[], other=[]))
        self.assertEqual(entries['sz000003']['tags']['concept'], ['AI硬件'])
        self.assertEqual(entries['sz000005']['tags']['event'], ['军工订单'])
        self.assertEqual(entries['sh600006']['tags']['theme'], ['东方'])
        self.assertEqual(entries['sh600006']['quant'], dict(turnover_rate=None, volume_ratio=None,
                                                            amplitude=None, float_mcap_yi=None))

    def test_view_tags_dedup_and_limit(self):
        self.sync(self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        with self.app.store.lock:
            for index in range(6):
                self.app.store.db.execute(
                    'INSERT INTO pool_episode(code,issue_id,published_at,percent,category,group_name,groups_json) '
                    'VALUES(?,?,?,?,?,?,?)',
                    ('sh600001', f'2026-11-1{index}T10:00:00+08:00', f'2026-11-1{index}T10:00:00+08:00',
                     1.0, '概念', f'概念{index % 5}', '[]'))
            self.app.store.db.commit()
        entry, _ = self.view_entry()
        self.assertEqual(len(entry['tags']['concept']), 4)
        self.assertEqual(len(entry['tags']['concept']), len(set(entry['tags']['concept'])))

    def test_view_tags_fallback_to_pool_row_without_episodes(self):
        with self.app.store.lock:
            self.app.store.db.execute(
                'INSERT INTO pool(code,name,added_day,added_price,source,category,group_name,entry_tag,'
                'groups_json,sector,state,plan,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('sh600001', '甲股份', '2026-11-09', 10.2, '建仓清单', '概念', '智能穿戴', '可建仓',
                 json.dumps(['概念']), '智能穿戴', '可建仓', '{}', '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        entry, _ = self.view_entry()
        self.assertEqual(entry['episodes']['total'], 0)
        self.assertEqual(entry['tags'], dict(concept=['智能穿戴'], theme=[], event=[], other=[]))

    # ---------- 回测 ----------
    def _seed_daily(self, code, closes):
        for day, close in closes.items():
            self.app.store.cache(code, 'daily', day, dict(date=day, close=close))

    def _seed_benchmark(self, closes):
        rows = [dict(date=day, close=value) for day, value in sorted(closes.items())]
        self.app.store.cache('sh000001', 'index_daily_v1', sorted(closes)[-1], dict(rows=rows))

    def test_pool_backtest_returns_pending_and_missing(self):
        self.sync(self.issue(day='2026-11-09', published='2026-11-09T13:00:00+08:00',
                             picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        self.sync(self.issue(day='2026-11-06', published='2026-11-06T13:00:00+08:00',
                             picks=[pick('sh600002', '乙股份')], directions=[], radar=[]))
        self._seed_benchmark({'2026-11-06': 3900.0, '2026-11-09': 3939.0, '2026-11-10': 3960.0,
                              '2026-11-11': 3980.0, '2026-11-12': 3970.0, '2026-11-13': 4000.0})
        self._seed_daily('sh600001', {'2026-11-10': 11.0, '2026-11-12': 12.0})
        self._seed_daily('sh600002', {'2026-11-13': 13.0})
        with patch('core.pool.now_cn', return_value=self.now):
            result = self.pool.pool_backtest()
        rows = {row['code']: row for row in result['rows']}
        self.assertEqual(result['coverage']['rows'], 2)
        self.assertEqual(result['coverage']['bench'], '上证指数')
        self.assertEqual(result['coverage']['episode_issues'], 2)
        self.assertEqual(result['coverage']['episode_range'], '2026-11-06~2026-11-09')
        fast = rows['sh600001']
        self.assertEqual(fast['first_day'], '2026-11-09')
        self.assertEqual(fast['first_price'], 10.2)
        self.assertEqual(fast['first_percent'], 1.2)
        self.assertEqual(fast['episodes'], 1)
        self.assertEqual(fast['pending'], ['T+5'])
        self.assertEqual(fast['missing'], [])
        self.assertAlmostEqual(fast['returns']['T+1']['ret_percent'], round((11.0 / 10.2 - 1) * 100, 2), places=2)
        self.assertEqual(fast['returns']['T+1']['ret_percent'], fast['returns']['T+1']['return_percent'])
        self.assertEqual(fast['returns']['T+1']['bench_percent'], fast['returns']['T+1']['benchmark_return'])
        self.assertEqual(fast['returns']['T+1']['date'], '2026-11-10')
        self.assertIsNone(fast['returns']['T+5'])
        slow = rows['sh600002']
        self.assertIsNone(slow['returns']['T+1'])
        self.assertIsNone(slow['returns']['T+3'])
        self.assertIsNotNone(slow['returns']['T+5'])
        self.assertEqual(slow['missing'], ['T+1', 'T+3'])
        self.assertEqual(slow['pending'], [])
        self.assertEqual(slow['tags'], dict(concept=['智能穿戴'], theme=[], event=[], other=[]))
        self.assertEqual(result['coverage']['with_returns'], 2)
        self.assertEqual(result['coverage']['daily_codes'], 2)

    def test_pool_backtest_skips_archived_and_caps_rows(self):
        self.sync(self.issue(day='2026-11-09', picks=[pick('sh600001', '甲股份')],
                             directions=[], radar=[]))
        with self.app.store.lock:
            for index in range(205):
                self.app.store.db.execute(
                    'INSERT INTO pool(code,name,added_day,added_price,source,state,updated_at) '
                    'VALUES(?,?,?,?,?,?,?)',
                    (f'sz2{index:05d}', f'样本{index}', '2026-11-09', 10.0, '手动', '观察',
                     '2026-11-09T08:00:00+08:00'))
            self.app.store.db.execute("UPDATE pool SET archived=1 WHERE code='sh600001'")
            self.app.store.db.commit()
        with patch('core.pool.now_cn', return_value=self.now):
            result = self.pool.pool_backtest()
        self.assertEqual(len(result['rows']), 200)
        codes = {row['code'] for row in result['rows']}
        self.assertNotIn('sh600001', codes)


    # ---------- 分组驱动 / 组级资金 ----------
    def test_view_driver_latest_episode_and_truncation(self):
        first = self.issue(day='2026-11-09', published='2026-11-09T13:00:00+08:00')
        second = self.issue(day='2026-11-10', published='2026-11-10T10:30:00+08:00')
        second['top_picks'][0]['sector'] = '人形机器人' * 20
        second['top_picks'][0]['why'] = '资金净流入且回踩买点。' * 12
        self.sync(first)
        self.sync(second)
        expected = self.pool._collect(second)['sh600001']['reason']
        self.assertGreater(len(expected), 80)
        entry, _ = self.view_entry(moment=datetime(2026, 11, 10, 15, 0, tzinfo=CN))
        self.assertEqual(entry['driver'], dict(at='2026-11-10T10:30:00+08:00', text=expected[:80]))

    def test_view_driver_and_fund_none_without_data(self):
        with self.app.store.lock:
            self.app.store.db.execute(
                'INSERT INTO pool(code,name,added_day,added_price,source,category,group_name,entry_tag,'
                'groups_json,sector,state,plan,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('sh600001', '甲股份', '2026-11-09', 10.2, '建仓清单', '概念', '智能穿戴', '可建仓',
                 json.dumps(['概念']), '智能穿戴', '可建仓', '{}', '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        entry, _ = self.view_entry()
        self.assertIsNone(entry['driver'])
        self.assertIsNone(entry['driver_short'])
        self.assertIsNone(entry['fund'])

    def test_view_entry_fund_comes_from_cache(self):
        self.sync(self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        fund = dict(net=32242504.0, net_yi=0.3224, rate=2.0, time='2026-11-11T12:45:00+08:00')
        self.pool.fund_flows = {'sh600001': fund}
        entry, _ = self.view_entry()
        self.assertEqual(entry['fund'], fund)

    # ---------- 简洁驱动 driver_short ----------
    def test_collect_driver_short_sources(self):
        issue = self.issue()
        issue['top_picks'][0]['why'] = '候选回落后已重回昨收上方，有同行上涨，板块上涨且资金净流入。'
        issue['directions'][0]['opportunity'] = (
            '当日净流入 48.73 亿元、板块内 6 只涨停、消息面「钧达股份早盘涨超10% 公司商业」。')
        issue['directions'][0]['why'] = '收盘时已走强，下一交易日开盘后再确认。'
        candidates = self.pool._collect(issue)
        self.assertEqual(candidates['sh600001']['driver_short'], '板块上涨、资金净流入')
        # 截断的「消息面」标题不再作为 driver，回退完整的 why 短句。
        self.assertEqual(candidates['sz000003']['driver_short'], '收盘时已走强，下一交易日开盘后再确认')
        self.assertEqual(candidates['sz000005']['driver_short'], '发酵·回踩低吸')
        self.assertEqual(candidates['sh600006']['driver_short'], '加速/高潮·只观察，不追高')

    def test_collect_driver_short_falls_back_to_direction_why(self):
        issue = self.issue()
        issue['directions'][0]['why'] = '候选回落后已重回昨收上方，有同行上涨，板块上涨且资金净流入。'
        candidates = self.pool._collect(issue)
        self.assertEqual(candidates['sz000003']['driver_short'], '板块上涨、资金净流入')

    def test_record_episodes_backfills_driver_short_for_legacy_rows(self):
        issue = self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[])
        issue['top_picks'][0]['why'] = '候选回落后已重回昨收上方，有同行上涨，板块上涨且资金净流入。'
        with self.app.store.lock:
            self.app.store.db.execute(
                'INSERT INTO pool_episode(code,issue_id,published_at,quote_date,source,entry_tag,price,'
                'reason,sector,sector_kind,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                ('sh600001', issue['published_at'], issue['published_at'], '2026-11-09', '建仓清单',
                 '可建仓', 10.2, '旧记录', '元件', '行业', '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        self.sync(issue)
        rows = self.app.store.query('SELECT driver_short,COUNT(*) OVER () AS n FROM pool_episode')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['n'], 1)
        self.assertEqual(rows[0]['driver_short'], '板块上涨、资金净流入')
        self.sync(issue)
        rows = self.app.store.query('SELECT COUNT(*) AS n,MAX(driver_short) AS driver_short FROM pool_episode')
        self.assertEqual(rows[0]['n'], 1)
        self.assertEqual(rows[0]['driver_short'], '板块上涨、资金净流入')

    def test_view_entry_driver_short_uses_latest_non_empty(self):
        first = self.issue(day='2026-11-09', published='2026-11-09T13:00:00+08:00',
                           picks=[pick('sh600001', '甲股份')], directions=[], radar=[])
        first['top_picks'][0]['why'] = '板块上涨且资金净流入。'
        second = self.issue(day='2026-11-10', published='2026-11-10T10:30:00+08:00',
                            picks=[pick('sh600001', '甲股份')], directions=[], radar=[])
        second['top_picks'][0]['why'] = '回踩低吸。'
        self.sync(first)
        self.sync(second)
        entry, _ = self.view_entry(moment=datetime(2026, 11, 10, 15, 0, tzinfo=CN))
        self.assertEqual(entry['driver_short'], '回踩低吸')
        # 最新一期为旧数据（driver_short 为空）时回退到最近的非空值。
        with self.app.store.lock:
            self.app.store.db.execute(
                'UPDATE pool_episode SET driver_short=NULL WHERE published_at=?',
                ('2026-11-10T10:30:00+08:00',))
            self.app.store.db.commit()
        entry, _ = self.view_entry(moment=datetime(2026, 11, 10, 15, 0, tzinfo=CN))
        self.assertEqual(entry['driver_short'], '板块上涨、资金净流入')

    def test_view_entry_driver_short_none_without_episodes(self):
        with self.app.store.lock:
            self.app.store.db.execute(
                'INSERT INTO pool(code,name,added_day,added_price,source,category,group_name,entry_tag,'
                'groups_json,sector,state,plan,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('sh600001', '甲股份', '2026-11-09', 10.2, '建仓清单', '概念', '智能穿戴', '可建仓',
                 json.dumps(['概念']), '智能穿戴', '可建仓', '{}', '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        entry, _ = self.view_entry()
        self.assertIsNone(entry['driver_short'])


    def test_refresh_fund_flows_limits_to_pool_codes(self):
        self.sync(self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        fetched = []

        def fake(codes, captured_at=None):
            fetched.append(list(codes))
            return {code: dict(net=1e8, net_yi=1.0, rate=1.0, time=captured_at) for code in codes}

        with patch.object(self.pool, '_fetch_sina_fund_flows', return_value={}), \
                patch.object(self.pool, '_fetch_fund_flows', side_effect=fake):
            flows = self.pool.refresh_fund_flows(['sh600001', 'sh999999'])
        self.assertEqual(fetched, [['sh600001']])
        self.assertEqual(set(flows), {'sh600001'})
        self.assertEqual(flows['sh600001']['net_yi'], 1.0)
        self.assertGreater(self.pool.fund_at, 0)

    def test_refresh_fund_flows_batches_at_eighty(self):
        with self.app.store.lock:
            for index in range(90):
                self.app.store.db.execute(
                    'INSERT INTO pool(code,name,added_day,added_price,source,state,updated_at) '
                    'VALUES(?,?,?,?,?,?,?)',
                    (f'sz3{index:05d}', f'样本{index}', '2026-11-09', 10.0, '手动', '观察',
                     '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        batches = []
        with patch.object(self.pool, '_fetch_sina_fund_flows', return_value={}), \
                patch.object(self.pool, '_fetch_fund_flows',
                             side_effect=lambda codes, captured_at=None: batches.append(len(codes)) or {}):
            self.pool.refresh_fund_flows()
        self.assertEqual(batches, [80, 10])

    def test_fetch_fund_flows_parses_response_and_swallows_failures(self):
        class FakeResponse:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        payload = {'data': {'diff': [{'f12': '600293', 'f13': 1, 'f62': 1e8, 'f184': 5.0}]}}
        with patch('core.pool.urllib.request.urlopen',
                   return_value=FakeResponse(json.dumps(payload).encode('utf-8'))):
            flows = self.pool._fetch_fund_flows(['sh600293'], '2026-11-11T12:45:00+08:00')
        self.assertEqual(flows['sh600293'], dict(net=1e8, net_yi=1.0, rate=5.0,
                                                 time='2026-11-11T12:45:00+08:00'))
        with patch('core.pool.urllib.request.urlopen', side_effect=OSError('network down')):
            self.assertEqual(self.pool._fetch_fund_flows(['sh600293']), {})
        with patch('core.pool.urllib.request.urlopen', return_value=FakeResponse(b'not-json')):
            self.assertEqual(self.pool._fetch_fund_flows(['sh600293']), {})


    def test_fetch_sina_fund_flows_parses_and_swallows_failures(self):
        payload = [
            {'symbol': 'sz002747', 'netamount': '32242504.0000', 'ratioamount': '0.163914'},
            {'symbol': 'sh600293', 'netamount': '-103805542.0000', 'ratioamount': '-0.2'},
            {'symbol': 'sh999999', 'netamount': '1.0000', 'ratioamount': '0.0001'},
            {'symbol': 'sz000001', 'netamount': '--', 'ratioamount': '-'},
        ]
        with patch('core.pool.urllib.request.urlopen',
                   return_value=FakeResponse(json.dumps(payload).encode('utf-8'))):
            flows = self.pool._fetch_sina_fund_flows(['sz002747', 'sh600293'], '2026-11-11T21:00:00+08:00')
        self.assertEqual(set(flows), {'sz002747', 'sh600293'})
        self.assertEqual(flows['sz002747'], dict(net=32242504.0, net_yi=0.3224, rate=16.39,
                                                 time='2026-11-11T21:00:00+08:00'))
        self.assertEqual(flows['sh600293']['net_yi'], -1.0381)
        self.assertEqual(flows['sh600293']['rate'], -20.0)
        self.assertIn('num=6000', SINA_FUND_FLOW_URL)
        self.assertIn('bankuai=hs_a', SINA_FUND_FLOW_URL)
        with patch('core.pool.urllib.request.urlopen', side_effect=OSError('network down')):
            self.assertEqual(self.pool._fetch_sina_fund_flows(['sz002747']), {})
        with patch('core.pool.urllib.request.urlopen', return_value=FakeResponse(b'not-json')):
            self.assertEqual(self.pool._fetch_sina_fund_flows(['sz002747']), {})

    def test_refresh_fund_flows_prefers_sina_and_skips_eastmoney(self):
        self.sync(self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        sina = {'sh600001': dict(net=1e8, net_yi=1.0, rate=2.5, time='2026-11-11T21:00:00+08:00')}
        with patch.object(self.pool, '_fetch_sina_fund_flows', return_value=sina) as sina_call, \
                patch.object(self.pool, '_fetch_fund_flows',
                             side_effect=AssertionError('Sina 成功时不应再请求 EM')):
            flows = self.pool.refresh_fund_flows()
        sina_call.assert_called_once()
        self.assertEqual(flows['sh600001'], sina['sh600001'])
        self.assertGreater(self.pool.fund_at, 0)

    def test_refresh_fund_flows_falls_back_to_eastmoney_when_sina_empty(self):
        self.sync(self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        em_calls = []

        def fake_em(codes, captured_at=None):
            em_calls.append(list(codes))
            return {code: dict(net=2e8, net_yi=2.0, rate=1.0, time=captured_at) for code in codes}

        with patch.object(self.pool, '_fetch_sina_fund_flows', return_value={}), \
                patch.object(self.pool, '_fetch_fund_flows', side_effect=fake_em):
            flows = self.pool.refresh_fund_flows(['sh600001'])
        self.assertEqual(em_calls, [['sh600001']])
        self.assertEqual(flows['sh600001']['net_yi'], 2.0)

    def test_refresh_fund_flows_keeps_old_values_when_all_sources_fail(self):
        self.sync(self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        old = dict(net=32242504.0, net_yi=0.3224, rate=2.0, time='2026-11-11T20:00:00+08:00')
        self.pool.fund_flows = {'sh600001': old}
        with patch.object(self.pool, '_fetch_sina_fund_flows', return_value={}), \
                patch.object(self.pool, '_fetch_fund_flows', return_value={}):
            flows = self.pool.refresh_fund_flows()
        self.assertEqual(flows['sh600001'], old)

    def test_collect_uses_news_driver_for_sources(self):
        issue = self.issue()
        issue['top_picks'][0]['why'] = '收盘时已走强，下一交易日开盘后再确认。'
        issue['pulse'] = {'hotspots': {'news': [
            {'title': '甲股份早盘涨超10% 公司获大额订单'},
            {'title': '丙电子午后涨停 获政策支持'},
            {'title': '戊航空今日涨停 军工订单落地'},
            {'title': '港股午评：恒指跌0.83% 科指跌1.36%'},
        ]}}
        candidates = self.pool._collect(issue)
        self.assertEqual(candidates['sh600001']['driver_short'], '甲股份早盘涨超10%')
        self.assertEqual(candidates['sz000003']['driver_short'], '丙电子午后涨停')
        self.assertEqual(candidates['sz000005']['driver_short'], '戊航空今日涨停')
        # 无新闻命中的雷达候选回退 stage/verdict 短句。
        self.assertEqual(candidates['sh600006']['driver_short'], '加速/高潮·只观察，不追高')

    def test_collect_news_driver_rejects_long_half_sentence(self):
        issue = self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[])
        issue['top_picks'][0]['why'] = '板块上涨且资金净流入。'
        issue['pulse'] = {'hotspots': {'news': [
            {'title': '甲股份早盘涨超12%公司获大额订单并签署战略合作协议推进人形机器人商业化落地进程'},
        ]}}
        candidates = self.pool._collect(issue)
        self.assertEqual(candidates['sh600001']['driver_short'], '板块上涨、资金净流入')

    def test_record_episodes_overwrites_legacy_driver_short(self):
        issue = self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[])
        issue['pulse'] = {'hotspots': {'news': [{'title': '甲股份早盘涨超10% 公司获大额订单'}]}}
        with self.app.store.lock:
            self.app.store.db.execute(
                'INSERT INTO pool_episode(code,issue_id,published_at,quote_date,source,entry_tag,price,'
                'reason,sector,sector_kind,driver_short,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                ('sh600001', issue['published_at'], issue['published_at'], '2026-11-09', '建仓清单',
                 '可建仓', 10.2, '旧记录', '元件', '行业', '旧驱动', '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        self.sync(issue)
        rows = self.app.store.query('SELECT driver_short,COUNT(*) OVER () AS n FROM pool_episode')
        self.assertEqual(rows[0]['n'], 1)
        self.assertEqual(rows[0]['driver_short'], '甲股份早盘涨超10%')
        self.sync(issue)
        rows = self.app.store.query('SELECT driver_short FROM pool_episode')
        self.assertEqual(rows[0]['driver_short'], '甲股份早盘涨超10%')

    def test_poll_refreshes_fund_flows_with_throttle(self):
        self.sync(self.issue(picks=[pick('sh600001', '甲股份')], directions=[], radar=[]))
        calls = []

        def fake(codes, captured_at=None):
            calls.append(list(codes))
            return {}

        with patch.object(self.pool, '_batch',
                          return_value={'sh600001': quote('sh600001', 10.5, 10.2)}), \
                patch.object(self.pool, '_fetch_sina_fund_flows', return_value={}), \
                patch.object(self.pool, '_fetch_fund_flows', side_effect=fake):
            self.pool.fund_at = 0.0
            self.pool.poll(force=True)
            self.assertEqual(len(calls), 1)
            self.pool.poll(force=True)
            self.assertEqual(len(calls), 1)
            self.pool.fund_at -= FUND_FLOW_SECONDS + 1
            self.pool.poll(force=True)
            self.assertEqual(len(calls), 2)


class DriverShortHelperTests(unittest.TestCase):
    def test_short_driver_keyword_mapping(self):
        self.assertEqual(_short_driver('候选回落后已重回昨收上方，有同行上涨，板块上涨且资金净流入。'),
                         '板块上涨、资金净流入')
        self.assertEqual(_short_driver('加速/高潮·只观察，不追高'), '只观察不追高')
        self.assertEqual(_short_driver('低空经济·发酵·回踩低吸，不追高'), '回踩低吸')
        self.assertEqual(_short_driver('涨停待回踩'), '涨停待回踩')
        self.assertEqual(_short_driver('加速/高潮·分歧'), '加速期')
        self.assertEqual(_short_driver('题材发酵'), '题材发酵')

    def test_short_driver_prefix_and_fallback(self):
        self.assertEqual(_short_driver('方向：AI硬件（可考虑建仓）；候选回落后已重回昨收上方。'),
                         '候选回落后已重回昨收上方')
        self.assertEqual(_short_driver('只有这一句。'), '只有这一句')
        long_segment = '；'.join(['前缀段', '一' * 40])
        self.assertEqual(_short_driver(long_segment), '一' * 20)
        self.assertEqual(_short_driver('候选股回落后重新超过昨收、同行同步上涨的条件尚未齐备。'),
                         '候选股回落后重新超过昨收')
        self.assertEqual(_short_driver(''), '')
        self.assertEqual(_short_driver(None), '')

    def test_message_driver_extraction(self):
        opportunity = '当日净流入 37.84 亿元、板块内 7 只涨停、消息面「Anthropic进军人工智能办」。'
        self.assertEqual(_message_driver(opportunity), 'Anthropic进军人工智能办')
        self.assertEqual(_message_driver('消息面「 大摩 高喊 抄底 半导体 」'), '大摩高喊抄底半导体')
        long_title = '消息面「' + '长' * 40 + '」'
        self.assertEqual(_message_driver(long_title), '长' * 26)
        self.assertEqual(_message_driver('当日净流入 3.16 亿元、板块内 1 只涨停。'), '')
        self.assertEqual(_message_driver(None), '')

    def test_radar_driver_extraction(self):
        self.assertEqual(_radar_driver('东方·加速/高潮·只观察，不追高'), '加速/高潮·只观察，不追高')
        self.assertEqual(_radar_driver('稀土/资源·启动初期·先观察，等首批涨停或资金确认'),
                         '启动初期·先观察，等首批涨停或资金确认'[:24])
        self.assertEqual(_radar_driver('东方·' + '阶' * 30 + '·只观察'), ('阶' * 30)[:24])
        self.assertEqual(_radar_driver('东方'), '东方')



class FundFlowSinaHelperTests(unittest.TestCase):
    def test_parse_sina_fund_flow_payload(self):
        payload = [
            {'symbol': 'sz002747', 'netamount': '32242504.0000', 'ratioamount': '0.163914'},
            {'symbol': 'sh600293', 'netamount': '-103805542.0000', 'ratioamount': '-0.2'},
            {'symbol': 'sh999999', 'netamount': '1.0000', 'ratioamount': '0.0001'},
            {'symbol': 'bad', 'netamount': '1.0000', 'ratioamount': '0'},
            {'symbol': 'sz000002', 'netamount': '--', 'ratioamount': '--'},
        ]
        flows = _parse_sina_fund_flow_payload(payload, ['sz002747', 'sh600293'],
                                              '2026-11-11T21:00:00+08:00')
        self.assertEqual(set(flows), {'sz002747', 'sh600293'})
        self.assertEqual(flows['sz002747'], dict(net=32242504.0, net_yi=0.3224, rate=16.39,
                                                 time='2026-11-11T21:00:00+08:00'))
        self.assertEqual(flows['sh600293']['net_yi'], -1.0381)
        self.assertEqual(flows['sh600293']['rate'], -20.0)
        self.assertEqual(_parse_sina_fund_flow_payload(payload, [], 'x'), {})
        self.assertEqual(_parse_sina_fund_flow_payload({'data': []}, ['sz002747'], 'x'), {})


class NewsDriverHelperTests(unittest.TestCase):
    def test_news_driver_matches_name_before_sector(self):
        news = [{'title': '半导体板块午后拉升，多股涨停'},
                {'title': '甲股份早盘涨超12%，公司获大额订单'}]
        self.assertEqual(_news_driver(news, '甲股份', '半导体', ''), '甲股份早盘涨超12%')

    def test_news_driver_matches_sector_theme_keywords(self):
        news = [{'title': '人形机器人板块午后拉升，多股涨停'}]
        self.assertEqual(_news_driver(news, '', '机器人执行器', ''), '人形机器人板块午后拉升')
        self.assertEqual(_news_driver([{'title': '大摩高喊抄底半导体！机构看好后市'}], '', '半导体', ''),
                         '大摩高喊抄底半导体')

    def test_news_driver_ignores_unrelated_titles(self):
        news = [{'title': '今日比特币：跌至7.4万美元附近，现货ETF上周遭12.8亿美元资金撤出'}]
        self.assertEqual(_news_driver(news, '甲股份', '半导体', ''), '')
        self.assertEqual(_news_driver([{'title': '港股午评：恒指跌0.83% 科指跌1.36%'}],
                                      '剑桥科技', '通信设备', ''), '')

    def test_news_driver_requires_complete_clause(self):
        news = [{'title': '甲股份早盘涨超12%公司获大额订单并签署战略合作协议推进人形机器人商业化落地进程'}]
        self.assertEqual(_news_driver(news, '甲股份', '', ''), '')

    def test_news_sentence_strips_media_prefix_and_keeps_complete_clause(self):
        self.assertEqual(_news_sentence('智通财经：优必选早盘涨超5%', '优必选'), '优必选早盘涨超5%')
        self.assertEqual(
            _news_sentence('光又回来了！超116亿资金涌入，“易中天”、源杰科技、联讯仪器、剑桥科技等集体大涨', '剑桥科技'),
            '剑桥科技等集体大涨')
        self.assertEqual(_news_sentence('公司公告：签订5亿元订单，股价涨停'), '签订5亿元订单')

    def test_news_ascii_tokens_need_word_boundary(self):
        openai_title = {'title': '台积电批准向Anthropic和OpenAI合计投资10亿美元，10月营收同比大增60%'}
        self.assertEqual(_news_driver([openai_title], '埃斯顿', '物理AI', ''), '')
        physical = {'title': '物理AI概念股涨幅居前 凯乐士科技大涨超57%'}
        self.assertEqual(_news_driver([physical], '埃斯顿', '物理AI', ''), '物理AI概念股涨幅居前')

    def test_news_name_variants_match_full_width_suffix(self):
        self.assertEqual(_news_driver([{'title': '京东方A午后涨超5%'}], '京东方Ａ', '', ''), '京东方A午后涨超5%')
        self.assertEqual(_news_driver([{'title': '宇树科技盘中涨超8%'}], '宇树科技-W', '', ''), '宇树科技盘中涨超8%')


class FundFlowHelperTests(unittest.TestCase):
    def test_secid_conversion_and_url(self):
        self.assertEqual(_secid('sh600293'), '1.600293')
        self.assertEqual(_secid('sz002747'), '0.002747')
        self.assertEqual(_secid('sh688001'), '1.688001')
        self.assertIsNone(_secid(''))
        self.assertIsNone(_secid(None))
        url = _fund_flow_url(['1.600293', '0.002747'])
        self.assertIn('fltt=2', url)
        self.assertIn('secids=1.600293,0.002747', url)
        self.assertIn('fields=f12,f13,f14,f62,f184', url)

    def test_parse_fund_flow_payload(self):
        payload = {'rc': 0, 'data': {'total': 3, 'diff': [
            {'f12': '600293', 'f13': 1, 'f14': '三峡新材', 'f62': 103805542.0, 'f184': 18.09},
            {'f12': '002747', 'f13': 0, 'f14': '埃斯顿', 'f62': 32242504.0, 'f184': 2.0},
            {'f12': '600001', 'f13': 1, 'f14': '坏数据', 'f62': '-', 'f184': '-'},
        ]}}
        flows = _parse_fund_flow_payload(payload, '2026-11-11T12:45:00+08:00')
        self.assertEqual(set(flows), {'sh600293', 'sz002747'})
        self.assertEqual(flows['sz002747'], dict(net=32242504.0, net_yi=0.3224, rate=2.0,
                                                 time='2026-11-11T12:45:00+08:00'))
        self.assertEqual(flows['sh600293']['net_yi'], 1.0381)
        self.assertEqual(_parse_fund_flow_payload({}, 'x'), {})
        self.assertEqual(_parse_fund_flow_payload({'data': None}, 'x'), {})
        self.assertEqual(_parse_fund_flow_payload({'data': {'diff': 'bad'}}, 'x'), {})


class PoolBacktestRpcTests(unittest.TestCase):
    def test_app_dispatches_pool_backtest_offline(self):
        from core.app import App
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = App(tmp.name, start_worker=False)
        self.addCleanup(app.stop.set)
        self.addCleanup(app.store.db.close)
        result = app.call('pool_backtest', {})
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['coverage']['rows'], 0)
        self.assertEqual(result['coverage']['with_returns'], 0)
        self.assertEqual(result['coverage']['bench'], '上证指数')
        self.assertIsNone(result['coverage']['episode_range'])
        self.assertEqual(result['coverage']['episode_issues'], 0)


class TradingDayTests(unittest.TestCase):
    def test_trading_day_weekend_falls_back_to_friday(self):
        from core.pool import _trading_day
        self.assertEqual(_trading_day(datetime(2026, 11, 14, 10, 0, tzinfo=CN)), '2026-11-13')
        self.assertEqual(_trading_day(datetime(2026, 11, 15, 10, 0, tzinfo=CN)), '2026-11-13')
        self.assertEqual(_trading_day(datetime(2026, 11, 13, 10, 0, tzinfo=CN)), '2026-11-13')


if __name__ == '__main__':
    unittest.main()
