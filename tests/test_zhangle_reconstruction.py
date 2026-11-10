import copy
import json
import unittest
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock,patch

from research.zhangle_reconstruction import TIMES, signals

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/zhangle-reconstruction.json').read_text())


def bars(case):
    return [dict(time=t, close=p, average=a, volume=v, complete=True)
            for t, p, a, v in zip(TIMES, case['prices'], case['averages'], case['volumes'])]


def synthetic(prices, start=0):
    return [dict(time=t, close=p, average=100., volume=10000, complete=True)
            for t, p in zip(TIMES, [100.] * start + prices)]


class ZhangleReconstructionTests(unittest.TestCase):
    def test_all_38_stock_days_match_frozen_proxy_outputs(self):
        self.assertEqual(len(FIXTURE['cases']), 38)
        self.assertEqual(sum(len(c['broker_marks']) for c in FIXTURE['cases']), 63)
        for c in FIXTURE['cases']:
            with self.subTest(day=c['day'], code=c['code']):
                got = signals(bars(c), c['opening_price'])
                geometry = [[m[k] for k in ('kind', 'time', 'price', 'candidateTime', 'candidatePrice')]
                            for m in got]
                self.assertEqual(geometry, c['expected'])

    def test_every_valid_prefix_preserves_past_events_and_values(self):
        for c in FIXTURE['cases']:
            rows = bars(c)
            full = signals(rows, c['opening_price'])
            for cut in range(1, len(rows) + 1):
                self.assertEqual(signals(rows[:cut], c['opening_price']),
                                 [m for m in full if m['time'] <= rows[cut - 1]['time']],
                                 (c['code'], c['day'], cut))

    def test_adversarial_future_cannot_create_or_move_a_past_signal(self):
        for c in FIXTURE['cases']:
            rows = bars(c)
            full = signals(rows, c['opening_price'])
            for cut in (10, 30, 60, 90):
                changed = [dict(b, close=b['close'] * 1.8, average=b['average'] * .6)
                           if i >= cut else b for i, b in enumerate(rows)]
                self.assertEqual([m for m in signals(changed, c['opening_price'])
                                  if m['time'] <= rows[cut - 1]['time']],
                                 [m for m in full if m['time'] <= rows[cut - 1]['time']])

    def test_sanfu_emits_at_1032_without_waiting_for_later_bars(self):
        c = next(c for c in FIXTURE['cases'] if c['code'] == 'sh603938' and c['day'] == '2026-11-10')
        rows = bars(c)
        index = TIMES.index('10:32')
        self.assertEqual(signals(rows[:index], c['opening_price']), [])
        self.assertEqual([(m['kind'], m['time']) for m in signals(rows[:index + 1], c['opening_price'])],
                         [('top', '10:32')])

    def test_incomplete_missing_duplicate_and_non_boolean_minutes_stop_the_prefix(self):
        c = next(c for c in FIXTURE['cases'] if c['code'] == 'sh603938' and c['day'] == '2026-11-10')
        rows = bars(c)
        index = TIMES.index('10:32')
        for flag in (False, 1, 'true'):
            changed = copy.deepcopy(rows)
            changed[index]['complete'] = flag
            self.assertEqual(signals(changed, c['opening_price']), [])
        self.assertEqual(signals(rows[:index] + rows[index + 1:], c['opening_price']), [])
        self.assertEqual(signals(rows + [rows[index]], c['opening_price']), [])

    def test_invalid_numbers_and_opening_prices_are_not_invented(self):
        for price in (0, -1, float('nan'), float('inf'), True, None):
            with self.assertRaises((TypeError, ValueError)):
                signals([], price)
        for field, value in [('close', 'NaN'), ('average', 0), ('volume', -1), ('volume', True)]:
            rows = synthetic([98., 98.7])
            rows[1][field] = value
            self.assertEqual(signals(rows, 100), [])

    def test_zero_volume_context_is_valid_but_cannot_emit(self):
        rows = synthetic([98., 98.7])
        rows[0]['volume'] = 0
        self.assertEqual(len(signals(rows, 100)), 1)
        rows[1]['volume'] = 0
        self.assertEqual(signals(rows, 100), [])

    def test_one_complete_reversal_minute_is_enough_early_and_late(self):
        for start in (0, 234):
            got = signals(synthetic([98., 98.7], start=start), 100)
            self.assertEqual([(m['candidateTime'], m['time']) for m in got],
                             [(TIMES[start], TIMES[start + 1])])
        self.assertEqual(signals(synthetic([98.,98.7],start=235),100),[])

    def test_same_wave_small_new_low_is_suppressed_but_a_material_new_low_can_emit(self):
        got = signals(synthetic([98., 98.7, 97.8, 98.5, 96., 97.5]), 100)
        self.assertEqual([m['candidatePrice'] for m in got], [98., 96.])
        self.assertEqual(len({m['key'] for m in got}), len(got))

    def test_expired_candidate_does_not_emit_on_a_late_bounce(self):
        self.assertEqual(signals(synthetic([98., 98.05, 98.1, 98.15, 99.]), 100), [])

    def test_repeat_calls_are_stable_and_do_not_mutate_input(self):
        c = FIXTURE['cases'][0]
        rows = bars(c)
        before = copy.deepcopy(rows)
        self.assertEqual(signals(rows, c['opening_price']), signals(rows, c['opening_price']))
        self.assertEqual(rows, before)
        self.assertEqual(signals([], c['opening_price']), [])
        self.assertEqual(signals(synthetic([100.] * 240), 100), [])


class FormalOpeningContextTests(unittest.TestCase):
    def test_app_passes_the_chart_opening_quote_and_detects_opening_revisions(self):
        from core.app import App
        from core.provider import CN
        from core.turning_shapes import signals as formal_signals
        c=FIXTURE['cases'][0]
        rows=[dict(time='09:30',close=str(c['opening_price']),average=str(c['opening_price']),volume=0,complete=True)]+bars(c)
        with tempfile.TemporaryDirectory() as directory:
            app=App(directory,start_worker=False)
            try:
                app.live_trading=Mock()
                now=datetime.fromisoformat(c['day']+'T10:31:50+08:00')
                quote=dict(date=c['day'],timestamp=now.isoformat(),price='30.86',limit_up='1000')
                def feed(at,source):
                    quote['timestamp']=at.isoformat()
                    group=dict(date=c['day'],bars=[b for b in source if b['time']<=at.strftime('%H:%M')],source='test_public_quote')
                    with patch('core.app.now_cn',return_value=at):app.ingest(c['code'],quote,[group],at)
                feed(now,rows)
                now+=timedelta(seconds=15);feed(now,rows)
                call=app.live_trading.ingest.call_args
                self.assertTrue(call.args[4])
                self.assertEqual(call.args[1][0]['time'],'09:30')
                self.assertEqual([(m['kind'],m['time']) for m in formal_signals(call.args[1])],[('top','10:32')])
                revised=[dict(b,close=str(c['opening_price']*1.01)) if b['time']=='09:30' else b for b in rows]
                now+=timedelta(seconds=10);feed(now,revised)
                call=app.live_trading.ingest.call_args
                self.assertFalse(call.args[4]);self.assertIn('修订',call.kwargs['admission_reason'])
                self.assertEqual(app.health[c['code']],'实时采样监控')
                self.assertEqual(app.sessions[c['code']]['bars'][0][0],'09:31')
            finally:app.store.db.close()


if __name__ == '__main__':
    unittest.main()
