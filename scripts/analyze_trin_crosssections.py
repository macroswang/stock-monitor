"""Recompute dated Money Tree CSVs and reconcile them with BaoStock snapshots.

The share/amount multipliers are tested against both OHLC bounds and BaoStock;
the feeds' upstream provenance is not independently established.
"""
import argparse
import csv
import json
from collections import Counter
from decimal import Decimal,InvalidOperation
from pathlib import Path
import re


def num(value):
    x=Decimal(value)
    if not x.is_finite():raise ValueError('non-finite')
    return x


def compute(rows,allowed,include_cdr=True):
    c=Counter();vol=Counter();amt=Counter();invalid=[]
    for r in rows:
        symbol=r['symbol'];code,exchange=symbol.split('.')
        if exchange not in allowed or (not include_cdr and exchange=='SH' and code.startswith('689')):continue
        try:
            close,prev,high,low,quantity,amount=(num(r[k]) for k in ('close','pre_close','high','low','vol','amount'))
            if min(close,prev,high,low,quantity,amount)<=0:raise ValueError('non-positive')
            shares=quantity*100;cash=amount*1000
            # Provider rounds amount to cents. Permit a tiny price tolerance;
            # one-price limit days can differ from that price by < 0.000001.
            if not low-Decimal('0.0001')<=cash/shares<=high+Decimal('0.0001'):raise ValueError('volume/amount units inconsistent with price range')
            group='up' if close>prev else 'down' if close<prev else 'flat'
            c[group]+=1;vol[group]+=shares;amt[group]+=cash
        except (ValueError,InvalidOperation,KeyError,ZeroDivisionError):invalid.append(symbol)
    if invalid:return dict(invalid=invalid,trin_volume=None,trin_amount=None,counts=dict(c))
    u,d=c['up'],c['down']
    return dict(invalid=invalid,counts=dict(c),up_volume_shares=str(vol['up']),down_volume_shares=str(vol['down']),
                up_amount_yuan=str(amt['up']),down_amount_yuan=str(amt['down']),
                trin_volume=float(Decimal(u)*vol['down']/(Decimal(d)*vol['up'])) if u and d and vol['up'] else None,
                trin_amount=float(Decimal(u)*amt['down']/(Decimal(d)*amt['up'])) if u and d and amt['up'] else None)


def reconcile(rows,bao):
    left={r['symbol']:r for r in rows if r['symbol'].endswith(('.SH','.SZ'))}
    right={r['code'][3:]+'.'+r['code'][:2].upper():r for r in bao['daily'] if r['tradestatus']=='1'}
    issues=[];compared=0;max_volume=Decimal(0);max_amount=Decimal(0)
    for code in left.keys()&right.keys():
        r,b=left[code],right[code]
        try:
            share_diff=abs(num(r['vol'])*100-num(b['volume']))
            cash_diff=abs(num(r['amount'])*1000-num(b['amount']))
            max_volume=max(max_volume,share_diff);max_amount=max(max_amount,cash_diff)
            mismatched=[f for f,g in [('open','open'),('high','high'),('low','low'),('close','close'),('pre_close','preclose')] if num(r[f])!=num(b[g])]
            if share_diff>100 or cash_diff>2 or mismatched:issues.append(dict(code=code,fields=mismatched,volume_diff=str(share_diff),amount_diff=str(cash_diff)))
            compared+=1
        except (KeyError,ValueError,InvalidOperation):issues.append(dict(code=code,fields=['invalid']))
    return dict(compared=compared,only_moneytree=sorted(left.keys()-right.keys()),only_baostock=sorted(right.keys()-left.keys()),
                mismatches=issues,max_shares_difference=str(max_volume),max_amount_difference_yuan=str(max_amount))


def main(csv_dir,bao_dir,output):
    report=[]
    for path in sorted(csv_dir.glob('????????.csv')):
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        day=f'{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:]}'
        if not rows or any(r['trade_date']!=path.stem for r in rows) or len({r['symbol'] for r in rows})!=len(rows):
            raise ValueError(day+' has missing, mixed-date or duplicate data')
        if any(not re.fullmatch(r'\d{6}\.(?:SH|SZ|BJ)',r['symbol']) for r in rows):raise ValueError(day+' unsupported symbol')
        bao=json.loads((bao_dir/(day+'.json')).read_text(encoding='utf-8'))
        item=dict(date=day,rows=len(rows),provider='Money Tree daily CSV (upstream data lineage unknown)',
                  csv_volume_unit='hands; normalized by multiplying by 100',
                  csv_amount_unit='thousand yuan; normalized by multiplying by 1000',
                  shsz=compute(rows,{'SH','SZ'}),shsz_no_cdr=compute(rows,{'SH','SZ'},False),
                  shszbj=compute(rows,{'SH','SZ','BJ'}),bao_reconciliation=reconcile(rows,bao))
        report.append(item)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in report:
        v=r['bao_reconciliation']
        print(r['date'],'shsz',round(r['shsz']['trin_volume'],5),'all',round(r['shszbj']['trin_volume'],5),
              'shares checked',v['compared'],'issues',len(v['mismatches']),'missing',len(v['only_moneytree']),len(v['only_baostock']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--csv-dir',type=Path,required=True);p.add_argument('--bao-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.csv_dir,a.bao_dir,a.output)
