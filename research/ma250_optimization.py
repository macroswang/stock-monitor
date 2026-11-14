"""Research-only finite hypothesis library. Never imported by core or the UI.

Same causal v3 events; changes below are experimental entry/filter/exit/sizing
policies. All hypotheses are frozen before scores are computed. Daily-bar proxy,
T+1 and locked sessions; no real broker, notification or user DB access.
"""
import argparse,hashlib,json,math,random,statistics,sys,time
from bisect import bisect_right
from dataclasses import dataclass,asdict
from datetime import date,datetime
from pathlib import Path

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from core.ma250_pullback import analyze,prepare,rule_spec
from research.ma250_breadth import load_panel,sma
from research.ma250_execution import entry_for,close_exit,locked,net_pct
from research.ma250_portfolio import simulate as old_simulate,summary as old_summary,events as old_events

DATA=BASE/'docs/ma250-pullback/data';OUT=BASE/'docs/ma250-pullback/optimization-v4-20261114'
START,END='2019-01-01','2026-11-13'

@dataclass(frozen=True)
class Policy:
    id:str
    label:str
    tier:str='strong'
    entry:str='open'
    filter:str='none'
    exit:str='hold20'
    sizing:str='equal'

# Limited mechanistic hypotheses, no threshold grid or post-score combinations.
POLICIES=(
 Policy('B0','现有强档 / 20日'),
 Policy('B1','指数在线上首次收回 / 20日',tier='market'),
 Policy('E1','强档 / 多一次收盘确认',entry='hold2'),
 Policy('E2','强档 / 三日内突破信号高点',entry='break3'),
 Policy('E3','指数收回 / 多一次收盘确认',tier='market',entry='hold2'),
 Policy('E4','指数收回 / 三日内突破高点',tier='market',entry='break3'),
 Policy('F1','强档 / 指数短期趋势',filter='regime'),
 Policy('F2','强档 / 20日相对强度',filter='relative'),
 Policy('F3','强档 / 回踩缩量',filter='shrink'),
 Policy('F4','强档 / 失效距离不超过8%',filter='risk8'),
 Policy('F5','指数收回 / 指数趋势且相对强',tier='market',filter='regime_relative'),
 Policy('X1','强档 / 10日',exit='hold10'),
 Policy('X2','强档 / 40日',exit='hold40'),
 Policy('X3','强档 / 收盘失效退出，最长20日',exit='invalid20'),
 Policy('X4','强档 / MA20退出，最长40日',exit='trend40'),
 Policy('X5','强档 / 收盘止盈8%止损5%，最长20日',exit='bracket20'),
 Policy('S1','强档 / ATR仓位',sizing='atr'),
 Policy('S2','强档 / 单笔0.25%失效风险预算',sizing='risk25'),
 Policy('S3','强档 / 半仓对照',sizing='half'),
 Policy('C1','指数收回 / 确认+相对强+趋势退出',tier='market',entry='hold2',filter='regime_relative',exit='trend40'),
 Policy('C2','强档 / 确认+失效距离+趋势退出+风险预算',entry='hold2',filter='risk8',exit='trend40',sizing='risk25'),
)
POLICY_BY_ID={p.id:p for p in POLICIES}


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def record_plan(out):
    out.mkdir(parents=True,exist_ok=True)
    files=[*BASE.joinpath('core').glob('*.py'),*BASE.joinpath('src').glob('*.ts*'),*BASE.joinpath('research').glob('ma250*.py')]
    files=[p for p in files if not p.name.startswith('ma250_optimization')]
    files += [p for folder in ('tencent','baostock-qfq','index') for p in (DATA/folder).glob('*.json')]
    hashes={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    plan=dict(created_at=datetime.now().astimezone().isoformat(),rule=rule_spec(),policies=[asdict(p) for p in POLICIES],
        start=START,end=END,costs_one_way=[.0015,.003],slots=10,panels=['raw415','raw_matched217','qfq217'],
        chronological_periods=['2019-2023','2024-2025','2026'],
        selection='walk-forward 2022..2026; previous 3 calendar years only; >=20 completed trades, positive CAGR, win>=45%; best Calmar; otherwise B0',
        retrospective_shortlist='top 3 by worst-panel 2019..2025 Calmar; >=20 trades in every panel; no 2026 scoring',
        uncertainty='circular consecutive 3-month blocks, 1000 resamples; max-t family adjustment against B0 for all tested alternatives',
        diagnostics=['same-stock raw/qfq','stock hash halves','exclude 2025 entries','double cost','yearly returns'],
        improvement_gate='all 3 panels: positive return, higher win, higher return, at least 20% smaller drawdown magnitude; then stress and 2026 checks; no automatic promotion',
        assumptions=['next-open entries; T+1','all experimental exit triggers are completed-close then next legal open; max-hold exits at close',
          'opening exit proceeds unavailable to same-opening entries','fixed current-listed panel, no historical ST/depth/corporate-action cash ledger',
          'qfq marks normalized to raw entry lots; return proxy, not exact total-return account',
          'all history previously used: rolling replay is not fresh independent OOS'],
        production_and_input_hashes=hashes)
    path=out/'plan.json'
    if path.exists():
        saved=json.loads(path.read_text());assert saved['policies']==plan['policies'] and saved['production_and_input_hashes']==hashes,'Plan/input drift'
        return saved
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2));return plan


