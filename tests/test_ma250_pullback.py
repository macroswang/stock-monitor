import json, unittest
from datetime import date, timedelta
from pathlib import Path

from core.ma250_pullback import PARAMETERS, analyze

FIXTURE = Path(__file__).parent / 'fixtures' / 'ma250-pullback-603533.json'


def calendar(count, start=date(2023, 1, 2)):
    days, day = [], start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def next_day(stamp):
    day = date.fromisoformat(stamp) + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def bar(day, close, open_=None, high=None, low=None):
    open_ = close - 0.04 if open_ is None else open_
    return dict(date=day.isoformat() if hasattr(day, 'isoformat') else day,
                open=round(open_, 4), close=round(close, 4),
                high=round(max(open_, close) + 0.06 if high is None else high, 4),
                low=round(min(open_, close) - 0.07 if low is None else low, 4))


def pullback_series(peak=12.5, trough=11.05, force_touch=True):
    """A slow-rise base, a rally, then a pullback into the annual line."""
    prices = [10.5 + 1.0 * index / 309 for index in range(310)]
    prices += [11.5 + (peak - 11.5) * index / 24 for index in range(1, 25)]
    prices += [peak - (peak - trough) * index / 8 for index in range(1, 9)]
    days = calendar(len(prices))
    bars = [bar(day, close) for day, close in zip(days, prices)]
    if force_touch:
        touch = len(bars) - 1
        line = sum(item['close'] for item in bars[touch - 249:touch + 1]) / 250
        bars[touch]['low'] = round(line * 0.99, 4)
        bars[touch]['open'] = max(bars[touch]['open'], bars[touch]['low'] + 0.02)
        bars[touch]['close'] = max(bars[touch]['close'], bars[touch]['open'])
        bars[touch]['high'] = max(bars[touch]['high'], bars[touch]['close'] + 0.06)
    return bars


def strong_close(bars):
    """A close above both the annual line and the still-high short average."""
    line = sum(item['close'] for item in bars[-250:]) / 250
    short = sum(item['close'] for item in bars[-5:]) / 5
    return max(line * 1.04, short * 1.02)


def confirmation(bars, close=None, open_=None, low=None):
    line = sum(item['close'] for item in bars[-250:]) / 250
    value = strong_close(bars) if close is None else close
    open_ = value - 0.2 if open_ is None else open_
    low = max(line * 1.02, min(open_, value) - 0.05) if low is None else low
    return bars + [bar(next_day(bars[-1]['date']), value, open_=open_, high=value + 0.06, low=round(low, 4))]


