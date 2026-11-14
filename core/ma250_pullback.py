"""Causal daily MA250 pullback-and-hold marker; alerts only, never an order.

The rule answers one question on a completed daily bar: after a real pullback
to the rising annual line, did the close reclaim the line with short-term
strength? Every input is at or before the signal bar, so a signal date never
moves when later bars arrive. Unadjusted prices are used, the same basis as the
daily chart; corporate actions can distort the annual line.
"""
import hashlib, json, math
from datetime import date

PERIOD = 250
VERSION = 'ma250-pullback-v3'
QUALITY = dict(maximum_window_days=400, maximum_gap_days=45, maximum_jump_pct=22.0)
# The strong tier is a post-hoc shape filter, not a validated probability of profit.
STRONG = dict(maximum_touch_depth_pct=0.0, maximum_reclaim_pct=7.0,
              prior_low_days=120, prior_gap_days=20, require_positive_macd=False,
              macd_fast=12, macd_slow=26, macd_signal=9)
PARAMETERS = dict(
    period=250,
    slope_days=60,
    minimum_slope_pct=0.5,
    strength_days=30,
    minimum_prior_above_pct=10.0,
    touch_days=10,
    touch_tolerance_pct=1.5,
    maximum_break_pct=15.0,
    pullback_days=60,
    minimum_pullback_pct=8.0,
    maximum_pullback_pct=35.0,
    reclaim_pct=1.0,
    maximum_extension_pct=15.0,
    cooldown_days=15,
)


def _number(value):
    if isinstance(value, bool):
        raise ValueError('布尔值不是价格')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('价格必须是有限数值')
    return number


def _rows(bars):
    """Validate one continuous daily series; any defect invalidates the input."""
    rows = []
    previous = None
    for bar in bars:
        day = bar.get('date') or bar.get('day')
        stamp = date.fromisoformat(day).isoformat()
        if previous is not None and stamp <= previous:
            raise ValueError('日线日期必须严格递增且不重复')
        open_, close = _number(bar['open']), _number(bar['close'])
        high, low = _number(bar['high']), _number(bar['low'])
        if min(open_, close, high, low) <= 0 or high < max(open_, close) or low > min(open_, close):
            raise ValueError('日线开高低收无效')
        volume = None if bar.get('volume') is None else _number(bar['volume'])
        if volume is not None and volume < 0:
            raise ValueError('成交量不能为负')
        rows.append(dict(date=stamp, open=open_, close=close, high=high, low=low, volume=volume))
        previous = stamp
    return rows


def _quality(dates, rows):
    """Span, largest date gap and any unadjusted corporate-action jump."""
    from collections import deque
    count = len(dates)
    gaps = [(dates[index] - dates[index - 1]).days for index in range(1, count)]
    jump = [0] * count
    for index in range(1, count):
        previous = rows[index - 1]['close']
        if abs(rows[index]['close'] / previous - 1) > QUALITY['maximum_jump_pct']/100 or abs(rows[index]['open'] / previous - 1) > QUALITY['maximum_jump_pct']/100:
            jump[index] = 1
    prefix = [0] * (count + 1)
    for index, flag in enumerate(jump):
        prefix[index + 1] = prefix[index] + flag
    jumped = [prefix[index + 1] - prefix[max(0, index - PERIOD + 1)] > 0 for index in range(count)]
    span, widest = [None] * count, [None] * count
    queue = deque()
    for index, gap in enumerate(gaps):
        while queue and gaps[queue[-1]] <= gap:
            queue.pop()
        queue.append(index)
        while queue[0] < index - 248:
            queue.popleft()
        if index >= 248:
            widest[index + 1] = gaps[queue[0]]
    for index in range(PERIOD - 1, count):
        span[index] = (dates[index] - dates[index - PERIOD + 1]).days
    return span, widest, jumped


def _ema(values, period):
    out, alpha, previous = [], 2 / (period + 1), None
    for value in values:
        previous = value if previous is None else alpha * value + (1 - alpha) * previous
        out.append(previous)
    return out


def _series(values, period):
    out, total = [], 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        out.append(total / period if index + 1 >= period else None)
    return out


def _latest(rows, closes):
    if not rows:
        return None
    last = len(rows) - 1
    line = _series(closes, PERIOD)[last]
    if line is None:
        return dict(date=rows[last]['date'], close=rows[last]['close'], ma250=None,
                    distance_pct=None, status='insufficient', bars=len(rows))
    return dict(date=rows[last]['date'], close=rows[last]['close'], ma250=line,
                distance_pct=(rows[last]['close'] / line - 1) * 100,
                status='above' if rows[last]['close'] >= line else 'below', bars=len(rows))


