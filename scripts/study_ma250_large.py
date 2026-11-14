"""Frozen shared-detector study. Existing history is exploratory, not fresh OOS."""
import argparse, hashlib, json, random, statistics, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from core.ma250_pullback import rule_spec
from research.ma250_breadth import load_panel
from research.ma250_pullback_lab import candidates,clean_bars,index_features,trend_baseline
from research.ma250_execution import COST_PCT
DATA=BASE/'docs'/'ma250-pullback'/'data'
SPLIT='2024-01-01'


def load(panel=DATA/'tencent'):
    series,missing={},[]
    for code,bars in load_panel(panel).items():
        try:bars=clean_bars(bars)
        except (KeyError,ValueError,TypeError) as error:
            missing.append(dict(code=code,error=str(error)));continue
        if len(bars)>=310:series[code]=bars
        else:missing.append(dict(code=code,error='insufficient_history'))
    if Path(panel).name != 'tencent':
        raw_panel=load_panel(DATA/'tencent')
        for code,bars in series.items():
            raw_dates={r['date']:r for r in raw_panel.get(code,[])}
            for bar in bars:
                if bar['date'] in raw_dates:bar['execution']=raw_dates[bar['date']]
    raw=json.loads((DATA/'index'/'sh000300.json').read_text())['rows']
    manifest=dict(sample=Path(panel).name,start=min(b[0]['date'] for b in series.values()),
                  end=max(b[-1]['date'] for b in series.values()),codes=len(series))
    return manifest,series,index_features(raw),missing


def build(series,index_map):
    rows,baseline=[],[]
    for code,bars in sorted(series.items()):
        rows.extend(candidates(code,bars,index_map));baseline.extend(trend_baseline(code,bars,index_map))
    return rows,baseline


def mean(values):return statistics.mean(values) if values else None

def apply_variant(table,predicate,cooldown=None):
    # Detection and cooldown belong exclusively to core.ma250_pullback.
    return [row for row in table if predicate(row)]

def base(row):return row.get('kind','pullback')=='pullback' and not row.get('upgrade',False)

VARIANTS=[('V0 首次收回观察',base),
          ('V1 指数在年线上',lambda r:base(r) and r['market_above'] is True),
          ('V29 强提醒（含升级）',lambda r:r['strong'])]


def uncertainty(rows):
    groups=defaultdict(list)
    for r in rows:
        if r['forward']['20'] is not None:groups[r['date'][:7]].append(r['forward']['20'])
    if len(groups)<2:return None
    blocks=list(groups.values());rng=random.Random(250);means=[]
    for _ in range(400):
        values=[v for block in rng.choices(blocks,k=len(blocks)) for v in block]
        means.append(statistics.mean(values))
    means.sort();return [means[10],means[-11]]


def metrics(rows,label_cutoff=None):
    out=dict(signals=len(rows),pending_entry=sum(r['execution_status']=='pending_entry' for r in rows),
             unavailable_entry=sum(r['execution_status']=='entry_unavailable' for r in rows),
             upgrades=sum(r.get('upgrade',False) for r in rows),
             corporate_action_flags=sum(bool(r.get('corporate_action_flag')) for r in rows))
    for h in (5,10,20,60):
        values=[r['forward'][str(h)] for r in rows if r['forward'][str(h)] is not None
                and (label_cutoff is None or (r['exits'][str(h)]['date'] or '9999')<label_cutoff)]
        out.update({f'n{h}':len(values),f'mean{h}':mean(values),
                    f'win{h}':sum(v>0 for v in values)/len(values) if values else None})
    values=[r['forward']['20'] for r in rows if r['forward']['20'] is not None]
    path=[r['path_outcome'] for r in rows if r['path_outcome'] is not None
          and (label_cutoff is None or (r.get('path_label_end') or '9999')<label_cutoff)]
    out.update(median20=statistics.median(values) if values else None,mean20_ci=uncertainty(rows),
               pending20=sum(r['execution_status']=='entered' and r['forward']['20'] is None for r in rows),
               path_win=path.count('target')/len(path) if path else None,n_path=len(path),
               excess20=mean([r['excess20'] for r in rows if r['excess20'] is not None]))
    out['policies']={key:mean([int(r['path_wins'][key]) for r in rows if r['path_wins'][key] is not None
                             and (label_cutoff is None or (r.get('path_policy_label_end',{}).get(key) or '9999')<label_cutoff)])
                     for key in ('5_3','8_4','10_5','15_8')}
    return out