def next_open_exit(bars,trigger):
    for j in range(trigger+1,len(bars)):
        raw=bars[j].get('execution',bars[j]);previous=bars[j-1].get('execution',bars[j-1])
        if locked(raw,previous['close'],'down'):continue
        return dict(status='closed',index=j,date=bars[j]['date'],price=bars[j]['open'],phase='open')
    return dict(status='pending_exit',index=None,date=None,price=None,phase=None)


def research_exit(bars,f,signal,entry,policy,sessions):
    if policy.startswith('hold'):
        return dict(close_exit(bars,entry['index'],int(policy[4:]),sessions),phase='close')
    ei=entry['index'];horizon=40 if policy=='trend40' else 20
    terminal=close_exit(bars,ei,horizon,sessions)
    end=terminal['index'] if terminal['index'] is not None else len(bars)-1
    for i in range(ei,end+1):
        close=bars[i]['close']
        broken=close<=signal['stop']
        trigger=broken if policy=='invalid20' else (broken or i>=ei+4 and f['ma20'][i] is not None and close<f['ma20'][i]) if policy=='trend40' else close<=entry['price']*.95 or close>=entry['price']*1.08
        # Timeout executes at this close; there is no remaining next-open decision.
        if trigger and (terminal['index'] is None or i<terminal['index']):return next_open_exit(bars,i)
    return dict(terminal,phase='close')


def research_entry(code,bars,f,signal_i,signal,policy,sessions,market):
    if policy=='open':return entry_for(bars,signal_i,code,sessions)
    if policy=='break3':
        from core.ma250_e2 import confirmation_for
        decision=confirmation_for(bars,f,signal_i,signal,market)
        if decision['index'] is not None:return entry_for(bars,decision['index'],code,sessions)
        return dict(status=decision['status'],index=None,date=None,price=None)
    i=signal_i;duration=1 if policy=='hold2' else 3
    at=bisect_right(sessions,bars[i]['date']);allowed=set(sessions[at:at+duration])
    for j in range(i+1,min(len(bars),i+duration+1)):
        b=bars[j]
        if b['date'] not in allowed:break
        if b['low']<signal['stop']:return dict(status='cancelled_structure',index=None,date=None,price=None)
        above=f['ma250'][j] is not None and b['close']>=f['ma250'][j]*1.01 and b['close']>f['ma5'][j]
        passes=above and (b['close']>=signal['close'] if policy=='hold2' else b['close']>bars[i]['high'])
        if passes and market.get(b['date']) is True:return entry_for(bars,j,code,sessions)
    remaining=at+duration>len(sessions) or not bars or bars[-1]['date']<(sessions[at+duration-1] if at+duration<=len(sessions) else '9999')
    return dict(status='pending_confirmation' if remaining else 'confirmation_not_met',index=None,date=None,price=None)


