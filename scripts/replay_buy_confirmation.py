"""Read-only full-day four-arm research on the current watch pool in a frozen DB."""
import argparse,collections,csv,hashlib,html,json,sqlite3,sys
from datetime import datetime,timedelta,date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.buy_confirmation import evaluate,valid,SESSIONS,TIMELINE,VARIANTS,RESEARCH_PARAMS,SUPPLEMENT_PARAMS
from core.buy_research import outcomes

def pct(x,p):return (float(x)/p-1)*100 if x is not None and p else None

def trajectory(event,data):
 by={b['time']:b for b in data['bars'] if b.get('complete') and b.get('close') is not None and float(b['close'])>0}
 i=TIMELINE.index(event['time']);entry=by.get(TIMELINE[i+1]) if i+1<len(TIMELINE) else None
 price=float(entry['close']) if entry else None
 later=[b for t,b in sorted(by.items()) if t>event['time']]
 result=dict(last_time=later[-1]['time'] if later else None,last_price=float(later[-1]['close']) if later else None,forward={},entry_forward={})
 for n in (5,15,30):
  t=TIMELINE[i+n] if i+n<len(TIMELINE) else None;b=by.get(t)
  result['forward'][str(n)]=dict(time=t,price=float(b['close']) if b else None,return_pct=pct(b['close'],event['price']) if b else None)
  result['entry_forward'][str(n)]=pct(b['close'],price) if b else None
 observed=[(b['time'],float(b['close'])) for b in later if entry and b['time']>=entry['time']]
 for label,fn in [('max',max),('min',min)]:
  point=fn(observed,key=lambda x:x[1]) if observed else None
  result[label]=dict(time=point[0],price=point[1],return_from_entry_pct=pct(point[1],price)) if point else None
 result['last_return_from_signal_pct']=pct(result['last_price'],event['price'])
 result['last_return_from_entry_pct']=pct(result['last_price'],price)
 result['path_complete']=all(t in by for t in TIMELINE[i+1:] if t<=result['last_time'] and t not in ('14:58','14:59')) if result['last_time'] else False
 return result

