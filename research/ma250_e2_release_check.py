"""Release parity checks only; no strategy fitting and no user DB access."""
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.app import App
from core.ma250_pullback import analyze,prepare,rule_spec
from core.ma250_e2 import analyze as e2_analyze,research_spec
from research.ma250_breadth import load_panel,sma
from research.ma250_optimization import research_entry

OUT=BASE/'docs/production-0.6.98'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def main():
    before=json.loads((OUT/'formal-before.json').read_text());data=BASE/'docs/ma250-pullback/data'
    index=json.loads((data/'index/sh000300.json').read_text())['rows'];line=sma([b['close'] for b in index],250)
    market={b['date']:b['close']>line[i] if line[i] is not None else None for i,b in enumerate(index)};sessions=sorted(market)
    proof=dict(formal_rule=rule_spec(),research_rule=research_spec(),panels={})
    assert proof['formal_rule']==before['rule']
    for label,folder in [('raw415','tencent'),('qfq217','baostock-qfq')]:
        series=load_panel(data/folder);formal={};new=[];expected=[];formal_time=e2_time=0.
        for code,bars in series.items():
            t=time.perf_counter();formal[code]=r=analyze(bars,market);formal_time+=time.perf_counter()-t
            t=time.perf_counter();result=e2_analyze(bars,market,formal=r);e2_time+=time.perf_counter()-t
            assert not result['error'],(code,result['error'])
            for s in result['signals']:
                new.append((code,s['source_date'],s['date'],s['close'],s['source_high'],s['stop']))
            if not any(s['strong'] for s in r['signals']):continue
            f=prepare(bars);positions={b['date']:i for i,b in enumerate(bars)}
            for s in r['signals']:
                if not s['strong']:continue
                e=research_entry(code,bars,f,positions[s['date']],s,'break3',sessions,market)
                if e['index'] is not None:
                    j=e['index']-1;expected.append((code,s['date'],bars[j]['date'],bars[j]['close'],bars[positions[s['date']]]['high'],s['stop']))
        assert digest(formal)==before['panels'][label]['digest'],label+' formal outputs drifted'
        assert sorted(new)==sorted(expected),(label,'E2 vs archived entry rule mismatch',set(new)^set(expected))
        frozen=json.loads((data.parent/'optimization-v4-20261114'/f'{label}-events.json').read_text())['E2']
        assert {(c,s) for c,s,*_ in new}=={(e['code'],e['signal_date']) for e in frozen}
        proof['panels'][label]=dict(formal_signals=sum(len(r['signals']) for r in formal.values()),
            formal_breakouts=sum(len(r['breakouts']) for r in formal.values()),formal_digest=digest(formal),
            e2_confirmations=len(new),exact_legacy_parity=True,formal_seconds=formal_time,e2_extra_seconds=e2_time)
        print(label,proof['panels'][label],flush=True)
        if label=='raw415':sample=(series[next(c for c in series if any(row[0]==c for row in new))],market)
    for p,sha in before['protected_hashes'].items():assert hashlib.sha256((BASE/p).read_bytes()).hexdigest()==sha,p
    with tempfile.TemporaryDirectory() as directory:
        app=App(directory,False);bars,market=sample;app.market_regime.above_map=lambda:market
        for b in bars:app.store.cache('sh600000','daily',b['date'],b)
        before_rows={t:app.store.query('SELECT * FROM '+t) for t in ('events','ma250_journal','trading_runs','broker_requests')}
        t=time.perf_counter();original=app.annual_signals.research_report('sh600000');cold=time.perf_counter()-t
        times=[]
        for _ in range(100):
            t=time.perf_counter();assert app.annual_signals.research_report('sh600000') is original;times.append(time.perf_counter()-t)
        assert {t:app.store.query('SELECT * FROM '+t) for t in before_rows}==before_rows
        proof['service_performance']=dict(cold_ms=cold*1000,warm_median_ms=statistics.median(times)*1000,warm_p95_ms=sorted(times)[94]*1000)
        app.stop.set();app.store.db.close()
    proof['unchanged_protected_files']=len(before['protected_hashes']);proof['business_outputs_unchanged']=True
    (OUT/'e2-parity.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    print(proof['service_performance'],flush=True)


if __name__=='__main__':main()
