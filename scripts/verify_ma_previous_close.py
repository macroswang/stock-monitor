"""Cross-check one historical daily file before using it in an MA bridge."""
import argparse
import csv
import hashlib
import json
import socket
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

import baostock as bs
from scripts.crosscheck_trin_continuous import read
from scripts.analyze_trin_crosssections import reconcile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/ma-quote-bridge-20261029'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',required=True);args=parser.parse_args()
    day=args.date;name=day.replace('-','')+'.csv';OUT.mkdir(parents=True,exist_ok=True)
    request=Request(f'https://money-tree.eyunzhu.com/daily_kline/date/{name}',headers={'User-Agent':'stock-monitor-research/1.0'})
    with urlopen(request,timeout=25) as res:data=res.read()
    rows=list(csv.DictReader(data.decode('utf-8-sig').splitlines()))
    if len(rows)<4000 or any(r.get('trade_date')!=name[:8] for r in rows) or len({r['symbol'] for r in rows})!=len(rows):raise ValueError('invalid daily source')
    (OUT/name).write_bytes(data)
    socket.setdefaulttimeout(45);login=bs.login()
    if login.error_code!='0':raise RuntimeError(login.error_msg)
    try:daily=read(bs.query_daily_history_k_AStock(date=day))
    finally:bs.logout()
    if not daily or any(r['date']!=day for r in daily) or len({r['code'] for r in daily})!=len(daily):raise ValueError('invalid BaoStock response')
    bao=dict(date=day,provider='BaoStock query_daily_history_k_AStock',fetched_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),daily=daily)
    (OUT/(day+'.baostock.json')).write_text(json.dumps(bao,ensure_ascii=False)+'\n')
    check=reconcile(rows,bao);result=dict(date=day,sha256=hashlib.sha256(data).hexdigest(),**check)
    (OUT/(day+'.crosscheck.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(date=day,compared=check['compared'],mismatches=len(check['mismatches']),only_moneytree=len(check['only_moneytree']),only_baostock=len(check['only_baostock']),max_shares=check['max_shares_difference']),ensure_ascii=False))
    if check['mismatches'] or check['only_moneytree'] or check['only_baostock'] or float(check['max_shares_difference'])!=0:raise ValueError('daily cross-check failed')


if __name__=='__main__':main()
