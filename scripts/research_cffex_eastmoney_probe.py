"""Cross-check one public IO option snapshot against an archived close table.

Research only: the snapshot has no explicit trading date; do not publish it as
an independently verified exchange record or use it for a trading signal.
"""
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .research_cffex_coverage import CODE, parse_close

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/author-trading-system-20261028/cffex-eastmoney-probe-20261031'
ARCHIVE = ROOT / 'docs/author-trading-system-20261028/cffex-coverage-20261031'
URL = 'https://futsseapi.eastmoney.com/list/option/221'
PARAMS = {'orderBy': 'zdf', 'sort': 'desc', 'pageSize': '20000', 'pageIndex': '0',
          'token': '58b2fa8f54638b60b87d69b31969089c',
          'field': 'dm,sc,name,p,zsjd,zde,zdf,f152,vol,cje,ccl,xqj,syr,rz,zjsj,o',
          'blockName': 'callback'}


def parse_snapshot(payload):
    data = json.loads(payload)
    entries, total = data.get('list'), data.get('total')
    if not isinstance(entries, list) or type(total) is not int or total != len(entries):
        raise ValueError('期权列表不完整')
    rows = {}
    for row in entries:
        if not isinstance(row, dict) or not isinstance(row.get('dm'), str):
            raise ValueError('期权合约字段异常')
        code = row['dm']
        if not code.startswith('IO'):
            continue
        if not CODE.fullmatch(code) or code in rows or row.get('sc') != 221:
            raise ValueError('IO 合约代码、市场或去重异常')
        volume = row.get('vol')
        if type(volume) is not int or volume < 0:
            raise ValueError('IO 成交量无效')
        price = row.get('p')
        try:
            value = None if price in ('-', None) else Decimal(str(price))
            if value is not None and (not value.is_finite() or value < 0):
                raise ValueError('IO 价格无效')
        except InvalidOperation:
            raise ValueError('IO 价格无效') from None
        rows[code] = {'volume': volume, 'price': str(value) if value is not None else None}
    if not rows:
        raise ValueError('缺少 IO 合约')
    return rows


def compare(snapshot, closed):
    only_snapshot = sorted(set(snapshot) - set(closed))
    only_close = sorted(set(closed) - set(snapshot))
    mismatches, price_mismatches, blank = [], [], []
    for code in sorted(set(snapshot) & set(closed)):
        quote, row = snapshot[code], closed[code]
        if row['volume'] is None:
            blank.append({'code': code, 'snapshot_volume': quote['volume']})
            continue
        if quote['volume'] != row['volume']:
            mismatches.append({'code': code, 'snapshot': quote['volume'], 'close': row['volume']})
        try:
            price = Decimal(str(row['close']).replace(',', ''))
        except InvalidOperation:
            raise ValueError('收盘表价格异常') from None
        if quote['price'] is None or Decimal(quote['price']) != price:
            price_mismatches.append(code)
    totals = {side: sum(row['volume'] for code, row in snapshot.items() if f'-{side}-' in code)
              for side in ('C', 'P')}
    return {'snapshot_count': len(snapshot), 'close_count': len(closed),
            'only_snapshot': only_snapshot, 'only_close': only_close,
            'volume_mismatches': mismatches, 'price_mismatches_on_nonblank': price_mismatches,
            'blank_close_volume': blank, 'call': totals['C'], 'put': totals['P'],
            'pcr': totals['P'] / totals['C'] if totals['C'] else None}


def main():
    archived = json.loads((ARCHIVE / 'report.json').read_text(encoding='utf-8'))
    reference = (ARCHIVE / 'pobo-20261030.html').read_bytes()
    if hashlib.sha256(reference).hexdigest() != archived['files_sha256']['pobo-20261030.html']:
        raise ValueError('收盘表哈希不一致')
    request = Request(URL + '?' + urlencode(PARAMS), headers={
        'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})
    with urlopen(request, timeout=15) as response:
        payload = response.read(3_000_001)
    if len(payload) > 3_000_000:
        raise ValueError('行情响应过大')
    snapshot, closed = parse_snapshot(payload), parse_close(reference)
    result = compare(snapshot, closed)
    result.update(observed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                  source=URL, snapshot_sha256=hashlib.sha256(payload).hexdigest(),
                  close_table_date='2026-10-30', close_table_sha256=hashlib.sha256(reference).hexdigest(),
                  note='快照无交易日期；以另一来源日期和逐项一致性作条件锚定，非交易所原始记录。')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'eastmoney.json').write_bytes(payload)
    (OUTPUT / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
