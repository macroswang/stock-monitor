"""Backend Q1, kept equivalent to the frozen chart engine (golden fixture tested).

This creates confirmed observations, never broker commands. The trading service
separately decides whether a newly observed, live event may create an intent.
"""
import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

TIMES = [f'{m//60:02}:{m%60:02}' for m in [*range(571, 691), *range(781, 901)]]


def cost_space(buy, sell):
    buy, sell = Decimal(str(buy)), Decimal(str(sell))
    purchase = (buy + max(Decimal('.01'), buy * Decimal('.0005'))).quantize(Decimal('.01'), rounding=ROUND_CEILING) * 1000
    sale = (sell - max(Decimal('.01'), sell * Decimal('.0005'))).quantize(Decimal('.01'), rounding=ROUND_FLOOR) * 1000
    cents = lambda n: n.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    fees = max(Decimal(5), cents(purchase * Decimal('.0002'))) + max(Decimal(5), cents(sale * Decimal('.0002')))
    fees += cents(sale * Decimal('.0005')) + cents(purchase * Decimal('.00001')) + cents(sale * Decimal('.00001'))
    return float(sale - purchase - fees)


def raw_signals(bars):
    by, duplicates = {}, set()
    for b in bars:
        if b['time'] in by:
            duplicates.add(b['time'])
        by[b['time']] = b
    all_bars = [by.get(t) for t in TIMES]

    def valid(b):
        if not b or b['time'] in duplicates or b.get('complete') is not True:
            return False
        try:
            return all(math.isfinite(float(b[k])) and float(b[k]) > 0 for k in ('close', 'average')) and math.isfinite(float(b['volume'])) and float(b['volume']) >= 0
        except (KeyError, ValueError, TypeError):
            return False

    raw = []
    eps = 1e-9
    for i in range(236):
        start = 0 if i < 120 else 120
        if i < 1 or not valid(all_bars[i]) or not valid(all_bars[i-1]) or min(float(all_bars[i]['volume']), float(all_bars[i-1]['volume'])) <= 0:
            continue
        for lag in range(5, 1, -1):
            c, lo = i-lag, i-lag-19
            if c < start or lo < 0 or not all(valid(b) for b in all_bars[lo:i+1]):
                continue
            pivot = all_bars[c]
            p, vwap = float(pivot['close']), float(pivot['average'])
            prior = [float(b['close']) for b in all_bars[lo:c+1]]
            support, resistance = min(prior), max(prior)
            path = [float(b['close']) for b in all_bars[c:i+1]]
            current, deviation = path[-1], p/vwap-1
            bottom = p <= support+eps and deviation <= -.005 and all(x >= path[j-1] for j, x in enumerate(path) if j) and current-p+eps >= max(.01, p*.003)
            top = p >= resistance-eps and deviation >= .005 and all(x <= path[j-1] for j, x in enumerate(path) if j) and p-current+eps >= max(.01, p*.003)
            kind = 'bottom' if bottom else 'top' if top else None
            if kind is None:
                continue
            before = sum(float(b['volume']) for b in all_bars[c-5:c])/5
            raw.append(dict(kind=kind, time=TIMES[i], price=current, candidateTime=TIMES[c], candidatePrice=p, vwap=vwap,
                            deviationPct=deviation*100, support=support, resistance=resistance,
                            movePct=abs(current/p-1)*100,
                            volumeRatio=(float(all_bars[i-1]['volume'])+float(all_bars[i]['volume']))/2/before if before > 0 else None))
            break
    return raw


def signals(bars):
    raw=raw_signals(bars)
    by={b['time']:b for b in bars}
    eps=1e-9
    result, last, count = [], {}, {'bottom': 0, 'top': 0}
    for m in raw:
        kind, i = m['kind'], TIMES.index(m['time'])
        previous = last.get(kind)
        if (-m['deviationPct'] if kind == 'bottom' else m['deviationPct'])+eps < (0.8 if kind == 'bottom' else 1.5):
            continue
        if m['volumeRatio'] is None or m['volumeRatio']+eps < 1:
            continue
        ticks = 1 if kind == 'bottom' or not count['top'] else 2
        if abs(m['price']-m['candidatePrice'])+eps < max(.01*ticks, m['candidatePrice']*.003):
            continue
        if previous and i-TIMES.index(previous['time']) < 30:
            continue
        if kind == 'top' and previous and m['candidatePrice']-previous['candidatePrice']+eps < max(.02, previous['candidatePrice']*.008):
            continue
        volumes = [by.get(t, {}).get('volume') for t in TIMES[i-4:i+1]]
        if len(volumes) != 5 or any(v is None or not math.isfinite(float(v)) or float(v) <= 0 for v in volumes):
            continue
        mean = sum(float(v) for v in volumes)/5
        current = by[m['time']]
        if 1000/mean > .01+1e-12 or 1000/float(current['volume']) > .01+1e-12:
            continue
        price, target = float(current['close']), float(current['average'])
        net = cost_space(price, target) if kind == 'bottom' else cost_space(target, price)
        space = net/(price*1000)*100
        if space+eps < .2:
            continue
        accepted = dict(m, key=f"quality-first-Q|{kind}|{m['candidateTime']}|{m['time']}",
                        quality=dict(meanShares=mean, currentShares=current['volume'], knownVwap=target, knownSpaceNetPct=space))
        result.append(accepted)
        last[kind], count[kind] = accepted, count[kind]+1
    return result