def run(snapshot,output,asof):
 db=sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro',uri=True)
 watch=db.execute('select code,name,enabled from watch order by code').fetchall()
 cache={(c,k,d):json.loads(p) for c,k,d,p in db.execute('select code,kind,day,payload from cache')};db.close()
 dates=sorted({d for c,k,d in cache if k=='minute' and c in {w[0] for w in watch}})
 calendar=sorted({d for c,k,d in cache if k in ('minute','daily')})
 cooldowns={v:[] for v in VARIANTS};coverage=[];signals={v:[] for v in VARIANTS};candidates={v:[] for v in VARIANTS};cutday=asof[:10];cuttime=asof[11:16]
 for code,name,enabled in watch:
  for day in dates:
   dat=cache.get((code,'minute',day));row=dict(code=code,name=name,date=day,status='missing');coverage.append(row)
   if not dat:continue
   if day>cutday:row.update(status='future_excluded');continue
   if dat.get('source')!='tencent' or dat.get('rule_compatible') is False or dat.get('volume_unit')!='shares':row.update(status='excluded_source',source=dat.get('source'));continue
   cutoff=cuttime if day==cutday else '15:00'
   dat=dict(dat,bars=[b for b in dat['bars'] if b['time']<=cutoff])
   required=SESSIONS[0][:110]+SESSIONS[1][:90];available={b['time'] for b in dat['bars'] if valid(b)}
   row.update(status='complete' if all(t in available for t in required) else 'partial',points=len(available&set(required)),last_complete=max(available) if available else None)
   nxt=date.fromisoformat(day)+timedelta(days=1)
   while nxt.weekday()>4:nxt+=timedelta(days=1)
   nxt=nxt.isoformat();observed=next((d for d in calendar if d>day),None);following=nxt if nxt==observed and nxt<=cutday else None
   daily=cache.get((code,'daily',following))
   if daily is None and following:
    live=cache.get((code,'daily_live',following));daily=dict(open=live.get('open'),close=None) if live else None
   for v in VARIANTS:
    r=evaluate(dat,v,as_of=cutoff) # No anchor: each arm runs its own continuous state and cooldown.
    if r['error']:raise ValueError(r['error'])
    cooldowns[v].extend(dict(code=code,date=day,**x) for x in r['cooldown_suppressed'])
    candidates[v].extend(dict(code=code,name=name,date=day,**c) for c in r['candidates'])
    seen=set();previous=None
    for e in r['signals']:
     identity=day+'|'+code+'|'+e['key']
     if identity in seen:raise AssertionError('Duplicate structure')
     if previous and e['time'][:2]==previous[:2]:assert TIMELINE.index(e['time'])-TIMELINE.index(previous)>=10
     seen.add(identity);previous=e['time']
     o=outcomes(e,dat,cache.get((code,'minute',following)),daily,None)
     signals[v].append(dict(code=code,name=name,date=day,identity=identity,coverage=row['status'],**e,outcome=o,trajectory=trajectory(e,dat)))
 base={e['identity']:e for e in signals['E']}
 summary={}
 for v,events in signals.items():
  for e in events:e['comparison']='same_structure' if e['identity'] in base else 'added_structure'
  summary[v]=dict(signals=len(events),added=sum(e['identity'] not in base for e in events),removed=len(set(base)-{e['identity'] for e in events}),cooldown_suppressed=len(cooldowns[v]),candidates=len(candidates[v]),states=dict(collections.Counter(c['status'] for c in candidates[v])))
 result=dict(as_of=asof,watch=watch,coverage_summary=dict(collections.Counter(c['status'] for c in coverage)),coverage=coverage,summary=summary,signals=signals,candidates=candidates,cooldowns=cooldowns,params=dict(base=RESEARCH_PARAMS,supplement=SUPPLEMENT_PARAMS),source_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),notifications_sent=0,notes=['当前自选池，含当前停用标的但独立标记enabled；不是历史自选池重建','七组各自全日状态机，确认后10交易分钟冷却，同结构唯一提醒，午休重置','仅腾讯已核对口径用于规则；新浪补充不计作无信号','当日未收盘，日终及次日结果不可用；价格均为分钟收盘采样，非逐笔极值','次日仅使用本地观测到的紧接工作日，缺日留空；当前日次日收盘不使用临时日K','信号时间收益与下一分钟收盘代理入场收益分列；未配置费用，不报告净收益或真实成交'])
 output.mkdir(parents=True,exist_ok=True);(output/'full-day.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 lines=['# 全部自选股E组确认方式三组全日回放','',f'快照截止：{asof}。正式监控和买点通知未改动。','',str(result['coverage_summary']),'','|组别|信号|相对V1新增|相对V1减少|候选状态|','|---|---:|---:|---:|---|']
 for v,s in summary.items():lines.append(f"|{v}|{s['signals']}|{s['added']}|{s['removed']}|{s['states']}|")
 lines+=['','## 所有确认信号','']
 for v,events in signals.items():
  for e in events:
   t=e['trajectory'];o=e['outcome']
   lines += [f"### {v} {e['name']} {e['date']} {e['time']}",f"信号价{e['price']}；下一分钟代理入场{o['entry_time']} / {o['entry_price']}；执行状态{o['execution']}。",f"放行条件：{e['evidence'].get('relaxed', ['破位后收复独立确认'])}；结构{e['identity']}；{e['comparison']}。",f"5/15/30分钟：{t['forward']}",f"相对代理入场价的5/15/30分钟变化：{t['entry_forward']}",f"最新：{t['last_time']} / {t['last_price']}，相对信号{t['last_return_from_signal_pct']}%，相对代理入场{t['last_return_from_entry_pct']}%。",f"入场后分钟收盘采样最高{t['max']}；最低{t['min']}；区间连续{t['path_complete']}。",f"日终/次日结果：{json.dumps(o,ensure_ascii=False)}",'']
 lines+=['## 口径与限制','']+['- '+n for n in result['notes']]
 body='\n'.join(lines);(output/'analysis.md').write_text(body)
 (output/'analysis.html').write_text('<!doctype html><meta charset="utf-8"><title>四组全日回放</title><style>body{max-width:1200px;margin:30px auto;font:15px system-ui;line-height:1.7}pre{white-space:pre-wrap}</style><pre>'+html.escape(body)+'</pre>')
 print(json.dumps(dict(coverage=result['coverage_summary'],summary=summary,signals={v:[(e['name'],e['date'],e['time'],e['trajectory']) for e in es] for v,es in signals.items()}),ensure_ascii=False,indent=2))
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--as-of',required=True);a=p.parse_args();run(a.snapshot,a.output,a.as_of)
