"""Compare fixed market scopes for author TRIN values; no fitted parameters."""
import csv
import hashlib
import json
import statistics
from pathlib import Path

from scripts.analyze_trin_crosssections import compute

ROOT = Path(__file__).resolve().parents[1]
SCOPES = {'shsz_ex_cdr': ({'SH', 'SZ'}, False),
          'shsz_in_cdr': ({'SH', 'SZ'}, True),
          'shszbj_ex_cdr': ({'SH', 'SZ', 'BJ'}, False),
          'shszbj_in_cdr': ({'SH', 'SZ', 'BJ'}, True)}
DIRECTORIES = [ROOT / 'docs/trin-sensitivity-20261028/daily',
               ROOT / 'docs/trin-reconstruction-20261028/money-tree',
               ROOT / 'docs/ma-quote-bridge-20261029']


def analyze(reference, sources):
    output = []
    for ref in reference:
        day = ref['date']
        rows = sources[day]
        if not rows or any(row['trade_date'] != day.replace('-', '') for row in rows):
            raise ValueError(f'{day} 底表日期不一致')
        if len({row['symbol'] for row in rows}) != len(rows):
            raise ValueError(f'{day} 存在重复股票')
        for scope, (exchanges, include_cdr) in SCOPES.items():
            result = compute(rows, exchanges, include_cdr)
            if result['invalid'] or result['trin_amount'] is None:
                raise ValueError(f'{day} {scope} 数据异常')
            output.append({'date': day, 'scope': scope, 'author_trin': ref['trin'],
                           'trin_amount': result['trin_amount'], 'counts': result['counts'],
                           'advance_amount_yuan': result['up_amount_yuan'],
                           'decline_amount_yuan': result['down_amount_yuan']})
    summaries = {}
    for scope in SCOPES:
        entries = [row for row in output if row['scope'] == scope]
        summaries[scope] = {'n': len(entries), 'mean_absolute_difference': statistics.mean(
            abs(row['trin_amount'] - row['author_trin']) for row in entries)}
    return {'rows': output, 'summary': summaries,
            'warning': '单一 Money Tree 底表范围试算；北交所未在本次逐股交叉核验，数据上游血缘未知；作者股票范围及时点未知，接近不证明口径。'}


def main():
    reference = json.loads((ROOT / 'fixtures/author-trin-reference.json').read_text())
    sources, hashes = {}, {}
    for ref in reference:
        day = ref['date']
        path = next((d / (day.replace('-', '') + '.csv') for d in DIRECTORIES
                     if (d / (day.replace('-', '') + '.csv')).exists()), None)
        if not path:
            raise ValueError(f'{day} 底表不存在')
        hashes[day] = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding='utf-8-sig', newline='') as stream:
            sources[day] = list(csv.DictReader(stream))
    report = analyze(reference, sources)
    report['input_sha256'] = hashes
    path = ROOT / 'docs/trin-author-table-comparison-20261029/scope-comparison.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
