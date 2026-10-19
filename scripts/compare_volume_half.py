"""Frozen-input experiment: one minute with >=50% contraction vs two-minute baseline."""
import csv,json,hashlib
from scripts.compare_volume_confirmation import ROOT,OUT,FULL,hashes

def run():
 before=hashes();records=json.loads((OUT/'inputs.json').read_text());old=list(csv.DictReader((OUT/'signals.csv').open(encoding='utf-8-sig')))
 oldtwo={r['key'] for r in old if r['extra']=='False'};one={r['key'] for r in old}
 signals={};windows={};rows=[]
 for record in records:
  bars=[b for b in record['data']['bars'] if b['time'] in FULL];maximum=0
  for i,b in enumerate(bars):
   if b['time']>'14:54':break
   maximum=max(maximum,b['volume']);v=b['volume']
   if not v or v!=maximum:continue
   key=record['code']+'|'+record['date']+'|'+b['time'];ratio=bars[i+1]['volume']/v
   # Integer comparison handles exactly 50% without float boundary error.
   half=2*bars[i+1]['volume']<=v;two=bars[i+1]['volume']<v and bars[i+2]['volume']<v
   assert (key in oldtwo)==two
   assert (key in one)==(bars[i+1]['volume']<v)
   if not (half or two):continue
   row=dict(key=key,code=record['code'],date=record['date'],top_time=b['time'],top_shares=v,next1_shares=bars[i+1]['volume'],next2_shares=bars[i+2]['volume'],next1_ratio=ratio,one_half=half,two=two,first_minute=b['time']=='09:31')
   for group,confirmed in [('one_half',i+1),('two',i+2)]:
    follow=bars[confirmed+1:confirmed+6];row[group+'_reexpand_5']=any(x['volume']>=v for x in follow) if len(follow)==5 else None
    row[group+'_reexpand_day']=any(x['volume']>=v for x in bars[confirmed+1:])
   rows.append(row);windows[key]=row
 def stats(selected,group):
  rs=[r for r in rows if r['key'] in selected];eligible=[r for r in rs if r[group+'_reexpand_5'] is not None]
  return dict(signals=len(rs),first_minute=sum(r['first_minute'] for r in rs),reexpand_5=sum(r[group+'_reexpand_5'] is True for r in eligible),eligible_5=len(eligible),reexpand_day=sum(r[group+'_reexpand_day'] for r in rs))
 halfkeys={r['key'] for r in rows if r['one_half']};extra=halfkeys-oldtwo;missed=oldtwo-halfkeys
 # Independent membership verification from prior CSV only.
 assert halfkeys=={r['key'] for r in old if 2*int(r['next1_shares'])<=int(r['top_shares'])}
 assert all(windows[k]['next2_shares']>=windows[k]['top_shares'] for k in extra)
 report=dict(input_snapshot_sha256=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest(),stocks=len({r['code'] for r in records}),stock_days=len(records),definition='下一完整分钟量<=顶部分钟量的50%；顶部量仍为截至当时最大正量，含并列；共同候选窗口09:31—14:54',one_half=stats(halfkeys,'one_half'),two=stats(oldtwo,'two'),shared=len(halfkeys&oldtwo),extra_over_two=len(extra),missed_from_two=len(missed),filtered_previous_one_extras=83-len(extra),first_minute_extra=sum(windows[k]['first_minute'] for k in extra),first_minute_missed=sum(windows[k]['first_minute'] for k in missed),hashes_before=before,hashes_after=hashes())
 assert before==hashes();out=OUT/'half-volume';out.mkdir(exist_ok=True)
 (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 with (out/'signals.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 print(json.dumps(report,ensure_ascii=False,indent=2))
 print('MEILIYUN',json.dumps([r for r in rows if r['code']=='sz000815' and r['date']=='2026-10-19'],ensure_ascii=False))
if __name__=='__main__':run()
