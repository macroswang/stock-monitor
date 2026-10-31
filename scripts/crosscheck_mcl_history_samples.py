"""Cross-check three dated samples of the isolated MCL history experiment."""
import csv
import json
import socket
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import baostock as bs
from scripts.analyze_trin_crosssections import reconcile
from scripts.crosscheck_trin_continuous import read

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/author-mcl-history-20261029'
DAYS=['2026-06-01','2026-07-13','2026-08-24']


def main():
    socket.setdefaulttimeout(40)
    result=bs.login()
    if result.error_code!='0':raise RuntimeError(result.error_msg)
    checks=[]
    try:
        for day in DAYS:
            with (OUT/'daily'/(day.replace('-','')+'.csv')).open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
            raw=read(bs.query_daily_history_k_AStock(date=day))
            if not raw or any(r['date']!=day for r in raw) or len({r['code'] for r in raw})!=len(raw):raise ValueError(day+': invalid BaoStock result')
            payload=dict(date=day,provider='BaoStock query_daily_history_k_AStock',fetched_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),daily=raw)
            (OUT/(day+'.baostock.json')).write_text(json.dumps(payload,ensure_ascii=False))
            item=dict(date=day,**reconcile(rows,payload));checks.append(item)
            (OUT/'sample-crosscheck.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
            print(day,'compared',item['compared'],'mismatches',len(item['mismatches']),'provider-only',len(item['only_moneytree']),len(item['only_baostock']),flush=True)
    finally:bs.logout()


if __name__=='__main__':main()
