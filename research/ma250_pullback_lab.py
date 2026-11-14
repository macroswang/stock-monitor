"""Feature and outcome builder for the large-sample MA250 pullback study.

This module is research-only. It builds a loose superset of reclaim candidates
with causal features, then lets a caller apply variant filters. Outcomes use a
next-session open entry, path-based target/stop and explicit costs, so the
reported win rate is a defined trade, not a close-to-close proxy.
"""
from datetime import date

PERIOD = 250
COST_PCT = 0.30          # 0.10% fees + 0.10% buy slippage + 0.10% sell slippage
STOP_PCT = 5.0           # fixed 5% stop for the path win-rate definition
TARGET_PCT = 10.0        # fixed 10% target
PATH_DAYS = 60
PATH_POLICIES = {'5_3': (5, 3), '8_4': (8, 4), '10_5': (10, 5), '15_8': (15, 8)}


def sma(values, period):
    out, total = [], 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        out.append(total / period if index + 1 >= period else None)
    return out


def mean(values):
    return sum(values) / len(values) if values else None


def ema(values, period):
    out, alpha, previous = [], 2 / (period + 1), None
    for value in values:
        previous = value if previous is None else alpha * value + (1 - alpha) * previous
        out.append(previous)
    return out


def clean_bars(rows):
    from core.ma250_pullback import _rows
    return _rows(rows)  # Reject the whole defective series; never splice bad rows.


def index_features(index_bars):
    """Date -> regime facts; missing index history never becomes a pass."""
    bars = clean_bars(index_bars)
    closes = [bar['close'] for bar in bars]
    line, short = sma(closes, PERIOD), sma(closes, 20)
    out = {}
    for index, bar in enumerate(bars):
        out[bar['date']] = dict(
            close=bar['close'], ma250=line[index], ma20=short[index],
            above_ma250=None if line[index] is None else bar['close'] > line[index],
            above_ma20=None if short[index] is None else bar['close'] > short[index],
            ret20=None if index < 20 else (closes[index] / closes[index - 20] - 1) * 100)
    return out


def feature_arrays(bars):
    closes = [bar['close'] for bar in bars]
    volumes = [bar['volume'] for bar in bars]
    return dict(closes=closes, ma250=sma(closes, PERIOD), ma5=sma(closes, 5), ma20=sma(closes, 20),
                vol20=sma([value for value in volumes], 20))


def window_quality(bars):
    """Span and largest adjacent-date gap for every 250-bar window."""
    from collections import deque
    dates = [date.fromisoformat(bar['date']) for bar in bars]
    gaps = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
    span, max_gap = [None] * len(bars), [None] * len(bars)
    queue = deque()
    for index, gap in enumerate(gaps):
        while queue and gaps[queue[-1]] <= gap:
            queue.pop()
        queue.append(index)
        while queue[0] < index - 248:
            queue.popleft()
        if index >= 248:
            max_gap[index + 1] = gaps[queue[0]]
    for index in range(249, len(bars)):
        span[index] = (dates[index] - dates[index - 249]).days
    return dict(span=span, max_gap=max_gap)


def suspicious_break(bars, start, end):
    """Unadjusted corporate actions show up as jumps far beyond the price limit."""
    for index in range(max(1, start), min(len(bars), end)):
        previous, bar = bars[index - 1]['close'], bars[index]
        if abs(bar['close'] / previous - 1) > 0.22:
            return True
        if abs(bar['open'] / previous - 1) > 0.22:
            return True
    return False


