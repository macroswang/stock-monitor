"""Read-only cached-data research; exports never enter live event/notification tables."""
import csv,json,html,statistics,math,hashlib
from datetime import date,datetime,timedelta
from pathlib import Path
from .buy_rules import evaluate,valid,number,PARAMS,VERSION,SESSIONS,TIMELINE
from .provider import symbol,now_cn
from .history import bounds

BENCHMARKS=lambda code:'sz399006' if code.startswith(('sz300','sz301')) else 'sz399001' if code.startswith('sz') else 'sh000001'

def pct(p,base):return (p/base-1)*100 if p is not None and base is not None and base>0 else None

def relative(event,stock,index):
 t=event['time']
 if t not in TIMELINE or TIMELINE.index(t)<5 or not index:return None
 window=TIMELINE[TIMELINE.index(t)-5:TIMELINE.index(t)+1];before=window[0]
 s={b['time']:number(b.get('close')) for b in stock.get('bars',[]) if b.get('complete') is True}
 m={b['time']:number(b.get('close')) for b in index.get('bars',[])}
 if not all(s.get(x) and m.get(x) for x in window):return None
 a,b=pct(s.get(t),s.get(before)),pct(m.get(t),m.get(before))
 return a-b if a is not None and b is not None else None

def outcomes(event,data,next_minute,next_daily,index):
 by={b['time']:b for b in data.get('bars',[]) if b.get('complete') is True and number(b.get('close')) is not None and number(b.get('close'))>0};t=event['time'];i=TIMELINE.index(t)
 entry=by.get(TIMELINE[i+1]) if i+1<len(TIMELINE) else None
 price=number(entry.get('close')) if entry else None
 result=dict(entry_time=TIMELINE[i+1] if entry else None,entry_price=price,execution='close_proxy' if price else 'missing_next_minute',
  execution_note='下一完整分钟收盘价代理；不证明订单成交',forward={},slippage_scenarios={},net_scenarios={})
 for n in (5,15,30):
  target=by.get(TIMELINE[i+n]) if i+n<len(TIMELINE) else None
  result['forward'][str(n)]=pct(number(target.get('close')) if target else None,event['price'])
 result['day_close_return']=pct(number(by.get('15:00',{}).get('close')),event['price'])
 result['next_open_return']=pct(number(next_daily.get('open')) if next_daily else None,price)
 next_close=number(next_daily.get('close')) if next_daily else None
 result['next_close_gross_pct']=pct(next_close,price)
 if price:
  limit=number(data.get('limit_up'))
  if limit is None or limit<=0:result['execution']='uncertain_trade_status'
  elif price>=limit-.000001:result['execution']='uncertain_limit_up'
  for slip in (.05,.1,.2):
   result['slippage_scenarios'][str(slip)]=pct(next_close*(1-slip/100) if next_close else None,price*(1+slip/100))
  observed=[number(b.get('close')) for tm,b in by.items() if tm>=result['entry_time']]
  next_bars={b['time']:b for b in (next_minute or {}).get('bars',[]) if b.get('complete') is True}
  next_open=number(next_daily.get('open')) if next_daily else None
  locked=[x for x in observed+[next_open] if x is not None and x>0]
  result['locked_adverse_pct']=min(0,pct(min(locked),price)) if locked else None
  observed += [number(b.get('close')) for b in next_bars.values()]
  observed=[x for x in observed if x is not None and x>0]
  result['observed_adverse_pct']=min(0,pct(min(observed),price)) if observed else None
  required_today=[x for x in TIMELINE if x>=result['entry_time'] and x not in ('14:58','14:59')]
  required_next=[x for x in TIMELINE if x not in ('14:58','14:59')]
  complete=all(x in by for x in required_today) and all(x in next_bars for x in required_next)
  result['locked_complete']=all(x in by for x in required_today) and next_open is not None
  result['adverse_window']='模拟进入至次日收盘'
  result['adverse_complete']=complete
  result['adverse_note']='分钟收盘采样，不能反映分钟内最差价格'+('；区间有缺口，非完整最大不利波动' if not complete else '')
 else:result.update(observed_adverse_pct=None,adverse_complete=False,locked_adverse_pct=None,locked_complete=False)
 return result

