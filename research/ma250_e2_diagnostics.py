"""Research-only E2 attribution and execution sensitivity; no new signal rules.

Accepted/rejected counterfactual cohorts and equal-exposure cash blends use
future confirmation/full-sample information. They are diagnostics, never
tradable strategies or independent out-of-sample validation.
"""
import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from research.ma250_optimization import (DATA, OUT as SOURCE, START, END, Portfolio,
                                         digest, old_summary)
from research.ma250_breadth import load_panel
from research.ma250_execution import entry_for, close_exit, net_pct

OUT = SOURCE.parent / 'e2-diagnostics-20261114'
PANEL_NAMES = ('raw415', 'raw_matched217', 'qfq217')
REPETITIONS = 200


def key(event):
    return event['code'], event['signal_date'], event['episode_id']


def freeze(out):
    old = json.loads((SOURCE / 'plan.json').read_text())
    hashes = dict(old['production_and_input_hashes'])
    drift=[]
    for rel,sha in list(hashes.items()):
        current=(BASE/rel).read_bytes()
        if hashlib.sha256(current).hexdigest()==sha:continue
        # The user committed a version-display repair since v4. Prove the
        # COMPLETE difference before reusing its archived signal/event inputs.
        assert rel=='core/app.py', ('unreviewed source drift',rel)
        previous=current.decode().replace('from .version import VERSION\n','').replace('version=VERSION',"version='0.6.64'")
        assert hashlib.sha256(previous.encode()).hexdigest()==sha, ('unexpected app change',rel)
        drift.append(dict(path=rel,change='only imported core.version.VERSION and replaced hardcoded snapshot version',
                          previous_sha256=sha,current_sha256=hashlib.sha256(current).hexdigest()))
        hashes[rel]=hashlib.sha256(current).hexdigest()
    for p in [*BASE.joinpath('core').glob('*.py'),*BASE.joinpath('src').glob('*')]:
        if p.is_file():hashes[str(p.relative_to(BASE))]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in [SOURCE / 'results.json', SOURCE / 'robustness.json',
              *[SOURCE / (name + '-events.json') for name in PANEL_NAMES]]:
        hashes[str(p.relative_to(BASE))] = hashlib.sha256(p.read_bytes()).hexdigest()
    for rel, sha in hashes.items():
        assert hashlib.sha256((BASE / rel).read_bytes()).hexdigest() == sha, rel
    plan = dict(created_at=datetime.now().astimezone().isoformat(),
        end=END, start=START, source_rule=old['rule'], protected_hashes=hashes, reviewed_since_v4_drift=drift,
        questions=['same-signal selection vs entry timing attribution',
                   'drawdown vs cash/exposure reduction and random thinning',
                   'execution delay and fixed 10/20/40-session horizon sensitivity'],
        variants=['E2 hold10', 'E2 hold20', 'E2 hold40',
                  'E2 hold20 +1 session delay', 'E2 hold20 +2 sessions delay',
                  'E2 hold20 +3 sessions delay',
                  'E2 hold20 +25bp entry price', 'E2 hold20 +50bp entry price',
                  'E2 hold20 +100bp entry price'],
        costs_one_way=.0015, slots=10,
        random_thinning=dict(repetitions=REPETITIONS, seed=25011,
                             strata='original signal calendar year',
                             count='same number as E2 matched to entered B0 source events per year'),
        cash_control='B0 full-sample cash blend matched to E2 average capital exposure; fractional and ex post, diagnostic only',
        attribution='only mature B0/E2 pairs; accepted B0 cohort known after signal, never tradable; arithmetic not causal',
        execution='fixed confirmation, delay 0/1/2/3 verified sessions; exact scheduled next open only, no retry or recheck; hold horizon restarts at actual entry; raw tradability and T+1',
        limitations=['existing current-listed panel, survivorship bias',
                     'all dates previously researched, no fresh OOS',
                     'qfq normalized raw-lot return proxy, no corporate-action cash ledger',
                     'entry price stress is hypothetical, not an observed fill',
                     'random thinning percentile is descriptive, not selection-adjusted significance'])
    out.mkdir(parents=True, exist_ok=True)
    p = out / 'plan.json'
    if p.exists():
        saved = json.loads(p.read_text())
        assert {k:v for k,v in saved.items() if k!='created_at'} == {k:v for k,v in plan.items() if k!='created_at'}
        return saved
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    return plan


