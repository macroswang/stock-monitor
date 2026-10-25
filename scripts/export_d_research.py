"""Export the verified, failed-gate D study for read-only in-app replay.

This only reads the isolated study. It never invokes a collector, database or RPC.
Run from any directory; --source can point to a restored research archive.
"""
import argparse,gzip,hashlib,json
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=REPO.parents[1]/'outputs/guanliang-D-reserved-supplement-20261025');args=parser.parse_args()
    source=args.source;read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    plan=read(source/'analysis-plan.json')
    assert sha(source/'analysis-plan.json')==(source/'analysis-plan.sha256').read_text().strip()
    for filename,digest in read(source/'artifact-sha256.json').items():assert sha(source/filename)==digest,filename
    for filename,digest in plan['input_hashes'].items():assert sha(filename)==digest,filename
    assert not read(source/'eligibility.json')['historical_passed']
    assert read(source/'final-state-verification.json')['Q1_monitor_doublebottom_existing_validation_untouched']
    parent=source.parent
    rows={(r['code'],r['day']):r for r in read(parent/'guanliang-guoke-point-study-20261025/dataset.json')}
    shapes={(r['code'],r['day']):r['variants'] for r in read(parent/'guanliang-weak-top-known-at-confirm-20261025/signals.json')}
    times=[f'{m//60:02}:{m%60:02}' for m in [*range(571,691),*range(781,901)]]
    trades=[json.loads(x) for x in gzip.open(source/'trades.jsonl.gz','rt')]
    slots=('D','U','S','S_L1','S_LQ');scenarios=('gross','fees','primary','stress','delay','delay_stress');reviews=read(source/'fourteen-point-review.json')
    harms={(r['code'],r['day']):r for r in reviews}
    selected={slot:{(t['code'],t['day']) for t in trades if t['slot']==slot and t['scenario']=='primary'} for slot in slots[2:]}
    weak=('sz300672','2026-10-23');keys=set(harms)|set.union(*selected.values())|{weak}
    assert len(harms)==14 and len(selected['S'])==21
    indexes={}
    for group in read(parent/'guanliang-q1-market-failure-20261025/index-groups.json'):
        g=indexes.setdefault(group['date'],{'previousClose':float(group['previous_close']),'bars':{},'conflicts':set()})
        for b in group['bars']:
            time=b['time'];price=float(b['close'])
            if time in g['bars'] and abs(g['bars'][time]-price)>1e-9:g['conflicts'].add(time)
            g['bars'].setdefault(time,price)
    decisions={}
    for d in read(source/'decisions.json'):
        if (d['code'],d['day']) in keys:decisions.setdefault((d['code'],d['day']),[]).append(d)
    selection={(s['code'],s['day']):s for s in read(source/'selection.json')}
    tl={(t['code'],t['day'],t['slot'],t['scenario']):t for t in trades}
    accounts={}
    for line in gzip.open(source/'accounts.jsonl.gz','rt'):
        a=json.loads(line);key=(a['code'],a['day'])
        if key in keys and a['arm'] in ('P','U','I','I_L1','I_LQ'):
            accounts.setdefault(key,{}).setdefault(a['arm'],{})[a['scenario']]={k:a[k] for k in ('initial_qty','net_cny','cash_buffer_needed','both_fills_within_1pct','actions')}
    fields=('status','signal_time','candidate_time','candidate_price','entry_time','exit_time','entry_index','exit_index','entry_reference','exit_reference','buy_fill','sell_fill','net_pct','net_cny','fees_cny','slippage_cny','opposite_confirmation','exit_reason','execution_flags')
    cases=[]
    for key in sorted(keys,key=lambda k:(k[1],k[0])):
        row=rows[key];idx=indexes.get(row['day']);old=harms.get(key);variants=shapes[key]
        cases.append({'id':'|'.join(key),'code':row['code'],'name':row['name'],'day':row['day'],
            'tags':(['harm'] if old else [])+[s for s in selected if key in selected[s]]+(['weak'] if key==weak else []),
            'price':row['price'],'volume':row['volume'],'average':row['average'],'previousClose':row['previous_close'],
            'index':{'previousClose':idx['previousClose'],'price':[idx['bars'].get(t) if t not in idx['conflicts'] else None for t in times]} if idx else None,
            'shapes':[{k:m[k] for k in ('key','kind','time','price','candidateTime','candidatePrice')} for m in variants['B']],
            'decisions':[{k:d[k] for k in ('time','key','c1','passed','features','lag')} for d in decisions.get(key,[])],
            'selection':{k:selection[key][k] for k in ('I','I_L1','I_LQ','U')},
            'oldJ':{'signal':old['new_signal'],'net_pct':old['new_net_pct'],'cause':old['cause'],'features':old['features']} if old else None,
            'weakTimes':['13:05','14:21'] if key==weak else [],
            'trades':{slot:{sc:({k:tl[*key,slot,sc].get(k) for k in fields} if (*key,slot,sc) in tl else None) for sc in scenarios} for slot in slots},
            'accounts':accounts[key]})
    quality=read(source/'data-quality.json');result={'schemaVersion':1,'id':'D-reserved-supplement-20261025','times':times,
        'meta':{'date':'2026-10-25','start':min(quality['dates']),'end':max(quality['dates']),'stockdays':quality['stockdays'],'stocks':quality['stocks'],'dates':len(quality['dates']),
            'caseCount':len(cases),'missingPreviousClose':len(quality['unknown_previous_close']),'normalizableStockdays':2046,'quantityPerSlot':1000,'newDates':0,'frozen':False},
        'metrics':{slot:read(source/'trade-results.json')['common_known'][slot] for slot in slots},
        'daily':[r for r in read(source/'daily-trades.json') if r['slot'] in slots],
        'resourceMetrics':{a:read(source/'account-results.json')[a] for a in ('P','U','I','I_L1','I_LQ','D2K')},
        'gates':read(source/'eligibility.json')['gates'],'verification':{k:read(source/'verification.json')[k] for k in ('independent_costs','independent_timing','D_primary_ge2pct_winners_preserved','shared_U_changes','shared_U_big_entries_changed')},
        'sources':{n:sha(source/n) for n in ('analysis-plan.json','trade-results.json','account-results.json','fourteen-point-review.json','verification.json')},'cases':cases}
    dest=REPO/'src/research/d-reserved-20261025.json';dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps({'file':str(dest.relative_to(REPO)),'case_count':len(cases),'bytes':dest.stat().st_size,'sha256':sha(dest)},ensure_ascii=False))
if __name__=='__main__':main()