def candidates(code,bars,index_map):
    """Research adds outcomes to exact client events; it never redetects signals."""
    from core.ma250_pullback import analyze,prepare
    from research.ma250_execution import forward_outcomes,path_outcomes,jump_in
    market={d:r['above_ma250'] for d,r in index_map.items()};sessions=sorted(index_map)
    report=analyze(bars,market=market)
    if report['error']:raise ValueError(report['error'])
    feats=prepare(bars);index_by_date={b['date']:i for i,b in enumerate(bars)};out=[]
    for signal in report['signals']:
        i=index_by_date[signal['date']];touch=index_by_date[signal['touch_date']]
        outcomes=forward_outcomes(code,bars,i,sessions);entry=outcomes['entry'];path=path_outcomes(code,bars,i,sessions)
        market_facts=index_map.get(signal['date'],{});close=signal['close']
        volume_base=mean([r.get('volume') for r in bars[max(0,i-20):i] if r.get('volume') is not None])
        touch_base=mean([r.get('volume') for r in bars[max(0,touch-20):touch] if r.get('volume') is not None])
        stock20=(close/bars[i-20]['close']-1)*100 if i>=20 else None
        window=bars[i+1:i+61];exit20=outcomes['exits']['20']
        benchmark=None
        if entry['date'] in index_map and exit20['date'] in index_map:
            benchmark=(index_map[exit20['date']]['close']/index_map[entry['date']]['close']-1)*100
        out.append(dict(signal,code=code,index=i,touch=touch,kind='pullback',
            slope60_pct=(signal['ma250']/feats['ma250'][i-60]-1)*100,
            slope120_pct=(signal['ma250']/feats['ma250'][i-120]-1)*100 if i>=369 else None,
            strength_pct=feats['prior_high'][i]/signal['ma250']*100-100,
            depth_pct=signal['touch_depth_pct'],reclaim_pct=signal['distance_pct'],touch_lag=i-touch,
            entry=entry['price'],entry_date=entry['date'],execution_status=entry['status'],
            gap_pct=(entry['price']/close-1)*100 if entry['price'] else None,
            unexecutable=entry['status']=='entry_unavailable',suspicious=False,
            corporate_action_flag=jump_in(bars,i+1,exit20['index']) if exit20['index'] is not None else None,
            vol_touch_ratio=bars[touch].get('volume')/touch_base if touch_base and bars[touch].get('volume') is not None else None,
            vol_signal_ratio=bars[i].get('volume')/volume_base if volume_base and bars[i].get('volume') is not None else None,
            vol_pullback_ratio=None,range_pos=(close-bars[i]['low'])/(bars[i]['high']-bars[i]['low']) if bars[i]['high']>bars[i]['low'] else None,
            hold2=bool(i and feats['ma250'][i-1] and bars[i-1]['close']>=feats['ma250'][i-1]*1.01),
            engulf=close>max((b['high'] for b in bars[touch:i]),default=bars[i-1]['high']),
            index_above_ma250=signal['market_above'],index_above_ma20=market_facts.get('above_ma20'),
            index_ret20=market_facts.get('ret20'),relative20=stock20-market_facts['ret20'] if stock20 is not None and market_facts.get('ret20') is not None else None,
            forward=outcomes['forward'],exits=outcomes['exits'],label_end=exit20['date'],
            mfe60=(max((b['high'] for b in window),default=close)/entry['price']-1)*100 if entry['price'] else None,
            mae60=(min((b['low'] for b in window),default=close)/entry['price']-1)*100 if entry['price'] else None,
            path_outcome=path['outcome'],path_wins=path['policies'],path_net=path['net'],
            path_label_end=path['label_end'],path_policy_label_end=path['policy_label_end'],
            close_ret20=outcomes['forward']['20'],excess20=outcomes['forward']['20']-benchmark if benchmark is not None else None))
    return out


def trend_baseline(code,bars,index_map):
    from core.ma250_pullback import prepare
    from research.ma250_execution import forward_outcomes
    f=prepare(bars);out=[];sessions=sorted(index_map)
    for i in range(309,len(bars)):
        if not f['valid'][i] or not f['valid'][i-60] or bars[i]['close']<=f['ma250'][i] or f['ma250'][i]<f['ma250'][i-60]*1.005:continue
        r=forward_outcomes(code,bars,i,sessions)
        out.append(dict(date=bars[i]['date'],code=code,net20=r['forward']['20'],
                        execution_status=r['entry']['status'],label_end=r['exits']['20']['date'],suspicious=False,excess20=None))
    return out
