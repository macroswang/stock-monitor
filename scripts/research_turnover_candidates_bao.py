"""Fetch BaoStock historical rows only for flagged turnover discrepancies.

Run with an isolated environment containing baostock. It never writes app
cache or trading data, and retains missing/error cases in the output.
"""
import argparse
import hashlib
import json
from pathlib import Path

from core.provider import now_cn

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/author-trading-system-20261028'
INPUT=DOCS/'turnover-close-followup-20261031.json'
OUTPUT=DOCS/'turnover-followup-baostock-20261031.json'


def main():
    import baostock as bs
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,default=INPUT)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--field',choices=('followup_candidates','control_sample'),default='followup_candidates')
    args=parser.parse_args()
    raw=args.input.read_bytes();source=json.loads(raw)
    day=source['anchor_timestamp'][:10]
    candidates=source[args.field]
    if not candidates or len({r['code'] for r in candidates})!=len(candidates):
        raise ValueError('候选名单为空或重复')
    started=now_cn().isoformat();login=bs.login()
    if login.error_code!='0': raise RuntimeError('BaoStock 登录失败: '+login.error_msg)
    items=[]
    try:
        for n,item in enumerate(candidates,1):
            code=item['code'];symbol=code[:2]+'.'+code[2:]
            try:
                result=bs.query_history_k_data_plus(symbol,'date,code,close,preclose,volume,turn,tradestatus',
                                                   start_date=day,end_date=day,frequency='d',adjustflag='3')
                if result.error_code!='0':
                    items.append({'code':code,'error':result.error_msg,'rows':[]})
                else:
                    rows=[]
                    while result.next(): rows.append(dict(zip(result.fields,result.get_row_data())))
                    items.append({'code':code,'rows':rows})
            except Exception as exc:
                items.append({'code':code,'error':type(exc).__name__,'rows':[]})
            if n%25==0: print(f'已查询 {n}/{len(candidates)}',flush=True)
    finally:
        bs.logout()
    report={'started_at':started,'finished_at':now_cn().isoformat(),'date':day,
            'source':'BaoStock 逐股未复权日线，事后获取',
            'input_sha256':hashlib.sha256(raw).hexdigest(), 'rows':items,
            'sample_field':args.field,'warning':'仅对所选候选补采；不可视为全市场独立核验。'}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'date':day,'queried':len(items),'nonempty':sum(bool(x['rows']) for x in items)},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
