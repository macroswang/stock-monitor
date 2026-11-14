"""Independently reconcile filled-trade cash ledgers and publish the readout."""
import hashlib
import json
import math
import re
import shutil
import statistics
import sys
from collections import defaultdict
from pathlib import Path

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from research.ma250_e2_diagnostics import OUT,SOURCE,metrics,variants,write_report
from research.ma250_optimization import DATA,Portfolio
from research.ma250_breadth import load_panel


def independent_ledger(run,events,series):
    assert run['open_positions']==0,'reconciliation must include unsettled holdings'
    matching={(e['code'],e['episode_id'],e['entry_date'],e['exit_date']):e for e in events}
    entries=defaultdict(list);exits=defaultdict(list)
    for t in run['trades_detail']:
        assert t['exit_date']>t['entry_date']
        expected=t['exit']*(1-.0015)/(t['entry']*(1+.0015))-1
        assert abs(expected-t['net'])<1e-12
        profit=t['shares']*(t['exit']*(1-.0015)-t['entry']*(1+.0015))
        assert abs(profit-t['profit'])<1e-7
        e=matching[t['code'],t['episode_id'],t['entry_date'],t['exit_date']]
        row=dict(t,factor=e['factor'],last=t['entry'])
        entries[t['entry_date']].append(row);exits[t['exit_date']].append(row)
    prices={c:{b['date']:b['close'] for b in bars} for c,bars in series.items()}
    cash=1_000_000.;held={};peak=1_000_000.;dd=0.;exposures=[]
    for day,wanted,exposure in run['curve']:
        for t in entries[day]:
            assert t['code'] not in held
            cash-=t['shares']*t['entry']*(1+.0015);held[t['code']]=t
        for t in exits[day]:
            cash+=t['shares']*t['exit']*(1-.0015);del held[t['code']]
        invested=0.
        for c,t in held.items():
            if day in prices[c]:t['last']=prices[c][day]*t['factor']
            invested+=t['shares']*t['last']
        value=cash+invested
        assert abs(value-wanted)<1e-6,(day,value,wanted)
        assert abs(invested/value-exposure)<1e-12
        peak=max(peak,value);dd=min(dd,value/peak-1);exposures.append(invested/value)
    assert not held
    assert abs(dd*100-run['max_drawdown'])<1e-10
    assert abs((cash/1_000_000-1)*100-run['total'])<1e-10
    assert abs(statistics.mean(exposures)-run['exposure'])<1e-12
    return dict(curve_points=len(run['curve']),trades=len(run['trades_detail']))


def finish_report(report,cost):
    write_report(OUT,report)
    p=OUT/'report.md';text=p.read_text()
    intro='''**本轮结论更谨慎：E2 有筛选出较好交易的迹象，但还不足以证明稳定提高收益。前复权样本的回撤改善较大部分来自减少资金占用；与相近交易数量的随机筛选相比，收益并未明显突出。继续保留为研究候选，不替换当前年线提醒。**

'''
    text=text.replace('# E2 进一步研究：改善来源与执行敏感性\n\n','# E2 进一步研究：改善来源与执行敏感性\n\n'+intro)
    text+='''
## 同等买入加价的公平对照

初步压力测试只给 E2 加价；为避免把原规则理想成交与 E2 压力成交混比，另补充以下双方相同加价的控制。补充计划在计算本表前写入 `cost-control-plan.json`，未据此挑选新策略。

|样本|额外买入加价|原规则总收益|E2总收益|
|---|---:|---:|---:|
'''
    for name,rows in cost.items():
        for bp,pair in rows.items():text+=f"|{name}|{int(bp)/100:.2f}%|{pair['B0']['total']:+.2f}%|{pair['E2']['total']:+.2f}%|\n"
    text+='''
## 对后续优化方向的判断

1. **重点是减少无效信号，同时控制确认后的追价。** 前复权样本通过确认的67个源信号，按原时点买入均值+2.99%，等待确认后实际买入均值+0.94%；不是“等得更久所以收益更高”。该事后拆解不代表能在信号日提前知道哪些会确认。
2. **不要把回撤下降全部归功于信号质量。** 前复权原规则回撤-11.13%；将其平均资金占用压到与E2相近后，回撤已降到-6.87%，E2为-6.64%。未复权415只相同仓位对照回撤-14.09%，甚至小于E2的-15.29%。平均暴露相同仍不能完全匹配持仓时点，不能解释为严格因果比例。
3. **现阶段不应选择“最佳持有天数”或“最佳等待天数”。** 前复权持有10/20/40日收益分别+1.93%/+6.13%/+13.54%，回撤-5.46%/-6.64%/-11.02%；收益改善伴随风险上升。延迟两日的历史结果较高，但不是新样本证据，不能据此新增延迟两日规则。
4. **追价限制值得作为下一轮预先固定的假设，而不是已验证优化。** 按事先固定的分组，前复权买入价较原信号收盘高出3%以上的11个事件，结果弱于其余56个；但超过6%仅2个事件。样本太少，且已看过结果，不能立即把3%写成业务门槛或宣布能提高胜率。
5. **下一步最有价值的是冻结候选、补全历史股票范围与公司行为，再用新日期跟踪。** 继续在同一批数据组合条件，会增加挑中偶然结果的风险；本轮没有启用或修改任何现有提醒、检测参数和交易规则。

## 校验

原规则与E2重放逐日曲线及逐笔交易均与上一轮冻结结果一致。51个重放场景由实际成交明细独立重建资金账和每日权益；600次随机对照保留全部结果。新增6项边界测试与全量1176项测试通过。输入与业务代码哈希检查见 `validation.json`。
'''
    p.write_text(text)
    with p.open('a') as f:f.write('\n![相近资金占用下的收益与回撤](cash-control.png)\n')


