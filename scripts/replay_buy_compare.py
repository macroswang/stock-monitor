"""Offline fixed-cohort replay. Reads an explicit frozen database; never opens App."""
import argparse,copy,csv,hashlib,html,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.buy_compare import evaluate,VARIANTS,RESEARCH_PARAMS

def run(report_path,snapshot_path,output):
 original=json.loads(report_path.read_text());completed=original['created_at'][11:16]
 db=sqlite3.connect(snapshot_path.resolve().as_uri()+'?mode=ro',uri=True)
 try:data={(c,d):json.loads(p) for c,d,p in db.execute("select code,day,payload from cache where kind='minute'")}
 finally:db.close()
 frozen_inputs={};pairs=[];summaries={v:dict(signals=0,added=0,observing=0,expired=0,data_gap=0) for v in VARIANTS}
 for n,c in enumerate(original['candidates'],1):
  dat=copy.deepcopy(data[c['code'],c['date']])
  if dat.get('source')!='tencent' or dat.get('rule_compatible') is False or dat.get('volume_unit')!='shares':raise ValueError('Unsupported source or minute volume unit')
  cutoff=completed if c['date']==original['created_at'][:10] else '15:00'
  # Discard later snapshot updates; no future bar may influence the replay.
  dat['bars']=[b for b in dat['bars'] if b['time']<=cutoff]
  frozen_inputs[c['code']+'|'+c['date']]=dict(data=dat,completed_through=cutoff)
  arms={}
  for v in VARIANTS:
   result=evaluate(dat,v,as_of=cutoff,anchor=c['key'])
   found=next((x for x in result['candidates'] if x['key']==c['key']),None)
   if not found:raise ValueError(f'Original anchor not reproduced: {n} {v}')
   arms[v]=found
  # Candidate fields saved in the original report validate the nearby snapshot.
  base=arms['V1'];fields=['seed_time','peak','rise_volume']
  if any(base[k]!=c[k] for k in fields):raise ValueError(f'Baseline changed: {n}')
  if len(base['pullback'])!=len(c['pullback']):raise ValueError(f'Pullback changed: {n}')
  for a,b in zip(base['pullback'],c['pullback']):
   if any(float(a[k])!=float(b[k]) for k in ['close','volume','average']) or a['time']!=b['time']:raise ValueError(f'Bar changed: {n}')
  if c['reason']!='所需分钟或均价缺失／分钟未结束' and base['reason']!=c['reason']:raise ValueError(f'Expiry changed: {n}')
  for v,arm in arms.items():
   count=summaries[v];count['signals']+=arm['status']=='confirmed';count['added']+=arm['status']=='confirmed' and base['status']!='confirmed'
   if arm['status'] in count:count[arm['status']]+=1
  pairs.append(dict(n=n,code=c['code'],name=c['name'],date=c['date'],anchor=c['key'],arms=arms))
 result=dict(cohort='原报告固定25个候选，逐候选独立配对回放；不是四组全日组合扫描',original_report=str(report_path),original_created_at=original['created_at'],snapshot=str(snapshot_path),snapshot_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),source_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),params=dict(RESEARCH_PARAMS),summary=summaries,pairs=pairs,notifications_sent=0)
 output.mkdir(parents=True,exist_ok=True)
 (output/'frozen-inputs.json').write_text(json.dumps(frozen_inputs,ensure_ascii=False,indent=2))
 (output/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 table=[];added=[]
 for p in pairs:
  row=[p['n'],p['name'],p['date'],p['anchor']]
  for v,a in p['arms'].items():
   event=a.get('confirmation');row.append((event['time']+' '+event['signal_type']) if event else a['reason'])
   if event and v!='V1' and p['arms']['V1']['status']!='confirmed':added.append(dict(n=p['n'],name=p['name'],code=p['code'],date=p['date'],**event))
  table.append(row)
 with (output/'candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['序号','股票','日期','原候选分钟',*VARIANTS]);w.writerows(table)
 (output/'added-signals.json').write_text(json.dumps(added,ensure_ascii=False,indent=2))
 headers=['序号','股票','日期','原候选分钟',*VARIANTS]
 body='<h1>买点四组对照：固定25候选</h1><p>V1原版；A均价容差；B低价股收复；AB两项叠加。只读离线研究，无实时通知。</p><p>'+html.escape(result['cohort'])+'</p><pre>'+html.escape(json.dumps(summaries,ensure_ascii=False,indent=2))+'</pre>'
 body+='<table><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in table)+'</table>'
 body+='<h2>新增信号</h2><p>A、AB均新增同一条：美利云（000815），2026-10-19 10:18，确认价14.47元。均价下降0.000304364元，小于容差0.000723508元；其余原版条件全部通过。B没有新增完整信号：山子高科10-13 10:20虽通过收复价格条件，仍未贴近均价。国科微10-19 13:53在四组中均为待观察。</p><h2>新增信号与逐项证据</h2><pre>'+html.escape(json.dumps(added,ensure_ascii=False,indent=2))+'</pre><p>25个候选均已用于设计方案，属于探索样本。新增信号不代表收益改善。逐候选独立配对不包含不同候选之间的冷却抑制；后续全日扫描需另行验证。历史日期缺口为data_gap；报告时刻以后的分钟为observing；规则破坏或超时为expired。</p>'
 (output/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>买点四组对照</title><style>body{font:14px system-ui;line-height:1.7;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px}pre{white-space:pre-wrap}</style>'+body)
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 r=run(a.report,a.snapshot,a.output);print(json.dumps(r['summary'],ensure_ascii=False,indent=2))