def passes_filter(name,features):
    if name=='none':return True
    if name=='regime_relative':return features['regime'] and features['relative']
    return features[name]


def build_events(series,raw,market,index_rows):
    sessions=sorted(market);idx={b['date']:i for i,b in enumerate(index_rows)}
    im20=sma([b['close'] for b in index_rows],20)
    events={p.id:[] for p in POLICIES};observations={p.id:[] for p in POLICIES}
    for code,bars in sorted(series.items()):
        report=analyze(bars,market=market)
        if report['error']:continue
        f=prepare(bars);f['ma20']=sma([b['close'] for b in bars],20)
        positions={b['date']:i for i,b in enumerate(bars)};raw_dates={b['date']:b for b in raw[code]}
        for signal in report['signals']:
            i=positions[signal['date']];ii=idx.get(signal['date']);peak=positions[signal['peak_date']];touch=positions[signal['touch_date']]
            before=[b.get('volume') for b in bars[max(0,peak-20):peak]]
            after=[b.get('volume') for b in bars[peak+1:touch+1]]
            shrink=bool(len(before)==20 and after and all(v is not None for v in before+after) and sum(before)>0 and statistics.mean(after)<=statistics.mean(before)*.8)
            regime=bool(ii is not None and ii>=24 and im20[ii] is not None and index_rows[ii]['close']>im20[ii] and im20[ii]>im20[ii-5])
            relative=bool(ii is not None and ii>=20 and i>=20 and bars[i]['close']/bars[i-20]['close']>index_rows[ii]['close']/index_rows[ii-20]['close'])
            features=dict(regime=regime,relative=relative,shrink=shrink,risk8=0<(signal['close']-signal['stop'])/signal['close']<=.08)
            for policy in POLICIES:
                eligible=signal['strong'] if policy.tier=='strong' else not signal['upgrade'] and signal['market_above'] is True
                if not eligible:continue
                row=dict(code=code,signal_date=signal['date'],episode_id=signal['episode_id'],policy=policy.id)
                if not passes_filter(policy.filter,features):observations[policy.id].append(dict(row,status='filter_rejected'));continue
                entry=research_entry(code,bars,f,i,signal,policy.entry,sessions,market)
                if entry['index'] is None:observations[policy.id].append(dict(row,status=entry['status']));continue
                e_i=entry['index'];raw_bar=raw_dates.get(entry['date'])
                if not raw_bar:observations[policy.id].append(dict(row,status='missing_raw_execution'));continue
                exit_=research_exit(bars,f,signal,entry,policy.exit,sessions)
                factor=raw_bar['open']/entry['price']
                event=dict(row,entry_date=entry['date'],entry=raw_bar['open'],exit_date=exit_['date'],
                    exit_phase=exit_['phase'],exit_price=exit_['price']*factor if exit_['price'] is not None else None,
                    factor=factor,strong=signal['strong'],stop=signal['stop']*factor,atr=signal['atr20_pct'],
                    sizing=policy.sizing,reference_entry=entry['price'],exit_status=exit_['status'])
                events[policy.id].append(event);observations[policy.id].append(dict(row,status='entered' if exit_['index'] is not None else 'pending_exit'))
    return events,observations


