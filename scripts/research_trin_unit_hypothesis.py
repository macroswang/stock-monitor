"""Retrospectively test fixed volume-unit hypotheses; never changes app data."""
import hashlib
import json
import statistics
from decimal import Decimal
from pathlib import Path

from scripts.trin_scope_diagnostics import contains

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/trin-author-table-comparison-20261029/unit-hypotheses-20261031.json'
SCENARIOS = ('shares', 'star_times_100', 'star_divided_by_100', 'amount')


def trin(rows, scenario):
    if scenario not in SCENARIOS:
        raise ValueError('unknown scenario')
    totals = {key: {'count': 0, 'value': Decimal(0)} for key in ('up', 'down')}
    for row in rows:
        if not contains(row['code'], 'all') or row['tradestatus'] != '1':
            continue
        volume = Decimal(row['volume'] or '0')
        if volume == 0:
            continue
        price, base = Decimal(row['close']), Decimal(row['preclose'])
        if min(volume, price, base) <= 0:
            raise ValueError('invalid active stock')
        if price == base:
            continue
        group = totals['up' if price > base else 'down']
        value = Decimal(row['amount']) if scenario == 'amount' else volume
        if not value.is_finite() or value <= 0:
            raise ValueError('invalid trade total')
        if row['code'].startswith('sh.688'):
            value *= Decimal(100) if scenario == 'star_times_100' else Decimal('.01') if scenario == 'star_divided_by_100' else Decimal(1)
        group['count'] += 1
        group['value'] += value
    a, d = totals['up'], totals['down']
    if not a['count'] or not d['count'] or not a['value'] or not d['value']:
        raise ValueError('empty trading group')
    return {'advance': a['count'], 'decline': d['count'],
            'trin': float(Decimal(a['count']) * d['value'] / (Decimal(d['count']) * a['value']))}


def main():
    references = json.loads((ROOT / 'fixtures/author-trin-reference.json').read_text()) + json.loads((ROOT / 'fixtures/author-trin-march-reference.json').read_text())
    history = {r['date']: r for r in json.loads((ROOT / 'fixtures/breadth-history-verified.json').read_text())}
    sources = [ROOT / 'docs/trin-diagnostic-20261028/baostock', ROOT / 'docs/trin-reconstruction-20261028/baostock']
    results = []
    for ref in sorted(references, key=lambda r: r['date']):
        day = ref['date']
        paths = [*(directory / f'{day}.json' for directory in sources), ROOT / 'docs/ma-quote-bridge-20261029' / f'{day}.baostock.json']
        path = next((p for p in paths if p.exists()), None)
        if path is None:
            raise ValueError(day + ': missing daily data')
        data = path.read_bytes()
        payload = json.loads(data)
        rows = payload['daily']
        if payload['date'] != day or not rows or any(r['date'] != day for r in rows) or len({r['code'] for r in rows}) != len(rows):
            raise ValueError(day + ': invalid date or duplicate stocks')
        values = {scenario: trin(rows, scenario) for scenario in SCENARIOS}
        checked = history[day]
        if not checked.get('historical') or checked.get('missing') != 0 or values['shares']['advance'] != checked['advance'] or values['shares']['decline'] != checked['decline'] or abs(values['shares']['trin'] - checked['trin']) > 1e-10 or abs(values['amount']['trin'] - checked['trin_amount']) > 1e-10:
            raise ValueError(day + ': verified baseline mismatch')
        results.append({'date': day, 'video_trin': ref['trin'], 'source_sha256': hashlib.sha256(data).hexdigest(),
                        'values': {key: value['trin'] for key, value in values.items()}})
    summary = {key: {'n': len(results), 'mean_absolute_difference': statistics.mean(abs(row['values'][key] - row['video_trin']) for row in results)} for key in SCENARIOS}
    output = {'scope': '已核对的沪深当日活跃股票，排除689类；同一日线源、固定四种口径',
              'limitation': '数值是视频显示值；两种错误单位为假设，并非作者实际数据处理。接近不能证明口径；未核验作者股票范围及采样时间。',
              'summary': summary, 'rows': results}
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
