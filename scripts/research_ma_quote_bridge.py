"""Replay a dated quote snapshot against the prior daily-history MA windows.

Research only. Do not join unmatched sources in the production indicator.
"""
import argparse
import csv
import hashlib
import json
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal
from pathlib import Path

from core.breadth import _next_verified_trading_day, summarize
from scripts.research_author_p_hypothesis import ROOT

OUT=ROOT/'docs/ma-quote-bridge-20261029'


def rows_for_day(day):
    name=day.replace('-','')+'.csv'
    dirs=['docs/author-mcl-history-20261029/daily','docs/trin-sensitivity-20261028/daily','docs/trin-reconstruction-20261028/money-tree','docs/ma-quote-bridge-20261029']
    path=next((ROOT/folder/name for folder in dirs if (ROOT/folder/name).exists()),None)
    if path is None:raise ValueError('missing daily source '+day)
    with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)<4000 or any(r.get('trade_date')!=name[:8] for r in rows) or len({r['symbol'] for r in rows})!=len(rows):raise ValueError('invalid daily source '+day)
    return rows


def replay(days, read_rows, raw, required_status='closed'):
    if not days or len(days)<59:raise ValueError('at least 59 prior sessions required')
    prior=days[-59:];current=date.fromisoformat(raw['date']);previous=None
    for day in prior:
        d=date.fromisoformat(day)
        if previous and _next_verified_trading_day(previous)!=d:raise ValueError('history gap')
        previous=d
    if _next_verified_trading_day(previous)!=current:raise ValueError('quote date not adjacent')
    check=summarize(raw['quotes'],raw['codes'],raw['date'],raw['collected_at'],raw['suspended'])
    if check['missing'] or check['status']!=required_status:raise ValueError('snapshot is incomplete or has an unexpected status')
    history=defaultdict(lambda:deque(maxlen=59));last_seen={};history_discontinuities=0
    for i,day in enumerate(prior):
        for row in read_rows(day):
            symbol=row['symbol'];number,exchange=symbol.split('.')
            if exchange not in ('SH','SZ') or (exchange=='SH' and number.startswith('689')):continue
            code=exchange.lower()+number
            p=Decimal(row['close']);base=Decimal(row['pre_close'])
            if not p.is_finite() or p<=0 or not base.is_finite() or base<=0:raise ValueError('invalid historical price')
            if last_seen.get(code)!=i-1:history[code].clear()
            elif history[code] and history[code][-1]!=base:
                history[code].clear();history_discontinuities+=1
            history[code].append(p);last_seen[code]=i
    result={str(n):dict(eligible=0,above=0) for n in (20,60)}
    excluded={'no_prior_session':0,'previous_close_mismatch':0,'zero_volume':0,'cdr':0,'historical_price_discontinuities':history_discontinuities}
    prices={}
    for q in raw['quotes']:
        code=q['code']
        if code.startswith('sh689'):excluded['cdr']+=1;continue
        if Decimal(str(q['volume']))<=0:excluded['zero_volume']+=1;continue
        current_price=Decimal(q['price']);prior_close=Decimal(q['previous_close'])
        if not current_price.is_finite() or current_price<=0 or not prior_close.is_finite() or prior_close<=0:raise ValueError('invalid quote')
        prices[code]=current_price
        if last_seen.get(code)!=len(prior)-1:
            excluded['no_prior_session']+=1;continue
        h=list(history[code])
        if h[-1]!=prior_close:
            excluded['previous_close_mismatch']+=1;continue
        for n in (20,60):
            if len(h)<n-1:continue
            result[str(n)]['eligible']+=1
            if current_price*n>sum(h[-(n-1):])+current_price:result[str(n)]['above']+=1
    for value in result.values():
        value['percent']=100*value['above']/value['eligible'] if value['eligible'] else None
    return dict(date=raw['date'],anchor=raw['anchor'],collected_at=raw['collected_at'],snapshot_status=check['status'],windows=result,excluded=excluded),prices


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--tag',default='');args=parser.parse_args()
    if args.tag and not all(c.isascii() and (c.isalnum() or c in '-_') for c in args.tag):raise ValueError('invalid sample tag')
    earlier=json.loads((ROOT/'docs/author-mcl-history-20261029/collection.json').read_text())
    later=json.loads((ROOT/'docs/trin-sensitivity-20261028/summary.json').read_text())
    days=earlier['expected']+[r['date'] for r in later['results']]
    if args.live:
        day='2026-10-28';check=json.loads((OUT/(day+'.crosscheck.json')).read_text())
        path=OUT/'20261028.csv'
        if check['date']!=day or hashlib.sha256(path.read_bytes()).hexdigest()!=check['sha256'] or check['mismatches'] or check['only_moneytree'] or check['only_baostock'] or float(check['max_shares_difference'])!=0 or float(check['max_amount_difference_yuan'])>.5:
            raise ValueError('previous day cross-check invalid')
        days.append(day)
        name='live-2026-10-29'+('-'+args.tag if args.tag else '')
        raw=json.loads((OUT/(name+'.raw.json')).read_text())
        result,_=replay([d for d in days if d<raw['date']],rows_for_day,raw,required_status='provisional')
        result['scope']='single provisional market snapshot; no independently verified live author formula'
        (OUT/(name+'.ma.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False));return
    raw=json.loads((ROOT/'docs/trin-validation-20261028/raw.json').read_text())
    result,prices=replay([d for d in days if d<raw['date']],rows_for_day,raw)
    ref=rows_for_day(raw['date']);money={}
    for row in ref:
        number,exchange=row['symbol'].split('.')
        if exchange not in ('SH','SZ') or (exchange=='SH' and number.startswith('689')):continue
        money[exchange.lower()+number]=Decimal(row['close'])
    common=prices.keys()&money.keys();different=sorted(code for code in common if prices[code]!=money[code])
    result['close_crosscheck']=dict(tencent_active=len(prices),moneytree_active=len(money),common=len(common),mismatches=different,
                                    only_tencent=sorted(prices.keys()-money.keys()),only_moneytree=sorted(money.keys()-prices.keys()))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
