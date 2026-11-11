import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.breadth import parse_quotes
from core.pool import Pool
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
            self.assertTrue({'percent', 'category', 'group_name', 'groups_json'} <= episode_columns)
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
