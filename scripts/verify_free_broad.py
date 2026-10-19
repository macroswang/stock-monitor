"""Offline audit of captured broad-sample evidence and calculation causality."""
import collections, hashlib, json, sys
from datetime import datetime
from decimal import Decimal as D
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.replay_free_broad import ROOT, GROUPS, QUOTAS, hashes, evaluate, confirmation
from core.provider import Tencent
from core.buy_supplement import TIMELINE
from scripts.replay_free_expanded import save, session

def run():
    report=json.loads((ROOT/'evaluation.json').read_text());frozen=report['frozen_pool']
    assert hashes()==frozen['rule_hashes']==report['hashes_before']==report['hashes_after']
    assert len(frozen['pool'])==1000==len({x['code'] for x in frozen['pool']})
    assert dict(collections.Counter(x['board'] for x in frozen['pool']))==QUOTAS
    checks=json.loads((ROOT/'quality.json').read_text())['checks']
    passed={(x['code'],x['date']) for x in checks if x.get('status')=='passed'}
    raw_hashes={};normalized={};days_checked=0;midday_checks=0;prefix_checks=0;score_checks=0
    for path in list((ROOT/'raw').glob('*.json'))+list((ROOT/'universe').glob('*.json')):
        captured=json.loads(path.read_text())
        assert hashlib.sha256(captured['body'].encode()).hexdigest()==captured['sha256']
        raw_hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for stock in frozen['pool']:
        code=stock['code'];path=ROOT/'normalized'/f'{code}.json'
        if not path.exists():continue
        data=json.loads(path.read_text());normalized[code]=data
        raw=json.loads(json.loads((ROOT/'raw'/f'{code}-minute.json').read_text())['body'])
        source={d['date']:d for d in raw['data'][code]['data']}
        for dt,day in data['minute'].items():
            assert (code,dt) in passed
            wrapped={'data':{code:{'data':[source[dt.replace('-','')]]}}}
            with patch('core.provider.get',return_value=json.dumps(wrapped)):
                adapter=Tencent().minutes(code,datetime.fromisoformat(report['created_at']))[0]
            inside=[b for b in adapter['bars'] if session(b['time'].replace(':',''))]
            assert inside==day['bars'],(code,dt,'normalized inputs changed')
            by={b['time']:b for b in inside}
            assert by['13:00']['volume']==0 and by['13:00']['average']==by['11:30']['average']
            midday_checks+=1;days_checked+=1
    assert days_checked==len(passed)
    for group,events in report['signals'].items():
        seen=set();times=collections.defaultdict(list)
        for e in events:
            assert e['identity'] not in seen;seen.add(e['identity'])
            times[(e['code'],e['date'])].append(e['time'])
            day=normalized[e['code']]['minute'][e['date']]
            prefix=dict(day,bars=[b for b in day['bars'] if b['time']<=e['time']])
            engine=confirmation if group in ('ES','EW') else evaluate
            r=engine(prefix,group,as_of=e['time'])
            assert any(x['time']==e['time'] and e['identity'].endswith('|'+x['key']) for x in r['signals'])
            prefix_checks+=1
            if e['entry_price'] is not None:
                tm=TIMELINE[TIMELINE.index(e['time'])+1]
                by={b['time']:b for b in day['bars']}
                assert e['entry_time']==tm and D(str(e['entry_price']))==D(by[tm]['close'])
            if e['net_pct'] is not None:
                exact=(D(str(e['next_close']))*D('.999')/(D(str(e['entry_price']))*D('1.001'))-1)*100-D('.1')
                assert abs(float(exact)-e['net_pct'])<1e-10
                score_checks+=1
        for key,labels in times.items():
            labels.sort()
            assert all(TIMELINE.index(b)-TIMELINE.index(a)>=10 for a,b in zip(labels,labels[1:])),(group,key,labels)
        completed=[e for e in events if e['net_pct'] is not None]
        stats=report['summary'][group]['all']
        assert stats['samples']==len(completed)
        assert stats['wins']==sum(e['net_pct']>0 for e in completed)
    result=dict(created_at=report['created_at'],core_hashes_unchanged=True,pool_unique=1000,
        board_quotas=QUOTAS,raw_responses_hash_checked=len(raw_hashes),raw_sha256=raw_hashes,
        stock_days_adapter_inputs_identical=days_checked,midday_carry_checks=midday_checks,
        confirmed_signals_prefix_causality_checked=prefix_checks,completed_net_scores_independently_checked=score_checks,
        cooldown_and_structure_dedup_checked=True,all_group_denominators_checked=True,
        notifications_sent=0)
    save(ROOT/'verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='raw_sha256'},ensure_ascii=False,indent=2))

if __name__=='__main__':run()