def mature(e):
    return bool(e['exit_date'] and e['exit_date'] <= END)


def stats(events):
    values = [net_pct(e['entry'], e['exit_price']) for e in events if mature(e)]
    return dict(n=len(values), mean=statistics.mean(values) if values else None,
                median=statistics.median(values) if values else None,
                win=sum(v>0 for v in values)/len(values) if values else None)


def attribution(baseline, candidate):
    b, c = {key(e):e for e in baseline}, {key(e):e for e in candidate}
    assert len(b)==len(baseline) and len(c)==len(candidate), 'duplicate source signal'
    keys = sorted(k for k in b.keys() & c.keys() if mature(b[k]) and mature(c[k]))
    accepted = [b[k] for k in keys]
    actual = [c[k] for k in keys]
    rejected = [e for k,e in b.items() if k not in c and mature(e)]
    all_b = [e for e in baseline if mature(e)]
    pre, post, full = stats(accepted), stats(actual), stats(all_b)
    selection = pre['mean']-full['mean'] if keys else None
    timing = post['mean']-pre['mean'] if keys else None
    return dict(all_baseline=full, accepted_baseline_counterfactual=pre,
        rejected_baseline_counterfactual=stats(rejected), accepted_e2=post,
        selection_mean_pp=selection, timing_and_rolled_exit_mean_pp=timing,
        total_mean_pp=post['mean']-full['mean'] if keys else None,
        candidate_only_sources=len(c.keys()-b.keys()),
        baseline_unpaired_maturity=sum(k in c and not (mature(e) and mature(c[k])) for k,e in b.items()),
        accepted_keys=[list(k) for k in keys])


def cash_blend(curve, weight):
    result=[]
    for day,equity,exposure in curve:
        value=1_000_000+weight*(equity-1_000_000)
        result.append((day,value,weight*equity*exposure/value))
    return result


def exposure_control(baseline, candidate):
    target=statistics.mean(row[2] for row in candidate)
    assert target <= statistics.mean(row[2] for row in baseline), 'would require leverage'
    low, high=0.,1.
    for _ in range(60):
        mid=(low+high)/2
        if statistics.mean(r[2] for r in cash_blend(baseline,mid))>target:high=mid
        else:low=mid
    weight=(low+high)/2
    curve=cash_blend(baseline,weight)
    return dict(weight=weight, target_exposure=target,
                result=old_summary(curve,[],START,END), curve=curve)


def thinning(context, baseline, candidate, repetitions=REPETITIONS):
    groups=defaultdict(list);candidate_keys={key(e) for e in candidate}
    for e in baseline:groups[e['signal_date'][:4]].append(e)
    counts=Counter(e['signal_date'][:4] for e in baseline if key(e) in candidate_keys)
    rng=random.Random(25011);runs=[]
    for _ in range(repetitions):
        selected=[]
        for year,items in sorted(groups.items()):selected.extend(rng.sample(items,counts[year]))
        selected.sort(key=lambda e:(e['code'],e['signal_date']))
        runs.append(context.run(selected))
    actual=context.run(candidate)
    result={}
    for field in ('total','max_drawdown','win','exposure'):
        values=sorted(r[field] for r in runs if r[field] is not None)
        # Empirical order statistics, not an inferential confidence interval.
        result[field]=dict(p05=values[math.floor(.05*(len(values)-1))],
            median=statistics.median(values),p95=values[math.ceil(.95*(len(values)-1))],
            e2=actual[field],fraction_random_at_or_above_e2=sum(v>=actual[field] for v in values)/len(values))
    return dict(year_counts=dict(sorted(counts.items())), matched_source_count=sum(counts.values()),
                candidate_sources=len(candidate), repetitions=repetitions, summaries=result, runs=runs)


