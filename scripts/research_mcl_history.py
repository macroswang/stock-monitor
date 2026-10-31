"""Collect earlier daily breadth as an isolated, single-provider MCL experiment.

Does not write application database, verified fixtures, or trading settings.
"""
import csv
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from core.breadth import _next_verified_trading_day
from scripts.analyze_trin_crosssections import compute

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/author-mcl-history-20261029'


def days_before(end, count):
    calendar = json.loads((ROOT/'fixtures/exchange-calendar-2026.json').read_text())
    closed = calendar['closed_ranges']
    day = date.fromisoformat(end)-timedelta(days=1)
    days = []
    while len(days)<count:
        if day.year != 2026: raise ValueError('calendar only covers 2026')
        s=day.isoformat()
        if day.weekday()<5 and not any(a<=s<=b for a,b in closed):days.append(s)
        day-=timedelta(days=1)
    return sorted(days)


def collect(day):
    name=day.replace('-','')+'.csv'
    target=OUT/'daily'/name
    if target.exists():
        data=target.read_bytes()
    else:
        request=Request(f'https://money-tree.eyunzhu.com/daily_kline/date/{name}',headers={'User-Agent':'stock-monitor-research/1.0'})
        for attempt in range(2):
            try:
                with urlopen(request,timeout=20) as response:data=response.read()
                break
            except HTTPError as exc:
                retry_after=exc.headers.get('Retry-After')
                delay=int(retry_after) if retry_after and retry_after.isdigit() else 10
                if exc.code!=429 or attempt or delay>20:raise
                time.sleep(delay)
    rows=list(csv.DictReader(StringIO(data.decode('utf-8-sig'))))
    if len(rows)<4000 or any(r.get('trade_date')!=name[:8] for r in rows) or len({r.get('symbol') for r in rows})!=len(rows):
        raise ValueError(day+': empty, duplicated or mixed-date rows')
    result=compute(rows,{'SH','SZ'},False)
    if result['invalid'] or not result['counts'].get('up') or not result['counts'].get('down'):
        raise ValueError(day+': invalid rows or empty group')
    if not target.exists():target.write_bytes(data)
    counts=result['counts']
    return dict(date=day,advance=counts['up'],decline=counts['down'],flat=counts.get('flat',0),
                rows=len(rows),sha256=hashlib.sha256(data).hexdigest(),path=str(target.relative_to(ROOT)),
                fetched_at=datetime.fromtimestamp(target.stat().st_mtime,ZoneInfo('Asia/Shanghai')).isoformat(),source='Money Tree; upstream unknown')


def main():
    (OUT/'daily').mkdir(parents=True,exist_ok=True)
    dates=days_before('2026-08-25',60)
    records=[];failures=[]
    for day in dates:
        already_cached=(OUT/'daily'/(day.replace('-','')+'.csv')).exists()
        try:
            record=collect(day);records.append(record)
            print(day,record['advance'],record['decline'],flush=True)
        except Exception as exc:
            failures.append(dict(date=day,error=f'{type(exc).__name__}: {exc}'))
            print(day,'FAILED',failures[-1]['error'],flush=True)
        (OUT/'collection.json').write_text(json.dumps(dict(expected=dates,records=records,failures=failures),ensure_ascii=False,indent=2)+'\n')
        if not already_cached:time.sleep(2)
    if failures or len(records)!=len(dates):raise RuntimeError('history is incomplete; do not use as continuous series')
    for a,b in zip(dates,dates[1:]):
        if _next_verified_trading_day(date.fromisoformat(a))!=date.fromisoformat(b):raise RuntimeError('calendar gap')
    print('COMPLETE',len(records),flush=True)


if __name__ == '__main__':main()
