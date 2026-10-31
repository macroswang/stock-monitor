"""Read four public Sina option series into an isolated research directory.

This probe is not a market-wide PCR and does not access application state.
"""
import ast
import hashlib
import json
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/author-trading-system-20261028/cffex-sina-probe-20261031'
SYMBOLS = ('io2703C3600', 'io2703C3700', 'io2703P3600', 'io2703P3700')
DATES = ('2026-10-29', '2026-10-30')
BASE = 'https://stock.finance.sina.com.cn/futures/api/jsonp.php/'


def parse_dayline(text, symbol, dates=DATES):
    if symbol not in SYMBOLS or f'var _{symbol}2026_10_31=' not in text:
        raise ValueError('日线响应合约标识不匹配')
    start, end = text.find('['), text.rfind(']')
    if start < 0 or end < start:
        raise ValueError('日线响应缺少数组')
    rows = ast.literal_eval(text[start:end + 1])
    if not isinstance(rows, list):
        raise ValueError('日线响应格式异常')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('d'), str):
            raise ValueError('日线日期异常')
        if row['d'] not in dates:
            continue
        if row['d'] in result or not re.fullmatch(r'\d+', str(row.get('v', ''))):
            raise ValueError('日线日期重复或成交量异常')
        try:
            close = Decimal(str(row['c']))
            if not close.is_finite() or close < 0:
                raise ValueError('收盘价异常')
        except (KeyError, InvalidOperation):
            raise ValueError('收盘价异常') from None
        result[row['d']] = {'close': str(row['c']), 'volume': int(row['v'])}
    if set(result) != set(dates):
        raise ValueError('日线缺少指定日期')
    return result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    for symbol in SYMBOLS:
        label = f'var%20_{symbol}2026_10_31=/FutureOptionAllService.getOptionDayline'
        url = BASE + label + '?' + urlencode({'symbol': symbol})
        try:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                           'Referer': 'https://stock.finance.sina.com.cn/'})
            with urlopen(request, timeout=12) as response:
                payload = response.read(1_000_001)
            if len(payload) > 1_000_000:
                raise ValueError('响应过大')
            observed = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
            parsed = parse_dayline(payload.decode('utf-8'), symbol)
            filename = symbol + '.txt'
            (OUTPUT / filename).write_bytes(payload)
            rows.append({'symbol': symbol, 'url': url, 'observed_at': observed,
                         'file': filename, 'sha256': hashlib.sha256(payload).hexdigest(),
                         'days': parsed})
        except (OSError, ValueError, SyntaxError, KeyError, UnicodeError) as exc:
            errors.append({'symbol': symbol, 'error': f'{type(exc).__name__}: {exc}'})
        time.sleep(.25)
    report = {'scope': '沪深300股指期权单一月份、两个行权价、看涨和看跌；非全部合约',
              'rows': rows, 'errors': errors}
    (OUTPUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'captured': len(rows), 'errors': errors, 'rows': rows}, ensure_ascii=False))


if __name__ == '__main__':
    main()
