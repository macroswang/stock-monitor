"""shape-v2 price top/bottom engine shared with src/turningFinal.ts.

This is the trading-facing engine: it must emit exactly the same events as the chart
implementation, event by event (golden-tested against tests/fixtures/turning-final-golden.json).

shape-v2.0 (stable) = frozen R1 kernel + quality gate Q>=5.0 + hard daily cap 3/kind.
shape-v2.4 (zhangle, trading default) = v2.0 main branch + an all-day fallback pass:
  rsi_arm=False, |price/VWAP-1|*100 >= 0.7, reversal >= max(0.01 yuan, 0.15%,
  0.2 * candidate-to-VWAP distance), 3-minute candidate expiry, RSI cross-back
  confirmation, Q' = prox + rev + dev + 2*amp >= 4.5, main-branch priority, +/-2 minute
  then a C1 causal chronological merge: scan both streams by (time_index, main before
  fallback); a main event is accepted while its kind is below 3/day, a fallback event is
  accepted while its kind is below 3/day and no same-kind already-accepted event is within
  +/-2 minutes. No future main event can displace an earlier fallback event, so any
  prefix output is exactly the final full-day output truncated at that prefix and the
  cumulative per-kind orders can never exceed 3.
Both branches keep: 09:30 opening contract, strict causal prefix, 14:56 emission
cutoff, same-kind advance rule, and the neutral-50 compatibility for a candidate RSI
that is exactly 0 (see quality_v2 note; needed for the frozen 27/37 metrics).

Lunch-crossing confirmation is allowed (same_session_only=False), matching the
2026-11-12 Zhangle marks sh600714/sz300094 top 13:01 that confirm an 11:30 candidate
and the legacy R1 behaviour. The option stays configurable for tests.

Signals are chart/display events, never broker commands; the trading service separately
decides which newly observed live event may create an intent.
"""
import math

from .turning_q1 import TIMES
from .turning_shapes import liquidity  # shared execution-size evidence, old engine untouched

SIGNAL = 'shape-v2'
LABEL = '观量底／顶信号'
VERSION = 'shape-v2.4'
KEY_PREFIX = 'shape-v2'
EPSILON = 1e-9
EMISSION_CUTOFF_INDEX = 236  # TIMES[:236] -> last possible emission minute 14:56
DAILY_CAP_PER_KIND = 3


def _number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a quote number')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Quote number must be finite')
    return number


def _clamp(value, low, high):
    return min(high, max(low, value))


def quality_v2(*, sign, candidate, high, low, movePct, **_ignored):
    """Frozen Q formula (0..10). A candidate RSI of exactly 0 is neutral 50, matching
    the quant reference used for the frozen 27/37 calibration (09_final_eval.py:
    `e.get('rsiCandidate') or 50.0`); strict-0 would predict one more event."""
    candidate_rsi = candidate['rsi'] if math.isfinite(candidate['rsi']) and candidate['rsi'] != 0 else 50.0
    rsi_term = _clamp(sign * (candidate_rsi - 50.0) / 25.0, 0, 2)
    rev_term = _clamp(movePct / 0.45, 0, 2)
    dev_term = _clamp(abs(candidate['deviationPct']) / 1.5, 0, 2)
    amplitude_pct = (high - low) / low * 100.0 if low > 0 else 0.0
    amp_term = _clamp(amplitude_pct / 1.5, 0, 2)
    return rsi_term + rev_term + dev_term + 2.0 * amp_term


def quality_proximity(*, sign, candidate, high, low, movePct, **_ignored):
    """v2.4 fallback Q' (tau 4.5): prox replaces the RSI term. prox measures how close
    the candidate extreme still is to the day's known extreme at confirmation."""
    if sign > 0:
        distance_pct = (high - candidate['price']) / high * 100.0 if high > 0 else 0.0
    else:
        distance_pct = (candidate['price'] - low) / low * 100.0 if low > 0 else 0.0
    prox_term = _clamp((1.0 - distance_pct) / 0.5, 0, 2)
    rev_term = _clamp(movePct / 0.45, 0, 2)
    dev_term = _clamp(abs(candidate['deviationPct']) / 1.5, 0, 2)
    amplitude_pct = (high - low) / low * 100.0 if low > 0 else 0.0
    amp_term = _clamp(amplitude_pct / 1.5, 0, 2)
    return prox_term + rev_term + dev_term + 2.0 * amp_term


STABLE = dict(
    version='shape-v2.0',
    rsi_period=9, top_rsi=75, bottom_rsi=25,
    minimum_deviation_pct=1.0, reversal_fraction=.2, reversal_min_pct=0.0,
    same_kind_advance_pct=1.0, candidate_expiry_minutes=3,
    same_session_only=False,
    emission_cutoff_index=EMISSION_CUTOFF_INDEX,
    daily_cap_per_kind=DAILY_CAP_PER_KIND,
    quality_tau_emit=5.0,
    quality=quality_v2,
    fallback=None,
)

