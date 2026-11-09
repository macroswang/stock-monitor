import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.pool import Pool
from core.provider import CN
from core.store import Store


def quote(code, price, previous, high=None, low=None, day='2026-11-09'):
    return dict(code=code, price=str(price), previous_close=str(previous),
                timestamp=day + 'T10:00:00+08:00',
                day_high=str(high if high is not None else price),
                day_low=str(low if low is not None else price),
                amount_yuan='100000000')


class FakeApp:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.store = Store(str(Path(folder) / 'monitor.sqlite3'))


def pick(code, name, price=10.2, percent=1.2, chase=10.6, sector='元件', kind='行业',
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


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = FakeApp(self.tmp.name)
        self.addCleanup(self.app.store.db.close)
        self.pool = Pool(self.app)
        self.now = datetime(2026, 11, 9, 13, 0, tzinfo=CN)
        (self.app.dir / 'daily-outlook').mkdir(exist_ok=True)

    def issue(self):
        return dict(quote_date='2026-11-09', screen_version=9,
                    published_at='2026-11-09T13:00:00+08:00', native_slot='2026-11-09 13:00',
                    top_picks=[
                        pick('sh600001', '甲股份'),
                        pick('sz000002', '乙科技', price=20.0, percent=10.01, chase=20.6,
                             sector='昨日首板', kind='概念', role='龙头'),
                    ],
                    directions=[
                        dict(sector='AI硬件', sector_code='BK0002', sector_kind='概念', state='可考虑建仓',
                             why='板块资金净流入。', candidate=dict(code='sz000003', name='丙电子'),
                             stocks=[stock('sz000003', '丙电子', 30.0, 2.0),
                                     stock('sh600009', '东方新能', 5.0, 9.9, role='龙头', chase=5.2)]),
                        dict(sector='煤炭', sector_code='BK0003', sector_kind='行业', state='继续等',
                             why='候选尚未回踩买点。', candidate=dict(code='sh600004', name='丁能源'),
                             stocks=[stock('sh600004', '丁能源', 8.0, 0.5)]),
                    ],
                    radar=[
                        dict(theme='低空经济', kind='事件/题材', stage='发酵', verdict='回踩低吸', news_count=2,
                             stocks=[stock('sz000005', '戊航空', 15.0, 10.0, role='龙头', chase=15.3)]),
                        dict(theme='东方', kind='名称类', stage='加速/高潮', verdict='只观察，不追高',
                             stocks=[stock('sh600006', '东方一', 12.0, 9.9, role='龙头', chase=12.2)]),
                        dict(theme='2027 羊年（跨年）', kind='生肖/玄学', stage='分歧', verdict='只观察，等重新一致',
                             stocks=[stock('sz000007', '羊羊羊', 9.0, 3.0, role='龙头', chase=9.3)]),
                    ])

    def sync(self, issue=None):
        with patch.object(self.pool, 'poll'):
            return self.pool.sync_issue(issue or self.issue())

    def set_quotes(self):
        self.pool.quotes = {
            'sh600001': quote('sh600001', 10.5, 10.2, high=10.8, low=10.0),
            'sz000002': quote('sz000002', 21.0, 20.0, high=21.0, low=19.8),
            'sz000003': quote('sz000003', 29.0, 30.0, high=30.2, low=28.8),
            'sh600004': quote('sh600004', 8.1, 8.0, high=8.2, low=7.9),
            'sz000005': quote('sz000005', 15.0, 15.0, high=15.2, low=14.8),
            'sh600006': quote('sh600006', 12.5, 12.0, high=12.6, low=11.9),
            'sz000007': quote('sz000007', 8.5, 9.0, high=9.0, low=8.4),
        }

    def test_sync_all_sources_with_groups_and_tags(self):
        result = self.sync()
        self.assertEqual(result['added'], 8)
        self.assertEqual(result['candidates'], 8)
        rows = {row['code']: row for row in self.app.store.query('SELECT * FROM pool')}
        self.assertEqual(rows['sh600001']['entry_tag'], '可建仓')
        self.assertEqual(rows['sh600001']['category'], '行业')
        self.assertEqual(rows['sz000002']['entry_tag'], '涨停待回踩')
        self.assertEqual(rows['sz000003']['entry_tag'], '可建仓')
        self.assertEqual(rows['sh600004']['entry_tag'], '条件未达')
        self.assertEqual(rows['sz000005']['category'], '事件')
        self.assertEqual(rows['sz000005']['entry_tag'], '题材观察')
        self.assertEqual(rows['sh600006']['category'], '名称辈')
        self.assertEqual(rows['sz000007']['category'], '生肖玄学')
        self.assertEqual(rows['sz000003']['source'], '方向候选')
        self.assertEqual(rows['sh600009']['category'], '名称辈')
        self.assertEqual(rows['sh600009']['entry_tag'], '涨停待回踩')
        self.assertEqual(rows['sz000005']['source'], '炒作雷达')
        self.assertTrue(all(row['group_name'] for row in rows.values()))
        self.assertEqual(rows['sh600009']['added_at'], '2026-11-09T13:00:00+08:00')

    def test_repeat_sync_keeps_baseline_and_refreshes_tag(self):
        self.sync()
        first = self.app.store.query('SELECT added_day,added_price FROM pool WHERE code=?', ('sh600001',))[0]
        issue = self.issue()
        issue['top_picks'][0]['price'] = 99.0
        issue['top_picks'][0]['percent'] = 10.0
        issue['top_picks'][0]['chase'] = 100.0
        result = self.sync(issue)
        self.assertEqual(result['added'], 0)
        row = self.app.store.query('SELECT * FROM pool WHERE code=?', ('sh600001',))[0]
        self.assertEqual(row['added_day'], first['added_day'])
        self.assertEqual(row['added_price'], first['added_price'])
        self.assertEqual(row['entry_tag'], '涨停待回踩')
        self.assertEqual(row['state'], '涨停待回踩')

    def test_view_win_rate_and_performance(self):
        self.sync()
        self.set_quotes()
        view = self.pool.view()
        summary = view['summary']
        self.assertEqual(summary['total'], 8)
        self.assertEqual(summary['sample'], 7)
        self.assertEqual(summary['wins'], 4)
        self.assertEqual(summary['losses'], 2)
        self.assertEqual(summary['flat'], 1)
        self.assertEqual(summary['win_rate'], 57.1)
        self.assertEqual(len(view['groups']), 5)
        entry = next(item for item in view['entries'] if item['code'] == 'sh600001')
        self.assertAlmostEqual(entry['since_add_percent'], (10.5 / 10.2 - 1) * 100, places=2)
        self.assertAlmostEqual(entry['max_gain_percent'], (10.8 / 10.2 - 1) * 100, places=2)
        self.assertAlmostEqual(entry['max_drawdown_percent'], (10.0 / 10.2 - 1) * 100, places=2)
        self.assertEqual(entry['hold_days'], 0)

    def test_filters_by_days_group_and_status(self):
        self.sync()
        self.set_quotes()
        self.app.store.db.execute("UPDATE pool SET added_day='2026-11-01' WHERE code='sh600001'")
        self.app.store.db.commit()
        self.assertEqual(len(self.pool.view(days=2)['entries']), 7)
        self.assertEqual(len(self.pool.view(start='2026-11-02')['entries']), 7)
        self.assertEqual({item['name'] for item in self.pool.view(group='名称辈')['entries']}, {'东方一', '东方新能'})
        self.assertEqual({item['name'] for item in self.pool.view(status='涨停待回踩')['entries']}, {'乙科技', '东方新能'})
        stable = self.pool.view(status='涨停待回踩')
        self.assertEqual(stable['counts']['total'], 8)
        self.assertEqual(stable['counts']['limit_up'], 2)
        self.assertEqual(stable['counts']['ready'], 2)
        self.assertIn('可建仓', {row['entry_tag'] for row in stable['tag_stats']})
        groups = {item['category']: item for item in self.pool.view(days=2)['groups']}
        self.assertEqual(groups['行业']['count'], 1)
        self.assertEqual(groups['概念']['count'], 3)  # 东方新能主分组名称辈，同时保留概念多标签
        self.assertEqual(groups['名称辈']['count'], 2)

    def test_no_market_data_excluded_from_sample(self):
        self.sync()
        self.pool.quotes = {}
        view = self.pool.view()
        self.assertEqual(view['summary']['sample'], 0)
        self.assertIsNone(view['summary']['win_rate'])
        entry = view['entries'][0]
        self.assertEqual(entry['quote']['basis'], 'added')
        self.assertIsNone(entry['since_add_percent'])

    def test_quote_fallback_uses_saved_snapshot(self):
        self.sync()
        self.set_quotes()
        self.pool._write_day('sh600001', '2026-11-09', quote('sh600001', 10.5, 10.2),
                             dict(high=10.9, low=9.9), self.now)
        self.pool.quotes = {}
        entry = next(item for item in self.pool.view()['entries'] if item['code'] == 'sh600001')
        self.assertEqual(entry['quote']['basis'], 'last')
        self.assertEqual(entry['quote']['price'], 10.5)
        self.assertAlmostEqual(entry['since_add_percent'], (10.5 / 10.2 - 1) * 100, places=2)
        self.assertIn('最近一次行情', entry['hint'])

    def test_legacy_rows_backfilled_from_issue_files(self):
        folder = self.app.dir / 'daily-outlook'
        (folder / '2026-11-09_130000_000001.json').write_text(json.dumps(self.issue(), ensure_ascii=False), encoding='utf-8')
        with self.app.store.lock:
            self.app.store.db.execute(
                'INSERT INTO pool(code,name,added_day,added_price,source,sector,role,reason,state,plan,updated_at) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                ('sh600001', '甲股份', '2026-11-09', 10.2, '建仓清单', '元件', '低吸候选', '旧记录', '可建仓', '{}', '2026-11-09T08:00:00+08:00'))
            self.app.store.db.commit()
        with patch.object(self.pool, 'poll'):
            self.pool.bootstrap()
        row = self.app.store.query('SELECT * FROM pool WHERE code=?', ('sh600001',))[0]
        self.assertEqual(row['category'], '行业')
        self.assertEqual(row['entry_tag'], '可建仓')
        self.assertEqual(row['state'], '可建仓')

    def test_marked_state_is_kept_on_sync(self):
        self.sync()
        self.pool.mark('sh600001', '已买入')
        issue = self.issue()
        issue['top_picks'][0]['price'] = 99.0
        issue['top_picks'][0]['percent'] = 10.0
        self.sync(issue)
        row = self.app.store.query('SELECT state,entry_tag FROM pool WHERE code=?', ('sh600001',))[0]
        self.assertEqual(row['state'], '已买入')
        self.assertEqual(row['entry_tag'], '涨停待回踩')

    def test_manual_add_defaults_and_remove(self):
        with patch.object(self.pool, '_batch', return_value={'sh600001': quote('sh600001', 10.2, 10.0)}):
            with patch('core.pool.get', return_value='v_sh600001="1~甲股份~600001~10.20~10.00";'):
                result = self.pool.add_manual('sh600001')
        self.assertTrue(result['ok'])
        row = self.app.store.query('SELECT * FROM pool WHERE code=?', ('sh600001',))[0]
        self.assertEqual((row['source'], row['category'], row['entry_tag']), ('手动', '手动', '观察'))
        self.pool.remove('sh600001')
        self.assertFalse(self.app.store.query('SELECT * FROM pool'))

    def test_names_are_remembered(self):
        self.sync()
        rows = self.app.store.query('SELECT name FROM instruments WHERE code=?', ('sz000003',))
        self.assertEqual(rows[0]['name'], '丙电子')

    def test_force_poll_outside_trading_hours(self):
        self.sync()
        with patch('core.pool.trading', return_value=False), patch.object(
                self.pool, '_batch', return_value={'sh600001': quote('sh600001', 10.5, 10.2)}):
            self.pool.poll(force=True)
        self.assertIn('sh600001', self.pool.quotes)
        self.assertTrue(self.app.store.query('SELECT * FROM pool_day WHERE code=?', ('sh600001',)))


    def test_pagination_rank_and_multi_groups(self):
        self.sync()
        self.set_quotes()
        first = self.pool.view(limit=3, offset=0)
        self.assertEqual(len(first['entries']), 3)
        self.assertEqual(first['filtered_total'], 8)
        self.assertTrue(first['has_more'])
        second = self.pool.view(limit=3, offset=3)
        self.assertFalse({item['code'] for item in first['entries']} & {item['code'] for item in second['entries']})
        entry = next(item for item in self.pool.view(limit=200)['entries'] if item['code'] == 'sh600009')
        self.assertEqual(entry['category'], '名称辈')
        self.assertEqual(set(entry['groups']), {'名称辈', '概念'})
        self.assertGreaterEqual(entry['group_rank'], 1)
        self.assertGreaterEqual(entry['group_size'], 2)
        concept_names = {item['name'] for item in self.pool.view(group='概念', limit=200)['entries']}
        self.assertIn('东方新能', concept_names)
        groups = {row['category']: row for row in self.pool.view(limit=200)['groups']}
        self.assertIn('sample', groups['概念'])
        self.assertGreaterEqual(groups['概念']['count'], groups['概念']['sample'])


    def test_windows_holding_and_benchmark(self):
        self.sync()
        self.set_quotes()
        self.app.store.db.execute("UPDATE pool SET added_day='2026-11-06' WHERE code='sh600001'")
        self.app.store.db.commit()
        self.app.store.cache('sh600001', 'daily', '2026-11-09', dict(date='2026-11-09', close='11.0'))
        self.app.store.cache('sh000001', 'index_daily_v1', '2026-11-09', dict(rows=[
            dict(date='2026-11-06', close=3900.0), dict(date='2026-11-09', close=3939.0)]))
        view = self.pool.view(limit=200)
        entry = next(item for item in view['entries'] if item['code'] == 'sh600001')
        self.assertEqual(entry['holding_days'], 1)
        self.assertEqual(entry['holding_bucket'], '1')
        row = entry['windows']['T+1']
        self.assertAlmostEqual(row['return_percent'], round((11.0 / 10.2 - 1) * 100, 2), places=2)
        self.assertAlmostEqual(row['benchmark_return'], 1.0, places=2)
        self.assertAlmostEqual(row['excess_percent'], round((11.0 / 10.2 - 1) * 100, 2) - 1.0, places=2)
        stats = view['windows']
        self.assertEqual(stats['T+1']['sample'], 1)
        self.assertEqual(stats['T+1']['win_rate'], 100.0)
        self.assertEqual(view['window_stats'][0]['window'], 'T+1')
        holding = {item['bucket']: item for item in view['holding']}
        self.assertEqual(holding['1']['count'], 1)
        self.assertEqual(view['benchmark'], '上证指数')
        # A list filter must not blank the reference window table.
        filtered = self.pool.view(holding='0', limit=200)
        self.assertEqual(filtered['windows']['T+1']['sample'], 1)
        self.assertEqual(next(item for item in filtered['holding'] if item['bucket'] == '1')['count'], 1)

    def test_alerts_transition_deduped(self):
        self.sync()
        entry = self.app.store.query('SELECT plan FROM pool WHERE code=?', ('sh600001',))[0]
        plan = json.loads(entry['plan'])
        self.assertIsNotNone(plan.get('buy_low'))
        self.pool.last_zones = {'sh600001': '高于追高上限'}
        now = datetime(2026, 11, 9, 10, 0, tzinfo=CN)
        quote_row = quote('sh600001', 10.1, 10.0, high=10.2, low=9.9)
        with patch('core.pool.trading', return_value=True):
            self.pool._check_alerts({'sh600001': quote_row}, now)
            self.pool._check_alerts({'sh600001': quote_row}, now)
        rows = self.app.store.query("SELECT key FROM events WHERE key LIKE 'pool|%'")
        self.assertEqual(len(rows), 1)
        alert = self.app.store.query('SELECT * FROM pool_alerts WHERE code=?', ('sh600001',))
        self.assertEqual(len(alert), 1)

    def test_archive_old_entries(self):
        self.sync()
        self.app.store.db.execute("UPDATE pool SET added_day='2020-01-01' WHERE code='sh600001'")
        self.app.store.db.commit()
        self.pool.archive_old()
        view = self.pool.view(limit=200)
        self.assertEqual(view['archived_count'], 1)
        self.assertNotIn('sh600001', {item['code'] for item in view['entries']})
        included = self.pool.view(limit=200, include_archived=True)
        self.assertIn('sh600001', {item['code'] for item in included['entries']})

    def test_export_writes_csv_and_report(self):
        self.sync()
        self.set_quotes()
        result = self.pool.export()
        self.assertTrue(__import__('os').path.exists(result['csv']))
        self.assertTrue(__import__('os').path.exists(result['report']))
        with open(result['csv'], encoding='utf-8-sig') as handle:
            header = handle.readline()
        self.assertIn('入选时间', header)
        self.assertIn('T+1%', header)
        with open(result['report'], encoding='utf-8') as handle:
            report = handle.read()
        self.assertIn('股票池复盘报告', report)
        self.assertIn('按窗口收益', report)

    def test_zone_levels(self):
        plan = dict(buy_low=10.0, buy_high=10.3, chase=10.5, stop=9.6)
        self.assertEqual(self.pool._zone(dict(plan=plan), quote('sh600001', 9.5, 10.0))[0], '已跌破防守位')
        self.assertEqual(self.pool._zone(dict(plan=plan), quote('sh600001', 9.9, 10.0))[0], '低于买区')
        self.assertEqual(self.pool._zone(dict(plan=plan), quote('sh600001', 10.1, 10.0))[0], '已进入买区')
        self.assertEqual(self.pool._zone(dict(plan=plan), quote('sh600001', 10.4, 10.0))[0], '等待回踩')
        self.assertEqual(self.pool._zone(dict(plan=plan), quote('sh600001', 10.8, 10.0))[0], '高于追高上限')


if __name__ == '__main__':
    unittest.main()