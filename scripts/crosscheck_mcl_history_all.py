"""Reconcile each earlier history day, resuming from validated local snapshots."""
import csv
import json
import socket
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import baostock as bs
from scripts.analyze_trin_crosssections import reconcile
from scripts.crosscheck_trin_continuous import read

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/author-mcl-history-20261029'


def main():
    collection=json.loads((OUT/'collection.json').read_text())
    if collection['failures'] or len(collection['records'])!=len(collection['expected']):raise ValueError('collection incomplete')
    socket.setdefaulttimeout(45)
    result=bs.login()
    if result.error_code!='0':raise RuntimeError(result.error_msg)
    checks=[]
    try:
        for entry in collection['records']:
            day=entry['date'];path=OUT/(day+'.baostock.json')
            with (ROOT/entry['path']).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            if path.exists():payload=json.loads(path.read_text())
            else:
                daily=read(bs.query_daily_history_k_AStock(date=day))
                payload=dict(date=day,provider='BaoStock query_daily_history_k_AStock',fetched_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),daily=daily)
                if not daily or any(r['date']!=day for r in daily) or len({r['code'] for r in daily})!=len(daily):raise ValueError(day+': invalid BaoStock data')
                path.write_text(json.dumps(payload,ensure_ascii=False))
                time.sleep(.3)
            if payload.get('date')!=day or any(r['date']!=day for r in payload['daily']):raise ValueError(day+': mixed data')
            item=dict(date=day,**reconcile(rows,payload));checks.append(item)
            (OUT/'all-crosscheck.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
            print(day,'compared',item['compared'],'mismatch',len(item['mismatches']),'missing',len(item['only_moneytree']),len(item['only_baostock']),flush=True)
    finally:bs.logout()


if __name__=='__main__':main()
