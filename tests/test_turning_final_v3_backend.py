import json
import math
import unittest
from pathlib import Path

from core.turning_q1 import TIMES
from core.turning_final import STABLE, ZHANGLE, signals as v2_signals, turning_final_streams
from core.turning_final_v3 import (SIGNAL, LABEL, VERSION, KEY_PREFIX, RULE,
                                   signals, candidates)

ROOT = Path(__file__).parent
GOLDEN_V3 = json.loads((ROOT / 'fixtures/turning-final-golden-v3.json').read_text())
GOLDEN_V2 = json.loads((ROOT / 'fixtures/turning-final-golden.json').read_text())
EVAL = json.loads((ROOT / 'fixtures/turning-v3-eval.json').read_text())
RECON = json.loads((ROOT / 'fixtures/zhangle-reconstruction.json').read_text())
TODAY = json.loads((ROOT / 'ui/fixtures/turning-final-20261112-cases.json').read_text())
SOURCES = {'fixture38': RECON['cases'], 'today21': TODAY}


def case_bars(case):
    return [dict(time='09:30', close=str(case['opening_price']), average=str(case['opening_price']),
                 volume=0, complete=True)] + [
        dict(time=TIMES[i], close=str(p), average=str(a), volume=v, complete=True)
        for i, (p, a, v) in enumerate(zip(case['prices'], case['averages'], case['volumes']))]


def eval_bars(case):
    return [dict(time='09:30', close=str(case['opening_price']), average=str(case['opening_price']),
                 volume=0, complete=True)] + [
        dict(time=b['time'], close=str(b['close']), average=str(b['average']),
             volume=b['volume'], complete=b['complete']) for b in case['bars']]


def rank(events):
    return [(e['kind'], e['time'], e['candidateTime']) for e in events]


def match_events(events, marks, tol=1):
    ev = [(TIMES.index(e['time']), e['kind']) for e in events]
    mk = [(TIMES.index(m['time']), m['kind']) for m in marks]
    adjacency = [[] for _ in ev]
    for a, (ia, ka) in enumerate(ev):
        for b, (ib, kb) in enumerate(mk):
            if ka == kb and abs(ia - ib) <= tol:
                adjacency[a].append(b)
    for a in range(len(ev)):
        adjacency[a].sort(key=lambda b: abs(ev[a][0] - mk[b][0]))
    match = [-1] * len(mk)

    def augment(a, seen):
        for b in adjacency[a]:
            if b in seen:
                continue
            seen.add(b)
            if match[b] == -1 or augment(match[b], seen):
                match[b] = a
                return True
        return False

    matched = 0
    for a in range(len(ev)):
        if augment(a, set()):
            matched += 1
    return matched


class GoldenParityTests(unittest.TestCase):
    def test_metadata_and_product_binding(self):
        self.assertEqual(VERSION, 'shape-v3.0')
        self.assertEqual(KEY_PREFIX, 'shape-v3')
        self.assertEqual(LABEL, '观量底／顶信号')
        # Product decision: v3 is chart-only; trading keeps shape-v2/v2.4.
        self.assertEqual(SIGNAL, 'shape-v2')
        self.assertEqual(GOLDEN_V3['meta']['version'], VERSION)
        self.assertEqual(GOLDEN_V3['meta']['keyPrefix'], KEY_PREFIX)
        self.assertEqual(GOLDEN_V3['meta']['tradingSignal'], 'shape-v2')
        self.assertEqual(len(GOLDEN_V3['cases']), 59)

    def test_python_engine_emits_exactly_the_typescript_v3_events(self):
        index = {'fixture38': 0, 'today21': 0}
        for case in GOLDEN_V3['cases']:
            bars = case_bars(SOURCES[case['source']][index[case['source']]])
            index[case['source']] += 1
            self.assertEqual(signals(bars), case['v3'], f"{case['source']}:{case['code']}:{case['day']}")
            self.assertEqual(v2_signals(bars, STABLE), case['stable'], f"stable:{case['code']}")

    def test_quoted_eval_fixture_cases_match(self):
        self.assertEqual([c['code'] for c in EVAL['cases']],
                         ['sh603938', 'sz300364', 'SYN_MISSING', 'SYN_TAIL'])
        for case in EVAL['cases']:
            got = signals(eval_bars(case))
            self.assertEqual([(e['kind'], e['time'], e['price'], e['candidateTime'], e['quality'])
                              for e in got],
                             [(e['kind'], e['time'], e['price'], e['candidateTime'], e['quality'])
                              for e in case['expected']], case['code'])
            self.assertEqual([e['key'] for e in got],
                             [f"shape-v3|{e['kind']}|{e['candidateTime']}" for e in case['expected']])
            counters = {'top': 0, 'bottom': 0}
            for event in got:
                counters[event['kind']] += 1
                self.assertEqual(event['capIndex'], counters[event['kind']])

    def test_eval_fixture_boundary_cases_stay_empty(self):
        for case in EVAL['cases']:
            if case['code'].startswith('SYN_'):
                self.assertEqual(signals(eval_bars(case)), [], case['code'])

    def test_fixture38_metrics_match_frozen_spec(self):
        matched = predicted = target = 0
        for case in RECON['cases']:
            events = signals(case_bars(case))
            matched += match_events(events, case['broker_marks'], 1)
            predicted += len(events)
            target += len(case['broker_marks'])
        precision, recall = matched / predicted, matched / target
        f05 = 1.25 * precision * recall / (0.25 * precision + recall)
        self.assertEqual((matched, predicted, target), (32, 52, 63))
        self.assertAlmostEqual(precision, .6154, places=3)
        self.assertAlmostEqual(recall, .5079, places=3)
        self.assertAlmostEqual(f05, .5904, places=3)


