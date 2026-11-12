import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.turning_q1 import TIMES, signals as q1_signals
from core.turning_final import (SIGNAL, LABEL, VERSION, STABLE, ZHANGLE, RULE,
                                signals, candidates, liquidity,
                                quality_v2, quality_proximity)
from core.live_trading import LiveTrading, DEFAULT_RULE
from core.provider import now_cn
from core.store import Store

ROOT = Path(__file__).parent
GOLDEN = json.loads((ROOT / 'fixtures/turning-final-golden.json').read_text())
RECON = json.loads((ROOT / 'fixtures/zhangle-reconstruction.json').read_text())
TODAY = json.loads((ROOT / 'ui/fixtures/turning-final-20261112-cases.json').read_text())
SOURCES = {'fixture38': RECON['cases'], 'today21': TODAY}


def case_bars(case):
    """Bars in the production time grid, including the synthetic 09:30 opening quote."""
    return [dict(time='09:30', close=str(case['opening_price']), average=str(case['opening_price']),
                 volume=0, complete=True)] + [
        dict(time=TIMES[i], close=str(p), average=str(a), volume=v, complete=True)
        for i, (p, a, v) in enumerate(zip(case['prices'], case['averages'], case['volumes']))]


class GoldenParityTests(unittest.TestCase):
    def test_metadata_matches_frozen_contract(self):
        self.assertEqual(SIGNAL, 'shape-v2')
        self.assertEqual(LABEL, '观量底／顶信号')
        self.assertEqual(VERSION, 'shape-v2.4')
        self.assertEqual(GOLDEN['meta']['signal'], SIGNAL)
        self.assertEqual(GOLDEN['meta']['version'], VERSION)
        self.assertIs(RULE, ZHANGLE)
        self.assertFalse(ZHANGLE['same_session_only'])
        self.assertEqual(ZHANGLE['daily_cap_per_kind'], 3)
        self.assertEqual(GOLDEN['meta']['mergeRule'], 'causal-chronological')

    def test_python_engine_emits_exactly_the_typescript_events(self):
        # 38 calibration stock-days + 21 full-day 2026-11-12 stock-days, both modes.
        index = {'fixture38': 0, 'today21': 0}
        for case in GOLDEN['cases']:
            source = case['source']
            bars = case_bars(SOURCES[source][index[source]])
            index[source] += 1
            label = f"{source}:{case['code']}:{case['day']}"
            self.assertEqual(signals(bars, ZHANGLE), case['zhangle'], label + ':zhangle')
            self.assertEqual(signals(bars, STABLE), case['stable'], label + ':stable')
        self.assertEqual(len(GOLDEN['cases']), 59)

    def test_three_per_kind_cap_keys_and_versions(self):
        for case in GOLDEN['cases']:
            for mode, expected_version in (('zhangle', 'shape-v2.4'), ('stable', 'shape-v2.0')):
                events = case[mode]
                for kind in ('top', 'bottom'):
                    same = [e for e in events if e['kind'] == kind]
                    self.assertLessEqual(len(same), 3, f"{case['code']}:{mode}:{kind}")
                    self.assertEqual([e['capIndex'] for e in same], list(range(1, len(same) + 1)))
                self.assertEqual(len({e['key'] for e in events}), len(events))
                for event in events:
                    self.assertEqual(event['ruleVersion'], expected_version)
                    self.assertTrue(event['key'].startswith('shape-v2|'))
                    self.assertIn(event['time'], TIMES)
                    self.assertIn(event['candidateTime'], TIMES)
                    self.assertLessEqual(TIMES.index(event['time']), 235)  # 14:56 cutoff

    def test_frozen_signal_totals(self):
        self.assertEqual(sum(len(c['zhangle']) for c in GOLDEN['cases']), 130)
        self.assertEqual(sum(len(c['stable']) for c in GOLDEN['cases']), 68)