class Portfolio:
    def __init__(self,series,dates=None,closes=None):
        self.series=series
        self.dates=dates or sorted({b['date'] for bs in series.values() for b in bs if START<=b['date']<=END})
        self.closes=closes or {c:{b['date']:b['close'] for b in bs} for c,bs in series.items()}

    def run(self,events,start=START,end=END,cost=.0015,details=False):
        dates=[d for d in self.dates if start<=d<=end];entries={}
        for e in events:
            if start<=e['entry_date']<=end:entries.setdefault(e['entry_date'],[]).append(e)
        cash=1_000_000.;positions={};curve=[];trades=[]
        for day in dates:
            for e in entries.get(day,[]):
                c=e['code']
                if c in positions or len(positions)>=10:continue
                equity=cash+sum(p['shares']*p['last'] for p in positions.values());allocation=min(cash,equity/10)
                sizing=e.get('sizing','equal')
                if sizing=='atr' and e.get('atr'):allocation=min(cash,equity/10*min(1.5,max(.5,3/e['atr'])))
                elif sizing=='half':allocation=min(cash,equity/20)
                elif sizing=='risk25':
                    distance=e['entry']-e['stop']
                    if distance<=0:continue
                    allocation=min(cash,equity/10,equity*.0025/distance*e['entry'])
                shares=math.floor(allocation/(e['entry']*100*(1+cost)))*100
                if shares<=0:continue
                value=shares*e['entry']*(1+cost);cash-=value
                positions[c]=dict(e,shares=shares,cost=value,last=e['entry'])
                if cash<-.00001:raise AssertionError('cash overdraft')
            # New opening purchases cannot use these opening exit proceeds.
            for c,p in list(positions.items()):
                if p['exit_date']==day and p['exit_phase']=='open' and day>p['entry_date']:
                    proceeds=p['shares']*p['exit_price']*(1-cost);cash+=proceeds
                    trades.append(self.trade(p,day,p['exit_price'],proceeds));del positions[c]
            for c,p in list(positions.items()):
                close=self.closes[c].get(day)
                if close is not None:p['last']=close*p.get('factor',1.)
                if p['exit_date']==day and p['exit_phase']=='close' and close is not None and day>p['entry_date']:
                    proceeds=p['shares']*p['exit_price']*(1-cost);cash+=proceeds
                    trades.append(self.trade(p,day,p['exit_price'],proceeds));del positions[c]
            invested=sum(p['shares']*p['last'] for p in positions.values());equity=cash+invested
            curve.append((day,equity,invested/equity if equity else 0))
        result=old_summary(curve,trades,start,end)
        result.update(open_positions=len(positions),cost_one_way=cost,year_returns=calendar_returns(curve))
        if details:result.update(curve=curve,trades_detail=trades)
        return result

    @staticmethod
    def trade(p,day,price,proceeds):
        return dict(code=p['code'],entry=p['entry'],exit=price,shares=p['shares'],entry_date=p['entry_date'],exit_date=day,
            planned_exit=p['exit_date'],strong=p['strong'],episode_id=p['episode_id'],policy=p['policy'],
            net=proceeds/p['cost']-1,profit=proceeds-p['cost'])


def calendar_returns(curve):
    previous=1_000_000.;result={}
    by_year={}
    for day,value,_ in curve:by_year[day[:4]]=value
    for year,end in sorted(by_year.items()):result[year]=(end/previous-1)*100;previous=end
    return result


def signal_metrics(events,start=START,end=END,cost=.0015):
    rows=[e for e in events if start<=e['signal_date']<=end];done=[e for e in rows if e['exit_date'] and e['exit_date']<=end]
    values=[(e['exit_price']*(1-cost)/(e['entry']*(1+cost))-1)*100 for e in done]
    return dict(entered=len(rows),mature=len(done),pending=len(rows)-len(done),mean=statistics.mean(values) if values else None,
        win=sum(v>0 for v in values)/len(values) if values else None)


