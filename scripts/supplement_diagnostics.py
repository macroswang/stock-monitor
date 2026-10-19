"""Structural false-signal diagnostics; observation only, no trade execution."""
import json,sqlite3,csv,html
from pathlib import Path
from scripts.replay_buy_full_day import trajectory
from core.buy_compare import TIMELINE

def failures(event,data):
 i=TIMELINE.index(event['time']);times=TIMELINE[i+1:i+6]
 by={b['time']:b for b in data['bars'] if b.get('complete') and b.get('average') and b.get('close')}
 full=len(times)==5 and all(t in by for t in times)
 resistance=event['evidence']['prior_two_high']
 def consecutive(test):
  count=0
  for t in times:
   if t not in by:count=0;continue
   count=count+1 if test(by[t]) else 0
   if count>=2:return t
  return None
 support=consecutive(lambda b:float(b['close'])<float(b['average']))
 breakout=consecutive(lambda b:float(b['close'])<resistance)
 return dict(complete=full,two_below_average=support,two_below_fixed_breakout=breakout,fixed_breakout_price=resistance,structural_failure=bool(support or breakout) if full else None)

def run(folder):
 r=json.loads((folder/'full-day.json').read_text())
 db=sqlite3.connect((folder/'snapshot.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
 cache={(c,d):json.loads(p) for c,d,p in db.execute("select code,day,payload from cache where kind='minute'")};db.close()
 unique={}
 for v in ['R','E','RE']:
  for e in r['signals'][v]:
   key=e['identity'];dat=cache[e['code'],e['date']];cutoff=r['as_of'][11:16] if e['date']==r['as_of'][:10] else '15:00'
   dat=dict(dat,bars=[b for b in dat['bars'] if b['time']<=cutoff])
   unique.setdefault(key,dict(event=e,groups=[],failure=failures(e,dat)))['groups'].append(v)
 group_failures={}
 for v,events in r['signals'].items():
  checks=[]
  for e in events:
   dat=cache[e['code'],e['date']];cutoff=r['as_of'][11:16] if e['date']==r['as_of'][:10] else '15:00'
   checks.append(failures(e,dict(dat,bars=[b for b in dat['bars'] if b['time']<=cutoff])))
  group_failures[v]=dict(signals=len(events),assessable=sum(x['complete'] for x in checks),structural_failures=sum(x['structural_failure'] is True for x in checks))
 result=dict(group_failures=group_failures,as_of=r['as_of'],summary=r['summary'],unique_added=list(unique.values()),recovery_rejections=[dict(code=c['code'],name=c['name'],date=c['date'],key=c['key'],**c['recovery_rejection']) for c in r['candidates']['R'] if c.get('recovery_rejection')],notes=['R/E/RE均以V1为基线，不自动叠加A/B；现有四组独立保留','同一结构按股票+日期+原候选分钟去重；合并组先确认者优先；确认后10交易分钟冷却','假突破参考价在确认时固定，后续不得移动；仅完整5分钟窗口评估，两根连续收盘低于参考价为结构失败','走势用下一完整分钟收盘代理入场；未知涨停/交易状态不得计作已认证可成交收益','所有参数按确认方案冻结；当前6日均已参与设计，只是探索样本，不能认证误报率改善','当日仅到14:36，无收盘和次日结果；分钟收盘极值不是逐笔极值；不含费用'])
 (folder/'diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 lines=['# 补充买点规则：七组全日对照','',f"快照截止：{r['as_of']}。当前4只自选，6个可用交易日，24个股票日规则判断时段齐备；当日尚未收盘。另16个非腾讯口径股票日排除。",'','|组别|确认数|含义|','|---|---:|---|']
 desc=dict(V1='原规则',A='均价容差',B='低价股收复',AB='A+B',R='V1+破位后收复',E='V1+远离均价继续转强',RE='V1+两条补充规则')
 for v,s in r['summary'].items():lines.append(f"|{v}|{s['signals']}|{desc[v]}|")
 lines+=['','5分钟内结构失败统计（样本极少，仅列数量，不认定稳定误报率）：'+json.dumps(group_failures,ensure_ascii=False),'','## 新增信号与后续走势','', '|股票／时间|分支|信号价→下一分钟代理价|5分／15分／30分变化（相对代理价）|最新或当日收盘变化|5分钟内结构失败|','|---|---|---|---|---|---|']
 def fmt(x):return '—' if x is None else f'{x:+.2f}%'
 for x in unique.values():
  e=x['event'];t=e['trajectory'];o=e['outcome'];f=x['failure']
  lines.append('|'+ '|'.join([e['name']+' '+e['date']+' '+e['time'],e['branch'],str(e['price'])+'→'+str(o['entry_price']),'/'.join(fmt(t['entry_forward'][str(n)]) for n in (5,15,30)),fmt(t['last_return_from_entry_pct']),str(f)])+'|')
 lines+=['','## 触发和风险证据','']
 for x in unique.values():
  e=x['event'];lines += [e['name']+' '+e['date']+' '+e['time'],json.dumps(e,ensure_ascii=False,indent=2),'']
 lines+=['## 收复分支未触发的原因',json.dumps(result['recovery_rejections'],ensure_ascii=False,indent=2),'','## 研究边界']+['- '+n for n in result['notes']]
 body='\n'.join(lines);(folder/'supplement-report.md').write_text(body)
 tablelines=[s for s in lines if s.startswith('|')];tables=[];current=[]
 for s in lines:
  if s.startswith('|'):current.append(s)
  elif current:tables.append(current);current=[]
 if current:tables.append(current)
 markup=''
 for table in tables:
  markup+='<table>'+''.join('<tr>'+''.join('<td>'+html.escape(cell)+'</td>' for cell in row.strip('|').split('|'))+'</tr>' for row in table if not row.startswith('|---'))+'</table><br>'
 (folder/'supplement-report.html').write_text('<!doctype html><meta charset="utf-8"><title>补充规则全日回放</title><style>body{font:15px system-ui;line-height:1.7;margin:30px}table{border-collapse:collapse}td{border:1px solid #ccd;padding:8px}pre{white-space:pre-wrap}</style><h1>补充规则全日回放</h1><p>'+html.escape(lines[2])+'</p>'+markup+'<details><summary>完整触发、误报和走势证据</summary><pre>'+html.escape(body)+'</pre></details>')
 print(json.dumps(dict(added=len(unique),failure_cases=sum(x['failure']['structural_failure'] is True for x in unique.values()),recovery_rejections=result['recovery_rejections']),ensure_ascii=False))
 return result
if __name__=='__main__':run(Path('docs/buy-v1/supplement'))