class CapTests(unittest.TestCase):
    def test_fourth_same_kind_candidate_is_suppressed_never_replaced(self):
        rows = [dict(time='09:30', close='100', average='100', volume=0, complete=True)] + [
            dict(time=TIMES[i], close=str(price), average='100', volume=10000, complete=True)
            for i, price in enumerate([98, 98.7, 96, 97.5, 94, 96, 90, 92])]
        raw = [e for e in candidates(rows) if e['kind'] == 'bottom']
        self.assertEqual(len(raw), 4)
        emitted = signals(rows, dict(ZHANGLE, quality_tau_emit=-float('inf')))
        bottoms = [e for e in emitted if e['kind'] == 'bottom']
        self.assertEqual(len(bottoms), 3)
        self.assertEqual([e['capIndex'] for e in bottoms], [1, 2, 3])
        self.assertEqual([e['candidateTime'] for e in bottoms], [e['candidateTime'] for e in raw[:3]])
        self.assertNotIn(raw[3]['candidateTime'], [e['candidateTime'] for e in bottoms])
        self.assertNotIn(raw[3]['key'], [e['key'] for e in bottoms])

    def test_cap_counts_only_emitted_signals_after_quality(self):
        # Quality-rejected candidates never consume a cap slot: the frozen 130 vs 118
        # raw candidate stream on 2026-11-12 confirms the gate applies before the cap.
        for case in GOLDEN['cases']:
            if case['source'] != 'today21':
                continue
            today_index = next(i for i, base in enumerate(TODAY) if base['code'] == case['code'])
            bars = case_bars(TODAY[today_index])
            emitted = signals(bars)
            self.assertEqual(sum(1 for e in emitted if e['kind'] == 'top'), len([e for e in emitted if e['kind'] == 'top']))
            self.assertLessEqual(len([e for e in emitted if e['kind'] == 'bottom']), 3)


