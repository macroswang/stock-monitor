"""Promote earlier research only after all dated constituent data reconciles."""
import argparse
import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from core.breadth import _next_verified_trading_day
from scripts.analyze_trin_crosssections import compute, reconcile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/author-mcl-history-20261029'
TARGET=ROOT/'fixtures/breadth-history-verified.json'


def build(source=None, expected_count=60, check_file='all-crosscheck.json'):
    source=OUT if source is None else source
    collection=json.loads((source/'collection.json').read_text())
    checks=json.loads((source/check_file).read_text())
    entries=collection['records']
    if collection['failures'] or len(entries)!=expected_count or len(checks)!=expected_count or [e['date'] for e in entries]!=collection['expected'] or [c['date'] for c in checks]!=collection['expected']:
        raise ValueError(f'all {expected_count} earlier trading days must be reconciled')
    historical={r['date']:r for r in json.loads(TARGET.read_text())}
    previous=None
    for entry,check in zip(entries,checks):
        day=entry['date'];current=date.fromisoformat(day)
        if previous and _next_verified_trading_day(previous)!=current:raise ValueError(day+': missing trading day')
        previous=current
        # On this date only, Money Tree rounds each volume to whole hands.
        # All other dates must agree at the single-share level.
        allowed_shares=Decimal('50') if day=='2026-06-08' else Decimal('0')
        if check['mismatches'] or check['only_moneytree'] or check['only_baostock'] or Decimal(check['max_shares_difference'])>allowed_shares or Decimal(check['max_amount_difference_yuan'])>Decimal('.5'):
            raise ValueError(day+': stored check failed')
        raw=(ROOT/entry['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError(day+': file hash changed')
        with (ROOT/entry['path']).open(encoding='utf-8-sig',newline='') as f:csv_rows=list(csv.DictReader(f))
        bao=json.loads((source/(day+'.baostock.json')).read_text())
        if bao['date']!=day or any(r['date']!=day for r in bao['daily']):raise ValueError(day+': BaoStock date mismatch')
        times=[datetime.fromisoformat(entry['fetched_at']),datetime.fromisoformat(bao['fetched_at'])]
        if any(t.tzinfo is None or t.utcoffset() is None for t in times):raise ValueError(day+': missing collection timezone')
        collected_at=max(times).isoformat()
        actual=reconcile(csv_rows,bao)
        for key in ('compared','mismatches','only_moneytree','only_baostock','max_shares_difference','max_amount_difference_yuan'):
            if actual[key]!=check[key]:raise ValueError(day+': stored check no longer matches raw files')
        independent=compute(csv_rows,{'SH','SZ'},False)
        if independent['invalid']:raise ValueError(day+': invalid active Money Tree records')
        stock=[r for r in bao['daily'] if r['code'].startswith(('sh.60','sh.68','sz.00','sz.30')) and not r['code'].startswith('sh.689')]
        groups={k:dict(count=0,volume=0,amount=Decimal(0)) for k in ('advance','decline','flat')};suspended=0
        for r in stock:
            volume=int(r['volume'] or 0)
            if r['tradestatus']!='1' or volume==0:suspended+=1;continue
            price,previous_price,amount=Decimal(r['close']),Decimal(r['preclose']),Decimal(r['amount'])
            if min(price,previous_price,amount)<=0:raise ValueError(day+': invalid BaoStock data')
            group='advance' if price>previous_price else 'decline' if price<previous_price else 'flat'
            groups[group]['count']+=1;groups[group]['volume']+=volume;groups[group]['amount']+=amount
        a,d,f=(groups[k] for k in ('advance','decline','flat'))
        if (a['count'],d['count'],f['count']) != (independent['counts']['up'],independent['counts']['down'],independent['counts'].get('flat',0)):raise ValueError(day+': grouped counts differ')
        for group,key in ((a,'up_volume_shares'),(d,'down_volume_shares')):
            if abs(Decimal(group['volume'])-Decimal(independent[key]))>allowed_shares*group['count']:raise ValueError(day+': grouped share totals differ')
        trin=a['count']*d['volume']/(d['count']*a['volume'])
        trin_amount=float(a['count']*d['amount']/(d['count']*a['amount']))
        if abs(trin-independent['trin_volume'])>(1e-6 if allowed_shares else 1e-12) or abs(trin_amount-independent['trin_amount'])>1e-6:raise ValueError(day+': grouped ratios differ')
        historical[day]=dict(date=day,trin=trin,trin_amount=trin_amount,advance=a['count'],decline=d['count'],flat=f['count'],advance_volume=a['volume'],decline_volume=d['volume'],flat_volume=f['volume'],advance_amount=float(a['amount']),decline_amount=float(d['amount']),advancing_percent=100*a['count']/(a['count']+d['count']+f['count']),advancing_volume_percent=100*a['volume']/(a['volume']+d['volume']),advancing_amount_percent=float(100*a['amount']/(a['amount']+d['amount'])),expected=len(stock),covered=len(stock),suspended=suspended,missing=0,status='closed',historical=True,first_quote=None,last_quote=None,collected_at=collected_at,source='BaoStock 收盘日线；Money Tree 逐股交叉核对',universe='沪深当日日线股票，排除689类存托凭证；近似新浪列表')
        if allowed_shares:historical[day]['reconciliation_note']='Money Tree 成交股数按手取整，逐股最大相差50股；MCL家数一致。'
    return [historical[day] for day in sorted(historical)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');parser.add_argument('--earlier-20261031',action='store_true');args=parser.parse_args()
    rows=build(ROOT/'docs/author-mcl-history-earlier-20261031',40,'crosscheck.json') if args.earlier_20261031 else build()
    if args.write:TARGET.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(rows)} historical records; '+('written' if args.write else 'dry run only'))


if __name__=='__main__':main()
