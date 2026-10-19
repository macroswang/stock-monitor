"""Offline E/ES/EW comparison, including missed baseline structures and latency."""
import csv,hashlib,html,json,sqlite3
from pathlib import Path
from scripts.supplement_diagnostics import failures

def run(folder=Path('docs/buy-v1/confirmation'),snapshot=Path('docs/buy-v1/supplement/snapshot.sqlite3')):
 r=json.loads((folder/'full-day.json').read_text());assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==r['source_sha256']
 db=sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro',uri=True)
 data={(c,d):json.loads(p) for c,d,p in db.execute("select code,day,payload from cache where kind='minute'")};db.close()
 base={e['identity']:e for e in r['signals']['E']};result=dict(as_of=r['as_of'],source_snapshot=str(snapshot.resolve()),source_sha256=r['source_sha256'],groups={},signals={},removed={},notes=['ES只对E分支增加结构高点过滤，V1信号原样保留；结构高点取最近上涨段终点至当前之前的最高分钟收盘，不含当前或未来分钟','EW仅观察原E触发后的下一完整分钟；要求不低于固定突破参考价且高于当时均价；失败即取消，不无限等待','EW确认时刻和代理入场均顺延，收益窗口也从新确认时刻计数；冷却从真正确认开始','三组独立全日回放，未叠加ES与EW；共同继承原来的冷却和同结构去重','全部6日已参与设计，两个信号不能作为新的独立验证样本；未做参数搜索','价格轨迹不证明成交，历史交易状态缺失单列；不含手续费滑点；当日尚未收盘'])
 for v,events in r['signals'].items():
  observations=[]
  for e in events:
   dat=data[e['code'],e['date']];cutoff=r['as_of'][11:16] if e['date']==r['as_of'][:10] else '15:00'
   f=failures(e,dict(dat,bars=[b for b in dat['bars'] if b['time']<=cutoff]))
   old=base.get(e['identity']);delay=None
   if old:
    from core.buy_confirmation import TIMELINE
    delay=TIMELINE.index(e['time'])-TIMELINE.index(old['time'])
   observations.append(dict(event=e,failure=f,delay_minutes=delay,entry_price_change_vs_E=(e['outcome']['entry_price']/old['outcome']['entry_price']-1)*100 if old and e['outcome']['entry_price'] and old['outcome']['entry_price'] else None))
  removed=[e for key,e in base.items() if key not in {e['identity'] for e in events}]
  result['groups'][v]=dict(signals=len(events),false_break_cases=sum(x['failure']['structural_failure'] is True for x in observations),assessable=sum(x['failure']['complete'] for x in observations),removed=len(removed),removed_positive_30m=sum(e['trajectory']['entry_forward']['30'] is not None and e['trajectory']['entry_forward']['30']>0 for e in removed),cooldown_suppressed=r['summary'][v]['cooldown_suppressed'])
  result['signals'][v]=observations;result['removed'][v]=removed
 # Save the actual rejection/acceptance paths for the losing example.
 result['filter_paths']={v:[dict(name=c['name'],date=c['date'],key=c['key'],reason=c['reason'],structure_checks=c.get('structure_checks'),acceptance_check=c.get('acceptance_check')) for c in r['candidates'][v] if c['code']=='sz300672' and c['date']=='2026-10-15' and c['key']=='13:40'] for v in ['ES','EW']}
 (folder/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 with (folder/'signals.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['组别','股票','日期','确认时间','代理入场时间','代理入场价','延后分钟','代理价相对E变化%','5分%','15分%','30分%','5分钟假突破','交易状态'])
  for v,items in result['signals'].items():
   for x in items:
    e=x['event'];w.writerow([v,e['name'],e['date'],e['time'],e['outcome']['entry_time'],e['outcome']['entry_price'],x['delay_minutes'],x['entry_price_change_vs_E'],*[e['trajectory']['entry_forward'][str(n)] for n in (5,15,30)],x['failure']['structural_failure'],e['outcome']['execution']])
 headers=['组别','信号数','5分钟假突破数','相对E过滤数','过滤掉的30分钟上涨样本数']
 rows=[[v,s['signals'],s['false_break_cases'],s['removed'],s['removed_positive_30m']] for v,s in result['groups'].items()]
 def table(head,rows):return '<table><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in head)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</table>'
 body='<h1>E组确认方式三组全日对照</h1><p>固定快照截至 '+html.escape(r['as_of'])+'；4只自选、6日；每组27个候选结构，含冷却与去重。E原规则，ES结构高点，EW一分钟验收。</p>'+table(headers,rows)
 body+='<p>两项过滤都取消国科微10月15日13:48结构；保留山子高科10月19日结构。山子高科在三组中仍于13:45出现两根连续收盘低于固定参考价2.42，因此减少的是误报数量，不能据此认定误报率改善。</p><p>ES保持山子高科13:41确认、13:42代理入场2.42；EW改为13:42确认、13:43代理入场2.42，实际延迟1分钟，本例代理价格无变化。EW的收益终点重新计算，不复用原E窗口。</p>'
 body+='<h2>逐条信号、收益窗口和被过滤案例</h2><details open><summary>完整数值证据</summary><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre></details>'
 (folder/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>确认方式三组对照</title><style>body{font:15px system-ui;line-height:1.7;max-width:1200px;margin:30px auto}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:10px}pre{white-space:pre-wrap;font-size:12px}</style>'+body)
 print(json.dumps(result['groups'],ensure_ascii=False,indent=2))
 return result
if __name__=='__main__':run()
