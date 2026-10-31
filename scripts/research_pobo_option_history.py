"""Archive three dated third-party close-table groups; do not fill empty volumes."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from core.provider import CN
from .research_cffex_coverage import fetch, parse_close

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / 'docs/author-trading-system-20261028/pobo-catalog-20261031.json'
OUT = ROOT / 'docs/author-trading-system-20261028/pobo-option-history-20261031'


def summarize(rows):
    result = {}
    for letter, key in (('C', 'call'), ('P', 'put')):
        entries = [row for code, row in rows.items() if f'-{letter}-' in code]
        result[key] = {'known_volume': sum(r['volume'] for r in entries if r['volume'] is not None),
                       'missing_contracts': sum(r['volume'] is None for r in entries)}
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding='utf8'))
    entries = catalog['items']
    expected = {(day, kind) for day in ('2026-10-28', '2026-10-29', '2026-10-30') for kind in ('IO', 'HO', 'MO')}
    if {(row['date'], row['kind']) for row in entries} != expected or len(entries) != len(expected):
        raise ValueError('目录日期或品种不完整')
    report = {'observed_at': datetime.now(CN).isoformat(), 'source_catalog': str(CATALOG.relative_to(ROOT)), 'tables': []}
    for row in entries:
        raw = fetch(row['url'])
        data = parse_close(raw, row['kind'], row['date'])
        filename = f"{row['date']}-{row['kind']}.html"
        (OUT / filename).write_bytes(raw)
        report['tables'].append({**row, 'file': filename, 'sha256': hashlib.sha256(raw).hexdigest(),
                                 'contracts': len(data), **summarize(data)})
    report['note'] = '收盘表空白成交量保持未知；第三方上游和历史合约完整性尚待核验，不能将部分总量当作完整PCR。'
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(report['tables'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
