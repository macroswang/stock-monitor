"""Audit dated cross-sectional public data; no curve fitting or account access."""
import argparse
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

TARGETS={'2026-03-23':.31,'2026-03-25':1.4,'2026-10-22':.51,'2026-10-23':.93}


def market(code):
    if re.fullmatch(r'sh\.(?:60|68)\d{4}',code):return 'sh'
    if re.fullmatch(r'sz\.(?:00|30)\d{4}',code):return 'sz'
    if re.fullmatch(r'bj\.(?:4\d|8\d|92)\d{4}',code):return 'bj'
    return None


def compute(payload,scope,measure):
    days=payload['daily'];names={r['code']:r for r in payload['universe']}
    allowed={'sh','sz'} if scope in ('shsz','shsz_no_cdr','shsz_no_st','main') else {scope}
    def eligible(code):
        if market(code) not in allowed:return False
        if scope=='main' and not re.fullmatch(r'(?:sh\.60|sz\.00)\d{4}',code):return False
        if scope=='shsz_no_cdr' and code.startswith('sh.689'):return False
        return True
    expected={c for c in names if eligible(c)}
    actual={r['code'] for r in days if eligible(r['code'])}
    suspended=[];missing=[];invalid=[];excluded_st=0
    counts=Counter();totals=Counter()
    for row in days:
        code=row['code']
        if not eligible(code):continue
        if scope=='shsz_no_st' and row['isST']=='1':excluded_st+=1;continue
        if row.get('tradestatus')=='0':suspended.append(code);continue
        try:
            p,base,v,amount=[Decimal(row[field]) for field in ('close','preclose','volume','amount')]
            if not all(x.is_finite() for x in (p,base,v,amount)) or min(p,base)<=0 or min(v,amount)<0:raise ValueError()
            if v==0 or amount==0:
                invalid.append(code);continue
        except (ValueError,InvalidOperation,KeyError):
            invalid.append(code);continue
        group='up' if p>base else 'down' if p<base else 'flat'
        counts[group]+=1;totals[group]+=v if measure=='volume' else amount
    a,d=counts['up'],counts['down'];up,down=totals['up'],totals['down']
    missing=sorted(expected-actual)
    value=float(Decimal(a)*down/(Decimal(d)*up)) if a and d and up and down and not missing and not invalid else None
    return dict(scope=scope,measure=measure,counts=dict(counts),up_measure=str(up),down_measure=str(down),
                all_measures=str(sum(totals.values())),up_ratio=a/sum(counts.values()) if sum(counts.values()) else None,
                up_measure_ratio=float(up/(up+down)) if up+down else None,trin=value,
                excluded_suspended=len(suspended),excluded_st=excluded_st,missing_from_daily=missing,invalid=invalid,
                expected=len(expected),present=len(actual),target=TARGETS.get(payload['date']),
                delta_from_target=value-TARGETS[payload['date']] if value is not None and payload['date'] in TARGETS else None,
                limitations=['only BaoStock-dated universe; independent listing cross-check needed']+
                    (['screenshot 03-25 may be 1.4; verify original figure'] if payload['date']=='2026-03-25' else []))


def main(source,output):
    results=[]
    for path in sorted(source.glob('????-??-??.json')):
        data=json.loads(path.read_text(encoding='utf-8'))
        results.append(dict(date=data['date'],source=data['provider'],fetched_at=data['fetched_at'],
                            rows=len(data['daily']),universe_rows=len(data['universe']),
                            bj_in_daily=sum(market(r['code'])=='bj' for r in data['daily']),
                            candidates=[compute(data,scope,metric) for scope in ('shsz','shsz_no_cdr','sh','sz','main','shsz_no_st') for metric in ('volume','amount')]))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for day in results:
        print(day['date'],'target',TARGETS.get(day['date']))
        for row in day['candidates']:
            print(' ',row['scope'],row['measure'],'TRIN',round(row['trin'],5) if row['trin'] is not None else None,
                  'up/down/flat',row['counts'],'excluded',row['excluded_suspended'],
                  'missing',len(row['missing_from_daily']),'invalid',len(row['invalid']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();main(args.source,args.output)