class BoundaryTests(unittest.TestCase):
    def test_1456_emission_cutoff(self):
        def synthetic(prices, start=0):
            return [dict(time='09:30', close='100', average='100', volume=0, complete=True)] + [
                dict(time=TIMES[i], close=str(price), average='100', volume=10000, complete=True)
                for i, price in enumerate([100] * start + list(prices))]
        for start in (0, 234):
            got = signals(synthetic([96, 97.5], start))
            self.assertEqual(len(got), 1)
            self.assertEqual((got[0]['candidateTime'], got[0]['time']), (TIMES[start], TIMES[start + 1]))
        self.assertEqual(TIMES[235], '14:56')
        self.assertEqual(signals(synthetic([96, 97.5], 235)), [])

    def test_0930_opening_contract(self):
        case = RECON['cases'][0]
        rows = case_bars(case)
        self.assertTrue(signals(rows))
        self.assertEqual(signals(rows[1:]), [])
        self.assertEqual(signals(rows + [rows[0]]), [])
        for flag in (False, 1, 'true'):
            self.assertEqual(signals([dict(rows[0], complete=flag), *rows[1:]]), [])
        for price in ('0', '-1', 'NaN'):
            self.assertEqual(signals([dict(rows[0], close=price, average=price), *rows[1:]]), [])

    def test_missing_duplicate_unfinished_minutes_truncate_the_prefix(self):
        for case in RECON['cases']:
            rows = case_bars(case)
            full = signals(rows)
            if not full:
                continue
            mark = full[0]
            at = next(i for i, b in enumerate(rows) if b['time'] == mark['time'])
            self.assertEqual(signals(rows[:at]), [e for e in full if e['time'] < mark['time']])
            broken = [dict(b, complete=False) if b['time'] == mark['time'] else b for b in rows]
            self.assertEqual(signals(broken), [e for e in full if e['time'] < mark['time']])
            duplicate = rows[:at] + [rows[at], rows[at]] + rows[at + 1:]
            self.assertFalse(any(e['key'] == mark['key'] for e in signals(duplicate)))
            return

    def _assert_strict_prefix_invariance(self, rule):
        for case in GOLDEN['cases']:
            source_cases = SOURCES[case['source']]
            case_index = next(i for i, base in enumerate(source_cases)
                              if base['code'] == case['code'] and base['day'] == case['day'])
            bars = case_bars(SOURCES[case['source']][case_index])
            full = signals(bars, rule)
            for cut in range(1, len(bars), 17):
                expected = [e for e in full if e['time'] <= bars[cut - 1]['time']]
                self.assertEqual(signals(bars[:cut], rule), expected)
                tampered = [b if i < cut else dict(b, close='9999', average='1', volume=1)
                            for i, b in enumerate(bars)]
                self.assertEqual([e for e in signals(tampered, rule) if e['time'] <= bars[cut - 1]['time']], expected)

    def test_stable_mode_is_strictly_prefix_invariant(self):
        # The stable main branch is causal: appending future minutes never changes it.
        self._assert_strict_prefix_invariance(STABLE)

    def test_both_modes_are_strictly_prefix_invariant(self):
        # C1 causal merge: every prefix output is exactly the final output truncated at
        # that prefix, so a displayed/emitted signal can never disappear later.
        self._assert_strict_prefix_invariance(STABLE)
        self._assert_strict_prefix_invariance(ZHANGLE)

    def test_live_prefix_union_equals_final_set(self):
        for case in GOLDEN['cases']:
            source_cases = SOURCES[case['source']]
            case_index = next(i for i, base in enumerate(source_cases)
                              if base['code'] == case['code'] and base['day'] == case['day'])
            bars = case_bars(SOURCES[case['source']][case_index])
            final = signals(bars)
            live = {}
            for cut in range(1, len(bars) + 1):
                for event in signals(bars[:cut]):
                    live.setdefault(event['key'], event)
            self.assertEqual(sorted(live), sorted(e['key'] for e in final))
            for kind in ('top', 'bottom'):
                self.assertLessEqual(len([e for e in final if e['kind'] == kind]), 3)

    def test_synthetic_five_candidate_day_stays_capped_and_monotonic(self):
        # Five meaningful bottom waves exist; the causal cap/merge emits 3 and every
        # prefix is a truncation of the final set (no later disappearance).
        prices = [98, 98.7, 96, 97.5, 94, 96, 90, 92, 88, 90]
        rows = [dict(time='09:30', close='100', average='100', volume=0, complete=True)] + [
            dict(time=TIMES[i], close=str(price), average='100', volume=10000, complete=True)
            for i, price in enumerate(prices)]
        raw = [e for e in candidates(rows) if e['kind'] == 'bottom']
        self.assertEqual(len(raw), 4)
        full = signals(rows)
        self.assertEqual([e['kind'] for e in full], ['bottom'] * 3)
        for cut in range(1, len(rows) + 1):
            self.assertEqual(signals(rows[:cut]),
                             [e for e in full if e['time'] <= rows[cut - 1]['time']])

    def test_engine_does_not_mutate_input(self):
        bars = case_bars(RECON['cases'][0])
        before = copy.deepcopy(bars)
        self.assertEqual(signals(bars), signals(bars))
        self.assertEqual(bars, before)


class QualityTests(unittest.TestCase):
    def test_quality_v2_formula(self):
        candidate = dict(index=0, time='09:31', price=102, vwap=100, rsi=80, deviationPct=2)
        value = quality_v2(sign=1, candidate=candidate, high=102, low=99, movePct=.45, deviationPct=1)
        self.assertAlmostEqual(value, 1.2 + 1 + 2 / 1.5 + 4, places=12)
        zero = quality_v2(sign=1, candidate=dict(candidate, rsi=0), high=102, low=99, movePct=.45)
        neutral = quality_v2(sign=1, candidate=dict(candidate, rsi=50), high=102, low=99, movePct=.45)
        self.assertAlmostEqual(zero, neutral, places=12)

    def test_quality_proximity_formula(self):
        candidate = dict(index=0, time='09:31', price=102, vwap=100, rsi=80, deviationPct=2)
        self.assertAlmostEqual(quality_proximity(sign=1, candidate=candidate, high=102, low=99, movePct=.45),
                               2 + 1 + 2 / 1.5 + 4, places=12)
        self.assertAlmostEqual(quality_proximity(sign=-1, candidate=dict(candidate, price=99), high=102, low=99, movePct=.45),
                               2 + 1 + 2 / 1.5 + 4, places=12)


