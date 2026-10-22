"""Read-only cached replay: retain 09:31 maximum, suppress only its candidate."""
import collections,csv,hashlib,json,sqlite3,statistics,sys
from pathlib import Path
from decimal import Decimal as D
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.rules import Session
from core.validated_engine import MINUTES
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/opening-baseline-20261021'
FULL=[f'{m//60:02}:{m%60:02}' for m in list(range(571,691))+list(range(781,901))]
PROTECTED=['core/rules.py','core/app.py','core/validated_engine.py','core/store.py','src/Chart.tsx','src/volumeMarks.ts','src/tCosts.ts']
def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in PROTECTED}
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def profile(event,bars):
 time=event['event_label'][:5];base=float(event['reference_price']);index=next(i for i,b in enumerate(bars) if b['time']==time)
 result=dict(anchor_time=time,anchor_price=base)
 for n in [5,15,30]:
  later=bars[index+1:index+n+1]
  result[f'complete_{n}']=len(later)==n
  result[f'return_{n}_pct']=(float(later[-1]['close'])/base-1)*100 if len(later)==n else None
 later=bars[index+1:];prices=[float(b['close']) for b in later]
 low=min([base]+prices);high=max([base]+prices)
 result.update(close_pct=(float(bars[-1]['close'])/base-1)*100,drop_pct=(base-low)/base*100,rise_pct=(high-base)/base*100,low_price=low,low_time=next((b['time'] for b in later if float(b['close'])==low),time),high_price=high,high_time=next((b['time'] for b in later if float(b['close'])==high),time))
 return result

