"""Post-run robustness diagnostics for every frozen policy; no new hypotheses."""
import hashlib,json,statistics,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from research.ma250_optimization import OUT,DATA,Portfolio,START,END,digest
from research.ma250_breadth import load_panel


def concentration(trades):
    wins=sorted([t['profit'] for t in trades if t['profit']>0],reverse=True)
    by_code={}
    for t in trades:by_code[t['code']]=by_code.get(t['code'],0)+t['profit']
    return dict(top5_winning_profit_share=sum(wins[:5])/sum(wins) if wins else None,
                top_code_profit=sorted(by_code.items(),key=lambda x:-x[1])[:5])


def main():
    report=json.loads((OUT/'results.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    raw,qfq=load_panel(DATA/'tencent'),load_panel(DATA/'baostock-qfq');common=set(raw)&set(qfq)
    series={'raw415':raw,'raw_matched217':{c:raw[c] for c in common},'qfq217':qfq};audit={}
    for name,bars in series.items():
        context=Portfolio(bars);events=json.loads((OUT/(name+'-events.json')).read_text());panel=report['panels'][name];results={}
        for k,es in events.items():
            for e in es:
                assert e['entry_date']>e['signal_date'],e
                if e['exit_date']:assert e['exit_date']>e['entry_date'],e
            results[k]=dict(double_cost=context.run(es,cost=.003),
                without_2025_entries=context.run([e for e in es if not e['entry_date'].startswith('2025')]),
                stock_halves={str(g):context.run([e for e in es if int(hashlib.sha256(e['code'].encode()).hexdigest(),16)%2==g]) for g in (0,1)},
                concentration=concentration(panel['runs'][k]['full']['trades_detail']))
        selected=[]
        for year,choice in panel['walk_forward']['choices'].items():selected += [e for e in events[choice['policy']] if e['entry_date'].startswith(year)]
        selected.sort(key=lambda e:(e['code'],e['signal_date']))
        audit[name]=dict(policies=results,walk_forward_baseline=context.run(events['B0'],'2022-01-01',END),
            walk_forward_double_cost=context.run(selected,'2022-01-01',END,cost=.003))
        print(name,'audited',len(events),flush=True)
    pairs={}
    for k in report['panels']['qfq217']['runs']:
        left=json.loads((OUT/'raw_matched217-events.json').read_text())[k];right=json.loads((OUT/'qfq217-events.json').read_text())[k]
        key=lambda e:(e['code'],e['signal_date'],e['entry_date'],e['exit_date'])
        a={key(e):e for e in left if e['exit_date']};b={key(e):e for e in right if e['exit_date']};keys=sorted(set(a)&set(b))
        net=lambda e:(e['exit_price']*.9985/(e['entry']*1.0015)-1)*100
        values_a=[net(a[x]) for x in keys];values_b=[net(b[x]) for x in keys]
        pairs[k]=dict(paired=len(keys),raw_only=len(set(a)-set(b)),qfq_only=len(set(b)-set(a)),
            raw_mean=statistics.mean(values_a) if values_a else None,qfq_mean=statistics.mean(values_b) if values_b else None,
            raw_win=sum(x>0 for x in values_a)/len(values_a) if values_a else None,
            qfq_win=sum(x>0 for x in values_b)/len(values_b) if values_b else None)
    audit['same_event_price_pairs']=pairs
    gates={}
    for k in report['simultaneous_improvement']:
        per={}
        for name in series:
            panel=report['panels'][name];p=audit[name]['policies'];r=panel['runs'][k]['full'];b=panel['runs']['B0']['full']
            per[name]=dict(double_cost_positive=p[k]['double_cost']['total']>0,
                double_cost_beats_baseline=p[k]['double_cost']['total']>p['B0']['double_cost']['total'],
                without_2025_beats_baseline=p[k]['without_2025_entries']['total']>p['B0']['without_2025_entries']['total'],
                both_stock_halves_positive=all(x['total']>0 for x in p[k]['stock_halves'].values()),
                late_2026_positive=panel['runs'][k]['periods']['late']['total']>0,
                late_2026_beats_baseline=panel['runs'][k]['periods']['late']['total']>panel['runs']['B0']['periods']['late']['total'],
                family_adjusted_significant=panel['uncertainty'][k]['family_adjusted_p']<.05)
        gates[k]=per
    for path,sha in plan['production_and_input_hashes'].items():assert hashlib.sha256((BASE/path).read_bytes()).hexdigest()==sha,path
    result=dict(plan_digest=digest(plan),results_digest=digest(report),panels=audit,robustness_gates=gates,production_or_input_changes=0,
        interpretation='Diagnostics only; no parameter refit. Price-paired cohorts are comparisons, not newly tradable strategies.')
    (OUT/'robustness.json').write_text(json.dumps(result,ensure_ascii=False,indent=1,allow_nan=False))
    print('GATES',json.dumps(gates,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
