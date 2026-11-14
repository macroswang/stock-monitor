"""Paired qfq versus unadjusted comparison for the MA250 rule.

Uses the same stocks, dates and market map; only the price basis changes. The
goal is to see whether the signals and strong-tier outcomes survive corporate
action adjustment, not to pick the better basis after the fact.
"""
import argparse, json, statistics, sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from core.ma250_pullback import analyze, rule_spec
from research.ma250_breadth import load_panel, sma

DATA = BASE / 'docs' / 'ma250-pullback' / 'data'
COST = 0.30


def market_map():
    rows = json.loads((DATA / 'index' / 'sh000300.json').read_text(encoding='utf-8'))['rows']
    line = sma([row['close'] for row in rows], 250)
    return {row['date']: (row['close'] > line[index] if line[index] is not None else None)
            for index, row in enumerate(rows)}


def forward(bars, date, horizon=20, code='', sessions=None):
    from research.ma250_execution import forward_outcomes
    i=next((i for i,b in enumerate(bars) if b['date']==date),None)
    return forward_outcomes(code,bars,i,sessions)['forward'][str(horizon)] if i is not None else None


def outcome(rows):
    net = [row for row in rows if row is not None]
    if not net:
        return dict(n=0, mean=None, win=None)
    return dict(n=len(net), mean=statistics.mean(net), win=sum(value > 0 for value in net) / len(net))


def main():
    parser = argparse.ArgumentParser(description='qfq 与未复权逐只对照')
    parser.add_argument('--tencent', default=str(DATA / 'tencent'))
    parser.add_argument('--qfq', default=str(DATA / 'baostock-qfq'))
    parser.add_argument('--out', default=str(BASE / 'docs' / 'ma250-pullback' / 'fixed-v3' / 'qfq-compare.json'))
    args = parser.parse_args()
    unadjusted, adjusted = load_panel(args.tencent), load_panel(args.qfq)
    market = market_map()
    common = sorted(set(unadjusted) & set(adjusted))
    report = dict(rule=rule_spec(),stocks=len(common), unadjusted=dict(v1=0, strong=0), adjusted=dict(v1=0, strong=0),
                  same_dates=0, only_unadjusted=0, only_adjusted=0, strong_flag_diff=0,
                  paired=dict(unadjusted=[], adjusted=[]), examples=[])
    for code in common:
        raw_by_date={r['date']:r for r in unadjusted[code]}
        for bar in adjusted[code]:
            if bar['date'] in raw_by_date:bar['execution']=raw_by_date[bar['date']]
        left = analyze(unadjusted[code], market=market)
        right = analyze(adjusted[code], market=market)
        a = {signal['date']: signal for signal in left['signals']}
        b = {signal['date']: signal for signal in right['signals']}
        report['unadjusted']['v1'] += len(a)
        report['unadjusted']['strong'] += sum(signal['strong'] for signal in a.values())
        report['adjusted']['v1'] += len(b)
        report['adjusted']['strong'] += sum(signal['strong'] for signal in b.values())
        report['same_dates'] += len(set(a) & set(b))
        report['only_unadjusted'] += len(set(a) - set(b))
        report['only_adjusted'] += len(set(b) - set(a))
        report['strong_flag_diff'] += sum(a[date]['strong'] != b[date]['strong'] for date in set(a) & set(b))
        for date in sorted(set(a) & set(b)):
            if a[date]['strong'] and b[date]['strong']:
                av=forward(unadjusted[code],date,code=code,sessions=sorted(market))
                bv=forward(adjusted[code],date,code=code,sessions=sorted(market))
                if av is not None and bv is not None:
                    report['paired']['unadjusted'].append(av)
                    report['paired']['adjusted'].append(bv)
        if set(a) != set(b) and len(report['examples']) < 10:
            report['examples'].append(dict(code=code, only_unadjusted=sorted(set(a) - set(b)),
                                           only_adjusted=sorted(set(b) - set(a))))
    report['paired']['unadjusted'] = outcome(report['paired']['unadjusted'])
    report['paired']['adjusted'] = outcome(report['paired']['adjusted'])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('stocks', 'unadjusted', 'adjusted', 'same_dates',
                                             'only_unadjusted', 'only_adjusted', 'strong_flag_diff', 'paired')},
                     ensure_ascii=False, indent=1))
    print('report', args.out)


if __name__ == '__main__':
    main()