class Ma250PullbackTest(unittest.TestCase):
    def test_real_snapshot_signals_are_frozen_and_causal(self):
        bars = json.loads(FIXTURE.read_text(encoding='utf-8'))['bars']
        report = analyze(bars)
        self.assertIsNone(report['error'])
        self.assertEqual([item['date'] for item in report['signals']],
                         ['2025-08-18', '2025-11-25', '2026-09-29', '2026-11-02'])
        full = report['signals']
        for signal in full:
            index = next(i for i, item in enumerate(bars) if item['date'] == signal['date'])
            prefix = analyze(bars[:index + 1])['signals']
            self.assertEqual([item['date'] for item in prefix],
                             [item['date'] for item in full if item['date'] <= signal['date']])
            self.assertEqual(prefix[-1], signal)
            self.assertNotIn(signal['date'], [item['date'] for item in analyze(bars[:index])['signals']])
        for signal in full:
            self.assertGreater(signal['close'], signal['ma250'])
            self.assertLess(signal['stop'], signal['touch_low'])
            self.assertLessEqual(signal['touch_depth_pct'], PARAMETERS['maximum_break_pct'])
        positions = [next(i for i, item in enumerate(bars) if item['date'] == signal['date']) for signal in full]
        for left, right in zip(positions, positions[1:]):
            self.assertGreaterEqual(right - left, PARAMETERS['cooldown_days'])

    def test_insufficient_history_has_no_signal_and_no_error(self):
        report = analyze(pullback_series()[:240])
        self.assertEqual(report['signals'], [])
        self.assertIsNone(report['error'])
        self.assertEqual(report['latest']['status'], 'insufficient')

    def test_confirmation_bar_after_the_touch_is_the_signal(self):
        bars = pullback_series()
        self.assertEqual(analyze(bars)['signals'], [])
        closed = confirmation(bars)
        report = analyze(closed)
        self.assertEqual(len(report['signals']), 1)
        signal = report['signals'][0]
        self.assertEqual(signal['date'], closed[-1]['date'])
        # The entire retracement low can precede the last touch.
        segment=[b for b in closed if signal['peak_date']<b['date']<=signal['date']]
        self.assertEqual(signal['touch_low'],min(b['low'] for b in segment))
        self.assertGreaterEqual(signal['pullback_pct'], PARAMETERS['minimum_pullback_pct'])

    def test_same_day_undercut_and_reclaim_is_also_a_signal(self):
        bars = pullback_series()
        line = sum(item['close'] for item in bars[-250:]) / 250
        day = next_day(bars[-1]['date'])
        value = strong_close(bars)
        reclaimed = dict(bars[-1])
        reclaimed.update(date=day.isoformat(), open=round(line * 0.99, 4), close=round(value, 4),
                         high=round(value * 1.01, 4), low=round(line * 0.985, 4))
        report = analyze(bars + [reclaimed])
        self.assertEqual(len(report['signals']), 1)
        self.assertEqual(report['signals'][0]['date'], day.isoformat())
        self.assertEqual(report['signals'][0]['touch_date'], day.isoformat())

    def test_extended_close_is_rejected(self):
        bars = pullback_series()
        line = sum(item['close'] for item in bars[-250:]) / 250
        closed = confirmation(bars, close=line * (1 + PARAMETERS['maximum_extension_pct'] / 100) + 0.5)
        self.assertEqual(analyze(closed)['signals'], [])

    def test_red_confirmation_is_rejected(self):
        bars = pullback_series()
        closed = confirmation(bars, close=strong_close(bars), open_=strong_close(bars) + 0.1)
        self.assertEqual(analyze(closed)['signals'], [])

    def test_falling_annual_line_is_rejected(self):
        bars = pullback_series()
        mirrored = [dict(item, open=round(24 - item['open'], 4), close=round(24 - item['close'], 4),
                         high=round(24 - item['low'], 4), low=round(24 - item['high'], 4)) for item in bars]
        self.assertEqual(analyze(confirmation(mirrored))['signals'], [])

    def test_weak_pullback_above_the_line_never_touches(self):
        shallow = pullback_series(trough=12.6, force_touch=False)
        line = sum(item['close'] for item in shallow[-250:]) / 250
        self.assertGreater(shallow[-1]['low'], line * (1 + PARAMETERS['touch_tolerance_pct'] / 100))
        self.assertEqual(analyze(confirmation(shallow))['signals'], [])

    def test_invalid_or_duplicated_dates_report_an_error(self):
        bars = pullback_series()
        self.assertIsNotNone(analyze(bars + [bars[-1]])['error'])
        broken = pullback_series()
        broken[-1]['high'] = broken[-1]['low'] - 1
        self.assertIsNotNone(analyze(broken)['error'])
        self.assertEqual(analyze([])['signals'], [])
        self.assertIsNone(analyze([])['error'])


class BreakoutTest(unittest.TestCase):
    def test_breakouts_are_separate_sorted_and_quality_flagged(self):
        bars = json.loads(FIXTURE.read_text(encoding='utf-8'))['bars']
        report = analyze(bars, market={bar['date']: True for bar in bars})
        breakouts = report['breakouts']
        self.assertGreater(len(breakouts), 0)
        self.assertEqual([item['date'] for item in breakouts], sorted(item['date'] for item in breakouts))
        for item in breakouts:
            self.assertEqual(item['kind'], 'breakout')
            self.assertGreater(item['close'], item['ma250'])
            self.assertIn('quality', item)
            self.assertIsInstance(item['quality'], bool)
        self.assertEqual([item['date'] for item in report['breakouts']],
                         [item['date'] for item in analyze(bars, market={})['breakouts']])

    def test_short_history_returns_no_breakouts(self):
        bars = json.loads(FIXTURE.read_text(encoding='utf-8'))['bars'][:200]
        report = analyze(bars, market={})
        self.assertEqual(report['breakouts'], [])


if __name__ == '__main__':
    unittest.main()

def strong_case(prior=(11.5, 11.3, 11.1, 11.0), touch_above=True, tell=1.04, base=(10.5, 11.5)):
    """A touch that stays above the line, a higher low and a tight reclaim."""
    prices = [base[0] + (base[1] - base[0]) * index / 309 for index in range(310)]
    prices += list(prior)
    prices += [prior[-1] + (12.8 - prior[-1]) * index / 20 for index in range(1, 21)]
    prices += [12.8 - (12.8 - 11.35) * index / 8 for index in range(1, 9)]
    days = calendar(len(prices))
    bars = [bar(day, close) for day, close in zip(days, prices)]
    touch = len(bars) - 1
    line = sum(item['close'] for item in bars[touch - 249:touch + 1]) / 250
    bars[touch]['low'] = round(line * (1.005 if touch_above else 0.99), 4)
    bars[touch]['open'] = max(bars[touch]['open'], bars[touch]['low'] + 0.02)
    bars[touch]['close'] = max(bars[touch]['close'], bars[touch]['open'])
    bars[touch]['high'] = max(bars[touch]['high'], bars[touch]['close'] + 0.06)
    day = next_day(bars[-1]['date'])
    close = round(line * tell, 4)
    confirmation = bar(day, close, open_=round(line * 1.02, 4), high=round(max(close, line * 1.05) + 0.06, 4),
                       low=round(line * 1.016, 4))
    return bars + [confirmation], day.isoformat()