def reschedule(event, bars, raw_bars, sessions, delay=0, hold=20):
    """Frozen confirmation; intentionally stale delayed-order stress, not retry."""
    by_date={b['date']:i for i,b in enumerate(bars)}
    si=bisect_left(sessions,event['entry_date'])+delay
    if si>=len(sessions):return None,'pending_entry'
    target=sessions[si];i=by_date.get(target)
    if i is None or i==0:return None,'entry_unavailable'
    entry=entry_for(bars,i-1,event['code'],sessions)
    if entry['index'] is None:return None,entry['status']
    out=close_exit(bars,i,hold,sessions)
    factor=raw_bars[target]['open']/bars[i]['open']
    new=dict(event,entry_date=target,entry=raw_bars[target]['open'],
             reference_entry=bars[i]['open'],factor=factor,
             stop=event['stop']/event['factor']*factor,
             exit_date=out['date'],exit_price=out['price']*factor if out['price'] is not None else None,
             exit_status=out['status'],exit_phase='close')
    return new,'entered'


def variants(events, series, raw, sessions):
    result={};coverage={}
    raw_by_date={c:{b['date']:b for b in bs} for c,bs in raw.items() if c in series}
    for hold,delay in [(10,0),(20,0),(40,0),(20,1),(20,2),(20,3)]:
        name=f'hold{hold}_delay{delay}';selected=[];counts=Counter()
        for e in events:
            row,status=reschedule(e,series[e['code']],raw_by_date[e['code']],sessions,delay,hold)
            counts[status]+=1
            if row:selected.append(row)
        result[name]=selected;coverage[name]=dict(counts)
    for bp in (25,50,100):
        result[f'entry_plus_{bp}bp']=[dict(e,entry=e['entry']*(1+bp/10000)) for e in events]
        coverage[f'entry_plus_{bp}bp']={'entered':len(events)}
    return result,coverage


def split_diagnostics(baseline,candidate,series,sessions):
    b={key(e):e for e in baseline};groups=defaultdict(list);rows=[]
    for e in candidate:
        code=e['code'];bars=series[code];by_date={x['date']:i for i,x in enumerate(bars)}
        signal=bars[by_date[e['signal_date']]]
        chase=(e['reference_entry']/signal['close']-1)*100
        lag=bisect_left(sessions,e['entry_date'])-bisect_left(sessions,e['signal_date'])-1
        groups['confirmation_day_'+str(lag)].append(e)
        groups['entry_vs_signal_close_'+('le3pct' if chase<=3 else '3to6pct' if chase<=6 else 'gt6pct')].append(e)
        source=b.get(key(e));same_exit=None
        if source and source['exit_date'] and source['exit_date']>e['entry_date'] and source['exit_date'] in by_date:
            price=bars[by_date[source['exit_date']]]['close']*e['factor']
            same_exit=net_pct(e['entry'],price)
        rows.append(dict(code=code,signal_date=e['signal_date'],year=e['signal_date'][:4],
            confirmation_day=lag,chase_pct=chase,
            b0=net_pct(source['entry'],source['exit_price']) if source and mature(source) else None,
            e2=net_pct(e['entry'],e['exit_price']) if mature(e) else None,
            e2_same_b0_exit=same_exit))
    paired=[r for r in rows if all(r[k] is not None for k in ('b0','e2','e2_same_b0_exit'))]
    means={k:statistics.mean(r[k] for r in paired) if paired else None for k in ('b0','e2','e2_same_b0_exit')}
    return dict(groups={k:stats(v) for k,v in sorted(groups.items())},paired_exit_attribution=dict(n=len(paired),means=means),rows=rows)


