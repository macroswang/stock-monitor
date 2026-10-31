"""Reconcile the saved exchange disclosures for one research date.

The resulting contract-count ratio covers SSE and SZSE ETF options only.
It is not the author's unpublished all-market PCR or a live signal.
"""
import argparse
import json
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/author-trading-system-20261028'
NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def integer(value):
    text = str(value).replace(',', '')
    if not text.isdigit():
        raise ValueError(f'无效成交张数: {value!r}')
    return int(text)


def verify(rows, expected):
    codes = [row[0] for row in rows]
    if len(codes) != len(expected) or set(codes) != expected:
        raise ValueError('标的缺失或重复')
    for _, call, put, total in rows:
        if call <= 0 or put < 0 or total != call + put:
            raise ValueError('认购、认沽与总成交量不一致')
    call = sum(r[1] for r in rows)
    put = sum(r[2] for r in rows)
    return {'call': call, 'put': put, 'pcr': put / call, 'codes': codes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', choices=['2026-10-29', '2026-10-30'], default='2026-10-30')
    day = parser.parse_args().date
    compact_date = day.replace('-', '')
    payload = json.loads((EVIDENCE / f'sse-options-{compact_date}.json').read_text())
    sh = []
    for row in payload['result']:
        if row['TRADE_DATE'] != day:
            raise ValueError('上交所日期不一致')
        call, put, total = [integer(row[k]) for k in ('CALL_VOLUME', 'PUT_VOLUME', 'TOTAL_VOLUME')]
        if call <= 0 or abs(Decimal(row['CP_RATE'].replace(',', '')) - Decimal(put) * 100 / Decimal(call)) > Decimal('.0051'):
            raise ValueError('上交所公布比例与成交量不一致')
        sh.append((row['SECURITY_CODE'], call, put, total))
    sse = verify(sh, {'510050', '510300', '510500', '588000', '588080'})

    with ZipFile(EVIDENCE / f'szse-options-{compact_date}.xlsx') as archive:
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = [[ ''.join(cell.itertext()).strip() for cell in row.findall('x:c', NS)]
                for row in sheet.findall('.//x:row', NS)]
    if not rows or rows[0][:5] != ['合约标的代码', '合约标的名称', '成交量（张）', '认购成交量（张）', '认沽成交量（张）']:
        raise ValueError('深交所表头不匹配')
    sz = [(r[0], integer(r[3]), integer(r[4]), integer(r[2])) for r in rows[1:] if r]
    szse = verify(sz, {'159901', '159915', '159919', '159922'})
    call, put = sse['call'] + szse['call'], sse['put'] + szse['put']
    print(json.dumps({'date': day, 'sse': sse, 'szse': szse,
                      'etf_only': {'call': call, 'put': put, 'pcr': put / call},
                      'note': '合约张数口径；不含中金所，非已核实的作者公式；深交所日期取自查询请求及网页'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