class SameSessionTests(unittest.TestCase):
    def test_lunch_crossing_marks_are_emitted_by_default(self):
        # sh600714 top 13:01 confirms an 11:30 candidate across the lunch break (a
        # verified 2026-11-12 Zhangle mark). sz300094 has the same cross-lunch candidate
        # but C1's causal cap fills its three top slots earlier, so 13:01 is correctly
        # dropped there; the legacy same-session switch is still covered below.
        by_code = {c['code']: c for c in TODAY}
        events = signals(case_bars(by_code['sh600714']))
        top = [e for e in events if e['kind'] == 'top' and e['time'] == '13:01'
               and e['candidateTime'] == '11:30']
        self.assertEqual(len(top), 1)
        self.assertAlmostEqual(top[0]['price'], 14.64, places=2)
        events = signals(case_bars(by_code['sz300094']))
        self.assertEqual(len([e for e in events if e['kind'] == 'top']), 3)

    def test_legacy_same_session_branch_is_configurable(self):
        strict = dict(ZHANGLE, same_session_only=True)
        by_code = {c['code']: c for c in TODAY}
        events = signals(case_bars(by_code['sh600714']), strict)
        self.assertFalse(any(e['time'] > '11:30' and e['candidateTime'] == '11:30' for e in events))


class LiquidityTests(unittest.TestCase):
    def test_liquidity_matches_legacy_shape_contract(self):
        bars = [dict(time=TIMES[i], close='10', average='10', volume=1000 + i, complete=True)
                for i in range(5)]
        result = liquidity(bars, TIMES[4])
        self.assertEqual(result['meanShares'], (1000 + 1001 + 1002 + 1003 + 1004) / 5)
        self.assertEqual(result['currentShares'], 1004)
        self.assertEqual(liquidity(bars[:2], TIMES[4]), {})
        self.assertEqual(liquidity([dict(b, complete=False) for b in bars], TIMES[4]), {})


class LiveTradingMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'test.sqlite3')
        self.addCleanup(self.store.db.close)
        self.app = SimpleNamespace(store=self.store)
        LiveTrading(self.app)  # create the trading schema before inserting legacy rules

    def insert_rule(self, payload, revision=7, armed_at='2026-11-02T09:30:00+08:00'):
        self.store.execute('INSERT INTO trading_rules VALUES(?,?,?,?,?)',
                           ('a', 'sz000981', json.dumps(payload), revision, armed_at))

    def test_shape_v1_rule_migrates_to_shape_v2_pauses_and_preserves_switches(self):
        self.insert_rule(dict(buy_enabled=True, sell_enabled=True, buy_lots=2, sell_lots=1,
                              buy_mode='lots', sell_mode='lots', buy_percent=50, sell_percent=50,
                              signal='shape-v1', strategy_mode='independent', paired_enabled=False,
                              t_lots=1, minimum_net_profit=10, commission_wan=2, minimum_commission=5,
                              stamp_per_mille=.5, transfer_per_mille=.01, slippage_per_mille=0))
        self.store.setconfig('trading_mode', 'live')
        self.store.setconfig('trading_paused', False)
        upgraded = LiveTrading(self.app)
        rule = upgraded.rule('a', 'sz000981')
        self.assertEqual(rule['signal'], SIGNAL)
        self.assertTrue(rule['buy_enabled'])
        self.assertTrue(rule['sell_enabled'])
        self.assertEqual((rule['buy_lots'], rule['sell_lots']), (2, 1))
        self.assertEqual(rule['revision'], 8)
        self.assertEqual(rule['armed_at'], upgraded.started_at)
        settings = upgraded.settings()
        self.assertTrue(settings['paused'])
        self.assertEqual(settings['mode'], 'live')
        self.assertEqual(settings['signal'], SIGNAL)
        self.assertEqual(settings['signal_label'], LABEL)
        self.assertIn('底/顶信号已升级为观量 v2', settings['signal_notice'])
        self.assertIn('自动执行已暂停', settings['signal_notice'])
        # A second restart must not migrate (or pause) again.
        self.store.setconfig('trading_paused', False)
        again = LiveTrading(self.app)
        self.assertEqual(again.rule('a', 'sz000981'), rule)
        self.assertFalse(again.settings()['paused'])

    def test_legacy_quantity_rule_migrates_to_shape_v2(self):
        old = dict(signal='Q1', buy_enabled=True, sell_enabled=True, buy_ratio='1/3', sell_ratio='1/4',
                   max_order_value=9876, daily_buy_value=3000, base_shares=1200,
                   daily_orders=2, max_deviation_pct=.5)
        self.insert_rule(old)
        self.store.setconfig('trading_mode', 'live')
        self.store.setconfig('trading_paused', False)
        upgraded = LiveTrading(self.app)
        rule = upgraded.rule('a', 'sz000981')
        self.assertEqual(rule['signal'], SIGNAL)
        self.assertEqual(rule['buy_mode'], 'lots')
        self.assertEqual(rule['buy_lots'], 4)
        self.assertNotIn('max_order_value', rule)
        self.assertTrue(upgraded.settings()['paused'])


