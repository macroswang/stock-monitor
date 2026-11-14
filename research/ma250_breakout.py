"""Breakout study consumes the client's exact events, including quality flags."""
import argparse,hashlib,json,statistics,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.ma250_pullback import analyze,rule_spec
from research.ma250_breadth import load_panel
from research.ma250_execution import forward_outcomes
from research.ma250_portfolio import DATA,market_map


def events(series,market):
    out=[];sessions=sorted(market)
    for code,bars in series.items():
        report=analyze(bars,market=market)
        if report['error']:continue
        indices={b['date']:i for i,b in enumerate(bars)}
        for event in report['breakouts']:
            result=forward_outcomes(code,bars,indices[event['date']],sessions)
            out.append(dict(event,code=code,margin=event['margin_pct'],slope=event['slope60_pct'],
                market=event['market_above'],forward=result['forward']['20'],label_end=result['exits']['20']['date'],
                execution_status=result['entry']['status']))
    return out


def metrics(rows):
    v=[r['forward'] for r in rows if r['forward'] is not None]
    return dict(signals=len(rows),n=len(v),pending=sum(r['execution_status'].startswith('pending') or r['execution_status']=='entered' and r['forward'] is None for r in rows),
                unavailable=sum(r['execution_status']=='entry_unavailable' for r in rows),
                mean=statistics.mean(v) if v else None,win=sum(x>0 for x in v)/len(v) if v else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('--panel',default=str(DATA/'tencent'))
    p.add_argument('--out',default=str(DATA.parent/'fixed-v3'/'breakout.json'));a=p.parse_args()
    rows=events(load_panel(a.panel),market_map());out=dict(rule=rule_spec(),variants={})
    variants={'B0 上穿观察':lambda r:True,'B1 斜率与量比确认':lambda r:r['quality']}
    for name,predicate in variants.items():
        rs=[r for r in rows if predicate(r)]
        out['variants'][name]=dict(all=metrics(rs),
            development=metrics([r for r in rs if r['date']<'2024-01-01' and (r['label_end'] or '9999')<'2024-01-01']),
            validation=metrics([r for r in rs if r['date']>='2024-01-01']),
            a=metrics([r for r in rs if int(hashlib.sha256(r['code'].encode()).hexdigest(),16)%2==0]),
            b=metrics([r for r in rs if int(hashlib.sha256(r['code'].encode()).hexdigest(),16)%2==1]))
        print(name,out['variants'][name]['development'],out['variants'][name]['validation'])
    out['rows']=rows;target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(out,ensure_ascii=False,indent=1))

if __name__=='__main__':main()
