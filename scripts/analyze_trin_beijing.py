"""Sensitivity to adding the *currently listed* BJ sample, not historic full-market TRIN."""
import argparse
import json
from collections import Counter
from decimal import Decimal,InvalidOperation
from pathlib import Path

PRIOR={'2026-03-23':'2026-03-20','2026-03-24':'2026-03-23','2026-03-25':'2026-03-24',
       '2026-10-22':'2026-10-21','2026-10-23':'2026-10-22'}


def main(base_file,beijing_file,output):
    bj=json.loads(beijing_file.read_text(encoding='utf-8'))
    base={r['date']:r for r in json.loads(base_file.read_text(encoding='utf-8'))}
    reports={}
    for day,prior in PRIOR.items():
        baseline=next(r for r in base[day]['candidates'] if r['scope']=='shsz_no_cdr' and r['measure']=='volume')
        if baseline['trin'] is None:raise ValueError(day+' 沪深基线不完整')
        counts=Counter(baseline['counts'])
        volumes={'up':Decimal(baseline['up_measure']),'down':Decimal(baseline['down_measure']),'flat':Decimal(0)}
        quality=Counter()
        for item in bj['stocks']:
            if item['status']!='ok':quality['fetch_error']+=1;continue
            records={r['date']:r for r in item['rows']};cur,prev=records.get(day),records.get(prior)
            if not cur:quality['missing_current']+=1;continue
            if not prev:quality['missing_previous']+=1;continue
            try:
                close,preclose,volume=Decimal(cur['close']),Decimal(prev['close']),Decimal(cur['volume'])
                if not all(x.is_finite() for x in (close,preclose,volume)) or min(close,preclose)<=0 or volume<0:
                    raise ValueError('invalid values')
                if volume==0:quality['zero_volume']+=1;continue
            except (ValueError,InvalidOperation,KeyError):quality['invalid']+=1;continue
            group='up' if close>preclose else 'down' if close<preclose else 'flat'
            counts[group]+=1;volumes[group]+=volume;quality['eligible']+=1
        value=Decimal(counts['up'])*volumes['down']/(Decimal(counts['down'])*volumes['up'])
        reports[day]=dict(base_trin=baseline['trin'],approximate_with_current_beijing_list=float(value),
                          beijing_quality=dict(quality),groups=dict(counts),caveats=bj['limitations'])
    output.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    for day,r in reports.items():print(day,'base',round(r['base_trin'],5),'with BJ sample',round(r['approximate_with_current_beijing_list'],5),r['beijing_quality'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--beijing',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.base,a.beijing,a.output)