def dispatch_bars(case):
    return case_bars(case)


class LiveDispatchTests(unittest.TestCase):
    def run_dispatch(self, case, kind, side):
        marks = [e for e in signals(dispatch_bars(case)) if e['kind'] == kind]
        self.assertTrue(marks, f'no {kind} signal in fixture')
        mark = marks[0]
        now = datetime.fromisoformat(case['day'] + 'T' + mark['time'] + ':05+08:00')
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
                                                     sellable=1000, price=mark['price'])])
                    service.apply_snapshot('a', snapshot)
                    rule = service.rule('a', case['code'])
                    service.save_rule('a', case['code'], {side + '_enabled': True, side + '_lots': 2},
                                      rule['revision'])
                    store.setconfig('trading_mode', 'live')
                    store.setconfig('trading_paused', False)
                    store.setconfig('monitor', True)
                    earlier = (now - timedelta(minutes=5)).isoformat()
                    service.started_at = earlier
                    store.execute('UPDATE trading_rules SET armed_at=?', (earlier,))
                    quote = dict(code=case['code'], price=mark['price'], timestamp=now.isoformat())
                    app.quotes[case['code']] = quote
                    bars = dispatch_bars(case)
                    index = next(i for i, b in enumerate(bars) if b['time'] == mark['time'])
                    service.ingest(case['code'], bars[:index], quote, now - timedelta(minutes=1), False)
                    service.ingest(case['code'], bars[:index + 1], quote, now, True)
                    service.ingest(case['code'], bars[:index + 1], quote, now, True)

                    def submit(*args, **kwargs):
                        kwargs['authorize']()
                        return dict(status='accepted', submitted=True, order_id='test-' + side)

                    with patch('core.live_trading.brokers.holdings', return_value=snapshot),                             patch('core.live_trading.brokers.submit_order', side_effect=submit) as gateway:
                        service.drain(reports=False)
                        gateway.assert_called_once()
                        self.assertEqual(gateway.call_args.args[1:4], ('a', side, case['code'][2:]))
                        runs = store.query('SELECT * FROM trading_runs')
                        self.assertEqual(len(runs), 1)
                        payload = json.loads(runs[0]['payload'])
                        self.assertEqual(payload['signal_source'], SIGNAL)
                        self.assertEqual(payload['signal']['key'], mark['key'])
                        self.assertEqual(payload['signal']['time'], mark['time'])
                        self.assertEqual(payload['signal']['candidateTime'], mark['candidateTime'])
                        # Repeated ingestion of the same confirmed minute never adds a run.
                        later = now + timedelta(minutes=2)
                        quote.update(timestamp=later.isoformat())
                        service.ingest(case['code'], bars[:index + 3], quote, later, True)
                        service.drain(reports=False)
                        gateway.assert_called_once()
                        self.assertEqual(len(store.query('SELECT * FROM trading_runs')), 1)
                        restarted = LiveTrading(app)
                        restarted.ingest(case['code'], bars[:index + 3], quote, later, True)
                        restarted.drain(reports=False)
                        gateway.assert_called_once()
                        self.assertEqual(len(store.query('SELECT * FROM trading_runs')), 1)
            finally:
                store.db.close()

    def test_bottom_signal_creates_one_buy_plan_at_emission_minute(self):
        case = next(c for c in RECON['cases'] if c['code'] == 'sh603938' and c['day'] == '2026-11-09')
        self.run_dispatch(case, 'bottom', 'buy')

    def test_top_signal_creates_one_sell_plan_at_emission_minute(self):
        case = next(c for c in RECON['cases'] if c['code'] == 'sh603938' and c['day'] == '2026-11-09')
        self.run_dispatch(case, 'top', 'sell')


