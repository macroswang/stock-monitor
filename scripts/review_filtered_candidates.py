"""Post-filter trajectory review from a fixed offline full-day research snapshot."""
import csv,hashlib,html,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.buy_compare import TIMELINE
ROOT=Path('docs/buy-v1/full-day');OUT=ROOT/'filtered-review'
LABELS=dict(length='回踩时长',depth='回踩深度',shrinking='回踩缩量',near_vwap='贴近均价',breakout='价格突破',above_vwap='站上均价',vwap_rising='均价方向',volume='反弹放量',premium='追高限制')
def pct(p,b):return (p/b-1)*100 if p is not None and b else None

def after(by,t):
 if t not in TIMELINE:return dict(error='时间不在交易分钟轴')
 i=TIMELINE.index(t);entry_t=TIMELINE[i+1] if i+1<len(TIMELINE) else None;entry=by.get(entry_t);base=entry['close'] if entry else None
 later=[(k,b['close']) for k,b in sorted(by.items()) if entry_t and k>=entry_t];last=later[-1] if later else None
 def peak(points,fn):
  if not points or base is None:return None
  t,p=fn(points,key=lambda x:x[1]);return dict(time=t,price=p,pct=pct(p,base))
 forward={}
 for n in (5,15,30):
  at=TIMELINE[i+n] if i+n<len(TIMELINE) else None;b=by.get(at);forward[str(n)]=dict(time=at,price=b['close'] if b else None,pct=pct(b['close'],base) if b else None)
 end30=TIMELINE[min(i+30,len(TIMELINE)-1)];window=[x for x in later if x[0]<=end30]
 return dict(anchor=t,entry_time=entry_t,entry_price=base,forward=forward,max30=peak(window,max),min30=peak(window,min),max_day=peak(later,max),min_day=peak(later,min),last_time=last[0] if last else None,last_price=last[1] if last else None,last_pct=pct(last[1],base) if last else None,day_close_pct=pct(by.get('15:00',{}).get('close'),base),complete30=all(k in by for k in TIMELINE[i+1:min(i+31,len(TIMELINE))] if k not in ('14:58','14:59')))

