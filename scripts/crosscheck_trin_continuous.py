"""Cross-check stored Money Tree daily CSVs with BaoStock, without app DB access."""
import csv
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import baostock as bs

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.analyze_trin_crosssections import reconcile

RESEARCH=ROOT/'docs/trin-sensitivity-20261028'
ORIGINAL=ROOT/'docs/trin-reconstruction-20261028'
OUTPUT=ROOT/'docs/trin-diagnostic-20261028'
BAO=OUTPUT/'baostock'


def read(result):
    if result.error_code!='0':raise RuntimeError(result.error_msg)
    rows=[]
    while result.next():rows.append(dict(zip(result.fields,result.get_row_data())))
    if result.error_code!='0':raise RuntimeError(result.error_msg)
    return rows


def main():
    expected=json.loads((RESEARCH/'summary.json').read_text())
    if expected['failed'] or expected['obtained'] != expected['expected']:
        raise ValueError('source history is incomplete')
    BAO.mkdir(parents=True,exist_ok=True)
    socket.setdefaulttimeout(60)
    login=bs.login()
    if login.error_code!='0':raise RuntimeError(login.error_msg)
    report=[]
    try:
        for item in expected['results']:
            day=item['date'];name=day.replace('-','')+'.csv'
            csv_path=RESEARCH/'daily'/name
            if not csv_path.exists():csv_path=ORIGINAL/'money-tree'/name
            with csv_path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            if len(rows)!=len({r['symbol'] for r in rows}) or any(r['trade_date']!=day.replace('-','') for r in rows):
                raise ValueError(f'{day}: Money Tree date or duplicate error')
            old=ORIGINAL/'baostock'/f'{day}.json';path=BAO/f'{day}.json'
            if old.exists():bao=json.loads(old.read_text(encoding='utf-8'))
            elif path.exists():bao=json.loads(path.read_text(encoding='utf-8'))
            else:
                daily=read(bs.query_daily_history_k_AStock(date=day))
                if not daily or any(r['date']!=day for r in daily) or len(daily)!=len({r['code'] for r in daily}):
                    raise ValueError(f'{day}: BaoStock missing or duplicate data')
                bao={'date':day,'provider':'BaoStock query_daily_history_k_AStock','fetched_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'daily':daily}
                path.write_text(json.dumps(bao,ensure_ascii=False),encoding='utf-8')
                time.sleep(.25)
            if bao.get('date')!=day or any(r['date']!=day for r in bao['daily']):raise ValueError(f'{day}: mixed date')
            check=reconcile(rows,bao)
            result={'date':day,'moneytree_path':str(csv_path.relative_to(ROOT)),
                    'bao_path':str((old if old.exists() else path).relative_to(ROOT)),**check}
            report.append(result)
            (OUTPUT/'continuous-crosscheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(day,'compared',check['compared'],'mismatch',len(check['mismatches']),
                  'missing',len(check['only_moneytree']),len(check['only_baostock']),flush=True)
    finally:bs.logout()


if __name__=='__main__':main()