def parity_check(context,events,market,raw):
    reference=old_events(context.series,market,'strong',START,END,raw)
    curve,trades=old_simulate(context.series,reference,START,END)
    actual=context.run(events,details=True)
    assert curve==actual['curve'],'baseline equity mismatch'
    wanted=[(t['code'],t['entry_date'],t['exit_date'],t['shares'],t['net']) for t in trades]
    got=[(t['code'],t['entry_date'],t['exit_date'],t['shares'],t['net']) for t in actual['trades_detail']]
    assert wanted==got,'baseline trades mismatch'
    return dict(curve_points=len(curve),trades=len(trades),exact=True)


def choose_policy(training):
    eligible=[(k,v) for k,v in training.items() if v.get('trades',0)>=20 and v.get('cagr',0)>0 and (v.get('win') or 0)>=.45 and v.get('max_drawdown',0)<0]
    if not eligible:return 'B0'
    return max(eligible,key=lambda kv:(kv[1]['cagr']/abs(kv[1]['max_drawdown']),kv[0]))[0]


def walk_forward(context,events):
    choices={};selected=[]
    for year in range(2022,2027):
        start=f'{year-3}-01-01';end=f'{year-1}-12-31'
        training={k:context.run(v,start,end) for k,v in events.items()}
        choice=choose_policy(training);choices[str(year)]=dict(policy=choice,train_start=start,train_end=end,training=training)
        selected += [e for e in events[choice] if e['entry_date'].startswith(str(year))]
    return dict(choices=choices,result=context.run(sorted(selected,key=lambda e:(e['code'],e['signal_date'])),'2022-01-01',END,details=True))


def monthly_returns(curve):
    previous=1_000_000.;months={};last={}
    for day,equity,_ in curve:last[day[:7]]=equity
    for month,equity in sorted(last.items()):months[month]=math.log(equity/previous);previous=equity
    return months


