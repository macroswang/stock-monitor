"""Independent before/after and causal-prefix audit. No user data or fitting."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import types

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.app import App
from core.ma250_pullback import analyze,prepare
from core.ma250_e2 import analyze as e2_analyze
from research.ma250_breadth import load_panel,sma
from research.ma250_execution import close_exit
from research.ma250_optimization import research_entry,Portfolio

OUT=BASE/'docs/production-0.6.99';DATA=BASE/'docs/ma250-pullback/data'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def previous_module(name,original,package=''):
    module=types.ModuleType(name);module.__file__=str(BASE/original);module.__package__=package
    sys.modules[name]=module
    source=(OUT/'baseline'/original.replace('/','__')).read_text()
    exec(compile(source,module.__file__,'exec'),module.__dict__)
    return module


def main():
    legacy=previous_module('e2_before_replay','research/ma250_optimization.py')
    previous=previous_module('core._e2_before_review','core/ma250_e2.py','core')
    index=json.loads((DATA/'index/sh000300.json').read_text())['rows'];line=sma([r['close'] for r in index],250)
    market={b['date']:b['close']>line[i] if line[i] is not None else None for i,b in enumerate(index)};sessions=sorted(market)
    raw,qfq=load_panel(DATA/'tencent'),load_panel(DATA/'baostock-qfq')
    for code,bars in qfq.items():
        lookup={b['date']:b for b in raw[code]}
        for b in bars:
            if b['date'] in lookup:b['execution']=lookup[b['date']]
    frozen_root=DATA.parent/'optimization-v4-20261114';frozen=json.loads((frozen_root/'results.json').read_text())
    official_before=json.loads((BASE/'docs/production-0.6.98/formal-before.json').read_text())
    report={'panels':{},'boundaries':'confirmation independent of future execution; verified-calendar holes do not extend the window'}
    for name,series in [('raw415',raw),('qfq217',qfq)]:
        reports={};prefixes=executions=confirmations=0;new_events=[];cold_e2=0.;started=time.perf_counter()
        for code,bars in series.items():
            r=reports[code]=analyze(bars,market);f=prepare(bars);positions={b['date']:i for i,b in enumerate(bars)}
            t=time.perf_counter();now=e2_analyze(bars,market,formal=r);cold_e2+=time.perf_counter()-t
            assert digest(now['signals'])==digest(previous.analyze(bars,market,formal=r)['signals']),(name,code,'display signal changed')
            confirmations+=len(now['signals'])
            sources=[s for s in r['signals'] if s['strong'] or (s['market_above'] is True and not s['upgrade'])]
            for s in sources:
                i=positions[s['date']]
                old=legacy.research_entry(code,bars,f,i,s,'break3',sessions,market)
                new=research_entry(code,bars,f,i,s,'break3',sessions,market)
                assert old==new,(name,code,s['date'],old,new)
                executions+=1
                if not s['strong'] or new['index'] is None:continue
                exit_=close_exit(bars,new['index'],20,sessions)
                rawbar=next(b for b in raw[code] if b['date']==new['date']);factor=rawbar['open']/new['price']
                new_events.append(dict(code=code,signal_date=s['date'],episode_id=s['episode_id'],policy='E2',
                    entry_date=new['date'],entry=rawbar['open'],exit_date=exit_['date'],exit_phase='close',
                    exit_price=exit_['price']*factor if exit_['price'] is not None else None,factor=factor,
                    strong=s['strong'],stop=s['stop']*factor,atr=s['atr20_pct'],sizing='equal',
                    reference_entry=new['price'],exit_status=exit_['status']))
            cutoffs={min(len(bars)-1,positions[s['date']]+offset) for s in r['signals'] if s['strong'] for offset in range(5)}
            for cutoff in sorted(cutoffs):
                prefix=bars[:cutoff+1];end=prefix[-1]['date'];past_market={d:v for d,v in market.items() if d<=end}
                wanted=[s for s in now['signals'] if s['date']<=end]
                actual=e2_analyze(prefix,past_market)['signals']
                assert digest(actual)==digest(wanted),(name,code,end,'prefix redraw')
                assert digest(e2_analyze(prefix,market)['signals'])==digest(wanted),(name,code,end,'future index dependence')
                prefixes+=1
        assert digest(reports)==official_before['panels'][name]['digest'],name+' official signal drift'
        archived=json.loads((frozen_root/f'{name}-events.json').read_text())
        new_events.sort(key=lambda e:(e['code'],e['signal_date']))
        assert digest(new_events)==digest(archived['E2']),name+' execution records changed'
        context=Portfolio(series);metrics={}
        for pid,events in [('B0',archived['B0']),('E2',new_events)]:
            run=context.run(events,details=True)
            assert digest(run)==digest(frozen['panels'][name]['runs'][pid]['full']),(name,pid,'portfolio changed')
            metrics[pid]={k:run[k] for k in ['total','win','max_drawdown','trades']}
        report['panels'][name]=dict(prefix_checks=prefixes,future_market_checks=prefixes,
            legacy_entry_checks=executions,e2_confirmations=confirmations,official_digest=digest(reports),
            signals_and_execution_exact=True,portfolio_metrics_exact=True,portfolio=metrics,
            cold_extra_e2_seconds=cold_e2,elapsed_seconds=time.perf_counter()-started)
        print(name,report['panels'][name],flush=True)
    plan=json.loads((OUT/'review-plan.json').read_text())
    for p,sha in plan['protected_hashes'].items():assert hashlib.sha256((BASE/p).read_bytes()).hexdigest()==sha,p
    with tempfile.TemporaryDirectory() as folder:
        app=App(folder,False);app.market_regime.above_map=lambda:market
        for b in raw['sh600000']:app.store.cache('sh600000','daily',b['date'],b)
        tables=['events','delivery','local_delivery','ma250_journal','trading_runs','broker_requests']
        before={t:app.store.query('SELECT * FROM '+t) for t in tables}
        t=time.perf_counter();app.annual_signals.research_report('sh600000');cold=time.perf_counter()-t;warm=[]
        for _ in range(100):
            t=time.perf_counter();app.annual_signals.research_report('sh600000');warm.append(time.perf_counter()-t)
        assert {t:app.store.query('SELECT * FROM '+t) for t in tables}==before
        report['performance']=dict(cold_ms=cold*1000,warm_median_ms=statistics.median(warm)*1000,warm_p95_ms=sorted(warm)[94]*1000)
        app.stop.set();app.store.db.close()
    report['protected_business_files_unchanged']=len(plan['protected_hashes'])
    (OUT/'deep-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('REVIEW',OUT/'deep-review.json',flush=True)


if __name__=='__main__':main()