def summarize(events):
 eligible=[e for e in events if e['outcome']['execution']=='close_proxy']
 values=[e['outcome']['next_close_gross_pct'] for e in eligible if e['outcome']['next_close_gross_pct'] is not None]
 net={str(s):[e['outcome']['net_scenarios'].get(str(s)) for e in eligible if e['outcome']['net_scenarios'].get(str(s)) is not None] for s in (.05,.1,.2)}
 return dict(net={k:dict(samples=len(v),mean=statistics.mean(v) if v else None) for k,v in net.items()},signals=len(events),execution_proxy=len(eligible),uncertain_execution=sum(e['outcome']['execution'].startswith('uncertain') for e in events),
  next_close_samples=len(values),mean_next_close=statistics.mean(values) if values else None,
  median_next_close=statistics.median(values) if values else None,positive_fraction=sum(v>0 for v in values)/len(values) if values else None,
  max_observed_loss=min(values) if values else None,slippage={str(s):dict(samples=len(v),mean=statistics.mean(v) if v else None)
   for s in (.05,.1,.2) for v in [[e['outcome']['slippage_scenarios'].get(str(s)) for e in eligible if e['outcome']['slippage_scenarios'].get(str(s)) is not None]]})

def run(app,args):
 start,end=bounds(args);codes=[symbol(x) for x in args.get('codes',[])];codes=list(dict.fromkeys(codes))
 if not codes:raise ValueError('请先选择回放股票')
 if len(codes)>100:raise ValueError('一次最多回放100只股票')
 cost=args.get('roundtrip_cost_bps')
 if cost in ('',None):cost=None
 else:
  cost=number(cost)
  if cost is None or not 0<=cost<=1000:raise ValueError('往返总费用请输入0至1000基点，留空则不计算净收益')
 names={r['code']:r['name'] for r in app.store.query('SELECT code,name FROM instruments')}
 # Read one consistent view of SQLite; never hold this lock during evaluation/export.
 with app.store.lock:
  cache=app.store.query('SELECT code,kind,day,payload FROM cache')
 rows={};calendar=set()
 for r in cache:
  rows.setdefault((r['code'],r['kind']),{})[r['day']]=json.loads(r['payload'])
  if r['kind'] in ('daily','minute'):calendar.add(r['day'])
 calendar=sorted(calendar);dates=[d for d in calendar if start<=d<=end]
 for code in codes:dates+= [d for d in rows.get((code,'minute'),{}) if start<=d<=end]
 dates=sorted(set(dates))
 usable_dates=sorted({day for code in codes for day,data in rows.get((code,'minute'),{}).items() if start<=day<=end and data.get('source')=='tencent' and data.get('rule_compatible') is not False and data.get('volume_unit')=='shares' and any(valid(b) for b in data.get('bars',[]))})
 cut=math.floor(len(usable_dates)*.6) if len(usable_dates)>1 else len(usable_dates)
 split={d:'development' if i<cut else 'validation' for i,d in enumerate(usable_dates)}
 coverage=[];candidates=[];baseline=[];signals=[];failures=[]
 for code in codes:
  daily=rows.get((code,'daily'),{});minutes=rows.get((code,'minute'),{});bench=BENCHMARKS(code)
  for day in dates:
   data=minutes.get(day);entry=dict(code=code,name=names.get(code,code),date=day,split=split.get(day,'unavailable'),benchmark=bench,
    benchmark_proxy=code.startswith('sh688'),status='missing',reason='没有对应日分钟缓存',points=0,expected=200)
   coverage.append(entry)
   if not data:continue
   if data.get('source')!='tencent' or data.get('rule_compatible') is False:
    entry.update(status='excluded',reason='非已核对腾讯口径，未参与回放');continue
   if data.get('volume_unit')!='shares':entry.update(status='excluded',reason='分钟成交量单位未确认');continue
   bars=data.get('bars',[]);required=SESSIONS[0][:110]+SESSIONS[1][:90]
   available={b.get('time') for b in bars if valid(b)};entry['points']=len(set(required)&available)
   valid_day=entry['points']==len(required)
   entry.update(status='complete' if valid_day else 'partial',reason='所需判断时段齐备' if valid_day else '有缺口或当日尚未完成，仅回放有效连续窗口')
   result=evaluate(data)
   if result['error']:entry.update(status='excluded',reason=result['error']);continue
   index=rows.get((bench,'market_minute'),{}).get(day)
   if index and index.get('date')!=day:index=None
   entry['benchmark_available']=bool(index)
   observed_next=next((x for x in calendar if x>day),None)
   weekday=date.fromisoformat(day)+timedelta(days=1)
   while weekday.weekday()>4:weekday+=timedelta(days=1)
   following=observed_next if observed_next==weekday.isoformat() else None
   next_prices=daily.get(following) if following else None
   if following and next_prices is None:
    live=rows.get((code,'daily_live'),{}).get(following)
    if live:next_prices=dict(open=live.get('open'),close=None)
   previous=[daily[d] for d in sorted(daily) if d<day and number(daily[d].get('close')) and number(daily[d].get('close'))>0][-20:]
   trend=None
   if len(previous)==20:
    closes=[float(x['close']) for x in previous];trend=closes[-1]>=sum(closes)/20 and sum(closes[-5:])/5>=sum(closes)/20
   common=dict(code=code,name=names.get(code,code),date=day,split=split.get(day,'unavailable'),coverage=entry['status'],benchmark=bench,benchmark_proxy=entry['benchmark_proxy'],
    daily_trend=trend,daily_trend_note='前一交易日收盘≥MA20且MA5≥MA20；未复权，仅用于分组' if trend is not None else '此前20根日线不足')
   for c in result['candidates']:
    clean={k:v for k,v in c.items() if k!='pullback'};clean['pullback']=[dict(time=b['time'],close=b['close'],volume=b['volume'],average=b['average']) for b in c['pullback']]
    candidates.append(dict(common,**clean))
   for target,source in [(baseline,result['baseline']),(signals,result['signals'])]:
    for event in source:
     e=dict(common,**event);e['key']=day+'|'+code+'|'+event['key'];e['relative_strength_5m']=relative(event,data,index)
     e['outcome']=outcomes(event,data,minutes.get(following),next_prices,index)
     e['outcome']['next_session']=following
     e['outcome']['next_session_observed']=observed_next
     e['outcome']['calendar_status']='next_weekday_observed' if following else '无法认证下一交易日／数据待积累'
     e['outcome']['cost_bps']=cost
     for s,v in e['outcome']['slippage_scenarios'].items():e['outcome']['net_scenarios'][s]=v-cost/100 if v is not None and cost is not None else None
     # Next-session benchmark returns are only defined with that exact session's close.
     next_index=rows.get((bench,'market_minute'),{}).get(following)
     ib={b['time']:number(b.get('close')) for b in (index or {}).get('bars',[])}
     nb={b['time']:number(b.get('close')) for b in (next_index or {}).get('bars',[])}
     br=pct(nb.get('15:00'),ib.get(e['outcome']['entry_time']))
     sr=e['outcome']['next_close_gross_pct'];e['outcome']['excess_next_close_pct']=sr-br if sr is not None and br is not None else None
     target.append(e)
     if target is signals and (sr is not None and sr<0 or e['outcome'].get('observed_adverse_pct') is not None and e['outcome']['observed_adverse_pct']<-1.2):failures.append(e)
 filtered=[e for e in signals if e['relative_strength_5m'] is not None and e['relative_strength_5m']>=0]
 groups={}
 for name,events in [('strength_only',baseline),('v1',signals),('v1_index',filtered)]:
  groups[name]=dict(all=summarize(events),development=summarize([e for e in events if e['split']=='development']),validation=summarize([e for e in events if e['split']=='validation']),complete_days=summarize([e for e in events if e['coverage']=='complete']),partial_days=summarize([e for e in events if e['coverage']=='partial']),daily_trend_positive=summarize([e for e in events if e['daily_trend'] is True]),daily_trend_other=summarize([e for e in events if e['daily_trend'] is False]))
 comparable=[e for e in signals if e['relative_strength_5m'] is not None]
 warnings=['当前固定自选池，存在事后选股／存活者偏差；不是历史全市场检验','执行价为下一完整分钟收盘价代理；不能证明成交或精确止损','缺失数据不计作无信号；部分日期与完整日期必须分开查看','参数固定，保留验证期不参与调参；本报告不认证策略有效','无独立完整交易日历：跨未确认工作日的下一交易日结果留空，不将缺失当休市']
 if cost is None:warnings.append('未配置实际费用：净收益为空，滑点结果不含交易费用')
 if len(usable_dates)<30 or len(signals)<100:warnings.append('可回放日期或信号样本不足，仅作为探索性结果')
 if not any(e['split']=='development' for e in signals) or not any(e['split']=='validation' for e in signals):warnings.append('开发段或保留验证段没有V1信号，不能据此验证有效性')
 fingerprint=hashlib.sha256(json.dumps(sorted((r['code'],r['kind'],r['day'],r['payload']) for r in cache),ensure_ascii=False).encode()).hexdigest()
 return dict(version=VERSION,params=PARAMS,data_fingerprint=fingerprint,created_at=now_cn().isoformat(),start=start,end=end,codes=codes,dates=dates,
  split=dict(development=usable_dates[:cut],validation=usable_dates[cut:],unavailable=[d for d in dates if d not in split]),coverage=coverage,candidates=candidates,baseline=baseline,signals=signals,
  failures=failures,groups=groups,index_comparable=summarize(comparable),index_missing=len(signals)-len(comparable),warnings=warnings,
  roundtrip_cost_bps=cost,notifications_sent=0)

