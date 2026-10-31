"""Download research-only historical data for testing the author's P250 column."""
import argparse
import csv
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from scripts.analyze_trin_crosssections import compute

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/p250-research-20261029'


def calendar():
    return {y:json.loads(p.read_text())['closed_ranges'] for y,p in
            ((2025,OUT/'exchange-calendar-2025.json'),(2026,ROOT/'fixtures/exchange-calendar-2026.json'))}


def before(day,count):
    cal=calendar();d=date.fromisoformat(day)-timedelta(days=1);dates=[]
    while len(dates)<count:
        if d.year not in cal:raise ValueError('no verified calendar for year')
        text=d.isoformat()
        if d.weekday()<5 and not any(a<=text<=b for a,b in cal[d.year]):dates.append(text)
        d-=timedelta(days=1)
    return sorted(dates)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip',nargs='*',default=[]);args=parser.parse_args()
    (OUT/'daily').mkdir(parents=True,exist_ok=True)
    expected=before('2026-06-01',171)
    records={};failures={}
    for day in reversed(expected):
        if day in args.skip:
            failures[day]='skipped after prior rate limit';continue
        path=OUT/'daily'/(day.replace('-','')+'.csv');cached=path.exists()
        try:
            if cached:data=path.read_bytes()
            else:
                req=Request('https://money-tree.eyunzhu.com/daily_kline/date/'+path.name,headers={'User-Agent':'stock-monitor-research/1.0'})
                for attempt in range(2):
                    try:
                        with urlopen(req,timeout=20) as response:data=response.read()
                        break
                    except HTTPError as exc:
                        retry=exc.headers.get('Retry-After');delay=int(retry) if retry and retry.isdigit() else 15
                        if exc.code!=429 or attempt or delay>30:raise
                        time.sleep(delay)
            rows=list(csv.DictReader(StringIO(data.decode('utf-8-sig'))))
            if len(rows)<4000 or any(r.get('trade_date')!=path.stem for r in rows) or len({r.get('symbol') for r in rows})!=len(rows):raise ValueError('invalid dated constituent data')
            c=compute(rows,{'SH','SZ'},False)
            if c['invalid'] or not c['counts'].get('up') or not c['counts'].get('down'):raise ValueError('invalid or missing active stocks')
            if not cached:path.write_bytes(data)
            records[day]=dict(date=day,rows=len(rows),sha256=hashlib.sha256(data).hexdigest(),path=str(path.relative_to(ROOT)),
                              fetched_at=datetime.fromtimestamp(path.stat().st_mtime,ZoneInfo('Asia/Shanghai')).isoformat())
            print(day,'OK',len(rows),flush=True)
        except Exception as exc:
            failures[day]=f'{type(exc).__name__}: {exc}';print(day,'FAILED',failures[day],flush=True)
        (OUT/'collection.json').write_text(json.dumps(dict(expected=expected,records=records,failures=failures,source='Money Tree; upstream unknown'),ensure_ascii=False,indent=2)+'\n')
        if day in failures and failures[day].startswith('HTTPError: HTTP Error 429'):break
        if not cached:time.sleep(6)
    if failures or len(records)!=len(expected):raise RuntimeError('incomplete historical data')
    print('COMPLETE',len(records),flush=True)


if __name__=='__main__':main()
