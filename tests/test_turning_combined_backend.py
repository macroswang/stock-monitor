import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.turning_combined import (SIGNAL, LABEL, VERSION, DAILY_CAP_PER_KIND,
                                   merge_signals, signals)
from core.turning_final import ZHANGLE, signals as v2_signals
from core.turning_q1 import signals as q1_signals, TIMES
from core.live_trading import LiveTrading
from core.store import Store

ROOT = Path(__file__).parent
GOLDEN = json.loads((ROOT / 'fixtures/turning-combined-golden.json').read_text())
RECON = json.loads((ROOT / 'fixtures/zhangle-reconstruction.json').read_text())
TODAY = json.loads((ROOT / 'ui/fixtures/turning-final-20261112-cases.json').read_text())
SOURCES = {'fixture38': RECON['cases'], 'today21': TODAY}


def case_bars(case):
    return [dict(time='09:30', close=str(case['opening_price']), average=str(case['opening_price']),
                 volume=0, complete=True)] + [
        dict(time=TIMES[i], close=str(p), average=str(a), volume=v, complete=True)
        for i, (p, a, v) in enumerate(zip(case['prices'], case['averages'], case['volumes']))]


def rank(events):
    return [(e['kind'], e['time'], e['key']) for e in events]


class GoldenParityTests(unittest.TestCase):
    def test_metadata_and_contract(self):
        self.assertEqual(SIGNAL, 'shape-v2-q1')
        self.assertEqual(LABEL, '观量底／顶信号')
        self.assertEqual(VERSION, 'shape-v2-q1.0')
        self.assertEqual(DAILY_CAP_PER_KIND, 3)
        self.assertEqual(GOLDEN['meta']['signal'], SIGNAL)
        self.assertEqual(GOLDEN['meta']['version'], VERSION)
        self.assertEqual(GOLDEN['meta']['capPerKind'], 3)
        self.assertEqual(len(GOLDEN['cases']), 59)

    def test_python_combined_events_match_the_typescript_golden(self):
        index = {'fixture38': 0, 'today21': 0}
        for case in GOLDEN['cases']:
            bars = case_bars(SOURCES[case['source']][index[case['source']]])
            index[case['source']] += 1
            self.assertEqual(signals(bars), case['events'], f"{case['source']}:{case['code']}:{case['day']}")

    def test_python_merge_rules_match_the_typescript_merge_cases(self):
        for case in GOLDEN['mergeCases']:
            self.assertEqual(merge_signals(case['final'], case['q1']), case['expected'], case['name'])
        names = [c['name'] for c in GOLDEN['mergeCases']]
        self.assertIn('same-minute-v2-wins', names)
        self.assertIn('q1-fills-remaining-slots-in-time-order', names)
        self.assertIn('same-display-price-deduped', names)

    def test_filtered_events_keep_original_fields_and_cap_holds(self):
        for case in GOLDEN['cases']:
            bars = case_bars(SOURCES[case['source']][[c['code'] + c['day'] for c in SOURCES[case['source']]].index(case['code'] + case['day'])])
            v2 = v2_signals(bars, ZHANGLE)
            combined = signals(bars)
            v2_keys = {e['key'] for e in v2}
            combined_keys = {e['key'] for e in combined}
            self.assertTrue(combined_keys.issubset(v2_keys | {e['key'] for e in q1_signals(bars)}))
            for kind in ('top', 'bottom'):
                self.assertLessEqual(len([e for e in combined if e['kind'] == kind]), 3)
            self.assertEqual([e['time'] for e in combined], sorted(e['time'] for e in combined))
            self.assertEqual(len(combined_keys), len(combined))
            for event in combined:
                if event['key'] in v2_keys:
                    self.assertIn(event['key'], {e['key'] for e in v2})
                else:
                    self.assertTrue(event['key'].startswith('quality-first-Q|'))


