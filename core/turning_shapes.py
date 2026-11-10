"""Causal R1 intraday bottom/top proxy, shared with the chart algorithm.

Fitted to observed Zhangle markers; not a verified proprietary formula.
The strategy binding stays shape-v1 so account settings are not migrated.
"""
import math
from collections import Counter
from .turning_q1 import TIMES

SIGNAL = 'shape-v1'
LABEL = '图中底／顶信号'
VERSION = 'zhangle-proxy-r1'
PARAMETERS = dict(rsi_period=9, top_rsi=75, bottom_rsi=25,
                  minimum_deviation_pct=1.0, reversal_fraction=.2,
                  same_kind_advance_pct=1.0, candidate_expiry_minutes=3)


def _number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a quote number')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Quote number must be finite')
    return number


def signals(bars):
    """Return stable events at the triggering minute, never at a past pivot.

    opening_price is the actual same-day 09:30 quote, not yesterday's close.
    Missing, duplicated, unfinished or invalid minutes end the usable prefix;
    unknown RSI context is never silently bridged. Zero-volume background
    minutes are valid, but cannot themselves emit a signal. The existing
    14:56 emission cutoff is retained; there is no daily signal-count cap.
    """
    counts = Counter(b.get('time') for b in bars)
    by_time = {b.get('time'): b for b in bars}
    opening = by_time.get('09:30')
    if not opening or counts['09:30'] != 1 or opening.get('complete') is not True:
        return []
    try:
        opening_price = _number(opening['close'])
        if opening_price <= 0:
            return []
    except (KeyError, TypeError, ValueError, OverflowError):
        return []
    result, armed, last = [], {}, {}
    gain = loss = 0.
    previous_price = opening_price
    high = low = None
    alpha = 1 / PARAMETERS['rsi_period']
    eps = 1e-9
    for index, stamp in enumerate(TIMES[:236]):
        bar = by_time.get(stamp)
        if not bar or counts[stamp] != 1 or bar.get('complete') is not True:
            break
        try:
            price, average, volume = (_number(bar[k]) for k in ('close', 'average', 'volume'))
            if min(price, average) <= 0 or volume < 0:
                break
        except (KeyError, TypeError, ValueError, OverflowError):
            break
        delta = price - previous_price
        gain = (1 - alpha) * gain + alpha * max(delta, 0)
        loss = (1 - alpha) * loss + alpha * max(-delta, 0)
        rsi = 100 * gain / (gain + loss) if gain + loss else 50.
        previous_price = price
        high = price if high is None else max(high, price)
        low = price if low is None else min(low, price)
        for kind, sign, edge, record in (
                ('top', 1, PARAMETERS['top_rsi'], high),
                ('bottom', -1, PARAMETERS['bottom_rsi'], low)):
            side = sign * (price - average)
            if side <= 0:
                armed.pop(kind, None)
                continue
            deviation = sign * (price / average - 1) * 100
            if (sign * (rsi - edge) > 0
                    and deviation + eps >= PARAMETERS['minimum_deviation_pct']
                    and abs(price - record) < eps):
                old = armed.get(kind)
                if old is None or sign * (price - old['price']) >= 0:
                    armed[kind] = dict(index=index, time=stamp, price=price, vwap=average)
            candidate = armed.get(kind)
            if candidate is None:
                continue
            age = index - candidate['index']
            if age > PARAMETERS['candidate_expiry_minutes']:
                armed.pop(kind)
                continue
            if age == 0 or sign * (rsi - edge) > 0 or volume <= 0:
                continue
            distance = sign * (candidate['price'] - candidate['vwap'])
            reverse = sign * (candidate['price'] - price)
            if reverse + eps < max(.01, distance * PARAMETERS['reversal_fraction']):
                continue
            previous = last.get(kind)
            if previous and result[-1]['kind'] == kind:
                advance = sign * (candidate['price'] - previous['candidatePrice'])
                if advance + eps < max(.01, previous['candidatePrice']
                                       * PARAMETERS['same_kind_advance_pct'] / 100):
                    continue
            prior_volume = [_number(by_time[t]['volume']) for t in TIMES[max(0,index-5):index]]
            before = sum(prior_volume) / len(prior_volume) if prior_volume else 0
            event = dict(key=f"{VERSION}|{kind}|{candidate['time']}",
                         kind=kind, time=stamp, price=price,
                         candidateTime=candidate['time'], candidatePrice=candidate['price'],
                         candidateVwap=candidate['vwap'], vwap=average, rsi=rsi,
                         deviationPct=(price / average - 1) * 100,
                         support=low, resistance=high,
                         movePct=reverse / candidate['price'] * 100,
                         volumeRatio=volume / before if before > 0 else None)
            result.append(event)
            last[kind] = event
            armed.pop(kind)
    return result


def liquidity(bars,stamp):
    """Execution-size evidence, independent of shape detection and Q1 screening."""
    by={b['time']:b for b in bars};index=TIMES.index(stamp)
    try:
        rows=[by[t] for t in TIMES[index-4:index+1]]
        if len(rows)!=5 or any(b.get('complete') is not True for b in rows):raise ValueError()
        volumes=[float(b['volume']) for b in rows]
        import math
        if not all(math.isfinite(v) and v>=0 for v in volumes):raise ValueError()
        return dict(meanShares=sum(volumes)/5,currentShares=volumes[-1])
    except (ValueError,TypeError,KeyError):return {}
