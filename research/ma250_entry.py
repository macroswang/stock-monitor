"""Entry-policy sensitivity on shared signals; no partial-window forced exits."""
import json,statistics,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.ma250_pullback import analyze,rule_spec
from research.ma250_breadth import load_panel
from research.ma250_execution import entry_for,close_exit,net_pct,locked
from research.ma250_portfolio import DATA,market_map


def limit_fill(bars,signal_i,price,code='',sessions=None):
    for i in range(signal_i+1,min(len(bars),signal_i+6)):
        # Daily low touching a limit is an assumed fill; queue depth is unavailable.
        if bars[i]['low']>price or locked(bars[i],bars[i-1]['close'],'up'):continue
        opened=entry_for(bars,i-1,code,sessions)
        if opened['status']=='entry_unavailable':continue
        return i,min(bars[i]['open'],price)
    return None,None


def result(bars,fill_index,entry,horizon=20,sessions=None):
    exit_=close_exit(bars,fill_index,horizon,sessions)
    return net_pct(entry,exit_['price']) if exit_['price'] is not None else None


def main():
    series=load_panel(DATA/'tencent');market=market_map();sessions=sorted(market);rows=[]
    for code,bars in series.items():
        r=analyze(bars,market=market)
        if r['error']:continue
        indices={b['date']:i for i,b in enumerate(bars)}
        for s in r['signals']:
            if not s['strong']:continue
            i=indices[s['date']];entry=entry_for(bars,i,code,sessions);row=dict(code=code,date=s['date'])
            for name,price in [('market',None),('close_limit',s['close']),('line_limit',s['ma250']*1.02)]:
                fi,fill=(entry['index'],entry['price']) if name=='market' else limit_fill(bars,i,price,code,sessions)
                row[name]=dict(filled=fi is not None,net=result(bars,fi,fill,sessions=sessions) if fi is not None else None)
            rows.append(row)
    out=dict(rule=rule_spec(),signals=len(rows),policies={})
    for name in ('market','close_limit','line_limit'):
        v=[r[name]['net'] for r in rows if r[name]['net'] is not None];filled=sum(r[name]['filled'] for r in rows)
        out['policies'][name]=dict(mature=len(v),filled=filled,pending=filled-len(v),mean=statistics.mean(v) if v else None,win=sum(x>0 for x in v)/len(v) if v else None)
    folder=DATA.parent/'fixed-v3';folder.mkdir(exist_ok=True);(folder/'entry.json').write_text(json.dumps(out,ensure_ascii=False,indent=1));print(out['policies'])

if __name__=='__main__':main()
