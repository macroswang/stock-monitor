"""Reconstruct historical TRIN in isolation from BaoStock public daily snapshots.

Install BaoStock in a separate environment, then run with PYTHONPATH pointing
to that installation. This script does not open the application databases.
"""
import argparse
import json
import socket
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import baostock as bs

DATES = ['2026-10-23','2026-10-22','2026-03-25','2026-03-24','2026-03-23','2026-10-27']


def read(result):
    if result.error_code != '0':
        raise RuntimeError(f'BaoStock error {result.error_code}: {result.error_msg}')
    out=[]
    while result.next():
        out.append(dict(zip(result.fields,result.get_row_data())))
    if result.error_code != '0':
        raise RuntimeError(f'BaoStock pagination error {result.error_code}: {result.error_msg}')
    return out


def main(output, dates):
    output.mkdir(parents=True,exist_ok=True)
    socket.setdefaulttimeout(120)
    login=bs.login()
    if login.error_code!='0':
        raise RuntimeError(f'BaoStock login error {login.error_code}: {login.error_msg}')
    try:
        for day in dates:
            target=output/(day+'.json')
            if target.exists():
                old=json.loads(target.read_text(encoding='utf-8'))
                if old.get('daily') and old.get('universe'):
                    print(f'{day} already fetched, preserving previous snapshot',flush=True)
                    continue
            print(f'{day}: requesting dated daily bars',flush=True)
            history=read(bs.query_daily_history_k_AStock(date=day))
            print(f'{day}: received {len(history)} bars; requesting dated universe',flush=True)
            (output/(day+'.daily.pending.json')).write_text(json.dumps(history,ensure_ascii=False),encoding='utf-8')
            universe=read(bs.query_all_stock(day=day))
            if not history or not universe:
                raise ValueError(f'{day} returned empty data')
            if any(x['date']!=day for x in history):
                raise ValueError(f'{day} returned rows from another date')
            if len({x['code'] for x in history})!=len(history) or len({x['code'] for x in universe})!=len(universe):
                raise ValueError(f'{day} returned duplicate codes')
            payload=dict(date=day,provider='BaoStock query_daily_history_k_AStock',
                         universe_provider='BaoStock query_all_stock',client_version=bs.__version__,
                         fetched_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                         daily=history,universe=universe)
            target.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
            print(json.dumps(dict(date=day,daily_rows=len(history),universe_rows=len(universe),
                                  daily_sample=history[:1],universe_sample=universe[:1]),ensure_ascii=False),flush=True)
    finally:
        bs.logout()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--dates',nargs='+',default=DATES)
    main(p.parse_args().output,p.parse_args().dates)
