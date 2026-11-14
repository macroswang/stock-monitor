"""Read-only E2 close confirmations. Never imported by alert/trading engines."""
from bisect import bisect_right
from datetime import date, timedelta
from functools import lru_cache
import hashlib
import json

from .ma250_pullback import analyze as formal_analyze, prepare, rule_spec


def research_spec():
    spec = dict(version='ma250-e2-research-v1', research_only=True,
                source_rule_id=rule_spec()['rule_id'], confirmation_sessions=3,
                minimum_annual_margin=0.01, close_above='source-day high and MA5',
                cancel_below='source stop', market='same-day CSI300 above MA250',
                historical_sessions='verified calendar; otherwise recorded CSI300 sessions',
                timestamp='completed confirmation close; no future entry requirement')
    spec['rule_id'] = spec['version'] + '-' + hashlib.sha256(
        json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    return spec


@lru_cache(maxsize=2048)
def confirmation_window(source_day, end):
    """At most three known sessions after the source; unknown years never bridge."""
    from .paper_session import calendar
    if calendar(int(source_day[:4])) is None:
        return (), False
    day = date.fromisoformat(source_day) + timedelta(days=1)
    days = []
    while day.isoformat() <= end and len(days) < 3:
        closed = calendar(day.year)
        if closed is None:
            return tuple(days), False
        stamp = day.isoformat()
        if day.weekday() < 5 and not any(a <= stamp <= b for a, b in closed):
            days.append(stamp)
        day += timedelta(days=1)
    return tuple(days), True


def confirmation_for(rows, features, source_index, source, market, sessions=None, observed_sessions=None):
    """Causal close decision shared by display and replay, before execution."""
    i = source_index
    verified = True
    from .paper_session import calendar
    if calendar(int(rows[i]['date'][:4])) is not None:
        allowed, verified = confirmation_window(rows[i]['date'], rows[-1]['date'])
    elif sessions is not None:
        sessions = sorted(set(sessions))
        if rows[i]['date'] not in sessions:
            return dict(status='unverified_calendar', index=None, date=None, calendar_verified=False)
        at = bisect_right(sessions, rows[i]['date'])
        allowed = sessions[at:at+3]
    else:
        if rows[i]['date'] not in market:
            return dict(status='unverified_calendar', index=None, date=None, calendar_verified=False)
        observed = observed_sessions if observed_sessions is not None else sorted(market)
        at = bisect_right(observed, rows[i]['date'])
        allowed = observed[at:at+3]
    for j in range(i+1, min(len(rows), i+4)):
        row = rows[j]
        if row['date'] not in allowed:
            break
        if row['low'] < source['stop']:
            return dict(status='cancelled_structure', index=None, date=None, calendar_verified=True)
        if (row['close'] > rows[i]['high'] and features['ma250'][j] is not None
                and row['close'] >= features['ma250'][j]*1.01
                and row['close'] > features['ma5'][j] and market.get(row['date']) is True):
            return dict(status='confirmed', index=j, date=row['date'],
                        confirmation_day=allowed.index(row['date'])+1, calendar_verified=True)
    pending = len(allowed)<3 or rows[-1]['date']<allowed[-1]
    return dict(status='pending_confirmation' if pending else 'confirmation_not_met',
                index=None, date=None, calendar_verified=verified)


def analyze(bars, market=None, sessions=None, formal=None):
    """Keep immutable confirmation dates; future bars cannot revoke a mark.

    This is the confirmation component of frozen research policy E2. Its
    hypothetical next-open execution remains separate from this display mark.
    """
    bars = list(bars)
    formal = formal if formal is not None else formal_analyze(bars, market)
    result = dict(signals=[], **research_spec(), error=formal.get('error'), unverified_sources=0)
    if result['error']:
        return result
    sources = [s for s in formal['signals'] if s['strong']]
    if not sources:
        return result
    f = prepare(bars)
    rows = f['rows']
    market = market or {}
    observed_sessions = sorted(market)
    positions = {b['date']:i for i,b in enumerate(rows)}
    for source in sources:
        i = positions.get(source['date'])
        if i is None:
            result['error'] = '源强信号对应日线缺失，E2待核实'
            continue
        decision = confirmation_for(rows, f, i, source, market, sessions, observed_sessions)
        result['unverified_sources'] += int(not decision['calendar_verified'])
        if decision['index'] is not None:
            j = decision['index'];row = rows[j]
            result['signals'].append(dict(
                key=source['date']+'|'+row['date']+'|'+source['episode_id'],
                date=row['date'], source_date=source['date'], episode_id=source['episode_id'],
                close=row['close'], ma250=f['ma250'][j], ma5=f['ma5'][j],
                distance_pct=(row['close']/f['ma250'][j]-1)*100,
                source_high=rows[i]['high'], confirmation_day=decision['confirmation_day'],
                stop=source['stop'], touch_date=source['touch_date'], touch_low=source['touch_low'],
                pullback_pct=source['pullback_pct'], atr20_pct=f['atr20'][j]/row['close']*100,
                market_above=True, research_only=True, kind='e2',
                rule_id=result['rule_id'], source_rule_id=source['rule_id']))
    return result