class StrongTierTest(unittest.TestCase):
    @staticmethod
    def fixture_until(stamp):
        bars = json.loads(FIXTURE.read_text(encoding='utf-8'))['bars']
        return bars[:next(index for index, bar in enumerate(bars) if bar['date'] == stamp) + 1]

    def test_real_strong_signal_needs_the_market_and_passes_macd(self):
        bars = self.fixture_until('2025-08-18')
        signal = next(item for item in analyze(bars, market={bar['date']: True for bar in bars})['signals']
                      if item['date'] == '2025-08-18')
        self.assertTrue(signal['strong'])
        self.assertEqual(signal['strong_reasons'], [])
        self.assertGreater(signal['macd_hist'], 0)
        self.assertLessEqual(signal['touch_depth_pct'], 0)
        for market in ({bar['date']: False for bar in bars}, {}, None):
            item = next(item for item in analyze(bars, market=market)['signals'] if item['date'] == '2025-08-18')
            self.assertFalse(item['strong'])
            self.assertIn('market', item['strong_reasons'])

    def test_reclaim_that_broke_the_line_or_macd_is_not_strong(self):
        bars = self.fixture_until('2026-11-02')
        market = {bar['date']: True for bar in bars}
        signal = next(item for item in analyze(bars, market=market)['signals'] if item['date'] == '2026-11-02')
        self.assertFalse(signal['strong'])
        self.assertIn('broke-line', signal['strong_reasons'])
        self.assertIn('extended', signal['strong_reasons'])
        bars = self.fixture_until('2026-09-29')
        signal = next(item for item in analyze(bars, market={bar['date']: True for bar in bars})['signals']
                      if item['date'] == '2026-09-29')
        self.assertFalse(signal['strong'])
        self.assertIn('broke-line', signal['strong_reasons'])

    def test_v1_signal_dates_survive_strong_filtering(self):
        bars = self.fixture_until('2026-11-02')
        market = {bar['date']: True for bar in bars}
        signals = analyze(bars, market=market)['signals']
        self.assertEqual([item['date'] for item in signals],
                         ['2025-08-18', '2025-11-25', '2026-09-29', '2026-11-02'])
        self.assertEqual([item['date'] for item in signals if item['strong']], ['2025-08-18'])

    def test_an_unadjusted_split_window_is_not_a_signal(self):
        bars, day = strong_case()
        for item in bars[320:]:
            for key in ('open', 'close', 'high', 'low'):
                item[key] *= 0.5
        self.assertEqual(analyze(bars, market={day: True})['signals'], [])

if __name__ == '__main__':
    unittest.main()

def strong_case(prior=(11.5, 11.3, 11.1, 11.0), touch_above=True, tell=1.04, base=(10.5, 11.5)):
    """A touch that stays above the line, a higher low and a tight reclaim."""
    prices = [base[0] + (base[1] - base[0]) * index / 309 for index in range(310)]
    prices += list(prior)
    prices += [prior[-1] + (12.8 - prior[-1]) * index / 20 for index in range(1, 21)]
    prices += [12.8 - (12.8 - 11.35) * index / 8 for index in range(1, 9)]
    days = calendar(len(prices))
    bars = [bar(day, close) for day, close in zip(days, prices)]
    touch = len(bars) - 1
    line = sum(item['close'] for item in bars[touch - 249:touch + 1]) / 250
    bars[touch]['low'] = round(line * (1.005 if touch_above else 0.99), 4)
    bars[touch]['open'] = max(bars[touch]['open'], bars[touch]['low'] + 0.02)
    bars[touch]['close'] = max(bars[touch]['close'], bars[touch]['open'])
    bars[touch]['high'] = max(bars[touch]['high'], bars[touch]['close'] + 0.06)
    day = next_day(bars[-1]['date'])
    close = round(line * tell, 4)
    confirmation = bar(day, close, open_=round(line * 1.02, 4), high=round(max(close, line * 1.05) + 0.06, 4),
                       low=round(line * 1.016, 4))
    return bars + [confirmation], day.isoformat()