"""Build a compact, dated seed from cross-checked historical close prices."""
import gzip
import hashlib
import json
from collections import deque
from decimal import Decimal

from scripts.build_p250_research_fixture import main as verify_history
from scripts.research_ma_quote_bridge import rows_for_day
from scripts.research_p250_history import OUT, ROOT


def main():
    verify_history()
    collection = json.loads((OUT / 'baostock-collection.json').read_text())
    early = json.loads((ROOT / 'docs/author-mcl-history-20261029/collection.json').read_text())
    later = json.loads((ROOT / 'docs/trin-sensitivity-20261028/summary.json').read_text())
    all_days = collection['expected'] + early['expected'] + [r['date'] for r in later['results']] + ['2026-10-28']
    days = all_days[-249:]
    if len(days) != 249 or days[-1] != '2026-10-28':
        raise ValueError('invalid seed date range')
    state = {}
    for index, day in enumerate(days):
        rec = collection['records'].get(day)
        if rec:
            data = (ROOT / rec['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != rec['sha256']:
                raise ValueError(day + ': source changed')
            payload = json.loads(data)
            rows = [{'symbol': r['code'][3:] + '.' + r['code'][:2].upper(), 'close': r['close']}
                    for r in payload['daily'] if r['tradestatus'] == '1' and int(r['volume'] or 0) > 0]
        else:
            rows = rows_for_day(day)
        seen = set()
        for row in rows:
            number, exchange = row['symbol'].split('.')
            if exchange not in ('SH', 'SZ') or (exchange == 'SH' and number.startswith('689')):
                continue
            code = exchange.lower() + number
            if code in seen:
                raise ValueError(day + ': duplicate stock')
            seen.add(code)
            cents = Decimal(row['close']) * 100
            if not cents.is_finite() or cents <= 0 or cents != cents.to_integral_value():
                raise ValueError(day + ': unsupported close precision')
            previous, prices = state.get(code, (-2, deque(maxlen=249)))
            if previous != index - 1:
                prices.clear()
            prices.append(int(cents))
            state[code] = (index, prices)
    stocks = {code: list(prices) for code, (index, prices) in state.items() if index == len(days) - 1}
    if len(stocks) < 4000:
        raise ValueError('insufficient seed stock coverage')
    result = {'version': 1, 'start_date': days[0], 'end_date': days[-1], 'session_count': len(days),
              'source': 'BaoStock、通达信及 Money Tree 交叉核对的历史未复权收盘价', 'stocks': stocks}
    encoded = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    target = ROOT / 'fixtures/ma-close-seed-v1.json.gz'
    target.write_bytes(gzip.compress(encoded, compresslevel=6, mtime=0))
    target.with_suffix('.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest() + '\n')
    print('seed', days[0], days[-1], 'stocks', len(stocks), 'gzip bytes', target.stat().st_size, flush=True)


if __name__ == '__main__':
    main()