class MergeRuleTests(unittest.TestCase):
    def test_same_kind_and_minute_keeps_v2_and_drops_q1(self):
        v2 = [dict(key='v2|top|09:40', kind='top', time='09:41', price=10.0)]
        q1 = [dict(key='q1|top|09:40|09:41', kind='top', time='09:41', price=10.2)]
        self.assertEqual(rank(merge_signals(v2, q1)), [('top', '09:41', 'v2|top|09:40')])

    def test_q1_fills_remaining_slots_in_time_order(self):
        v2 = [dict(key='v2|top|09:40', kind='top', time='09:41', price=10.0)]
        q1 = [dict(key='q1-a', kind='top', time='09:50', price=10.5),
              dict(key='q1-b', kind='top', time='09:45', price=10.3),
              dict(key='q1-c', kind='top', time='09:55', price=10.7),
              dict(key='q1-d', kind='top', time='10:00', price=10.9)]
        merged = merge_signals(v2, q1)
        self.assertEqual([e['key'] for e in merged], ['v2|top|09:40'])

    def test_same_display_price_is_deduped(self):
        v2 = [dict(key='v2|top|09:40', kind='top', time='09:41', price=10.43)]
        q1 = [dict(key='q1-dup', kind='top', time='09:50', price=10.434),
              dict(key='q1-other', kind='bottom', time='09:51', price=10.44)]
        merged = merge_signals(v2, q1)
        self.assertEqual([e['key'] for e in merged], ['v2|top|09:40', 'q1-other'])

    def test_cap_counts_v2_plus_q1_together(self):
        v2 = [dict(key='v2-1', kind='bottom', time='09:40', price=9.9),
              dict(key='v2-2', kind='bottom', time='09:45', price=9.8)]
        q1 = [dict(key='q1-1', kind='bottom', time='09:50', price=9.7),
              dict(key='q1-2', kind='bottom', time='09:55', price=9.6)]
        merged = merge_signals(v2, q1)
        self.assertEqual([e['key'] for e in merged], ['v2-1', 'q1-1'])

    def test_zhongwen_spacing_preserves_first_signal_and_pool_summary(self):
        from core.pool_signals import bottom_point
        data = json.loads((ROOT / 'ui/fixtures/turning-spacing-20261113.json').read_text())
        bars = data['bars']
        self.assertEqual([e['time'] for e in v2_signals(bars, ZHANGLE) if e['kind'] == 'top'],
                         ['09:34', '09:41', '10:34'])
        combined = signals(bars)
        self.assertEqual([e['time'] for e in combined if e['kind'] == 'top'], ['09:34', '10:34'])
        self.assertEqual(bottom_point(data, 'zhangle')['time'],
                         [e['time'] for e in combined if e['kind'] == 'bottom'][-1])


def _dispatch(case, target_key, side):
    check = unittest.TestCase()
    bars = case_bars(case)
    target = next(e for e in signals(bars) if e['key'] == target_key)
    now = datetime.fromisoformat(case['day'] + 'T' + target['time'] + ':05+08:00')
    index = next(i for i, b in enumerate(bars) if b['time'] == target['time'])
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / 'test.sqlite3')
        try:
            with patch('core.live_trading.now_cn', return_value=now):
                app = SimpleNamespace(store=store, quotes={})
                service = LiveTrading(app)
                store.execute("INSERT INTO broker_accounts(id,broker,account) VALUES('a','zhangle','123456789')")
                snapshot = dict(account_id='a', account_verified=True, observed_at=now.isoformat(),
                                complete=True, funds=dict(available='100000'),
                                positions=[dict(code=case['code'], name='测试股', quantity=1000,
                                                 sellable=1000, price=target['price'])])
                service.apply_snapshot('a', snapshot)
                rule = service.rule('a', case['code'])
                service.save_rule('a', case['code'], {side + '_enabled': True, side + '_lots': 2}, rule['revision'])
                store.setconfig('trading_mode', 'live')
                store.setconfig('trading_paused', False)
                store.setconfig('monitor', True)
                earlier = (now - timedelta(minutes=5)).isoformat()
                service.started_at = earlier
                store.execute('UPDATE trading_rules SET armed_at=?', (earlier,))
                quote = dict(code=case['code'], price=target['price'], timestamp=now.isoformat())
                app.quotes[case['code']] = quote
                service.ingest(case['code'], bars[:index], quote, now - timedelta(minutes=1), False)
                service.ingest(case['code'], bars[:index + 1], quote, now, True)
                service.ingest(case['code'], bars[:index + 1], quote, now, True)

                def submit(*args, **kwargs):
                    kwargs['authorize']()
                    return dict(status='accepted', submitted=True, order_id='test-' + side)

                with patch('core.live_trading.brokers.holdings', return_value=snapshot), \
                        patch('core.live_trading.brokers.submit_order', side_effect=submit) as gateway:
                    service.drain(reports=False)
                    gateway.assert_called_once()
                    runs = store.query('SELECT * FROM trading_runs')
                    check.assertEqual(len(runs), 1)
                    payload = json.loads(runs[0]['payload'])
                    check.assertEqual(payload['signal_source'], SIGNAL)
                    check.assertEqual(payload['signal']['key'], target_key)
                    check.assertEqual(payload['signal']['time'], target['time'])
                    check.assertEqual(payload['signal']['kind'], 'bottom' if side == 'buy' else 'top')
        finally:
            store.db.close()