def metrics(run):
    return {k:run[k] for k in ('trades','win','total','cagr','max_drawdown','exposure','open_positions')}


def write_report(out,report):
    lines=['# E2 进一步研究：改善来源与执行敏感性','',
        '范围：2019-01-01 至 2026-11-13；沿用 v3 信号与上一轮 E2，单边成本 0.15%，10 个持仓位。现有业务规则未修改。',
        '三组样本有重合，均为既有历史数据；不是三份独立验证，也不是新的样本外证据。', '',
        '## 同一信号的收益拆解','',
        '下表都是逐信号净收益均值，不是组合总收益。确认通过/未通过使用事后分组，只用于解释，不可在原信号日提前使用。', '',
        '|样本|全部原信号|E2通过组按原时点买|E2未通过组按原时点买|通过组按E2买|筛选差值|入场与退出日期平移差值|',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,p in report['panels'].items():
        a=p['attribution'];vals=[a['all_baseline'],a['accepted_baseline_counterfactual'],a['rejected_baseline_counterfactual'],a['accepted_e2']]
        cells=[f"{v['mean']:+.2f}%（{v['n']}）" if v['mean'] is not None else '无成熟样本' for v in vals]
        lines.append('|'+name+'|'+'|'.join(cells)+f"|{a['selection_mean_pp']:+.2f}pp|{a['timing_and_rolled_exit_mean_pp']:+.2f}pp|")
    lines+=['','## 相同平均资金暴露的现金对照','',
        '将原组合收益曲线与零收益现金混合，按全样本平均仓位反求比例。该对照允许小数仓位、使用事后比例，不是可直接实施的规则；不改变原交易胜率。', '',
        '|样本|原规则收益/回撤|等暴露原规则收益/回撤|E2收益/回撤|E2平均仓位|',
        '|---|---:|---:|---:|---:|']
    for name,p in report['panels'].items():
        def cell(r):return f"{r['total']:+.2f}% / {r['max_drawdown']:.2f}%"
        lines.append(f"|{name}|{cell(p['baseline'])}|{cell(p['cash_control']['result'])}|{cell(p['candidate'])}|{p['candidate']['exposure']*100:.2f}%|")
    lines+=['','## 执行与持有期敏感性','',
        '延迟从原 E2 入场日顺延指定交易日，固定原确认、无重新检查，仅该日开盘尝试；不可成交则放弃，持有期从实际入场重算。加价压力是假设买入价格上浮，不是历史真实成交。', '',
        '|样本|情景|已平仓笔数|胜率|总收益|最大回撤|', '|---|---|---:|---:|---:|---:|']
    for name,p in report['panels'].items():
        for label,r in p['variants'].items():
            lines.append(f"|{name}|{label}|{r['trades']}|{r['win']*100:.1f}%|{r['total']:+.2f}%|{r['max_drawdown']:.2f}%|")
    lines+=['','## 随机减少交易对照','',
        '对原规则按原信号年份分层，随机保留与 E2 匹配源信号相同的笔数，200 次固定种子重放。保留事件笔数相近不等于仓位或成交笔数完全相等。以下为经验分位，不是显著性检验。', '',
        '|样本|随机收益5%分位|随机收益中位数|随机收益95%分位|E2收益|随机不低于E2比例|', '|---|---:|---:|---:|---:|---:|']
    for name,p in report['panels'].items():
        x=p['random_thinning']['summaries']['total']
        lines.append(f"|{name}|{x['p05']:+.2f}%|{x['median']:+.2f}%|{x['p95']:+.2f}%|{x['e2']:+.2f}%|{x['fraction_random_at_or_above_e2']*100:.1f}%|")
    lines+=['','## 同事件、同退出日期的拆解','',
        '只保留三种路径均可计算的成熟匹配事件。中间列使用 E2 买入时点、原规则退出日；用于区分买贵/买便宜与退出日期延后的账面贡献。', '',
        '|样本|匹配数|原入场/原退出|E2入场/原退出|E2入场/E2退出|', '|---|---:|---:|---:|---:|']
    for name,p in report['panels'].items():
        x=p['splits']['paired_exit_attribution'];v=x['means']
        lines.append(f"|{name}|{x['n']}|{v['b0']:+.2f}%|{v['e2_same_b0_exit']:+.2f}%|{v['e2']:+.2f}%|")
    lines+=['','## 适用边界','',
        '- 本轮为对既有 E2 的诊断与有限敏感性检验，不能据此选择最优持有期或新阈值。',
        '- 当前上市股票固定样本有幸存者偏差；原始价格可能受除权影响，前复权使用原价股数归一化收益代理，未模拟完整公司行为现金账本。',
        '- 降低回撤、提高胜率与提高收益不必同时成立；原信号后的分组、现金混合与随机对照都不可当作新的实时信号。',
        '- 实际成交、资金容量、历史 ST、完整停牌深度未验证；全部结论仍是日线历史模拟。',
        '', '复现：`.venv/bin/python research/ma250_e2_diagnostics.py`。参数冻结与输入哈希见同目录 `plan.json`；逐事件拆解与所有随机结果见 `results.json`。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan-only',action='store_true');args=parser.parse_args()
    plan=freeze(OUT)
    if args.plan_only:print('Frozen',OUT/'plan.json');return
    started=time.perf_counter();raw=load_panel(DATA/'tencent');qfq=load_panel(DATA/'baostock-qfq')
    common=set(raw)&set(qfq);index=json.loads((DATA/'index/sh000300.json').read_text())['rows'];sessions=[b['date'] for b in index]
    for code,bars in qfq.items():
        raw_dates={b['date']:b for b in raw[code]}
        for b in bars:
            if b['date'] in raw_dates:b['execution']=raw_dates[b['date']]
    source=json.loads((SOURCE/'results.json').read_text());report=dict(plan_digest=digest(plan),panels={})
    for name,series in [('raw415',raw),('raw_matched217',{c:raw[c] for c in common}),('qfq217',qfq)]:
        events=json.loads((SOURCE/(name+'-events.json')).read_text());base,candidate=events['B0'],events['E2'];context=Portfolio(series)
        b=context.run(base,details=True);c=context.run(candidate,details=True)
        for pid,run in [('B0',b),('E2',c)]:
            frozen=source['panels'][name]['runs'][pid]['full']
            assert digest(run)==digest(frozen),(name,pid,'baseline drift')
        es,coverage=variants(candidate,series,raw,sessions)
        same=context.run(es['hold20_delay0'],details=True)
        assert same['curve']==c['curve'] and same['trades_detail']==c['trades_detail'],'reconstructed E2 mismatch'
        results={k:metrics(context.run(v)) for k,v in es.items()}
        random_runs=thinning(context,base,candidate)
        p=dict(baseline=metrics(b),candidate=metrics(c),attribution=attribution(base,candidate),
               cash_control=exposure_control(b['curve'],c['curve']),random_thinning=random_runs,
               variants=results,variant_coverage=coverage,splits=split_diagnostics(base,candidate,series,sessions),
               exact_frozen_parity=True)
        report['panels'][name]=p
        print('DONE',name,round(time.perf_counter()-started,1),'seconds',flush=True)
    for rel,sha in plan['protected_hashes'].items():assert hashlib.sha256((BASE/rel).read_bytes()).hexdigest()==sha,rel
    report['protected_files_unchanged']=len(plan['protected_hashes']);report['elapsed_seconds']=time.perf_counter()-started
    report['research_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=1,allow_nan=False))
    write_report(OUT,report)
    print('REPORT',OUT/'report.md',flush=True)


if __name__=='__main__':main()