def main():
    report=json.loads((OUT/'results.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    cost=json.loads((OUT/'cost-controls.json').read_text())
    raw=load_panel(DATA/'tencent');qfq=load_panel(DATA/'baostock-qfq');common=set(raw)&set(qfq)
    sessions=[b['date'] for b in json.loads((DATA/'index/sh000300.json').read_text())['rows']]
    for code,bs in qfq.items():
        rb={b['date']:b for b in raw[code]}
        for b in bs:
            if b['date'] in rb:b['execution']=rb[b['date']]
    audits={};points=trades=0
    for name,series in [('raw415',raw),('raw_matched217',{c:raw[c] for c in common}),('qfq217',qfq)]:
        es=json.loads((SOURCE/(name+'-events.json')).read_text());context=Portfolio(series)
        cases,_=variants(es['E2'],series,raw,sessions)
        cases.update(B0=es['B0'],E2=es['E2'])
        for bp in (25,50,100):
            for pid in ('B0','E2'):cases[f'{pid}_paired_plus_{bp}bp']=[dict(e,entry=e['entry']*(1+bp/10000)) for e in es[pid]]
        audits[name]={}
        for case,events in cases.items():
            run=context.run(events,details=True);v=independent_ledger(run,events,series)
            points+=v['curve_points'];trades+=v['trades'];audits[name][case]=v
            if case.startswith(('B0_paired','E2_paired')):
                pid,_,_,bps=case.split('_');expected=cost[name][bps[:-2]][pid]
            else:expected=report['panels'][name][{'B0':'baseline','E2':'candidate'}.get(case,'variants')]
            if case not in ('B0','E2') and '_paired_' not in case:expected=expected[case]
            assert metrics(run)==expected,(name,case)
        a=report['panels'][name]['attribution']
        assert abs(a['selection_mean_pp']+a['timing_and_rolled_exit_mean_pp']-a['total_mean_pp'])<1e-12
        accepted=a['accepted_baseline_counterfactual'];rejected=a['rejected_baseline_counterfactual'];all_=a['all_baseline']
        assert accepted['n']+rejected['n']==all_['n']
        assert abs((accepted['n']*accepted['mean']+rejected['n']*rejected['mean'])/all_['n']-all_['mean'])<1e-12
        random=report['panels'][name]['random_thinning'];assert len(random['runs'])==200
        for field,row in random['summaries'].items():
            values=sorted(x[field] for x in random['runs'])
            assert row['median']==statistics.median(values)
            assert row['fraction_random_at_or_above_e2']==sum(x>=row['e2'] for x in values)/200
    for rel,sha in plan['protected_hashes'].items():assert hashlib.sha256((BASE/rel).read_bytes()).hexdigest()==sha,rel
    log=Path('/tmp/ma250-e2-full-tests.log').read_text();assert re.search(r'Ran 1176 tests.*\n\nOK',log,re.S)
    shutil.copyfile('/tmp/ma250-e2-full-tests.log',OUT/'tests-full.log')
    files=[*BASE.joinpath('research').glob('ma250_e2_*.py'),BASE/'tests/test_ma250_e2_diagnostics.py']
    validation=dict(ledger_scenarios=sum(len(v) for v in audits.values()),independent_equity_points=points,
        independently_checked_closed_trades=trades,audits=audits,full_tests=1176,
        protected_files_unchanged=len(plan['protected_hashes']),
        source_hashes={str(f.relative_to(BASE)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        results_sha256=hashlib.sha256((OUT/'results.json').read_bytes()).hexdigest(),
        cost_controls_sha256=hashlib.sha256((OUT/'cost-controls.json').read_bytes()).hexdigest())
    (OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
    finish_report(report,cost)
    print({k:v for k,v in validation.items() if k not in ('source_hashes','audits')})


if __name__=='__main__':main()