class CombinedTradingTests(unittest.TestCase):
    def test_q1_only_bottom_triggers_a_buy_plan(self):
        case = next(c for c in RECON['cases'] if c['code'] == 'sz300502' and c['day'] == '2026-11-10')
        q1_only = next(e for e in signals(case_bars(case))
                       if e['kind'] == 'bottom' and e['key'].startswith('quality-first-Q'))
        _dispatch(case, q1_only['key'], 'buy')

    def test_q1_only_top_triggers_a_sell_plan(self):
        case = next(c for c in TODAY if c['code'] == 'sz300058')
        q1_only = next(e for e in signals(case_bars(case))
                       if e['kind'] == 'top' and e['key'].startswith('quality-first-Q'))
        _dispatch(case, q1_only['key'], 'sell')

    def test_same_minute_v2_and_q1_produce_one_signal(self):
        v2 = [dict(key='v2|top|09:40', kind='top', time='09:41', price=10.0)]
        q1 = [dict(key='quality-first-Q|top|09:40|09:41', kind='top', time='09:41', price=10.0)]
        self.assertEqual(len(merge_signals(v2, q1)), 1)

    def test_order_level_daily_cap_skips_the_fourth_same_direction_signal(self):
        from tests import test_trading_quantity_modes as fixtures
        test = fixtures.QuantityServiceTests('test_one_hand_order_above_old_single_and_daily_caps_is_allowed')
        test.setUp()
        try:
            test.service.configure(dict(mode='live', confirm_live=True)); test.arm()
            snapshot = {**test.snapshot, 'observed_at': test.now.isoformat()}
            with patch('core.live_trading.brokers.holdings', return_value=snapshot), \
                    patch('core.live_trading.brokers.submit_order', return_value=dict(status='accepted')) as submit:
                for n in range(4):
                    key = f'sig-{n}'
                    test.service.observe('sh603938', [dict(kind='bottom', key=key, time='10:01', price=30,
                                                           liquidity=dict(meanShares=100000, currentShares=100000))],
                                         test.app.quotes['sh603938'], test.now, True)
                    test.service.drain(reports=False)
                    test.now += timedelta(seconds=1)
            self.assertEqual(submit.call_count, 3)
            runs = test.store.query('SELECT * FROM trading_runs ORDER BY rowid')
            statuses = [r['status'] for r in runs]
            self.assertEqual(statuses.count('skipped'), 1)
            skipped = next(r for r in runs if r['status'] == 'skipped')
            payload = json.loads(skipped['payload'])
            self.assertIn('当日该方向已达3个信号上限（含Q1补位）', payload['message'])
            self.assertEqual(payload['signal_source'], SIGNAL)
            self.assertEqual(statuses.count('accepted'), 3)
        finally:
            test.doCleanups()


class MigrationTests(unittest.TestCase):
    def test_shape_v2_rule_migrates_to_combined_with_pause_and_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.sqlite3')
            try:
                app = SimpleNamespace(store=store)
                LiveTrading(app)  # schema
                old = dict(signal='shape-v2', buy_enabled=True, sell_enabled=True, buy_mode='lots', sell_mode='lots',
                           buy_lots=2, sell_lots=1, buy_percent=50, sell_percent=50, strategy_mode='independent',
                           paired_enabled=False, t_lots=1, minimum_net_profit=10, commission_wan=2,
                           minimum_commission=5, stamp_per_mille=.5, transfer_per_mille=.01, slippage_per_mille=0)
                store.execute('INSERT INTO trading_rules VALUES(?,?,?,?,?)',
                              ('a', 'sz000981', json.dumps(old), 7, '2026-11-02T09:30:00+08:00'))
                store.setconfig('trading_mode', 'live')
                store.setconfig('trading_paused', False)
                upgraded = LiveTrading(app)
                rule = upgraded.rule('a', 'sz000981')
                self.assertEqual(rule['signal'], SIGNAL)
                self.assertTrue(rule['buy_enabled'])
                self.assertTrue(rule['sell_enabled'])
                self.assertEqual((rule['buy_lots'], rule['sell_lots']), (2, 1))
                self.assertEqual(rule['revision'], 8)
                self.assertEqual(rule['armed_at'], upgraded.started_at)
                settings = upgraded.settings()
                self.assertTrue(settings['paused'])
                self.assertEqual(settings['signal'], SIGNAL)
                self.assertEqual(settings['signal_label'], LABEL)
                self.assertIn('观量 v2+Q1', settings['signal_notice'])
                self.assertIn('自动执行已暂停', settings['signal_notice'])
                # Restart does not migrate or pause again.
                store.setconfig('trading_paused', False)
                again = LiveTrading(app)
                self.assertEqual(again.rule('a', 'sz000981'), rule)
                self.assertFalse(again.settings()['paused'])
            finally:
                store.db.close()

    def test_paired_t_rules_are_not_affected_by_the_order_cap(self):
        from tests import test_trading_quantity_modes as fixtures
        test = fixtures.QuantityServiceTests('test_one_hand_order_above_old_single_and_daily_caps_is_allowed')
        test.setUp()
        try:
            rule = test.service.rule('a', 'sh603938')
            test.service.save_rule('a', 'sh603938', dict(buy_enabled=True, sell_enabled=True,
                                                         strategy_mode='paired_t', paired_enabled=True),
                                   rule['revision'])
            test.service.configure(dict(paused=False))
            test.service.started_at = (test.now - timedelta(minutes=3)).isoformat()
            test.store.execute('UPDATE trading_rules SET armed_at=?', ((test.now - timedelta(minutes=3)).isoformat(),))
            for n in range(4):
                test.service.observe('sh603938', [dict(kind='top', key=f'paired-{n}', time='10:01', price=30,
                                                       liquidity=dict(meanShares=100000, currentShares=100000))],
                                     test.app.quotes['sh603938'], test.now, True)
                test.now += timedelta(seconds=1)
            runs = test.store.query('SELECT * FROM trading_runs')
            for run in runs:
                self.assertNotIn('当日该方向已达3个信号上限', run['payload'])
        finally:
            test.doCleanups()


if __name__ == '__main__':
    unittest.main()
