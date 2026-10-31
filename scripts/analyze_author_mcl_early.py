"""Compare author MCL against one-provider daily series, with explicit coverage.

Research only: this does not write application data or establish author rules.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from scripts.analyze_mcl_warmup import run

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/author-mcl-history-earlier-20261031'


def breadth(path, day):
    payload = json.loads(path.read_text())
    rows = payload['daily']
    if payload['date'] != day or len(rows) < 4000 or len({r['code'] for r in rows}) != len(rows):
        raise ValueError(f'{day}: missing, duplicate or mixed-date data')
    result = {'date': day, 'advance': 0, 'decline': 0, 'flat': 0}
    for row in rows:
        if row['date'] != day:
            raise ValueError(f'{day}: mixed dates')
        code = row['code']
        if not code.startswith(('sh.', 'sz.')) or code.startswith('sh.689') or row['tradestatus'] != '1':
            continue
        try:
            close, prev, volume, amount = (Decimal(row[k]) for k in ('close', 'preclose', 'volume', 'amount'))
            if any(not v.is_finite() or v <= 0 for v in (close, prev, volume, amount)):
                raise ValueError('non-positive or non-finite value')
        except (InvalidOperation, KeyError) as exc:
            raise ValueError(f'{day} {code}: malformed value') from exc
        result['advance' if close > prev else 'decline' if close < prev else 'flat'] += 1
    return result


def main():
    earlier = json.loads((OUT / 'collection.json').read_text())
    checks = json.loads((OUT / 'crosscheck.json').read_text())
    middle = json.loads((ROOT / 'docs/author-mcl-history-20261029/collection.json').read_text())
    later = json.loads((ROOT / 'docs/trin-sensitivity-20261028/summary.json').read_text())
    if len(checks) != 40 or any('error' in r for r in checks):
        raise ValueError('BaoStock crosscheck is not complete')
    dates = earlier['expected'] + middle['expected'] + [r['date'] for r in later['results']]
    if len(dates) != 140 or len(set(dates)) != len(dates):
        raise ValueError('unexpected or duplicated dates')
    rows = []
    input_hashes = {}
    for day in dates:
        candidates = [OUT / (day + '.baostock.json'),
                      ROOT / 'docs/author-mcl-history-20261029' / (day + '.baostock.json'),
                      ROOT / 'docs/trin-reconstruction-20261028/baostock' / (day + '.json'),
                      ROOT / 'docs/trin-diagnostic-20261028/baostock' / (day + '.json')]
        path = next((p for p in candidates if p.exists()), None)
        if not path:
            raise ValueError(f'{day}: BaoStock snapshot missing')
        rows.append(breadth(path, day))
        input_hashes[day] = hashlib.sha256(path.read_bytes()).hexdigest()
    starts = [dates[0], '2026-06-01', '2026-07-01']
    models = {start: run(rows, start) for start in starts}
    author = json.loads((ROOT / 'fixtures/author-mcl-reference.json').read_text())
    result = []
    for item in author:
        day = item['date']
        if day not in models[starts[0]]:
            continue
        result.append({'date': day, 'author': item['mcl'],
                       **{start: models[start][day] for start in starts}})
    errors = {start: sum(abs(row[start]['mcl'] - row['author']) for row in result) / len(result) for start in starts}
    summary = {'source': 'BaoStock daily snapshots only; upstream lineage unknown',
               'dates': len(rows), 'first': dates[0], 'last': dates[-1], 'starts': starts,
               'initialization': 'both EMAs initialized to first net advances',
               'crosschecked_days': sum('compared' in c for c in checks),
               'single_source_days': [c['date'] for c in checks if 'status' in c],
               'crosscheck_problems': [c['date'] for c in checks if c.get('mismatches') or c.get('only_moneytree') or c.get('only_baostock')],
               'input_sha256': input_hashes, 'mean_absolute_difference': errors, 'comparison': result,
               'warning': 'Historical reconstruction only. Start, universe, source and author formula remain unverified; do not use as a position signal.'}
    (OUT / 'mcl-comparison.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ('dates', 'first', 'last', 'crosschecked_days', 'single_source_days', 'crosscheck_problems', 'mean_absolute_difference')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
