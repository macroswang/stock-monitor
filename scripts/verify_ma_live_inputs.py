"""Capture one current public breadth sample for isolated MA bridge validation."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.breadth import collect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/ma-quote-bridge-20261029'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-date',required=True);parser.add_argument('--tag',default='');args=parser.parse_args()
    if args.tag and not re.fullmatch(r'[a-z0-9_-]+',args.tag):raise ValueError('invalid sample tag')
    started=datetime.now(ZoneInfo('Asia/Shanghai'))
    if started.date().isoformat()!=args.expected_date or not ('09:30'<=started.strftime('%H:%M')<'11:30' or '13:00'<=started.strftime('%H:%M')<'15:00'):
        raise ValueError('expected date and continuous trading session required')
    summary,raw=collect()
    if raw['date']!=args.expected_date or summary['status']!='provisional' or summary['missing']:
        raise ValueError('live sample is not complete or is dated incorrectly')
    OUT.mkdir(parents=True,exist_ok=True)
    name='live-'+args.expected_date+('-'+args.tag if args.tag else '')
    (OUT/(name+'.raw.json')).write_text(json.dumps(raw,ensure_ascii=False)+'\n')
    (OUT/(name+'.summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('date','status','expected','covered','missing','first_quote','last_quote','collected_at')},ensure_ascii=False))


if __name__=='__main__':main()
