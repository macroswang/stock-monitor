"""Causal daily portfolio: opening entries, evening exits, owned positions only."""
import argparse,json,math,statistics,sys
from datetime import date
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.ma250_pullback import analyze,prepare,rule_spec
from research.ma250_breadth import load_panel,sma
from research.ma250_execution import entry_for,close_exit,BUY_COST,SELL_COST,jump_in
DATA=BASE/'docs'/'ma250-pullback'/'data'
COST_BUY,COST_SELL=BUY_COST,SELL_COST
HOLD,SLOTS=20,10


def market_map():
    rows=json.loads((DATA/'index'/'sh000300.json').read_text())['rows'];line=sma([r['close'] for r in rows],250)
    return {r['date']:(r['close']>line[i] if line[i] is not None else None) for i,r in enumerate(rows)}


def atr_pct(bars,index,period=20):
    f=prepare(bars);return f['atr20'][index]/bars[index]['close']*100 if f['atr20'][index] else None


def events(series,market,tier,start,end,raw_series=None):
    out=[];sessions=sorted(market)
    for code,bars in sorted(series.items()):
        report=analyze(bars,market=market)
        if report['error']:continue
        raw=(raw_series or series).get(code)
        if not raw:continue
        raw_indices={b['date']:i for i,b in enumerate(raw)};indices={b['date']:i for i,b in enumerate(bars)}
        for signal in report['signals']:
            if tier=='strong' and not signal['strong'] or tier=='all' and signal.get('upgrade'):continue
            i=raw_indices.get(signal['date'])
            if i is None:continue
            e=entry_for(raw,i,code,sessions)
            if e['status']!='entered' or not start<=e['date']<=end:continue
            qi=indices.get(e['date'])
            if qi is None:continue
            exit_=close_exit(raw,e['index'],HOLD,sessions)
            factor=e['price']/bars[qi]['open']
            out.append(dict(code=code,signal=signal['date'],entry_date=e['date'],entry=e['price'],
                exit_date=exit_['date'],strong=signal['strong'],episode_id=signal['episode_id'],
                rule_id=signal['rule_id'],stop=signal['stop']*factor,distance=signal['distance_pct'],
                pullback=signal['pullback_pct'],atr=signal['atr20_pct'],factor=factor,
                corporate_action_flag=jump_in(raw,e['index'],exit_['index']) if exit_['index'] is not None else None))
    return out


def simulate(series,trade_events,start,end,slots=SLOTS,rank='fifo',sizing='equal'):
    dates=sorted({b['date'] for bars in series.values() for b in bars if start<=b['date']<=end})
    closes={c:{b['date']:b['close'] for b in bs} for c,bs in series.items()};by_entry={}
    for e in trade_events:by_entry.setdefault(e['entry_date'],[]).append(e)
    cash,positions,curve,trades=1_000_000.,{},[],[]
    for day in dates:
        # Morning: yesterday's cash and marks only. Evening sale proceeds are
        # unavailable, and positions due to exit this evening still occupy slots.
        candidates=list(by_entry.get(day,[]))
        if rank in ('distance','pullback','atr'):candidates.sort(key=lambda e:e.get(rank) or 0)
        elif rank=='random':
            import hashlib
            candidates.sort(key=lambda e:hashlib.sha256(e['code'].encode()).hexdigest())
        for e in candidates:
            if e['code'] in positions or len(positions)>=slots:continue
            equity=cash+sum(p['shares']*p['last'] for p in positions.values())
            allocation=min(cash,equity/slots)
            if sizing=='atr' and e.get('atr'):allocation=min(cash,equity/slots*min(1.5,max(.5,3/e['atr'])))
            elif sizing in ('risk','risk_half') and e.get('stop') and e['entry']>e['stop']:
                risk=.005 if sizing=='risk' else .0025
                allocation=min(cash,equity*risk/(e['entry']-e['stop'])*e['entry'],equity/slots*(1.5 if sizing=='risk' else 1))
            elif sizing=='half':allocation=min(cash,equity/(2*slots))
            shares=math.floor(allocation/(e['entry']*100*(1+COST_BUY)))*100
            if shares<=0:continue
            cost=shares*e['entry']*(1+COST_BUY);cash-=cost
            positions[e['code']]=dict(e,shares=shares,cost=cost,last=e['entry'])
            if cash < -.00001:raise AssertionError('portfolio cash overdraft')
        # Evening: exit only the plan belonging to this actually filled position.
        for code,p in list(positions.items()):
            close=closes[code].get(day)
            if close is not None:p['last']=close*p.get('factor',1.)
            if p['exit_date'] is None or day<p['exit_date'] or close is None or day<=p['entry_date']:continue
            price=p['last'];proceeds=p['shares']*price*(1-COST_SELL);cash+=proceeds
            trades.append(dict(code=code,entry=p['entry'],exit=price,shares=p['shares'],entry_date=p['entry_date'],
                exit_date=day,planned_exit=p['exit_date'],strong=p['strong'],episode_id=p.get('episode_id'),
                net=proceeds/p['cost']-1,profit=proceeds-p['cost'],corporate_action_flag=p.get('corporate_action_flag')))
            del positions[code]
        invested=sum(p['shares']*p['last'] for p in positions.values());equity=cash+invested
        curve.append((day,equity,invested/equity if equity else 0))
    return curve,trades


