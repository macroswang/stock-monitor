"""Compare retrospective ETF entry cases using identical execution assumptions.

The all-date baseline overlaps the other groups and is not a causal estimate.
"""
import hashlib
import json
from pathlib import Path

from scripts.research_etf_position import load_etf
from scripts.research_low_trin_entry import evaluate
from scripts.research_market_regime_extended import load_index

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/market-regime-research-20261029'


def compare_groups(rows, index, etf):
    selectors = {
        'all_dates': lambda r: True,
        'weak_low_trin': lambda r: r['weak'] and r['trin'] < .7,
        'weak_other_trin': lambda r: r['weak'] and r['trin'] >= .7,
        'not_weak': lambda r: not r['weak'],
    }
    results = {}
    for name, select in selectors.items():
        # Reuse the same date, range and fee/slippage checks for every group.
        selected = [dict(row, weak_low_trin=bool(select(row))) for row in rows]
        results[name] = evaluate(selected, index, etf)
    return results


def main():
    input_path = OUT / 'extended-results.json'
    source = json.loads(input_path.read_text())
    index = load_index()
    groups = compare_groups(source['rows'], index, load_etf(index))
    result = {'groups': groups, 'input_sha256': hashlib.sha256(input_path.read_bytes()).hexdigest(),
              'warning': '同期、同假设的事后描述；基准组与其他组重叠，收益窗口重叠且可能受市场环境影响，不构成因果或样本外验证。'}
    (OUT / 'low-trin-baseline-comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    fixture = {name: {'summary': group['all'], 'skipped': len(group['skipped'])} for name, group in groups.items()}
    (ROOT / 'fixtures/low-trin-baseline-comparison.json').write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(fixture, ensure_ascii=False))


if __name__ == '__main__':
    main()
