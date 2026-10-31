"""Compare a few reconstructed price scales with BaoStock forward-adjusted bars."""
import json
import socket
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import baostock as bs
from scripts.crosscheck_trin_continuous import read
from scripts.research_ma_quote_bridge import ROOT, rows_for_day

OUT=ROOT/'docs/adjusted-ma-research-20261029'
SAMPLES=['600017.SH','600360.SH','688293.SH']


def main():
    earlier=json.loads((ROOT/'docs/author-mcl-history-20261029/collection.json').read_text())
    later=json.loads((ROOT/'docs/trin-sensitivity-20261028/summary.json').read_text())
    days=earlier['expected']+[r['date'] for r in later['results']]
    histories={s:[] for s in SAMPLES}
    for day in days:
        rows=rows_for_day(day)
        for row in rows:
            if row['symbol'] not in histories:continue
            values=histories[row['symbol']];p,base=Decimal(row['close']),Decimal(row['pre_close'])
            if values and values[-1][1]!=base:
                factor=base/values[-1][1]
                values[:]=[(d,x*factor) for d,x in values]
            values.append((day,p))
    if any(len(rows)!=len(days) for rows in histories.values()):raise ValueError('sample stock history has missing sessions')
    socket.setdefaulttimeout(45);login=bs.login()
    if login.error_code!='0':raise RuntimeError(login.error_msg)
    report=[]
    try:
        for symbol in SAMPLES:
            number,market=symbol.split('.');code=market.lower()+'.'+number
            data=read(bs.query_history_k_data_plus(code,'date,code,close',start_date=days[0],end_date=days[-1],frequency='d',adjustflag='2'))
            if not data or any(r['code']!=code for r in data):raise ValueError('missing or mismatched source')
            qfq={r['date']:Decimal(r['close']) for r in data if r['close']}
            calc=dict(histories[symbol]);common=sorted(calc.keys()&qfq.keys())
            if len(common)<60 or common[-1]!=days[-1]:raise ValueError('insufficient overlap')
            # BaoStock may report a later adjustment basis. Scale both series
            # to the same last common close before comparing the shape.
            scale=calc[common[-1]]/qfq[common[-1]]
            errors=[abs(calc[d]-qfq[d]*scale) for d in common]
            item=dict(symbol=symbol,dates=len(common),start=common[0],end=common[-1],
                      max_abs_price_error=float(max(errors)),last_scale=float(scale),
                      fetched_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),raw=data)
            report.append(item)
            (OUT/'baostock-adjusted-samples.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(symbol,'n',len(common),'maxdiff',item['max_abs_price_error'],flush=True)
    finally:bs.logout()


if __name__=='__main__':main()
