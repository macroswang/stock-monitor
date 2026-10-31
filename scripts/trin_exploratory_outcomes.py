"""Exploratory, close-only breadth comparison; index is a market proxy, not a trade.

All observations use dated public data saved under docs. The test does not
submit orders, mutate the product cache, or represent an investment backtest.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'docs/trin-sensitivity-20261028/summary.json'
INDEX = ROOT/'docs/trin-diagnostic-20261028/index-daily.json'
OUTPUT = ROOT/'docs/trin-diagnostic-20261028/exploratory-outcomes.json'


def summarize(rows, name):
    selected=[r for r in rows if name=='all' or (name=='trin_lt_0_7' and r['trin']<.7) or
              (name=='breadth_lt_20' and r['breadth']<.2) or
              (name=='both' and r['trin']<.7 and r['breadth']<.2)]
    def stats(values):
        return {'n':len(values),'mean_pct':statistics.mean(values) if values else None,
                'median_pct':statistics.median(values) if values else None,
                'positive_count':sum(x>0 for x in values),
                'min_pct':min(values) if values else None,'max_pct':max(values) if values else None}
    return {'dates':[x['signal_date'] for x in selected],
            'shanghai_next_open_close':stats([x['shanghai_open_close_pct'] for x in selected]),
            'csi300_next_open_close':stats([x['csi300_open_close_pct'] for x in selected])}


def main():
    s=json.loads(SOURCE.read_text(encoding='utf-8'))
    if s['failed'] or s['obtained']!=s['expected']:raise ValueError('incomplete breadth history')
    data=s['results'];indices=json.loads(INDEX.read_text(encoding='utf-8'))
    if len(data)!=len({d['date'] for d in data}) or data!=sorted(data,key=lambda r:r['date']):raise ValueError('duplicate or unordered dates')
    days=[d['date'] for d in data]
    for code,rows in indices.items():
        if [r['date'] for r in rows]!=days or any(r['code']!=code for r in rows):raise ValueError(f'index calendar mismatch: {code}')
    rows=[]
    for i,d in enumerate(data[:-1]):
        next_day=data[i+1]['date']
        rec=dict(signal_date=d['date'],next_date=next_day,trin=d['trin'],breadth=d['breadth'])
        for key,code in (('shanghai','sh.000001'),('csi300','sh.000300')):
            bar=indices[code][i+1];o,c=float(bar['open']),float(bar['close'])
            if min(o,c)<=0:raise ValueError('invalid index price')
            rec[key+'_open_close_pct']=(c/o-1)*100
        rows.append(rec)
    conditions=('all','trin_lt_0_7','breadth_lt_20','both')
    scopes={'all_39':rows,'earlier_20':rows[:20],'later_19':rows[20:]}
    out=dict(source='Money Tree SH/SZ ex 689, BaoStock Shanghai and CSI300 index daily bars',
             method='close on day t, compare index next trading day open-to-close; raw index proxy, not executable fills or trading returns',
             limitation='conditions and date split are exploratory and not pre-registered; 40 sessions, no trading costs or out-of-sample validation',
             rows=rows,summary={scope:{key:summarize(part,key) for key in conditions} for scope,part in scopes.items()})
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,part in out['summary'].items():
        print(name)
        for condition,x in part.items():
            q=x['csi300_next_open_close']
            print(condition,'n',q['n'],'mean',round(q['mean_pct'],3) if q['n'] else None,'positive',q['positive_count'])


if __name__=='__main__':main()
