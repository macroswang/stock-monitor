"""Replay saved market snapshots against 249 cross-checked historical sessions.

Research only: the author's exact formula and quote synchronization are unknown.
"""
import argparse
import hashlib
import json
from collections import deque
from datetime import date
from decimal import Decimal

from core.breadth import summarize
from scripts.analyze_p250_history import next_research_day
from scripts.research_ma_oct28 import main as verify_later
from scripts.research_ma_quote_bridge import rows_for_day
from scripts.research_p250_history import OUT, ROOT

WINDOWS = (20, 60, 250)


def replay(days, reader, raw, status):
    prior = days[-249:]
    if len(prior) != 249:
        raise ValueError('249 prior trading days required')
    previous = None
    for d in prior:
        current = date.fromisoformat(d)
        if previous and next_research_day(previous) != current:
            raise ValueError('history has a trading-day gap')
        previous = current
    if next_research_day(previous) != date.fromisoformat(raw['date']):
        raise ValueError('snapshot does not follow historical closes')
    summary = summarize(raw['quotes'], raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])
    if summary['missing'] or summary['status'] != status:
        raise ValueError('incomplete snapshot or unexpected status')
    state = {}
    discontinuities = 0
    for index, d in enumerate(prior):
        seen = set()
        for row in reader(d):
            symbol = row['symbol']
            number, exchange = symbol.split('.')
            if exchange not in ('SH', 'SZ') or (exchange == 'SH' and number.startswith('689')):
                continue
            if symbol in seen:
                raise ValueError('duplicate symbol in history')
            seen.add(symbol)
            close, prev = Decimal(row['close']), Decimal(row['pre_close'])
            if not close.is_finite() or close <= 0 or not prev.is_finite() or prev <= 0:
                raise ValueError('invalid historical prices')
            last, standard, strict = state.get(symbol, (-2, deque(maxlen=249), deque(maxlen=249)))
            if last != index - 1:
                standard.clear()
                strict.clear()
            elif strict and strict[-1] != prev:
                strict.clear()
                discontinuities += 1
            standard.append(close)
            strict.append(close)
            state[symbol] = (index, standard, strict)
    models = {name: {str(w): {'eligible': 0, 'above': 0} for w in WINDOWS}
              for name in ('unadjusted_all', 'unadjusted_prevclose_checked', 'reset_on_discontinuity')}
    mismatch = 0
    matched_prices = {}
    for q in raw['quotes']:
        code = q['code']
        if code.startswith('sh689') or Decimal(str(q['volume'])) <= 0:
            continue
        symbol = code[2:] + '.' + code[:2].upper()
        price, reference = Decimal(q['price']), Decimal(q['previous_close'])
        if not price.is_finite() or price <= 0 or not reference.is_finite() or reference <= 0:
            raise ValueError('invalid snapshot price')
        matched_prices[symbol] = price
        row = state.get(symbol)
        if not row or row[0] != len(prior) - 1:
            continue
        _, normal, strict = row
        changed = normal[-1] != reference
        mismatch += changed
        for model, hist in (('unadjusted_all', normal), ('unadjusted_prevclose_checked', normal),
                            ('reset_on_discontinuity', strict)):
            if changed and model != 'unadjusted_all':
                continue
            for window in WINDOWS:
                if len(hist) < window - 1:
                    continue
                item = models[model][str(window)]
                item['eligible'] += 1
                if price * window > sum(list(hist)[-(window - 1):]) + price:
                    item['above'] += 1
    for model in models.values():
        for row in model.values():
            row['percent'] = 100 * row['above'] / row['eligible'] if row['eligible'] else None
    return {'date': raw['date'], 'status': status, 'first_quote': summary['first_quote'],
            'last_quote': summary['last_quote'], 'collected_at': raw['collected_at'],
            'current_previous_close_mismatches': mismatch, 'historical_discontinuities': discontinuities,
            'models': models}, matched_prices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--additional-snapshot', action='append', default=[])
    args = parser.parse_args()
    collection = json.loads((OUT / 'baostock-collection.json').read_text())
    cross = json.loads((OUT / 'tdx-close-crosscheck.json').read_text())
    if (collection['failures'] or set(collection['expected']) != set(collection['records'])
        or [r['date'] for r in cross['rows']] != collection['expected']
        or any(r['only_baostock'] or r['only_tdx'] or r['close_mismatches'] for r in cross['rows'])):
        raise ValueError('earlier close cross-check incomplete')
    verify_later()
    earlier = json.loads((ROOT / 'docs/author-mcl-history-20261029/collection.json').read_text())
    later = json.loads((ROOT / 'docs/trin-sensitivity-20261028/summary.json').read_text())
    days = collection['expected'] + earlier['expected'] + [r['date'] for r in later['results']] + ['2026-10-28']

    def read(day):
        rec = collection['records'].get(day)
        if not rec:
            return rows_for_day(day)
        data = (ROOT / rec['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != rec['sha256']:
            raise ValueError(day + ': earlier data changed')
        payload = json.loads(data)
        if payload['date'] != day or any(r['date'] != day for r in payload['daily']):
            raise ValueError(day + ': mixed dates')
        return [{'symbol': r['code'][3:] + '.' + r['code'][:2].upper(),
                 'close': r['close'], 'pre_close': r['preclose']}
                for r in payload['daily'] if r['tradestatus'] == '1' and int(r['volume'] or 0) > 0]

    snapshots = [ROOT / 'docs/trin-validation-20261028/raw.json',
                 ROOT / 'docs/ma-quote-bridge-20261029/live-2026-10-29.raw.json',
                 ROOT / 'docs/ma-quote-bridge-20261029/live-2026-10-29-second.raw.json']
    for tag in args.additional_snapshot:
        if not tag or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in tag):
            raise ValueError('invalid snapshot tag')
        snapshots.append(ROOT / f'docs/ma-quote-bridge-20261029/live-2026-10-29-{tag}.raw.json')
    results = []
    for path in snapshots:
        raw = json.loads(path.read_text())
        status = 'closed' if raw['date'] == '2026-10-27' else 'provisional'
        result, prices = replay([d for d in days if d < raw['date']], read, raw, status)
        if status == 'closed':
            reference = {r['symbol']: Decimal(r['close']) for r in read(raw['date'])
                         if r['symbol'].endswith(('.SH', '.SZ')) and not r['symbol'].startswith('689')}
            if prices != reference:
                raise ValueError('closed quote sample does not match dated independent closes')
            saved = json.loads((OUT / 'baostock-daily-research.json').read_text())
            expected = next(r for r in saved if r['date'] == raw['date'])
            for key in ('above', 'eligible'):
                if result['models']['unadjusted_all']['250'][key] != expected[key]:
                    raise ValueError('closed quote replay differs from historical calculation')
        results.append(result)
    (OUT / 'quote-bridge-research.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
