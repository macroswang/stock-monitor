"""Shared causal execution assumptions; these are daily-bar simulations, not fills.

Signals are never filtered using future corporate actions or future trade results.
Holding N sessions includes the entry session. Mainland stock sales obey T+1.
One-price up/zero-volume entry is unavailable; locked-down exits defer. Historical
ST flags, depth and full corporate-action cash ledgers are not in the free archive.
"""
from bisect import bisect_left, bisect_right
from decimal import Decimal, ROUND_HALF_UP
import math

BUY_COST = SELL_COST = .0015
COST_PCT = .30
HORIZONS = (5, 10, 20, 60)


def net_pct(entry, exit_):
    return (exit_ * (1 - SELL_COST) / (entry * (1 + BUY_COST)) - 1) * 100


def limit_pct(code, day):
    if code.startswith('sh68'):
        return 20
    if code.startswith('sz30'):
        return 20 if day >= '2020-08-24' else 10
    return 10 if code.startswith(('sh60', 'sz00')) else None


def price_limit(previous, pct):
    return float((Decimal(str(previous)) * (1 + Decimal(str(pct)) / 100)).quantize(
        Decimal('.01'), rounding=ROUND_HALF_UP))


def locked(bar, previous, direction):
    return (bar.get('volume') == 0 or
            math.isclose(bar['high'], bar['low'], abs_tol=1e-8) and
            (bar['close'] > previous if direction == 'up' else bar['close'] < previous))


def entry_for(bars, signal_index, code='', sessions=None):
    if signal_index + 1 >= len(bars):
        return dict(status='pending_entry', index=None, price=None, date=None)
    i = signal_index + 1
    bar = bars[i]
    trade_bar = bar.get('execution', bar)
    previous_bar = bars[signal_index].get('execution', bars[signal_index])
    previous = previous_bar['close']
    if sessions:
        next_i = bisect_right(sessions, bars[signal_index]['date'])
        if next_i >= len(sessions):
            return dict(status='pending_entry', index=None, price=None, date=None)
        if bar['date'] != sessions[next_i]:
            return dict(status='entry_unavailable', index=None, price=None, date=sessions[next_i])
    band = limit_pct(code, bar['date'])
    if (locked(trade_bar, previous, 'up') or
            band is not None and trade_bar['open'] >= price_limit(previous, band) - .00001):
        return dict(status='entry_unavailable', index=None, price=None, date=bar['date'])
    return dict(status='entered', index=i, price=bar['open'], date=bar['date'])


def target_session(bars, entry_index, horizon, sessions=None):
    if sessions:
        i = bisect_left(sessions, bars[entry_index]['date']) + horizon - 1
        return sessions[i] if i < len(sessions) else None
    i = entry_index + horizon - 1
    return bars[i]['date'] if i < len(bars) else None


def close_exit(bars, entry_index, horizon=20, sessions=None):
    target = target_session(bars, entry_index, horizon, sessions)
    if target is None:
        return dict(status='pending_exit', index=None, price=None, date=None)
    for i in range(entry_index + 1, len(bars)):
        if bars[i]['date'] < target or locked(bars[i].get('execution',bars[i]),
                bars[i-1].get('execution',bars[i-1])['close'], 'down'):
            continue
        return dict(status='closed', index=i, price=bars[i]['close'], date=bars[i]['date'])
    return dict(status='pending_exit', index=None, price=None, date=None)


def jump_in(bars, start, end):
    return any(abs(bars[i]['close'] / bars[i - 1]['close'] - 1) > .22 or
               abs(bars[i]['open'] / bars[i - 1]['close'] - 1) > .22
               for i in range(max(1, start), min(len(bars), end + 1)))


def forward_outcomes(code, bars, signal_index, sessions=None):
    entry = entry_for(bars, signal_index, code, sessions)
    forward, exits = {}, {}
    for h in HORIZONS:
        out = close_exit(bars, entry['index'], h, sessions) if entry['index'] is not None else dict(
            status=entry['status'], index=None, price=None, date=None)
        exits[str(h)] = out
        forward[str(h)] = net_pct(entry['price'], out['price']) if out['price'] is not None else None
    return dict(entry=entry, forward=forward, exits=exits)


def path_exit(bars, entry_index, stop, target=None, max_hold=60, sessions=None):
    """Entry-day stop breach queues the earliest legal exit; targets require T+1."""
    timeout = target_session(bars, entry_index, max_hold, sessions)
    pending_stop = bars[entry_index]['low'] <= stop
    for i in range(entry_index + 1, len(bars)):
        bar = bars[i]
        if locked(bar.get('execution',bar), bars[i-1].get('execution',bars[i-1])['close'], 'down'):
            pending_stop |= bar['low'] <= stop
            continue
        if pending_stop:
            return dict(status='closed', outcome='stop', index=i, price=bar['open'], date=bar['date'])
        if bar['low'] <= stop:
            return dict(status='closed', outcome='stop', index=i, price=min(stop, bar['open']), date=bar['date'])
        if target is not None and bar['high'] >= target:
            return dict(status='closed', outcome='target', index=i, price=max(target, bar['open']), date=bar['date'])
        if timeout is not None and bar['date'] >= timeout:
            return dict(status='closed', outcome='timeout', index=i, price=bar['close'], date=bar['date'])
    return dict(status='pending_exit', outcome=None, index=None, price=None, date=None)


def path_outcomes(code, bars, signal_index, sessions=None):
    entry = entry_for(bars, signal_index, code, sessions)
    if entry['index'] is None:
        return dict(outcome=None, policies={k: None for k in ('5_3','8_4','10_5','15_8')},
                    label_end=None, policy_label_end={}, net=None, status=entry['status'])
    outcomes = {}
    for key, gain, loss in (('5_3',5,3),('8_4',8,4),('10_5',10,5),('15_8',15,8)):
        result = path_exit(bars, entry['index'], entry['price'] * (1-loss/100),
                           entry['price'] * (1+gain/100), sessions=sessions)
        outcomes[key] = result
    primary = outcomes['10_5']
    return dict(outcome=primary['outcome'], status=primary['status'],
                label_end=primary['date'],policy_label_end={k:v['date'] for k,v in outcomes.items()},
                net=net_pct(entry['price'], primary['price']) if primary['price'] is not None else None,
                policies={k:(v['outcome']=='target' if v['status']=='closed' else None) for k,v in outcomes.items()})