class V24EquivalenceTests(unittest.TestCase):
    def test_fallback_bottom_enabled_true_reproduces_v24_event_for_event(self):
        legacy = dict(RULE, version='shape-v2.4', key_prefix='shape-v2',
                      fallback=dict(RULE['fallback'], fallback_bottom_enabled=True))
        index = {'fixture38': 0, 'today21': 0}
        for case in GOLDEN_V2['cases']:
            bars = case_bars(SOURCES[case['source']][index[case['source']]])
            index[case['source']] += 1
            self.assertEqual(signals(bars, legacy), case['zhangle'], f"{case['code']}:{case['day']}")

    def test_v3_is_a_causal_remerge_not_a_v24_simple_filter(self):
        # sz300364 2026-11-12: v2.4 loses the main bottom 13:31 to three earlier fallback
        # bottoms; v3 removes the fallback bottoms and the freed slot admits 13:31.
        case = next(c for c in TODAY if c['code'] == 'sz300364')
        bars = case_bars(case)
        v24 = v2_signals(bars, ZHANGLE)
        v3 = signals(bars)
        self.assertFalse(any(e['kind'] == 'bottom' and e['time'] == '13:31' for e in v24))
        self.assertTrue(any(e['kind'] == 'bottom' and e['time'] == '13:31' for e in v3))
        # General relation on all 59 stock-days: every v3 event absent from the v2.4 final
        # list must be a main-branch event, and every dropped v2.4 event a fallback bottom.
        index = {'fixture38': 0, 'today21': 0}
        for case in GOLDEN_V3['cases']:
            bars = case_bars(SOURCES[case['source']][index[case['source']]])
            index[case['source']] += 1
            v24 = v2_signals(bars, ZHANGLE)
            v3 = signals(bars)
            v24_keys = {(e['kind'], e['time'], e['candidateTime']) for e in v24}
            v3_keys = {(e['kind'], e['time'], e['candidateTime']) for e in v3}
            streams = turning_final_streams(bars, ZHANGLE)
            main_keys = {(e['kind'], e['time'], e['candidateTime']) for e in streams['main']}
            fallback_bottom_keys = {(e['kind'], e['time'], e['candidateTime'])
                                    for e in streams['fallback'] if e['kind'] == 'bottom'}
            for added in v3_keys - v24_keys:
                self.assertIn(added, main_keys, f"new v3 event is not main-branch: {added}")
            for dropped in v24_keys - v3_keys:
                self.assertIn(dropped, fallback_bottom_keys, f"dropped v2.4 event is not a fallback bottom: {dropped}")


class CapAndBoundaryTests(unittest.TestCase):
    def test_fourth_same_kind_candidate_is_suppressed_never_replaced(self):
        # Four causal top waves; with every quality gate opened the C1 cap still emits 3.
        prices = [102, 101.3, 104, 102.5, 106, 104, 110, 108]
        rows = [dict(time='09:30', close='100', average='100', volume=0, complete=True)] + [
            dict(time=TIMES[i], close=str(price), average='100', volume=10000, complete=True)
            for i, price in enumerate(prices)]
        open_rule = dict(RULE, quality_tau_emit=-float('inf'),
                         fallback=dict(RULE['fallback'], quality_tau_emit=-float('inf')))
        raw = [e for e in candidates(rows, open_rule) if e['kind'] == 'top']
        self.assertGreaterEqual(len(raw), 4)
        emitted = signals(rows, open_rule)
        tops = [e for e in emitted if e['kind'] == 'top']
        self.assertEqual(len(tops), 3)
        self.assertEqual([e['capIndex'] for e in tops], [1, 2, 3])
        self.assertNotIn(raw[-1]['candidateTime'], [e['candidateTime'] for e in tops])

    def test_1456_cutoff_and_0930_contract(self):
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

    def test_every_prefix_is_a_truncation_of_the_final_v3_events(self):
        index = {'fixture38': 0, 'today21': 0}
        for case in GOLDEN_V3['cases']:
            bars = case_bars(SOURCES[case['source']][index[case['source']]])
            index[case['source']] += 1
            full = signals(bars)
            last = TIMES.index(full[-1]['time']) + 1 if full else 0
            for cut in range(0, last + 1):
                prefix = signals(bars[:cut + 1])
                limit = -1 if cut == 0 else cut - 1  # bars[0] is the 09:30 opening row
                expected = [e for e in full if TIMES.index(e['time']) <= limit]
                self.assertEqual(prefix, expected, f"prefix changed later: {case['code']} cut {cut}")
                for kind in ('top', 'bottom'):
                    self.assertLessEqual(len([e for e in prefix if e['kind'] == kind]), 3)

    def test_engine_does_not_mutate_input_and_is_idempotent(self):
        bars = case_bars(RECON['cases'][0])
        before = json.loads(json.dumps(bars))
        self.assertEqual(signals(bars), signals(bars))
        self.assertEqual(bars, before)


if __name__ == '__main__':
    unittest.main()