def run():
 r=json.loads((ROOT/'full-day.json').read_text());dbpath=ROOT/'snapshot.sqlite3'
 assert hashlib.sha256(dbpath.read_bytes()).hexdigest()==r['source_sha256']
 db=sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True)
 cache={(c,d):json.loads(p) for c,d,p in db.execute("select code,day,payload from cache where kind='minute'")};db.close();rows=[]
 for c in r['candidates']['V1']:
  if c['code']=='sz000815':continue
  dat=cache[c['code'],c['date']];cutoff=r['as_of'][11:16] if c['date']==r['as_of'][:10] else '15:00'
  by={b['time']:dict(close=float(b['close']),average=float(b['average'])) for b in dat['bars'] if b['time']<=cutoff and b.get('complete') and b.get('close') and b.get('average')}
  end=c['pullback'][-1]['time'] if c['pullback'] else c['seed_time']
  expiry=TIMELINE[TIMELINE.index(end)+1] if end in TIMELINE else None
  validchecks=[h for h in c.get('checks_history',[]) if h['checks']['length']]
  closest=min(validchecks,key=lambda h:sum(not v for v in h['checks'].values())) if validchecks else None
  arms={}
  for v in ['V1','A','B','AB']:
   found=next(x for x in r['candidates'][v] if (x['code'],x['date'],x['key'])==(c['code'],c['date'],c['key']))
   hs=[h for h in found.get('checks_history',[]) if h['checks']['length']]
   best=min(hs,key=lambda h:sum(not v for v in h['checks'].values())) if hs else None
   arms[v]=dict(time=best['time'],failed=[LABELS[k] for k,v in best['checks'].items() if not v]) if best else None
  first=after(by,c['key']);post=after(by,expiry)
  # Descriptive review flag, not a new trigger or parameter change.
  strong=post['complete30'] and post['max30'] and post['max30']['pct']>=1
  sustained=strong and post['forward']['30']['pct'] is not None and post['forward']['30']['pct']>=.5
  row=dict(n=len(rows)+1,name=c['name'],code=c['code'],date=c['date'],first_seed=c['key'],latest_seed=c['seed_time'],expiry_time=expiry,reason=c['reason'],closest=arms,first_seed_outcome=first,post_expiry=post,post_filter_rise_1pct=bool(strong),post_filter_sustained=bool(sustained))
  if closest:
   pb=[b for b in c['pullback'] if b['time']<closest['time']]
   row['closest_evidence']=dict(time=closest['time'],**{k:closest[k] for k in ['price','prior_two_high','previous_close','average','previous_average','tolerance']},depth_pct=(c['peak']-min(b['close'] for b in pb))/c['peak']*100,shrink_pct=sum(b['volume'] for b in pb)/len(pb)/c['rise_volume']*100,near_pct=min(abs(b['close']/b['average']-1)*100 for b in pb))
  rows.append(row)
 OUT.mkdir(exist_ok=True);result=dict(as_of=r['as_of'],rows=rows,method='原始候选key的下一分钟收盘为候选观察基准；失效时刻下一分钟收盘为被过滤后的基准。5/15/30终点从各锚点计交易分钟。不是实际入场或收益。',review_flag='事后描述标记：失效后30交易分钟内分钟收盘采样涨幅≥1%；其中30分钟终点仍≥0.5%称相对持续。只是本报告展示阈值，不改变策略参数。')
 (OUT/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 def f(v):return '—' if v is None else f'{v:+.2f}%'
 def mx(x):return f(x['pct']) if x else '—'
 lines=['# 未确认候选后续走势逐一复盘','',f"固定快照：{r['as_of']}；3只股票，{len(rows)}个候选。",'',result['method'],'',result['review_flag'],'','所有时点与极值均为分钟收盘采样；不代表逐笔最高最低或可成交价格。10月19日只观察至14:27，缺失的未来窗口留空。候选可在同日重叠，不是独立交易样本。','', '|序号|股票／日期|初始候选→失效|失效后代理价|5分|15分|30分|30分最高|当日最高|收盘／截至缓存|V1最接近检查及拦截|','|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
 for x in rows:
  p=x['post_expiry'];a=x['closest']['V1'];why=(a['time']+'：'+'、'.join(a['failed'])) if a else x['reason']
  lines.append('|'+ '|'.join(map(str,[x['n'],x['name']+' '+x['date'][5:],x['first_seed']+'→'+x['expiry_time'],p['entry_price'],*[f(p['forward'][str(n)]['pct']) for n in (5,15,30)],mx(p['max30']),mx(p['max_day']),f(p['last_pct']),why]))+'|')
 lines+=['','## 各候选的两种基准与数值证据','']
 for x in rows:
  lines+=[f"### {x['n']} {x['name']} {x['date']} {x['first_seed']}",f"最终原因：{x['reason']}；最近上涨段终点{x['latest_seed']}；失效检查{x['expiry_time']}。",'初始候选后：'+json.dumps(x['first_seed_outcome'],ensure_ascii=False),'失效之后：'+json.dumps(x['post_expiry'],ensure_ascii=False),'四组最近一次检查：'+json.dumps(x['closest'],ensure_ascii=False),'数值证据：'+json.dumps(x.get('closest_evidence'),ensure_ascii=False),'']
 body='\n'.join(lines);(OUT/'review.md').write_text(body);(OUT/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>未确认候选复盘</title><style>body{font:14px system-ui;line-height:1.7;margin:30px}pre{white-space:pre-wrap}</style><pre>'+html.escape(body)+'</pre>')
 print('\n'.join(lines[:12+len(rows)]))
 print('FLAGGED',[(x['n'],x['name'],x['date'],x['first_seed'],x['post_filter_sustained']) for x in rows if x['post_filter_rise_1pct']])
 return result
if __name__=='__main__':run()
