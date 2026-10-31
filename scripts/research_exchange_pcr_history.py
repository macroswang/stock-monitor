"""Collect post-close ETF-option statistics into an isolated research folder.

This experiment is not wired to monitoring or orders. SZSE's export contains
no date column: its date is the query date, not an independently verified field.
"""
import argparse
import io
import json
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from core.option_pcr import eligible_sessions, fetch_day
from core.provider import CN
from scripts.research_exchange_pcr_20261030 import NS, integer, verify

SH = {'510050', '510300', '510500', '588000', '588080'}
SZ = {'159901', '159915', '159919', '159922'}


def summarize_sse(payload, day):
    rows = []
    for row in payload['result']:
        if row['TRADE_DATE'] != day:
            raise ValueError('上交所日期不一致')
        call, put, total = [integer(row[k]) for k in ('CALL_VOLUME', 'PUT_VOLUME', 'TOTAL_VOLUME')]
        if call <= 0 or abs(Decimal(str(row['CP_RATE']).replace(',', '')) - Decimal(put)*100/Decimal(call)) > Decimal('.0051'):
            raise ValueError('上交所比例与成交量不一致')
        rows.append((row['SECURITY_CODE'], call, put, total))
    return verify(rows, SH)


def summarize_szse(data):
    with ZipFile(io.BytesIO(data)) as archive:
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = [[''.join(c.itertext()).strip() for c in r.findall('x:c', NS)]
                for r in sheet.findall('.//x:row', NS)]
    if not rows or rows[0][:5] != ['合约标的代码', '合约标的名称', '成交量（张）', '认购成交量（张）', '认沽成交量（张）']:
        raise ValueError('深交所表头不匹配')
    return verify([(r[0], integer(r[3]), integer(r[4]), integer(r[2])) for r in rows[1:] if r], SZ)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--sessions', type=int, default=22, choices=range(1, 31))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(CN)
    days = eligible_sessions(now, args.sessions)
    if len(days) != args.sessions:
        raise ValueError('缺少已核验交易日历')
    report = {'captured_at': now.isoformat(), 'dates': days, 'rows': [], 'errors': [],
              'scope': '沪深9只ETF期权成交张数，深交所日期由查询锚定，不含中金所，不用于交易信号'}
    for day in days:
        try:
            observed = datetime.now(CN).isoformat()
            _, payload = fetch_day(day, observed)
            sse = summarize_sse(payload, day)
            params = urlencode({'SHOWTYPE': 'xlsx', 'CATALOGID': 'ysprdzb', 'TABKEY': 'tab1',
                                'txtQueryDate': day, 'random': str(time.time())})
            request = Request('https://www.szse.cn/api/report/ShowReport?' + params,
                              headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(request, timeout=10) as response:
                raw = response.read()
            szse = summarize_szse(raw)
            (output / f'sse-{day}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            (output / f'szse-{day}.xlsx').write_bytes(raw)
            call, put = sse['call'] + szse['call'], sse['put'] + szse['put']
            report['rows'].append({'date': day, 'captured_at': observed, 'sse': sse, 'szse': szse,
                                   'call': call, 'put': put, 'pcr': put / call})
            print(day, 'ok', flush=True)
        except Exception as exc:
            report['errors'].append({'date': day, 'error': f'{type(exc).__name__}: {exc}'})
            print(day, 'failed', type(exc).__name__, flush=True)
        time.sleep(.15)
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"完成 {len(report['rows'])}/{len(days)}；失败 {len(report['errors'])}", flush=True)


if __name__ == '__main__':
    main()