def block_comparison(runs,repetitions=1000):
    import numpy as np
    ids=[k for k in runs if k!='B0'];baseline=monthly_returns(runs['B0']['curve']);months=sorted(baseline)
    diffs=np.array([[monthly_returns(runs[k]['curve'])[m]-baseline[m] for m in months] for k in ids])
    mean=diffs.mean(axis=1);sd=diffs.std(axis=1,ddof=1);sd=np.maximum(sd,1e-12)
    observed=mean/sd*math.sqrt(len(months));rng=np.random.default_rng(250);boot=[];max_null=[]
    for _ in range(repetitions):
        starts=rng.integers(0,len(months),size=math.ceil(len(months)/3));indices=np.concatenate([(np.arange(s,s+3)%len(months)) for s in starts])[:len(months)]
        sample=diffs[:,indices];boot.append(sample.mean(axis=1)*12*100)
        centered=sample-mean[:,None];denom=np.maximum(centered.std(axis=1,ddof=1),1e-12)
        max_null.append(float(np.max(centered.mean(axis=1)/denom*math.sqrt(len(months)))))
    boot=np.array(boot);max_null=np.array(max_null)
    return {k:dict(annualized_log_excess_pct=float(mean[i]*12*100),ci=list(map(float,np.quantile(boot[:,i],[.025,.975]))),
        family_adjusted_p=float((1+np.sum(max_null>=observed[i]))/(repetitions+1))) for i,k in enumerate(ids)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default=str(OUT));p.add_argument('--plan-only',action='store_true');args=p.parse_args()
    out=Path(args.out);plan=record_plan(out)
    if args.plan_only:print('Frozen plan',out/'plan.json');return
    started=time.perf_counter();raw=load_panel(DATA/'tencent');qfq=load_panel(DATA/'baostock-qfq')
    common=sorted(set(raw)&set(qfq));index_rows=json.loads((DATA/'index/sh000300.json').read_text())['rows']
    line=sma([b['close'] for b in index_rows],250);market={b['date']:b['close']>line[i] if line[i] is not None else None for i,b in enumerate(index_rows)}
    for code,bars in qfq.items():
        raw_dates={b['date']:b for b in raw[code]}
        for b in bars:
            if b['date'] in raw_dates:b['execution']=raw_dates[b['date']]
    report=dict(plan_digest=digest(plan),rule=rule_spec(),status='retrospective exploratory replay; no production change',
                engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),panels={})
    contexts={};event_sets={}
    for name,series in [('raw415',raw),('raw_matched217',{c:raw[c] for c in common}),('qfq217',qfq)]:
        print('BUILD',name,flush=True);context=Portfolio(series);events,observations=build_events(series,raw,market,index_rows)
        contexts[name]=context;event_sets[name]=events;parity=parity_check(context,events['B0'],market,raw)
        runs={};full={}
        for policy in POLICIES:
            full[policy.id]=context.run(events[policy.id],details=True)
            periods={label:context.run(events[policy.id],start,end) for label,start,end in [('early',START,'2023-12-31'),('middle','2024-01-01','2025-12-31'),('late','2026-01-01',END),('pre2026',START,'2025-12-31')]}
            counts={status:sum(r['status']==status for r in observations[policy.id]) for status in sorted({r['status'] for r in observations[policy.id]})}
            runs[policy.id]=dict(full=full[policy.id],periods=periods,signals=signal_metrics(events[policy.id]),coverage=counts)
        (out/(name+'-events.json')).write_text(json.dumps(events,ensure_ascii=False,separators=(',',':'),allow_nan=False))
        report['panels'][name]=dict(stocks=len(series),baseline_parity=parity,runs=runs,uncertainty=block_comparison(full),walk_forward=walk_forward(context,events))
        print('DONE',name,round(time.perf_counter()-started,1),flush=True)
    # Frozen pre-2026 ranking; no selection using the latest year.
    ranked=[]
    for policy in POLICIES:
        if policy.id in ('B0','B1'):continue
        old=[report['panels'][name]['runs'][policy.id]['periods']['pre2026'] for name in contexts]
        if all(r.get('trades',0)>=20 and r.get('max_drawdown',0)<0 for r in old):
            ranked.append((min(r['cagr']/abs(r['max_drawdown']) for r in old),policy.id))
    shortlist=[k for _,k in sorted(ranked,reverse=True)[:3]];report['shortlist_pre2026']=shortlist
    for name,context in contexts.items():
        diagnostics={}
        for k in ['B0',*shortlist]:
            es=event_sets[name][k];halves={str(g):context.run([e for e in es if int(hashlib.sha256(e['code'].encode()).hexdigest(),16)%2==g]) for g in (0,1)}
            diagnostics[k]=dict(double_cost=context.run(es,cost=.003),without_2025_entries=context.run([e for e in es if not e['entry_date'].startswith('2025')]),stock_halves=halves)
        report['panels'][name]['diagnostics']=diagnostics
    report['simultaneous_improvement']=[]
    for k in POLICY_BY_ID:
        if k=='B0':continue
        ok=[]
        for panel in report['panels'].values():
            r=panel['runs'][k]['full'];b=panel['runs']['B0']['full']
            ok.append(r['trades']>=30 and r['total']>max(0,b['total']) and (r['win'] or 0)>(b['win'] or 0) and abs(r['max_drawdown'])<=abs(b['max_drawdown'])*.8)
        if all(ok):report['simultaneous_improvement'].append(k)
    report['elapsed_seconds']=time.perf_counter()-started
    for path,sha in plan['production_and_input_hashes'].items():assert hashlib.sha256((BASE/path).read_bytes()).hexdigest()==sha,path
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=1,allow_nan=False))
    print('SHORTLIST',shortlist,'GATE',report['simultaneous_improvement'],flush=True)
    for name,panel in report['panels'].items():
        for k in ['B0',*shortlist]:print(name,k,{x:panel['runs'][k]['full'].get(x) for x in ('total','max_drawdown','trades','win')},flush=True)

if __name__=='__main__':main()
