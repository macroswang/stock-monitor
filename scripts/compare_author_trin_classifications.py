"""Fixed BaoStock stock-classification comparisons against author observations."""
import hashlib
import json
import statistics
from pathlib import Path

from scripts.trin_scope_diagnostics import compute

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ('all', 'exclude_st', 'sh', 'sz', 'main', 'growth')
DIRECTORIES = [ROOT / 'docs/trin-diagnostic-20261028/baostock',
               ROOT / 'docs/trin-reconstruction-20261028/baostock']


def analyze(reference, payloads, historical):
    history = {item['date']: item for item in historical}
    results = []
    for ref in reference:
        day = ref['date']
        payload = payloads[day]
        rows = payload['daily']
        if payload['date'] != day or not rows or any(row['date'] != day for row in rows):
            raise ValueError(f'{day} 股票数据日期不一致')
        if len({row['code'] for row in rows}) != len(rows):
            raise ValueError(f'{day} 股票数据重复')
        if any(row.get('isST') not in ('0', '1') for row in rows):
            raise ValueError(f'{day} ST 标记不完整')
        baseline = compute(rows, 'all', 'amount')
        checked = history[day]
        if (baseline['advance'] != checked['advance'] or baseline['decline'] != checked['decline']
                or abs(baseline['trin'] - checked['trin_amount']) > 1e-9):
            raise ValueError(f'{day} 与已核对沪深底表不一致')
        for scope in SCOPES:
            result = baseline if scope == 'all' else compute(rows, scope, 'amount')
            if result['trin'] is None:
                raise ValueError(f'{day} {scope} 的 TRIN 无定义')
            results.append({'date': day, 'scope': scope, 'author_trin': ref['trin'], **result})
    summary = {}
    for scope in SCOPES:
        rows = [row for row in results if row['scope'] == scope]
        summary[scope] = {'n': len(rows), 'mean_absolute_difference': statistics.mean(
            abs(row['trin'] - row['author_trin']) for row in rows)}
    return {'rows': results, 'summary': summary,
            'warning': '固定股票分类的单一底表试算，不表示作者使用任何一种分类；作者计算时点、股票范围和口径仍未知。'}


def main():
    reference = json.loads((ROOT / 'fixtures/author-trin-reference.json').read_text())
    historical = json.loads((ROOT / 'fixtures/breadth-history-verified.json').read_text())
    payloads, hashes = {}, {}
    for item in reference:
        day = item['date']
        paths = [*(directory / f'{day}.json' for directory in DIRECTORIES),
                 ROOT / 'docs/ma-quote-bridge-20261029' / f'{day}.baostock.json']
        path = next((p for p in paths if p.exists()), None)
        if path is None:
            raise ValueError(f'{day} 缺少 BaoStock 底表')
        payloads[day] = json.loads(path.read_text())
        hashes[day] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = analyze(reference, payloads, historical)
    report['input_sha256'] = hashes
    path = ROOT / 'docs/trin-author-table-comparison-20261029/classification-comparison.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