def run():
 OUT.mkdir(exist_ok=True);before=hashes();records={};names={};excluded=[];conflicts=[];appkeys=set()
 frozen=json.loads((ROOT/'docs/confirmation-1-vs-2-20261019/inputs.json').read_text())
 for r in frozen:records[(r['code'],r['date'])]=dict(r)
 db=Path.home()/'Library/Application Support/com.xreddot.stockmonitor/monitor.sqlite3'
 with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as c:
  names.update(dict(c.execute('select code,name from instruments')))
  for code,day,payload in c.execute("select code,day,payload from cache where kind='minute' order by code,day"):
   data=json.loads(payload)
   if data.get('source')!='tencent' or data.get('rule_compatible') is False:
    excluded.append(dict(code=code,date=day,reason='non_tencent'));continue
   appkeys.add((code,day));key=(code,day)
   if key in records:
    signature=lambda d:[(b['time'],b['close'],b['volume'],b.get('complete')) for b in d['bars'] if b['time'] in FULL]
    if signature(records[key]['data'])!=signature(data):conflicts.append(dict(code=code,date=day,selected='current_app_cache'))
   records[key]=dict(code=code,date=day,data=data,origin='current_app_cache')
 for folder in ['free-broad-1000','free-expanded']:
  poolpath=ROOT/'docs/buy-v1'/folder/'frozen-pool.json'
  if poolpath.exists():
   pool=json.loads(poolpath.read_text(encoding='utf-8'))['pool']
   names.update({p['code']:p['name'] for p in pool if isinstance(p,dict)})
 source=(ROOT/'core/rules.py').read_text(encoding='utf-8');needle='if v>0 and v>=prev:';assert source.count(needle)==1
 namespace={'__package__':'core','__name__':'core.opening_baseline_experiment'}
 exec(compile(source.replace(needle,"if t!='09:31' and v>0 and v>=prev:"),'<opening-baseline-experiment>','exec'),namespace)
 Modified=namespace['Session'];inventory=[];signals=[];snapshots=[];verified=0
 def replay(cls,record,bars,limit):
  session=cls(record['code'][2:],record['date'],limit)
  for b in bars:session.bar(b)
  assert not session.gap
  return session.events
 for key,r in sorted(records.items()):
  bars=[b for b in r['data'].get('bars',[]) if b['time'] in FULL]
  if [b['time'] for b in bars]!=FULL or not all(b.get('complete') is True for b in bars):
   excluded.append(dict(code=r['code'],date=r['date'],reason='incomplete_day'));continue
  try:
   if not all(D(b['close']).is_finite() and D(b['close'])>0 and D(str(b['volume'])).is_finite() and D(str(b['volume']))>=0 and D(str(b['volume']))==int(b['volume']) for b in bars):raise ValueError('invalid bar')
   safe=max(D(b.get('high') or b['close']) for b in bars)+1
   old=replay(Session,r,bars,safe);new=replay(Modified,r,bars,safe)
  except (ValueError,ArithmeticError):
   excluded.append(dict(code=r['code'],date=r['date'],reason='invalid_day'));continue
  assert new==[e for e in old if e['candidate_time']!='09:31']
  # Independently enumerate all running-maximum + two-strictly-lower structures.
  rulebars=[b for b in bars if b['time'] in MINUTES];direct=[]
  for i,b in enumerate(rulebars[:-2]):
   v=b['volume']
   if v>0 and v==max(x['volume'] for x in rulebars[:i+1]) and all(x['volume']<v for x in rulebars[i+1:i+3]):direct.append(b['time'])
  assert [e['candidate_time'] for e in old]==direct
  cohort='app' if key in appkeys else 'expanded';actual_old=actual_new=None
  if r['data'].get('limit_up'):
   try:
    actual_old=replay(Session,r,bars,r['data']['limit_up']);actual_new=replay(Modified,r,bars,r['data']['limit_up'])
    assert actual_new==[e for e in actual_old if e['candidate_time']!='09:31']
   except (ValueError,ArithmeticError):actual_old=actual_new=None
  def record_events(es,kind):
   if es is None:return
   for event in es:
    row=dict(kind=kind,cohort=cohort,code=r['code'],name=names.get(r['code'],r['code']),date=r['date'],candidate_time=event['candidate_time'],filtered=event['candidate_time']=='09:31',event_time=event['event_label'],**profile(event,bars));signals.append(row)
  record_events(old,'volume_structure');record_events(actual_old,'limit_reference_replay')
  inventory.append(dict(code=r['code'],date=r['date'],cohort=cohort,original=len(old),modified=len(new),removed=sum(e['candidate_time']=='09:31' for e in old),original_actual=len(actual_old) if actual_old is not None else None,modified_actual=len(actual_new) if actual_new is not None else None))
  snapshots.append(r);verified+=1
 def summary(rows,oldfield,newfield):
  valid=[r for r in rows if r[oldfield] is not None]
  return dict(stock_days=len(valid),original=sum(r[oldfield] for r in valid),modified=sum(r[newfield] for r in valid),days_original_signal=sum(r[oldfield]>0 for r in valid),days_modified_signal=sum(r[newfield]>0 for r in valid),days_no_signal_after=sum(r[oldfield]>0 and r[newfield]==0 for r in valid))
 def movements(rows):
  def median(field):
   values=[r[field] for r in rows if r[field] is not None];return statistics.median(values) if values else None
  return dict(signals=len(rows),median_drop_pct=median('drop_pct'),median_rise_pct=median('rise_pct'),median_close_pct=median('close_pct'),median_return_5_pct=median('return_5_pct'),median_return_15_pct=median('return_15_pct'),median_return_30_pct=median('return_30_pct'),drop_at_least_1pct=sum(r['drop_pct']>=1-1e-9 for r in rows),drop_at_least_2pct=sum(r['drop_pct']>=2-1e-9 for r in rows),rise_at_least_1pct=sum(r['rise_pct']>=1-1e-9 for r in rows),rise_at_least_2pct=sum(r['rise_pct']>=2-1e-9 for r in rows),close_lower=sum(r['close_pct']<0 for r in rows),close_higher=sum(r['close_pct']>0 for r in rows),close_flat=sum(r['close_pct']==0 for r in rows))
 report=dict(stocks=len({r['code'] for r in inventory}),dates=sorted({r['date'] for r in inventory}),cohorts={g:summary([r for r in inventory if g=='all' or r['cohort']==g],'original','modified') for g in ['all','app','expanded']},actual=summary(inventory,'original_actual','modified_actual'),removed_movement={kind:movements([r for r in signals if r['kind']==kind and r['filtered']]) for kind in ['volume_structure','limit_reference_replay']},retained_movement=movements([r for r in signals if r['kind']=='volume_structure' and not r['filtered']]),latest_days={d:summary([r for r in inventory if r['date']==d],'original','modified') for d in sorted({r['date'] for r in inventory})},exclusions=dict(collections.Counter(r['reason'] for r in excluded)),conflicting_stock_days=conflicts,verified_stock_days=verified,non_opening_events_identical=True,hashes_before=before,hashes_after=hashes())
 assert before==hashes()
 dump(OUT/'inputs.json',snapshots);dump(OUT/'inventory.json',inventory);dump(OUT/'results.json',report);dump(OUT/'exclusions.json',excluded)
 for filename,rows in [('signals.csv',signals),('filtered-0931.csv',[r for r in signals if r['filtered']])]:
  with (OUT/filename).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(signals[0]));w.writeheader();w.writerows(rows)
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
