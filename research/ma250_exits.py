"""Exit comparisons on exact shared signals with matured outcomes and T+1."""
import argparse,json,statistics,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.ma250_pullback import analyze,prepare,rule_spec
from research.ma250_breadth import load_panel,sma
from research.ma250_execution import entry_for,close_exit,path_exit,net_pct,locked,target_session
from research.ma250_portfolio import market_map,DATA


def trail_exit(bars,entry_i,line,horizon=60,sessions=None):
    timeout=target_session(bars,entry_i,horizon,sessions)
    for i in range(entry_i,len(bars)):
        if line[i] is not None and bars[i]['close']<line[i]:
            for j in range(i+1,len(bars)):
                if locked(bars[j],bars[j-1]['close'],'down'):continue
                return dict(status='closed',index=j,price=bars[j]['open'],date=bars[j]['date'])
            break
        if timeout is not None and bars[i]['date']>=timeout and i>entry_i and not locked(bars[i],bars[i-1]['close'],'down'):
            return dict(status='closed',index=i,price=bars[i]['close'],date=bars[i]['date'])
    return dict(status='pending_exit',index=None,price=None,date=None)


def run(panel,tier):
    series=load_panel(panel);market=market_map();sessions=sorted(market);out=[]
    for code,bars in series.items():
        r=analyze(bars,market=market)
        if r['error']:continue
        f=prepare(bars);indices={b['date']:i for i,b in enumerate(bars)}
        ma10=sma([b['close'] for b in bars],10);ma20=sma([b['close'] for b in bars],20)
        for s in r['signals']:
            if tier=='strong' and not s['strong'] or tier=='all' and s['upgrade']:continue
            i=indices[s['date']];e=entry_for(bars,i,code,sessions)
            if e['index'] is None:continue
            ei=e['index'];entry=e['price'];row=dict(code=code,date=s['date'],strong=s['strong'],exits={})
            policies={f'hold{h}':close_exit(bars,ei,h,sessions) for h in (5,10,20,40,60)}
            policies['ma10']=trail_exit(bars,ei,ma10,60,sessions)
            policies['ma20']=trail_exit(bars,ei,ma20,40,sessions)
            # Initial ATR is known at the signal close, before the entry open.
            policies['atr2']=path_exit(bars,ei,entry-2*f['atr20'][i],max_hold=40,sessions=sessions)
            policies['struct']=path_exit(bars,ei,s['stop'],max_hold=40,sessions=sessions)
            full=policies['ma10'];half=dict(full)
            if full['index'] is not None:
                target=entry*1.08
                hit=next((j for j in range(ei+1,full['index']+1) if bars[j]['high']>=target),None)
                if hit is not None:half['price']=(max(target,bars[hit]['open'])+full['price'])/2
            policies['half8']=half
            for name,exit_ in policies.items():
                row[name]=net_pct(entry,exit_['price']) if exit_['price'] is not None else None
                row['exits'][name]=exit_['date']
            out.append(row)
    return out


def metrics(values):
    mature=[v for v in values if v is not None];wins=[v for v in mature if v>0];losses=[v for v in mature if v<0]
    return dict(n=len(mature),pending=len(values)-len(mature),mean=statistics.mean(mature) if mature else None,
        win=len(wins)/len(mature) if mature else None,pf=sum(wins)/abs(sum(losses)) if losses else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('--panel',default=str(DATA/'tencent'))
    p.add_argument('--out',default=str(BASE/'docs'/'ma250-pullback'/'fixed-v3'/'exits.json'));a=p.parse_args()
    report=dict(rule=rule_spec(),runs={})
    for tier in ('strong','all'):
        rows=run(a.panel,tier);report['runs'][tier]={}
        for part in ('development','validation','all'):
            selected=[r for r in rows if part=='all' or (r['date']<'2024-01-01' if part=='development' else r['date']>='2024-01-01')]
            results={}
            for policy in ('hold5','hold10','hold20','hold40','hold60','ma10','ma20','atr2','struct','half8'):
                eligible=[r for r in selected if part!='development' or (r['exits'][policy] or '9999')<'2024-01-01']
                results[policy]=metrics([r[policy] for r in eligible])
            report['runs'][tier][part]=results
        print(tier,report['runs'][tier]['all']['hold20'])
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=1))

if __name__=='__main__':main()