def by_period(rows,period):
    if period=='development':
        # Purge labels crossing the chronological boundary.
        return [r for r in rows if r['date']<SPLIT and (r.get('label_end') or '9999')<SPLIT]
    if period=='validation':return [r for r in rows if r['date']>=SPLIT]
    return rows


def baseline_metrics(rows):
    v=[r['net20'] for r in rows if r['net20'] is not None]
    return dict(samples=len(v),mean20=mean(v),win20=sum(x>0 for x in v)/len(v) if v else None)


def fmt(v):return '—' if v is None else f'{v:+.2f}%'
def pct(v):return '—' if v is None else f'{v*100:.1f}%'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--panel',default=str(DATA/'tencent'))
    parser.add_argument('--out',default=str(BASE/'docs'/'ma250-pullback'/'fixed-v3'))
    args=parser.parse_args();manifest,series,index_map,missing=load(args.panel)
    table,baseline=build(series,index_map)
    report=dict(generated_at=datetime.now().astimezone().isoformat(),rule=rule_spec(),sample=manifest,
                stocks=len(series),missing=missing,cost_pct=COST_PCT,
                price_basis='unadjusted_price_proxy' if Path(args.panel).name=='tencent' else 'adjusted_return_proxy_with_raw_execution_checks',
                status='exploratory_reanalysis_of_previously_used_history',variants={})
    for name,predicate in VARIANTS:
        selected=apply_variant(table,predicate)
        report['variants'][name]={p:metrics(by_period(selected,p),SPLIT if p=='development' else None) for p in ('all','development','validation')}
        report['variants'][name]['years']={year:metrics([r for r in selected if r['date'].startswith(year)])
                                          for year in sorted({r['date'][:4] for r in selected})}
        report['variants'][name]['stock_split']={str(g):metrics([r for r in selected if int(hashlib.sha256(r['code'].encode()).hexdigest(),16)%2==g]) for g in (0,1)}
    report['baseline']={p:baseline_metrics(by_period(baseline,p)) for p in ('all','development','validation')}
    report['signal_rows']=[dict(code=r['code'],date=r['date'],strong=r['strong'],upgrade=r['upgrade'],
        episode_id=r['episode_id'],rule_id=r['rule_id'],entry_date=r['entry_date'],label_end=r['label_end'],
        execution_status=r['execution_status'],forward=r['forward']) for r in table]
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=1,allow_nan=False))
    lines=['# 年线信号：统一检测器修复后复核','',f"规则：{report['rule']['rule_id']}；股票 {len(series)} 只。",'',
           '本历史已参与过设计与调参，以下是修复后的探索性复核，不是新的独立样本外证明。',
           '入场为下一交易日开盘；持有20个交易日（含买入日），T+1，买卖各0.15%成本；无法入场、未到期单列。',
           f"收益口径：{report['price_basis']}。不按未来跳变剔除信号；缺少完整公司行为与历史ST、盘口成交数据。",
           '开发期剔除跨2024边界的20日标签；区间不确定性采用信号月份整组重采样。','',
           '|信号|区间|完整20日样本|均值|胜率|未到期|无法入场|', '|---|---|---|---|---|---|---|']
    for name,result in report['variants'].items():
        for part in ('development','validation','all'):
            m=result[part];lines.append(f"|{name}|{part}|{m['n20']}|{fmt(m['mean20'])}|{pct(m['win20'])}|{m['pending20']}|{m['unavailable_entry']}|")
    lines+=['','## 强提醒分年','', '|年份|样本|20日均值|胜率|','|---|---|---|---|']
    for year,m in report['variants'][VARIANTS[-1][0]]['years'].items():
        lines.append(f"|{year}|{m['n20']}|{fmt(m['mean20'])}|{pct(m['win20'])}|")
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    for name,m in report['variants'].items():print(name,{p:(m[p]['n20'],m[p]['mean20'],m[p]['win20']) for p in ('development','validation')})
    print('report',out/'report.md')

if __name__=='__main__':main()
