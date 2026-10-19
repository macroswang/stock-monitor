"""Independent direct-window check against immutable replay inputs; no network or DB."""
import csv,hashlib,json
from pathlib import Path
from scripts.compare_volume_confirmation import OUT,FULL,hashes

def run():
 inputs=json.loads((OUT/'inputs.json').read_text());rows=list(csv.DictReader((OUT/'signals.csv').open(encoding='utf-8-sig')))
 observed_one={r['key'] for r in rows};observed_two={r['key'] for r in rows if r['extra']=='False'}
 expected={1:set(),2:set()};checked=0
 for record in inputs:
  bars=[b for b in record['data']['bars'] if b['time'] in FULL]
  assert [b['time'] for b in bars]==FULL
  volumes=[b['volume'] for b in bars]
  for i,b in enumerate(bars):
   if b['time']>'14:54':break
   for n in [1,2]:
    if volumes[i]>0 and volumes[i]==max(volumes[:i+1]) and all(v<volumes[i] for v in volumes[i+1:i+1+n]):
     expected[n].add(record['code']+'|'+record['date']+'|'+b['time'])
   checked+=1
 assert expected[1]==observed_one and expected[2]==observed_two
 assert observed_two<=observed_one
 for r in rows:
  assert (int(r['next2_shares'])>=int(r['top_shares']))==(r['extra']=='True')
  assert int(r['next1_shares'])<int(r['top_shares'])
  if r['extra']=='True':assert r['first_reexpand_day']==r['next2_time']
 result=json.loads((OUT/'results.json').read_text());assert hashes()==result['hashes_before']==result['hashes_after']
 verification=dict(stock_days=len(inputs),candidate_windows_checked=checked,one=len(expected[1]),two=len(expected[2]),independent_direct_window_matches=True,extra_second_minute_reexpansion_verified=True,protected_files_unchanged=True,input_snapshot_sha256=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest())
 (OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2));print(json.dumps(verification,ensure_ascii=False))
if __name__=='__main__':run()
