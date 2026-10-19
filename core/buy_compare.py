"""Isolated four-arm research engine; no live integration or notification side effects."""
from decimal import Decimal,InvalidOperation

VERSION='strong_pullback_v1'
PARAMS=dict(rise_minutes=5,prior_volume_minutes=10,rise_pct=0.8,rise_volume_ratio=1.2,
 above_vwap_count=4,pullback_min=2,pullback_max=8,depth_min_pct=0.3,depth_max_pct=1.2,
 pullback_volume_ratio=0.65,near_vwap_pct=0.4,support_ratio=0.997,confirm_volume_ratio=1.2,
 confirm_tick=0.01,max_premium_pct=1.5,cooldown_minutes=10)

def number(v):
 try:
  d=Decimal(str(v));return float(d) if d.is_finite() else None
 except (InvalidOperation,ValueError,TypeError):return None

def labels(start,end):return [f'{m//60:02}:{m%60:02}' for m in range(start,end+1)]
SESSIONS=[labels(571,690),labels(781,896)]
TIMELINE=SESSIONS[0]+labels(781,900)

def valid(b):
 return bool(b and b.get('complete') is True and number(b.get('close')) is not None and number(b.get('close'))>0
  and number(b.get('volume')) is not None and number(b.get('volume'))>=0
  and number(b.get('average')) is not None and number(b.get('average'))>0)

VARIANTS = ('V1', 'A', 'B', 'AB')
RESEARCH_PARAMS = dict(vwap_relative_tolerance=.00005, vwap_absolute_cap=.005, low_price_max=5, reclaim_tick=.01)

