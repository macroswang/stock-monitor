"""Offline, reproducible latency/parity checks against a disposable SQLite DB."""
import argparse,hashlib,json,statistics,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.app import App
from core.ma250_pullback import analyze,rule_spec
from core.market_regime import CODE,KIND,SOURCE
from research.ma250_breadth import load_panel
DATA=BASE/'docs'/'ma250-pullback'/'data'


def measure(fn,n=1):
    samples=[];result=None
    for _ in range(n):
        start=time.perf_counter();result=fn();samples.append((time.perf_counter()-start)*1000)
    ordered=sorted(samples)
    return dict(median_ms=statistics.median(samples),p95_ms=ordered[min(len(ordered)-1,int(len(ordered)*.95))],samples_ms=samples),result


def size_of(obj,seen=None):
    seen=set() if seen is None else seen
    if id(obj) in seen:return 0
    seen.add(id(obj));size=sys.getsizeof(obj)
    if isinstance(obj,dict):size+=sum(size_of(k,seen)+size_of(v,seen) for k,v in obj.items())
    elif isinstance(obj,(list,tuple,set)):size+=sum(size_of(v,seen) for v in obj)
    return size


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default=str(DATA.parent/'fixed-v3'/'performance.json'));a=p.parse_args()
    series=load_panel(DATA/'tencent');index=json.loads((DATA/'index'/'sh000300.json').read_text())['rows']
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((DATA/'tencent').glob('*.json'))}
    report=dict(rule=rule_spec(),stocks=len(series),bars=sum(map(len,series.values())),input_hashes=sources,
                index_input_hash=hashlib.sha256((DATA/'index'/'sh000300.json').read_bytes()).hexdigest(),
                detector_hash=hashlib.sha256((BASE/'core'/'ma250_pullback.py').read_bytes()).hexdigest(),
                environment=dict(python=sys.version.split()[0],platform=sys.platform),network_included=False)
    report['uncached_all'],_=measure(lambda:[analyze(b) for b in series.values()],3)
    with tempfile.TemporaryDirectory(prefix='ma250-benchmark-') as folder:
        app=App(folder,False);app.store.execute('DELETE FROM watch');app.store.execute("DELETE FROM cache WHERE kind='daily'")
        t=time.perf_counter()
        with app.store.lock,app.store.db:
            app.store.db.executemany('INSERT INTO watch(code,name) VALUES(?,?)',[(code,code) for code in series])
            app.store.db.executemany('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',
                ((code,'daily',b['date'],json.dumps(b,separators=(',',':'))) for code,bs in series.items() for b in bs))
        report['fixture_load_seconds']=time.perf_counter()-t
        app.store.cache(CODE,KIND,'latest',dict(rows=index,source=SOURCE))
        report['cold_scan'],result=measure(lambda:app.call('ma250_scan',dict(universe='watch',recent=5)))
        report['coverage']=result['coverage']
        misses=app.annual_signals.misses
        report['warm_scan'],_=measure(lambda:app.call('ma250_scan',dict(universe='watch',recent=5)),30)
        report['warm_additional_detections']=app.annual_signals.misses-misses
        code=max(series,key=lambda c:len(series[c]));report['cached_single'],_=measure(lambda:app.annual_signals.report(code),100)
        report['history_rpc'],_=measure(lambda:app.call('history',dict(code=code,start='2025-01-01',end='2026-11-13')),10)
        report['retained_cache_bytes']=size_of(app.annual_signals.memo);report['cache_entries']=len(app.annual_signals.memo)
        # On the whole panel, research rows must identify exactly the same client events.
        saved=json.loads((DATA.parent/'fixed-v3'/'tencent'/'report.json').read_text())
        key=lambda c,s:(c,s['date'],s['episode_id'],s['rule_id'],s['strong'],s['upgrade'])
        live={key(c,s) for c in series for s in app.annual_signals.report(c)['signals']}
        study={key(r['code'],r) for r in saved['signal_rows']}
        report['parity']=dict(client=len(live),research=len(study),differences=len(live^study))
        if live!=study:raise AssertionError('client/research event mismatch')
        breakout_key=lambda c,s:(c,s['date'],s['rule_id'],s['quality'],s['volume_ratio'],s['slope60_pct'])
        live_breakouts={breakout_key(c,s) for c in series for s in app.annual_signals.report(c)['breakouts']}
        study_breakouts={breakout_key(s['code'],s) for s in json.loads((DATA.parent/'fixed-v3'/'breakout.json').read_text())['rows']}
        report['breakout_parity']=dict(client=len(live_breakouts),research=len(study_breakouts),differences=len(live_breakouts^study_breakouts))
        if live_breakouts!=study_breakouts:raise AssertionError('client/research breakout mismatch')
        # A cold scan runs in a job; lightweight IPC remains callable during it.
        app.annual_signals.memo.clear();app.ma250_scan.memo.clear();latencies=[]
        dispatched=time.perf_counter();job=app.call('ma250_scan_start',dict(universe='watch',recent=5))
        report['job_dispatch_ms']=(time.perf_counter()-dispatched)*1000
        while True:
            t=time.perf_counter();state=app.call('job',job);latencies.append((time.perf_counter()-t)*1000)
            if state['status']!='running':break
            if time.perf_counter()-dispatched>60:raise AssertionError('scan job exceeded 60 seconds')
            time.sleep(.005)
        if state['status']!='done':raise AssertionError(state)
        latencies.sort();report['inprocess_job_poll_during_cold_scan']=dict(polls=len(latencies),median_ms=statistics.median(latencies),p95_ms=latencies[int(len(latencies)*.95)])
        report['cache_stats']=dict(hits=app.annual_signals.hits,misses=app.annual_signals.misses)
        app.store.db.close()
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=1))
    print(json.dumps({k:v for k,v in report.items() if k not in ('input_hashes','rule')},ensure_ascii=False,indent=1))

if __name__=='__main__':main()
