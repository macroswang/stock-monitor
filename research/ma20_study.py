"""Frozen E versus E + prior-session close >= MA20. Pure functions only."""
import json
from decimal import Decimal as D, ROUND_HALF_UP
from core.buy_supplement import evaluate, PARAMS, SUPPLEMENT_PARAMS, RESEARCH_PARAMS
from core.buy_research import outcomes
from scripts.evaluate_buy_net_profit import net_return, metrics

VERSION='E_prior_close_MA20_v1'
CONFIG=dict(version=VERSION,variant='E',ma_window=20,roundtrip_fee_pct=.10,
            slip_per_side_pct=.10,entry='next_complete_minute_close',exit='next_session_close',
            minimum_new_trading_dates=30,minimum_completed_per_arm=100,
            base=PARAMS,supplement=SUPPLEMENT_PARAMS,research=RESEARCH_PARAMS)

def parse_sina(text):
    """Sina scale=240 is daily OHLC, volume shares, no adjustment requested."""
    text=text.strip()
    if text.startswith('['):rows=json.loads(text)
    elif '=(' in text:rows=json.loads(text.split('=(',1)[1].rsplit(');',1)[0])
    else:raise ValueError('Unexpected Sina daily response')
    if not isinstance(rows,list) or not rows:raise ValueError('Empty daily response')
    result={};previous=''
    from datetime import date
    for raw in rows:
        day=raw['day'][:10];date.fromisoformat(day)
        if day<=previous:raise ValueError('Daily dates duplicate or unordered')
        previous=day
        vals={k:D(str(raw[k])) for k in ('open','close','high','low','volume')}
        if not all(x.is_finite() for x in vals.values()):raise ValueError('Nonfinite daily data')
        if not 0<vals['low']<=min(vals['open'],vals['close'])<=max(vals['open'],vals['close'])<=vals['high']:raise ValueError('Invalid daily OHLC')
        if vals['volume']<0 or vals['volume']!=int(vals['volume']):raise ValueError('Invalid shares')
        result[day]=dict(date=day,**{k:str(v) for k,v in vals.items()},source='sina',
                        adjustment='none',volume_unit='shares')
    return result

def finalized(rows,asof):
    today=asof.date().isoformat()
    return {d:r for d,r in rows.items() if d<today or d==today and asof.strftime('%H:%M')>='15:15'}

def audit_daily(rows):
    """Convert shares to the rounded whole-hand precision observed in Tencent daily.

    Original Sina shares are retained. The frozen minute audit still uses exact
    equality on comparable whole-hand values; MA20 uses prices, never volume.
    """
    return {d:dict(r,raw_volume=str((D(r['volume'])/100).quantize(D(1),rounding=ROUND_HALF_UP))) for d,r in rows.items()}

def crosscheck_daily(sina,reference):
    checked=[];errors=[]
    for day in sorted(set(sina)&set(reference)):
        s,t=sina[day],reference[day]
        mismatched=[k for k in ('open','close','high','low') if D(s[k])!=D(str(t[k]))]
        delta=D(s['volume'])-D(str(t['raw_volume']))*100
        if mismatched or abs(delta)>50:errors.append(dict(date=day,price_fields=mismatched,shares_delta=str(delta)))
        checked.append(dict(date=day,shares_delta=str(delta),prices_equal=not mismatched))
    return dict(checked=checked,errors=errors)

def ma20_gate(day,daily,calendar):
    before=sorted(d for d in set(calendar) if d<day)
    if not before:return dict(passed=None,reason='missing_previous_session',previous_session=None)
    previous=before[-1]
    if previous not in daily:return dict(passed=None,reason='missing_previous_close',previous_session=previous)
    prefix=sorted(d for d in daily if d<=previous)
    if len(prefix)<20:return dict(passed=None,reason='fewer_than_20_bars',previous_session=previous,bars=len(prefix))
    dates=prefix[-20:];values=[D(str(daily[d]['close'])) for d in dates]
    if any(not x.is_finite() or x<=0 for x in values):raise ValueError('Invalid MA input')
    mean=sum(values)/20;close=values[-1]
    return dict(passed=close>=mean,reason='ready',previous_session=previous,
                prior_close=str(close),ma20=str(mean),dates=dates,margin_pct=str((close/mean-1)*100))