class CapDispatchIntegrationTests(unittest.TestCase):
    def test_fourth_same_kind_signal_creates_no_fourth_order(self):
        # Four causal bottom waves exist, but the engine emits only three; streaming the
        # same minutes through the real trading service must therefore create 3 orders.
        prices = [98, 98.7, 96, 97.5, 94, 96, 90, 92]
        start = now_cn()
        day = start.date().isoformat()
        rows = [dict(time='09:30', close='100', average='100', volume=0, complete=True)] + [
            dict(time=TIMES[i], close=str(price), average='100', volume=10000, complete=True)
            for i, price in enumerate(prices)]
        self.assertEqual(len(signals(rows)), 3)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.sqlite3')
            try:
                app = SimpleNamespace(store=store, quotes={})
                service = LiveTrading(app)
                store.execute("INSERT INTO broker_accounts(id,broker,account) VALUES('a','zhangle','123456789')")
                now = start
                snapshot = dict(account_id='a', account_verified=True, observed_at=now.isoformat(),
                                complete=True, funds=dict(available='100000'),
                                positions=[dict(code='sz000981', name='测试股', quantity=1000,
                                                 sellable=1000, price='98')],
                                quote=dict(price='98'))
                service.apply_snapshot('a', snapshot)
                rule = service.rule('a', 'sz000981')
                service.save_rule('a', 'sz000981', dict(buy_enabled=True, buy_lots=1), rule['revision'])
                store.setconfig('trading_mode', 'trial')
                store.setconfig('trading_paused', False)
                store.setconfig('monitor', True)
                earlier = (start - timedelta(hours=20)).isoformat()
                service.started_at = earlier
                store.execute('UPDATE trading_rules SET armed_at=?', (earlier,))
                for i in range(1, len(rows)):
                    stamp = rows[i]['time']
                    now = datetime.fromisoformat(day + 'T' + stamp + ':05+08:00')
                    quote = dict(code='sz000981', price=rows[i]['close'], timestamp=now.isoformat())
                    app.quotes['sz000981'] = quote
                    prefix = signals(rows[:i + 1])
                    for kind in ('top', 'bottom'):
                        self.assertLessEqual(len([e for e in prefix if e['kind'] == kind]), 3)
                    service.ingest('sz000981', rows[:i + 1], quote, now, True)
                    service.drain(reports=False)
                runs = store.query("SELECT * FROM trading_runs WHERE side='buy'")
                # C1 causal merge makes the streaming union equal the full-day set, so the
                # cumulative order count is naturally capped at 3 without a trading cap.
                self.assertEqual(len(runs), 3)
                self.assertEqual(len({json.loads(r['payload'])['signal']['key'] for r in runs}), 3)
                keys = json.loads(runs[0]['payload'])['signal']['key']
                self.assertTrue(keys.startswith('shape-v2|bottom|'))
            finally:
                store.db.close()


class QualityIndependenceTests(unittest.TestCase):
    def test_shape_engine_does_not_inherit_q1_gates(self):
        case = RECON['cases'][0]
        bars = case_bars(case)
        stripped = [dict(b, volume=1) for b in bars]
        self.assertEqual([(e['key'], e['time'], e['price']) for e in signals(bars)],
                         [(e['key'], e['time'], e['price']) for e in signals(stripped)])
        self.assertEqual([m['key'] for m in q1_signals(stripped)], [])


if __name__ == '__main__':
    unittest.main()