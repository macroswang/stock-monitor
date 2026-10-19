"""Offline-only 1 vs 2 minute confirmation experiment. Never instantiates App/Store."""
import collections,csv,hashlib,json,sqlite3,sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.rules import Session
from core.validated_engine import MINUTES
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/confirmation-1-vs-2-20261019'
FULL=[f'{m//60:02}:{m%60:02}' for m in list(range(571,691))+list(range(781,901))]
PROTECTED=['core/rules.py','core/app.py','core/validated_engine.py','src/Chart.tsx','src/volumeMarks.ts']
def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in PROTECTED}
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False))
def run():
 OUT.mkdir(exist_ok=True);before=hashes();names={};inputs={};duplicates=[];excluded=[]
 def add(code,day,data,origin,priority):
  key=code+'|'+day
  if key in inputs:
   old=inputs[key];a=[(b['time'],b['volume'],b['close'],b.get('complete')) for b in old['data']['bars'] if b['time'] in FULL];b=[(b['time'],b['volume'],b['close'],b.get('complete')) for b in data['bars'] if b['time'] in FULL]
   duplicates.append(dict(key=key,old=old['origin'],new=origin,identical=a==b))
   if old['priority']>=priority:return
  inputs[key]=dict(code=code,date=day,data=data,origin=origin,priority=priority)
 pool=json.loads((ROOT/'docs/buy-v1/free-broad-1000/frozen-pool.json').read_text())['pool'];names.update({p['code']:p['name'] for p in pool})
 for folder,priority in [('free-broad-1000',1),('free-expanded',2)]:
  for path in sorted((ROOT/'docs/buy-v1'/folder/'normalized').glob('*.json')):
   content=json.loads(path.read_text());days=content.get('minute',content)
   for day,data in days.items():add(path.stem,day,data,str(path.relative_to(ROOT)),priority)
 db=Path.home()/'Library/Application Support/com.xreddot.stockmonitor/monitor.sqlite3'
 with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
  names.update(dict(conn.execute('select code,name from instruments')))
  appkeys=set()
  for code,day,payload in conn.execute("select code,day,payload from cache where kind='minute' order by code,day"):
   data=json.loads(payload)
   if data.get('source')!='tencent' or data.get('rule_compatible') is False:
    excluded.append(dict(code=code,date=day,reason='non_tencent',origin='app'));continue
   appkeys.add(code+'|'+day);add(code,day,data,'app_cache_readonly',3)
 # Change only confirmation length in an isolated in-memory class; production file is untouched.
 source=(ROOT/'core/rules.py').read_text();assert source.count("len(c['volumes'])==3")==1
 namespace={'__package__':'core','__name__':'core.research_one_minute'}
 exec(compile(source.replace("len(c['volumes'])==3","len(c['volumes'])==2"),'<one-minute-experiment>','exec'),namespace)
 One=namespace['Session'];snapshot=[];events=[];inventory=[]
 for key,record in sorted(inputs.items()):
  data=record['data'];bars=[b for b in data['bars'] if b['time'] in FULL]
  reason=None
  if data.get('source','tencent')!='tencent' or data.get('rule_compatible') is False:reason='source_unverified'
  elif [b['time'] for b in bars]!=FULL or not all(b.get('complete') is True for b in bars):reason='incomplete_or_duplicate_minutes'
  elif not all(isinstance(b['volume'],(int,float)) and b['volume']>=0 and int(b['volume'])==b['volume'] and Decimal(b['close'])>0 for b in bars):reason='invalid_volume_or_price'
  if reason:excluded.append(dict(code=record['code'],date=record['date'],reason=reason,origin=record['origin']));continue
  cohort='app' if key in appkeys else 'expanded';snapshot.append(record)
  maximum=0;dayevents=[]
  for i,b in enumerate(bars):
   # Common eligibility: 09:31 through 14:54, so both confirmations fit the existing 14:56 rule boundary.
   if b['time']>'14:54':break
   candidate=b['volume']>0 and b['volume']>=maximum;maximum=max(maximum,b['volume'])
   if not candidate:continue
   v=b['volume'];one=bars[i+1]['volume']<v;two=one and bars[i+2]['volume']<v
   if not one:continue
   row=dict(key=key+'|'+b['time'],code=record['code'],name=names.get(record['code'],record['code']),date=record['date'],cohort=cohort,top_time=b['time'],top_shares=v,next1_time=bars[i+1]['time'],next1_shares=bars[i+1]['volume'],next2_time=bars[i+2]['time'],next2_shares=bars[i+2]['volume'],one_confirmation=bars[i+1]['time'],two_confirmation=bars[i+2]['time'] if two else None,extra=not two)
   for n in [5,10]:
    following=bars[i+2:i+2+n];row[f'follow_{n}_complete']=len(following)==n
    hits=[x for x in following if x['volume']>=v];row[f'reexpand_{n}']=bool(hits) if len(following)==n else None
    row[f'first_reexpand_{n}']=hits[0]['time'] if hits else None
   later=bars[i+2:];hits=[x for x in later if x['volume']>=v]
   row.update(reexpand_day=bool(hits),strictly_larger_day=any(x['volume']>v for x in later),first_reexpand_day=hits[0]['time'] if hits else None,first_minute=b['time']=='09:31')
   dayevents.append(row)
  # All candidates compared against exact production engine on a synthetic safely-high limit.
  safe_limit=max(Decimal(b.get('high') or b['close']) for b in bars)+1
  baseline=Session(record['code'][2:],record['date'],safe_limit);experimental=One(record['code'][2:],record['date'],safe_limit)
  for b in bars:baseline.bar(b);experimental.bar(b)
  eligible=lambda es:{e['candidate_time'] for e in es if e['candidate_time']<='14:54'}
  assert eligible(baseline.events)=={e['top_time'] for e in dayevents if not e['extra']},key
  assert eligible(experimental.events)=={e['top_time'] for e in dayevents},key
  # Actual limit-up behavior is calculated only when the day's reference exists; no guessed limit.
  limit=data.get('limit_up');actual=None
  if limit:
   try:
    a=Session(record['code'][2:],record['date'],limit);b=One(record['code'][2:],record['date'],limit)
    for bar in bars:a.bar(bar);b.bar(bar)
    assert not a.gap and not b.gap
    old=eligible(a.events);new=eligible(b.events)
    actual=dict(one=len(new),two=len(old),extra=len(new-old),missing_from_one=len(old-new))
    for row in dayevents:
     row['actual_one']=row['top_time'] in new;row['actual_two']=row['top_time'] in old
   except (ValueError,ArithmeticError):actual=None
  for row in dayevents:
   row.setdefault('actual_one',None);row.setdefault('actual_two',None)
  inventory.append(dict(code=record['code'],name=names.get(record['code'],record['code']),date=record['date'],cohort=cohort,origin=record['origin'],one=len(dayevents),two=sum(not e['extra'] for e in dayevents),actual=actual))
  events.extend(dayevents)
 def summarize(rows):
  extras=[r for r in rows if r['extra']];shared=[r for r in rows if not r['extra']]
  def subset(rs):return dict(count=len(rs),first_minute=sum(r['first_minute'] for r in rs),reexpand_5=sum(r['reexpand_5'] is True for r in rs),eligible_5=sum(r['follow_5_complete'] for r in rs),reexpand_10=sum(r['reexpand_10'] is True for r in rs),eligible_10=sum(r['follow_10_complete'] for r in rs),reexpand_day=sum(r['reexpand_day'] for r in rs),strictly_larger_day=sum(r['strictly_larger_day'] for r in rs))
  return dict(one=len(rows),two=len(shared),extra=len(extras),extra_stats=subset(extras),shared_stats=subset(shared))
 summary={g:summarize([r for r in events if g=='all' or r['cohort']==g]) for g in ['all','app','expanded']}
 actual=[r for r in inventory if r['actual'] is not None]
 report=dict(definitions=dict(candidate='完整分钟正量>=截至当时最大分钟量，含并列；不含09:30集合竞价；共同候选窗口09:31—14:54',confirmation='之后连续1或2个完整交易分钟分别严格低于候选量，午休不计分钟',reexpand='从1分钟确认后的下一分钟起，成交量>=候选顶部量；5/10分钟按交易分钟计，跨午休',scope='结构信号为主，不推断缺失的历史涨停价；实际涨停逻辑仅在参考价齐备子集回放。非交易收益或有效卖点评价'),stock_days=len(inventory),stocks=len({r['code'] for r in inventory}),dates=sorted({r['date'] for r in inventory}),summary=summary,actual_reference_subset=dict(stock_days=len(actual),one=sum(r['actual']['one'] for r in actual),two=sum(r['actual']['two'] for r in actual),extra=sum(r['actual']['extra'] for r in actual),missing_from_one=sum(r['actual']['missing_from_one'] for r in actual)),actual_extra_stats=summarize([r for r in events if r['actual_one'] is True and r['actual_two'] is False]),cohorts={g:dict(stock_days=sum(r['cohort']==g for r in inventory),stocks=len({r['code'] for r in inventory if r['cohort']==g})) for g in ['app','expanded']},duplicates=dict(count=len(duplicates),conflicting=sum(not r['identical'] for r in duplicates),policy='app优先，其次free-expanded，再free-broad；同股票日期只计一次'),excluded=dict(collections.Counter(r['reason'] for r in excluded)),hashes_before=before,hashes_after=hashes())
 assert report['hashes_before']==report['hashes_after']
 dump(OUT/'inputs.json',snapshot);dump(OUT/'inventory.json',inventory);dump(OUT/'quality.json',dict(exclusions=excluded,duplicates=duplicates));dump(OUT/'results.json',report)
 for filename,rows in [('signals.csv',events),('extra-signals.csv',[r for r in events if r['extra']])]:
  with (OUT/filename).open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=list(events[0]));w.writeheader();w.writerows(rows)
 print(json.dumps(report,ensure_ascii=False,indent=2))
 print('MEILIYUN',json.dumps([e for e in events if e['code']=='sz000815' and e['date']=='2026-10-19'],ensure_ascii=False))
 return report
if __name__=='__main__':run()