ZHANGLE = dict(
    STABLE,
    version='shape-v2.4',
    fallback=dict(
        enabled=True, rsi_arm=False, rsi_confirm=True,
        quality=quality_proximity, quality_tau_emit=4.5,
        early_limit=float('inf'), only_when_main_kind_empty=False,
        max_per_kind=float('inf'), dedupe_minutes=2, min_same_gap=0,
        minimum_deviation_pct=.7, reversal_min_pct=.15,
    ),
)

# Trading uses the high-coverage v2.4 rule; STABLE stays available for parity tests.
DEFAULT_RULE = ZHANGLE
RULE = DEFAULT_RULE  # backwards-friendly alias for rule constants


def _parse(bars, rule):
    by_time, duplicates = {}, set()
    for bar in bars:
        stamp = bar.get('time')
        if stamp in by_time:
            duplicates.add(stamp)
        by_time[stamp] = bar
    opening = by_time.get('09:30')
    if not opening or '09:30' in duplicates or opening.get('complete') is not True:
        return None
    try:
        opening_price = _number(opening['close'])
        if opening_price <= 0:
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    limit = min(rule['emission_cutoff_index'], len(TIMES))
    prefix = 0
    while prefix < limit:
        stamp = TIMES[prefix]
        bar = by_time.get(stamp)
        if not bar or stamp in duplicates or bar.get('complete') is not True:
            break
        try:
            price, average, volume = (_number(bar[key]) for key in ('close', 'average', 'volume'))
            if min(price, average) <= 0 or volume < 0:
                break
        except (KeyError, TypeError, ValueError, OverflowError):
            break
        prefix += 1
    return by_time, opening_price, prefix


def _kernel(parsed, rule, quality, rsi_arm=None, rsi_confirm=True,
            minimum_deviation_pct=None, reversal_min_pct=0.0):
    """Causal R1 kernel (plus the optional same-session rule and branch overrides)."""
    by_time, opening_price, prefix = parsed
    result, armed, last = [], {}, {}
    alpha = 1.0 / rule['rsi_period']
    previous_price = opening_price
    gain = loss = 0.0
    high = low = None
    min_dev = rule['minimum_deviation_pct'] if minimum_deviation_pct is None else minimum_deviation_pct
    for index in range(prefix):
        stamp = TIMES[index]
        bar = by_time[stamp]
        price, average, volume = _number(bar['close']), _number(bar['average']), _number(bar['volume'])
        delta = price - previous_price
        gain = (1 - alpha) * gain + alpha * max(delta, 0.0)
        loss = (1 - alpha) * loss + alpha * max(-delta, 0.0)
        rsi = 100.0 * gain / (gain + loss) if gain + loss else 50.0
        previous_price = price
        high = price if high is None else max(high, price)
        low = price if low is None else min(low, price)
        for kind, sign, edge, record in (
                ('top', 1, rule['top_rsi'], high),
                ('bottom', -1, rule['bottom_rsi'], low)):
            if sign * (price - average) <= 0:
                armed.pop(kind, None)
                continue
            deviation = sign * (price / average - 1.0) * 100.0
            arm_required = True if rsi_arm is None else rsi_arm(index)
            rsi_armed = sign * (rsi - edge) > 0 if arm_required else True
            if rsi_armed and deviation + EPSILON >= min_dev and abs(price - record) < EPSILON:
                old = armed.get(kind)
                if old is None or sign * (price - old['price']) >= 0:
                    armed[kind] = dict(index=index, time=stamp, price=price, vwap=average,
                                       rsi=rsi, deviationPct=deviation)
            candidate = armed.get(kind)
            if candidate is None:
                continue
            age = index - candidate['index']
            # expiry, same-bar, (optional) session boundary, RSI cross-back, volume,
            # reversal, same-kind advance: exactly the R1 order.
            if age > rule['candidate_expiry_minutes']:
                armed.pop(kind, None)
                continue
            if not age:
                continue
            if rule['same_session_only'] and (candidate['index'] < 120) != (index < 120):
                armed.pop(kind, None)
                continue
            if rsi_confirm and sign * (rsi - edge) > 0:
                continue
            if volume <= 0:
                continue
            distance = sign * (candidate['price'] - candidate['vwap'])
            reverse = sign * (candidate['price'] - price)
            required = max(.01, distance * rule['reversal_fraction'],
                           candidate['price'] * reversal_min_pct / 100.0)
            if reverse + EPSILON < required:
                continue
            previous = last.get(kind)
            if previous is not None and result and result[-1]['kind'] == kind:
                advance = sign * (candidate['price'] - previous['candidatePrice'])
                if advance + EPSILON < max(.01, previous['candidatePrice']
                                           * rule['same_kind_advance_pct'] / 100.0):
                    continue
            move_pct = reverse / candidate['price'] * 100.0
            deviation_pct = (price / average - 1.0) * 100.0
            quality_value = quality(kind=kind, sign=sign, price=price, average=average,
                                    high=high, low=low, movePct=move_pct,
                                    deviationPct=deviation_pct, candidate=candidate)
            prior = [_number(by_time[t]['volume']) for t in TIMES[max(0, index - 5):index]]
            before = sum(prior) / len(prior) if prior else 0.0
            event = dict(key=f"{KEY_PREFIX}|{kind}|{candidate['time']}",
                         kind=kind, time=stamp, price=price,
                         candidateTime=candidate['time'], candidatePrice=candidate['price'],
                         candidateVwap=candidate['vwap'], vwap=average, rsi=rsi,
                         rsiCandidate=candidate['rsi'],
                         deviationPct=deviation_pct,
                         deviationCandidatePct=candidate['deviationPct'],
                         support=low, resistance=high,
                         movePct=move_pct,
                         volumeRatio=volume / before if before > 0 else None,
                         quality=quality_value, capIndex=0, ruleVersion=rule['version'])
            result.append(event)
            last[kind] = event
            armed.pop(kind, None)
    return result


