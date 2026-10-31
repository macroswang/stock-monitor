"""Independent close-only MA breadth reference; never generates trading signals."""
import gzip
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


def cents(value):
    value = Decimal(str(value)) * 100
    if not value.is_finite() or value <= 0 or value != value.to_integral_value():
        raise ValueError('均线参考数据的价格精度无效')
    return int(value)


def load_seed(path):
    path = Path(path)
    digest = path.with_suffix('.sha256').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{64}', digest) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('均线参考基准校验失败')
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        seed = json.load(stream)
    if seed.get('version') != 1 or seed.get('session_count') != 249 or len(seed.get('stocks', {})) < 4000:
        raise ValueError('均线参考基准不完整')
    date.fromisoformat(seed['end_date'])
    for code, prices in seed['stocks'].items():
        if (not isinstance(code, str) or not re.fullmatch(r'(?:sh(?:60|68)|sz(?:00|30))\d{4}', code)
            or code.startswith('sh689') or not prices or len(prices) > 249
            or any(type(p) is not int or p <= 0 for p in prices)):
            raise ValueError('均线参考基准包含无效价格')
    return seed


def load_close_reference(path, *, as_of, summarize, expected_date='2026-10-29', expected_count=5222):
    """Load one recorded, dated close; never expose it before its collection."""
    path = Path(path)
    digest = path.with_suffix('.sha256').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{64}', digest) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('收盘参考快照校验失败')
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        raw = json.load(stream)
    if raw.get('date') != expected_date or len(raw.get('codes', [])) != expected_count:
        raise ValueError('收盘参考快照日期或覆盖异常')
    stamp = datetime.fromisoformat(raw['collected_at'])
    if stamp.tzinfo is None or as_of.tzinfo is None:
        raise ValueError('收盘参考快照时区异常')
    if stamp > as_of:
        return None
    anchor = datetime.fromisoformat(raw['anchor'])
    if anchor.tzinfo is None or anchor > stamp or anchor.date().isoformat() != raw['date']:
        raise ValueError('收盘参考锚点异常')
    if any((quote_stamp := datetime.fromisoformat(q['timestamp'])).tzinfo is None or quote_stamp > stamp
           for q in raw['quotes']):
        raise ValueError('收盘参考报价时间异常')
    summary = summarize(raw['quotes'], raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])
    if summary['status'] != 'closed' or summary['missing'] or summary['expected'] != expected_count:
        raise ValueError('收盘参考快照不完整')
    summary['reconciliation_note'] = '固定的腾讯单来源收盘参考；历史底表另行核对，非逐股双源核验'
    return raw, summary


def calculate(seed, snapshots, next_day, summarize, *, allow_provisional=False, as_of=None):
    """Advance across complete consecutive snapshots from the dated seed.

    A stock's history is reset after a missing/suspended session. Today's
    previous-close mismatches are excluded from today's result, while the
    unadjusted close is retained for the next day. This is a defined research
    convention, not proof of corporate-action handling or the author's formula.
    """
    state = {code: list(prices) for code, prices in seed['stocks'].items()}
    previous = date.fromisoformat(seed['end_date'])
    results = []
    for raw in sorted(snapshots, key=lambda r: r['date']):
        current = date.fromisoformat(raw['date'])
        if current <= date.fromisoformat(seed['end_date']):
            continue
        if next_day(previous) != current:
            break
        try:
            collected = datetime.fromisoformat(raw['collected_at'])
            if collected.tzinfo is None or (as_of is not None and (as_of.tzinfo is None or collected > as_of)):
                break
            if any((stamp := datetime.fromisoformat(q['timestamp'])).tzinfo is None or stamp > collected
                   for q in raw['quotes']):
                break
            if raw.get('anchor'):
                anchor = datetime.fromisoformat(raw['anchor'])
                if anchor.tzinfo is None or anchor > collected or anchor.date() != current:
                    break
            check = summarize(raw['quotes'], raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            break
        if check['missing'] or (check['status'] != 'closed' and not (allow_provisional and check['status'] == 'provisional')):
            break
        # A provisional quote is usable in isolated research only. Never use it
        # as the previous close for a later date.
        windows = {str(w): {'eligible': 0, 'above': 0} for w in (20, 60, 250)}
        next_state = {}
        mismatches = 0
        try:
            for quote in raw['quotes']:
                code = quote['code']
                if code.startswith('sh689') or Decimal(str(quote['volume'])) <= 0:
                    continue
                price, reference = cents(quote['price']), cents(quote['previous_close'])
                history = state.get(code, [])
                if history and history[-1] != reference:
                    mismatches += 1
                elif history:
                    for window in (20, 60, 250):
                        if len(history) < window - 1:
                            continue
                        item = windows[str(window)]
                        item['eligible'] += 1
                        if price * window > sum(history[-(window - 1):]) + price:
                            item['above'] += 1
                next_state[code] = (history + [price])[-249:]
        except (KeyError, TypeError, ValueError, ArithmeticError):
            break
        for item in windows.values():
            item['percent'] = 100 * item['above'] / item['eligible'] if item['eligible'] else None
        results.append({'date': raw['date'], 'windows': windows, 'active': len(next_state),
                        'previous_close_mismatches': mismatches, 'status': check['status'],
                        'first_quote': check['first_quote'], 'last_quote': check['last_quote'],
                        'collected_at': raw['collected_at'],
                        'source': '已核对历史未复权收盘价与腾讯当日收盘报价；当日昨收不一致股票排除',
                        'warning': '独立研究参考，作者公式未确认；未复权价格可能受除权影响。'})
        if check['status'] != 'closed':
            break
        state = next_state
        previous = current
    return results