def rule_spec():
    """The exact frozen rule travels with journals and every research report."""
    spec = dict(version=VERSION, parameters=dict(PARAMETERS), strong=dict(STRONG),
                breakout=dict(cooldown_days=20, slope_days=60, minimum_volume_ratio=1.0),
                quality=dict(QUALITY),
                structure='peak-before-touch; full-episode-low-and-depth; one-reclaim-and-one-upgrade',
                price_basis='caller-provided consistent OHLC; client unadjusted')
    spec['rule_id'] = VERSION + '-' + hashlib.sha256(
        json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    return spec


def prepare(bars):
    """Linear-time shared, validated features. Provisional candles are not evidence."""
    from collections import deque
    bars=list(bars)
    while bars and bars[-1].get('provisional'):bars.pop()
    if any(bar.get('provisional') for bar in bars):raise ValueError('历史日线含未完成数据，不能跨缺口拼接')
    rows = _rows(bars)
    closes = [row['close'] for row in rows]
    line, short = _series(closes, PERIOD), _series(closes, 5)
    fast, slow = _ema(closes, STRONG['macd_fast']), _ema(closes, STRONG['macd_slow'])
    dif = [a - b for a, b in zip(fast, slow)]
    hist = [2 * (a - b) for a, b in zip(dif, _ema(dif, STRONG['macd_signal']))]
    true = [max(row['high'] - row['low'],
                abs(row['high'] - closes[i - 1]), abs(row['low'] - closes[i - 1]))
            if i else row['high'] - row['low'] for i, row in enumerate(rows)]
    atr = _series(true, 20)
    span, gap, jumped = _quality([date.fromisoformat(row['date']) for row in rows], rows)
    valid = [bool(i >= 249 and span[i] <= QUALITY['maximum_window_days'] and gap[i] <= QUALITY['maximum_gap_days'] and not jumped[i])
             for i in range(len(rows))]
    # Previous 30-bar high, excluding today's intraday high; no ambiguous OHLC order.
    prior_high, queue = [], deque()
    for i, row in enumerate(rows):
        while queue and queue[0] < i - PARAMETERS['strength_days']:
            queue.popleft()
        prior_high.append(rows[queue[0]]['high'] if queue else None)
        while queue and rows[queue[-1]]['high'] <= row['high']:
            queue.pop()
        queue.append(i)
    return dict(rows=rows, closes=closes, ma250=line, ma5=short, macd_hist=hist,
                atr20=atr, valid=valid, prior_high=prior_high)


def analyze(bars, market=None):
    """One causal detector for the client, scanner, journals and all research.

    The first completed reclaim is an observation. The same episode may upgrade
    once when all strong conditions become known; ordinary cooldown cannot hide
    that upgrade. Later candles never rewrite earlier observations.
    """
    spec = rule_spec()
    try:
        feats = prepare(bars)
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return dict(signals=[], breakouts=[], latest=None, **spec,
                    error=str(error) if isinstance(error, ValueError) else '日线数据无效')
    rows, closes, line = feats['rows'], feats['closes'], feats['ma250']
    p, result, episode, last_normal = PARAMETERS, [], None, -10 ** 9
    quality_rejected = 0
    for i, row in enumerate(rows):
        if i < PERIOD-1+p['slope_days']:
            continue
        if not feats['valid'][i] or not feats['valid'][i - p['slope_days']]:
            episode = None
            quality_rejected += 1
            continue
        ma = line[i]
        near = row['low'] <= ma * (1 + p['touch_tolerance_pct'] / 100)
        if episode and (i - episode['last_touch'] >= p['touch_days'] or
                        (i > episode['first_touch'] and closes[i - 1] > episode['peak'])):
            episode = None
        if episode is None:
            if not near or ma < line[i - p['slope_days']] * (1 + p['minimum_slope_pct'] / 100) or feats['prior_high'][i] < ma * (1 + p['minimum_prior_above_pct'] / 100):
                continue
            peak_i = max(range(max(0, i - p['pullback_days']), i), key=lambda j: rows[j]['high'])
            low_i = min(range(peak_i + 1, i + 1), key=lambda j: rows[j]['low'])
            episode = dict(peak=rows[peak_i]['high'], peak_i=peak_i, low_i=low_i,
                           first_touch=i, last_touch=i, emitted=False, strong_sent=False,
                           max_depth=max((line[j]-rows[j]['low'])/line[j]*100 for j in range(peak_i+1,i+1)))
        else:
            if row['low'] < rows[episode['low_i']]['low']:
                episode['low_i'] = i
            if near:
                episode['last_touch'] = i
            episode['max_depth']=max(episode['max_depth'],(ma-row['low'])/ma*100)
        touch = episode['low_i']
        low, peak = rows[touch]['low'], episode['peak']
        depth = (line[touch] - low) / line[touch] * 100
        pullback = (peak - low) / peak * 100
        # A deep earlier low is retained for the entire episode, never overwritten.
        if episode['max_depth'] > p['maximum_break_pct'] or not p['minimum_pullback_pct'] <= pullback <= p['maximum_pullback_pct']:
            continue
        if ma < line[i - p['slope_days']] * (1 + p['minimum_slope_pct'] / 100) or feats['prior_high'][i] < ma * (1 + p['minimum_prior_above_pct'] / 100):
            continue
        close = closes[i]
        reclaim = (close / ma - 1) * 100
        if not p['reclaim_pct'] <= reclaim <= p['maximum_extension_pct'] or close <= feats['ma5'][i] or close <= closes[i - 1] or close < row['open']:
            continue
        prior = min((r['low'] for r in rows[max(0, touch - STRONG['prior_low_days']):max(0, touch - STRONG['prior_gap_days'])]), default=None)
        higher_low = prior is not None and low > prior
        market_above = market.get(row['date']) if isinstance(market, dict) else None
        reasons = []
        if market_above is not True: reasons.append('market')
        if episode['max_depth'] > STRONG['maximum_touch_depth_pct']: reasons.append('broke-line')
        if not higher_low: reasons.append('no-higher-low')
        if reclaim > STRONG['maximum_reclaim_pct']: reasons.append('extended')
        if STRONG['require_positive_macd'] and feats['macd_hist'][i] <= 0: reasons.append('macd')
        strong, upgrade = not reasons, episode['emitted']
        if upgrade:
            if not strong or episode['strong_sent']:
                continue
        elif i - last_normal < p['cooldown_days']:
            continue
        else:
            last_normal = i
        episode['emitted'] = True
        episode['strong_sent'] |= strong
        episode_id = rows[episode['peak_i']]['date'] + '|' + rows[episode['first_touch']]['date']
        result.append(dict(key=row['date'], date=row['date'], close=close, ma250=ma,
            ma5=feats['ma5'][i], distance_pct=reclaim, touch_date=rows[touch]['date'],
            touch_low=low, touch_depth_pct=depth, pullback_pct=pullback, stop=low * .99,
            peak_date=rows[episode['peak_i']]['date'], peak_price=peak,
            first_touch_date=rows[episode['first_touch']]['date'], episode_id=episode_id,
            maximum_touch_depth_pct=episode['max_depth'],
            upgrade=upgrade, setup_type='support' if episode['max_depth'] <= 0 else 'undercut_reclaim',
            higher_low=higher_low, prior_low=prior, market_above=market_above,
            macd_hist=feats['macd_hist'][i], atr20_pct=feats['atr20'][i] / close * 100,
            strong=strong, strong_reasons=reasons, version=VERSION, rule_id=spec['rule_id']))
    breakouts, last_breakout, below = [], -999, 0
    for i, row in enumerate(rows):
        if i < 249:
            continue
        previous_below = below
        below = below + 1 if closes[i] < line[i] else 0
        if i < 250 or not feats['valid'][i]:
            continue
        if not (closes[i] > line[i] and closes[i - 1] <= line[i - 1]) or i - last_breakout < 20:
            continue
        last_breakout = i
        slope = (line[i] / line[i - 60] - 1) * 100 if i >= 309 and feats['valid'][i - 60] else None
        prior_volumes = [r['volume'] for r in rows[i - 5:i]]
        base = sum(prior_volumes) / 5 if all(v is not None for v in prior_volumes) else None
        ratio = row['volume'] / base if base and row['volume'] is not None else None
        quality = bool(slope is not None and slope >= 0 and ratio is not None and ratio >= 1)
        breakouts.append(dict(date=row['date'], close=closes[i], ma250=line[i],
            margin_pct=(closes[i] / line[i] - 1) * 100, slope60_pct=slope,
            volume_ratio=ratio, days_below=previous_below,
            market_above=market.get(row['date']) if isinstance(market, dict) else None,
            quality=quality, kind='breakout', version=VERSION, rule_id=spec['rule_id']))
    latest = _latest(rows, closes)
    if latest:
        warmup=PERIOD+p['slope_days']
        ready=bool(len(rows)>=warmup and feats['valid'][-1] and feats['valid'][-p['slope_days']-1])
        latest.update(ready=ready,quality_ok=bool(rows and feats['valid'][-1]),
                      readiness='insufficient' if len(rows)<warmup else 'ready' if ready else 'quality_blocked')
    return dict(signals=result, breakouts=breakouts, latest=latest, **spec,
                quality_rejected=quality_rejected, error=None)