def summary(curve,trades,start,end):
    if not curve:return {}
    initial=1_000_000.;final=curve[-1][1];peak=initial;dd=0
    for _,v,_ in curve:peak=max(peak,v);dd=min(dd,v/peak-1)
    profits=[t.get('profit',t['net']) for t in trades];positive=sum(v for v in profits if v>0);negative=-sum(v for v in profits if v<0)
    years=max(1,(date.fromisoformat(curve[-1][0])-date.fromisoformat(curve[0][0])).days)/365.25
    return dict(start=curve[0][0],end=curve[-1][0],days=len(curve),total=(final/initial-1)*100,
        cagr=((final/initial)**(1/years)-1)*100,max_drawdown=dd*100,trades=len(trades),
        win=sum(t['net']>0 for t in trades)/len(trades) if trades else None,pf=positive/negative if negative else None,
        mean=statistics.mean(t['net'] for t in trades)*100 if trades else None,
        exposure=statistics.mean(r[2] for r in curve),corporate_action_flags=sum(bool(t.get('corporate_action_flag')) for t in trades),
        wrong_exits=sum(t['exit_date']!=t['planned_exit'] for t in trades))


def main():
    p=argparse.ArgumentParser();p.add_argument('--panel',default=str(DATA/'tencent'));p.add_argument('--raw-panel')
    p.add_argument('--out',default=str(BASE/'docs'/'ma250-pullback'/'fixed-v3'/'portfolio.json'));args=p.parse_args()
    series=load_panel(args.panel);raw=load_panel(args.raw_panel) if args.raw_panel else None;market=market_map()
    result=dict(rule=rule_spec(),price_basis='adjusted_return_proxy_with_raw_lots' if raw else 'unadjusted_price_proxy',
                limitations=['fixed current-listed sample','daily-bar fill assumptions; historical ST/depth incomplete',
                             'adjusted returns approximate reinvestment; raw returns omit corporate-action cash ledger'],runs={})
    for tier in ('strong','all'):
        es=events(series,market,tier,'2019-01-01','2026-11-13',raw)
        for sizing in ('equal','atr'):
            for label,start,end in [('all','2019-01-01','2026-11-13'),('development','2019-01-01','2023-12-31'),('validation','2024-01-01','2026-11-13')]:
                curve,trades=simulate(series,es,start,end,sizing=sizing);m=summary(curve,trades,start,end)
                result['runs'][f'{tier}/{sizing}/{label}']=dict(m,curve=curve,trades_detail=trades)
                print(tier,sizing,label,{k:v for k,v in m.items() if k in ('trades','total','max_drawdown','win','wrong_exits')})
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=1))

if __name__=='__main__':main()