def evaluate(data, variant='V1', *, as_of=None, anchor=None):
 # as_of is a market-date-local HH:MM completed-bar cutoff, not wall clock.
 if variant not in VARIANTS:raise ValueError('Unknown research variant')
 if as_of is None:raise ValueError('Explicit completed-minute cutoff required')
 bars=data.get('bars',[]);times=[b.get('time') for b in bars]
 if len(times)!=len(set(times)) or times!=sorted(times):
  return dict(candidates=[],baseline=[],signals=[],error='分钟重复或顺序异常，未回放')
 by={b['time']:b for b in bars};candidates=[];baseline=[];signals=[];cooldown_suppressed=[]
 for session,end in zip(SESSIONS,['11:20','14:30']):
  rows=[];candidate=None;cooldown=-1
  def expire(reason):
   nonlocal candidate
   if candidate:
    candidate.update(status='expired',reason=reason);candidate=None
  for i,t in enumerate(session):
   if t>as_of:
    if candidate:
     if as_of>=end:expire('超过确认时间范围')
     else:candidate.update(status='observing',reason='待观察：后续完整分钟尚未到达')
    break
   if t>end:
    expire('超过确认时间范围');break
   b=by.get(t)
   if not valid(b):
    if candidate:
     candidate.update(status='data_gap',reason='数据不足：已到达分钟缺失、未完整或均价不可用');candidate=None
    rows=[];continue
   b=dict(b,close=number(b['close']),volume=number(b['volume']),average=number(b['average']))
   rows.append(b)
   eligible=t>=('09:45' if end=='11:20' else '13:15')
   if not eligible:continue
   def seed():
    if len(rows)<15:return None
    rise=rows[-5:];prior=rows[-15:-5];vol=sum(x['volume'] for x in rise)/5;base=sum(x['volume'] for x in prior)/10
    if base<=0 or vol<=0:return None
    gain=(b['close']/rows[-6]['close']-1)*100
    if gain+1e-9<0.8 or sum(x['close']>x['average'] for x in rise)<4 or vol+1e-9<1.2*base:return None
    if b['close']<max(x['close'] for x in rise):return None
    return dict(peak=b['close'],rise_volume=vol,rise_pct=gain,seed_time=t)
   if candidate:
    pb=candidate['pullback'];h=candidate['peak'];depth=(h-b['close'])/h*100
    if b['close']<b['average']*.997-1e-9 or depth>1.2+1e-9:
     expire('回踩跌破均价支撑' if b['close']<b['average']*.997-1e-9 else '回踩深度超过1.2%');continue
    if pb:
     avg=sum(x['volume'] for x in pb)/len(pb);d=(h-min(x['close'] for x in pb))/h*100
     near=any(abs(x['close']/x['average']-1)*100<=.4+1e-9 for x in pb)
     checks=dict(length=2<=len(pb)<=8,depth=.3-1e-9<=d<=1.2+1e-9,
      shrinking=avg<=candidate['rise_volume']*.65+1e-9,near_vwap=near,
      breakout=b['close']+1e-9>=max(x['close'] for x in pb[-2:])+.01,
      above_vwap=b['close']>b['average'],vwap_rising=len(rows)>=4 and b['average']>=rows[-4]['average'],
      volume=b['volume']>0 and b['volume']+1e-9>=avg*1.2,premium=(b['close']/b['average']-1)*100<=1.5+1e-9)
     strict_checks=dict(checks)
     tolerance=min(rows[-4]['average']*RESEARCH_PARAMS['vwap_relative_tolerance'],RESEARCH_PARAMS['vwap_absolute_cap'])
     if variant in ('A','AB'):
      checks['vwap_rising']=b['average']>=rows[-4]['average']-tolerance
     reclaim=(b['close']<=RESEARCH_PARAMS['low_price_max'] and b['close']+1e-9>=max(x['close'] for x in pb[-2:])
       and b['close']+1e-9>=pb[-1]['close']+RESEARCH_PARAMS['reclaim_tick'])
     if variant in ('B','AB'):checks['breakout']=checks['breakout'] or reclaim
     evidence=dict(time=t,checks=dict(checks),strict_checks=strict_checks,
      relaxed=[k for k in checks if checks[k] and not strict_checks[k]],
      average=b['average'],previous_average=rows[-4]['average'],tolerance=tolerance,
      price=b['close'],prior_two_high=max(x['close'] for x in pb[-2:]),previous_close=pb[-1]['close'])
     candidate.setdefault('checks_history',[]).append(evidence)
     candidate['last_checks']=checks
     if all(checks.values()):
      event=dict(key=candidate['key'],seed_time=candidate['seed_time'],time=t,price=b['close'],
       peak=h,pullback_low=min(x['close'] for x in pb),depth_pct=d,pullback_minutes=len(pb),
       rise_volume=candidate['rise_volume'],pullback_volume=avg,confirm_volume=b['volume'],average=b['average'])
      event.update(variant=variant,evidence=evidence,signal_type='收复转强' if not strict_checks['breakout'] else '严格突破');signals.append(event);candidate.update(status='confirmed',reason='强势回踩后再次转强',confirmation=event)
      candidate=None;cooldown=i+10;continue
     if len(pb)>=8:expire('回踩8分钟后仍未确认');continue
     pb.append(b)
    elif b['close']<h:
     pb.append(b);candidate['pullback_start']=t
    else:
     new=seed()
     if new:candidate.update(new)
     else:expire('继续上涨但不再满足上涨段条件')
    continue
   if i<cooldown:
    skipped=seed()
    if skipped:cooldown_suppressed.append(dict(time=t,reason='确认后10交易分钟冷却',next_allowed=session[cooldown] if cooldown<len(session) else None,seed=skipped))
    continue
   s=seed()
   if s and (anchor is None or t==anchor):
    candidate=dict(s,key=t,status='observing',reason='等待缩量回踩',pullback=[])
    candidates.append(candidate)
    baseline.append(dict(key=t,seed_time=t,time=t,price=b['close'],rise_volume=s['rise_volume']))
  if candidate and candidate['status']!='observing':expire('午休／时段结束')
 return dict(candidates=candidates,baseline=baseline,signals=signals,cooldown_suppressed=cooldown_suppressed,error=None)