def export(app,report):
 folder=app.dir/'buy-research'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');folder.mkdir(parents=True)
 (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
 for name in ('coverage','candidates','baseline','signals','failures'):
  items=report[name];keys=list(dict.fromkeys(k for r in items for k in r))
  with (folder/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
   for r in items:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
 def table(headers,items):
  return '<table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in items)+'</tbody></table>'
 def fmt(v):return '—' if v is None else f'{v:.2f}%'
 names={'strength_only':'只出现强势上涨','v1':'完整V1','v1_index':'V1＋指数相对强度≥0'}
 summary=table(['规则组','信号数','可评估次日样本','均值（未含成本）','中位数','正收益比例'],[[names[k],v['all']['signals'],v['all']['next_close_samples'],fmt(v['all']['mean_next_close']),fmt(v['all']['median_next_close']),fmt(v['all']['positive_fraction']*100 if v['all']['positive_fraction'] is not None else None)] for k,v in report['groups'].items()])
 counts={s:sum(r['status']==s for r in report['coverage']) for s in ['complete','partial','missing','excluded']}
 coverage=table(['股票','日期','覆盖','有效分钟','说明'],[[r['name'],r['date'],r['status'],str(r['points'])+'/'+str(r['expected']),r['reason']] for r in report['coverage'][:300]])
 candidates=table(['股票','日期','最近上涨段终点','状态','原因'],[[r['name'],r['date'],r['seed_time'],r['status'],r['reason']] for r in report['candidates'][:100]])
 signals=table(['股票','日期','时间','确认价','次日收盘变化','执行状态'],[[e['name'],e['date'],e['time'],e['price'],fmt(e['outcome']['next_close_gross_pct']),e['outcome']['execution']] for e in report['signals'][:200]])
 warnings=''.join('<li>'+html.escape(x)+'</li>' for x in report['warnings'])
 links=' · '.join('<a href="'+name+'.csv">'+label+'</a>' for name,label in [('coverage','覆盖CSV'),('candidates','候选CSV'),('baseline','强势上涨CSV'),('signals','V1信号CSV'),('failures','失败案例CSV')])
 body='<h1>强势回踩再转强 V1 · 历史研究</h1><p>'+html.escape(report['start']+' 至 '+report['end'])+'</p><p>生成：'+html.escape(report['created_at'])+'；买点实时通知未启用。</p><ul>'+warnings+'</ul><p>'+links+' · <a href="report.json">完整JSON</a></p>'
 body+='<h2>三组对照</h2>'+summary+'<p>成交采用下一完整分钟收盘价代理。成交不确定样本不进入交易收益统计；指数缺失不默认过滤失败。相对强度可比较样本 '+str(report['index_comparable']['signals'])+' 条，缺基准 '+str(report['index_missing'])+' 条。</p>'
 body+='<h2>数据覆盖</h2><p>'+html.escape(str(counts))+'</p><p>分组仅使用有可用腾讯分钟数据的日期，开发 '+str(len(report['split']['development']))+' 日，保留验证 '+str(len(report['split']['validation']))+' 日。</p>'+coverage
 body+='<h2>V1确认信号</h2>'+signals+'<h2>候选与失效原因</h2>'+candidates+'<details><summary>固定参数</summary><pre>'+html.escape(json.dumps(report['params'],ensure_ascii=False,indent=2))+'</pre></details><details><summary>分组、滑点和费用完整统计</summary><pre>'+html.escape(json.dumps(report['groups'],ensure_ascii=False,indent=2))+'</pre></details>'
 (folder/'report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>强势回踩再转强 V1</title><style>body{font:15px system-ui;color:#243047;max-width:1250px;margin:32px auto;padding:24px;line-height:1.7}h1{color:#152943}h2{margin-top:36px}pre{white-space:pre-wrap;font-size:12px}td,th{border:1px solid #d9e1eb;padding:8px;text-align:left}th{background:#edf2f8}table{border-collapse:collapse;width:100%;font-size:13px}a{color:#275da9}li{margin:8px 0}</style>'+body+'</html>',encoding='utf-8')
 return str(folder)