def _select(events, tau, cap):
    """Q >= tau first, then the hard per-kind cap in emission order (spec §2.2/§6)."""
    emitted = {'top': 0, 'bottom': 0}
    out = []
    for event in events:
        if event['quality'] < tau:
            continue
        following = emitted[event['kind']] + 1
        if following > cap:
            continue
        emitted[event['kind']] = following
        accepted = dict(event, capIndex=following)
        out.append(accepted)
    return out


def _time_index(stamp):
    return TIMES.index(stamp)


def signals(bars, rule=None):
    """Confirmed chart/trading events for one trading day, quality gate and cap applied."""
    rule = rule or DEFAULT_RULE
    parsed = _parse(bars, rule)
    if not parsed:
        return []
    main = _select(_kernel(parsed, rule, quality=rule['quality']),
                   rule['quality_tau_emit'], rule['daily_cap_per_kind'])
    fallback = rule.get('fallback')
    if not fallback or not fallback.get('enabled'):
        return main
    raw = _kernel(parsed, rule, quality=fallback['quality'],
                  rsi_arm=lambda index: fallback['rsi_arm'] or index >= fallback['early_limit'],
                  rsi_confirm=fallback['rsi_confirm'],
                  minimum_deviation_pct=fallback['minimum_deviation_pct'],
                  reversal_min_pct=fallback['reversal_min_pct'])
    # C1 causal merge: one (time, main-before-fallback) scan, never looking ahead.
    queue = [(event, True) for event in main]
    queue += [(event, False) for event in raw
              if event['quality'] >= fallback['quality_tau_emit']
              and _time_index(event['candidateTime']) < fallback['early_limit']]
    queue.sort(key=lambda item: (_time_index(item[0]['time']), 0 if item[1] else 1))
    accepted = {'top': [], 'bottom': []}
    out = []
    for event, is_main in queue:
        same_kind = accepted[event['kind']]
        if len(same_kind) >= rule['daily_cap_per_kind']:
            continue
        if not is_main:
            at = _time_index(event['time'])
            if any(abs(_time_index(m['time']) - at) <= fallback['dedupe_minutes'] for m in same_kind):
                continue
        same_kind.append(event)
        out.append(event)
    emitted = {'top': 0, 'bottom': 0}
    capped = []
    for event in out:
        emitted[event['kind']] += 1
        capped.append(dict(event, capIndex=emitted[event['kind']]))
    return capped


def turning_final_streams(bars, rule=None):
    """Shared raw streams for the shape-v3 module (additive; the v2 entry points above
    are unchanged and the v2 golden still locks their behaviour). main is already Q-gated
    and cap-selected among itself; fallback is the raw causal fallback stream (quality
    attached) so a caller can apply extra filters before its own C1 merge."""
    rule = rule or DEFAULT_RULE
    parsed = _parse(bars, rule)
    if not parsed:
        return dict(main=[], fallback=[])
    main = _select(_kernel(parsed, rule, quality=rule['quality']),
                   rule['quality_tau_emit'], rule['daily_cap_per_kind'])
    fallback = rule.get('fallback')
    if not fallback or not fallback.get('enabled'):
        return dict(main=main, fallback=[])
    raw = _kernel(parsed, rule, quality=fallback['quality'],
                  rsi_arm=lambda index: fallback['rsi_arm'] or index >= fallback['early_limit'],
                  rsi_confirm=fallback['rsi_confirm'],
                  minimum_deviation_pct=fallback['minimum_deviation_pct'],
                  reversal_min_pct=fallback['reversal_min_pct'])
    return dict(main=main, fallback=raw)


def candidates(bars, rule=None):
    """Diagnostic only: the kernel stream BEFORE the quality gate and cap."""
    rule = rule or DEFAULT_RULE
    parsed = _parse(bars, rule)
    if not parsed:
        return []
    return _kernel(parsed, rule, quality=rule['quality'])