def score_day(code,name,day,minute,daily,calendar,next_minute=None):
    gate=ma20_gate(day,daily,calendar)
    next_days=sorted(d for d in calendar if d>day)
    nxt=next_days[0] if next_days else None
    nd=daily.get(nxt) if nxt else None
    result=evaluate(minute,'E',as_of='15:00')
    if result['error']:raise ValueError(result['error'])
    events=[]
    for event in result['signals']:
        outcome=outcomes(event,minute,next_minute,nd,None)
        entry=outcome['entry_price'];exit_price=float(nd['close']) if nd else None
        status='pending_next_session' if nxt is None else 'missing_next_daily' if nd is None else 'missing_entry' if entry is None else 'completed_price_proxy'
        scenarios={f'{fee:.2f}/{slip:.2f}':net_return(entry,exit_price,fee,slip)
                   for fee in (.10,.20) for slip in (.05,.10,.20)}
        events.append(dict(code=code,name=name,date=day,time=event['time'],identity=day+'|'+code+'|'+event['key'],
            branch=event['branch'],entry_time=outcome['entry_time'],entry_price=entry,next_date=nxt,next_close=exit_price,
            net_pct=scenarios['0.10/0.10'],scenarios=scenarios,status=status,execution=outcome['execution'],
            ma20_passed=gate['passed'],gate=gate,adverse_pct=outcome['observed_adverse_pct'],
            adverse_complete=outcome['adverse_complete'],evidence=event['evidence']))
    # This is a whole-day prior-session gate, not a new intraday state machine.
    # Passing days retain exactly the original E timing, cooldown and structure IDs.
    return dict(gate=gate,baseline=events,filtered=events if gate['passed'] is True else [],
                unknown=events if gate['passed'] is None else [],cooldown_suppressed=len(result['cooldown_suppressed']))

def summarize(events):
    completed=[e for e in events if e['net_pct'] is not None]
    summary=metrics([e['net_pct'] for e in completed])
    risks=[e['adverse_pct'] for e in completed if e['adverse_complete'] and e['adverse_pct'] is not None]
    summary.update(signals=len(events),pending=sum(e['status']=='pending_next_session' for e in events),
        missing_next_daily=sum(e['status']=='missing_next_daily' for e in events),
        unverified_execution=sum(e['execution']!='close_proxy' for e in completed),
        risk_complete_samples=len(risks),worst_sampled_adverse_pct=min(risks) if risks else None,
        sensitivity={k:metrics([e['scenarios'][k] for e in completed]) for k in ('0.10/0.05','0.10/0.10','0.10/0.20','0.20/0.05','0.20/0.10','0.20/0.20')})
    return summary

def compare(events):
    known=[e for e in events if e['ma20_passed'] is not None]
    kept=[e for e in events if e['ma20_passed'] is True]
    rejected=[e for e in events if e['ma20_passed'] is False]
    unknown=[e for e in events if e['ma20_passed'] is None]
    missed_winners=[e for e in rejected if e['net_pct'] is not None and e['net_pct']>0]
    avoided_losers=[e for e in rejected if e['net_pct'] is not None and e['net_pct']<0]
    known_winners=[e for e in known if e['net_pct'] is not None and e['net_pct']>0]
    return dict(E_all=summarize(events),E_comparable=summarize(known),E_MA20=summarize(kept),
        rejected=summarize(rejected),ma20_unknown=summarize(unknown),missed_winners=missed_winners,
        avoided_losers=avoided_losers,
        missed_winner_fraction=len(missed_winners)/len(known_winners) if known_winners else None,
        known_gate_signal_retention=len(kept)/len(known) if known else None)
