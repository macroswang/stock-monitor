"""Publish the labelled P250 hypothesis as a research-only dated reference."""
import json
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.analyze_p250_baostock import main as calculate
from scripts.research_p250_history import OUT, ROOT


def main():
    calculate()  # Revalidates date continuity, source hashes and overlapping raw bars.
    comparison = json.loads((OUT / 'baostock-comparison.json').read_text())
    daily = json.loads((OUT / 'baostock-daily-research.json').read_text())
    overlap = json.loads((OUT / 'baostock-overlap.json').read_text())
    tdx = json.loads((OUT / 'tdx-close-crosscheck.json').read_text())
    collection = json.loads((OUT / 'baostock-collection.json').read_text())
    if len(comparison) != 10 or len({r['date'] for r in comparison}) != 10:
        raise ValueError('comparison is incomplete or duplicated')
    if len(overlap) < 33 or any(r['mismatches'] or r['only_moneytree'] or r['only_baostock'] for r in overlap):
        raise ValueError('overlapping source comparison is incomplete or inconsistent')
    if ([r['date'] for r in tdx['rows']] != collection['expected']
        or any(r['only_baostock'] or r['only_tdx'] or r['close_mismatches'] or r['matched'] < 4000 for r in tdx['rows'])):
        raise ValueError('TDX constituent close cross-check is incomplete or inconsistent')
    digest = hashlib.sha256()
    with (OUT / 'tdx-hsjday-20261028.zip').open('rb') as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != tdx['archive_sha256']:
        raise ValueError('TDX archive changed after cross-check')
    if len(daily) < 10 or len({r['date'] for r in daily}) != len(daily):
        raise ValueError('daily P250 reference incomplete or duplicated')
    for row in daily:
        if not 0 <= row['above'] <= row['eligible'] or row['eligible'] <= 0:
            raise ValueError('invalid MA breadth count')
        if abs(row['percent'] - 100 * row['above'] / row['eligible']) > 1e-9:
            raise ValueError('invalid MA breadth percentage')
    output = {'computed_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'scope': '研究假设：当日高于未复权250日均线的沪深活跃股票比例',
              'source': '早期171日 BaoStock 与通达信逐股核对收盘价；后101日 BaoStock 与 Money Tree 核对',
              'warning': '作者公式和股票池未确认，来源上游血缘未知，未复权价格可能受除权影响。',
              'rows': [{k: r[k] for k in ('date', 'eligible', 'above', 'percent')} for r in daily]}
    path = ROOT / 'fixtures/author-p250-research.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print('wrote research-only P250 dates:', len(output['rows']))


if __name__ == '__main__':
    main()
