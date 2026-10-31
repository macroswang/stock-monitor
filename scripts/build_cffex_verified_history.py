"""Build the read-only seed from archived, contract-by-contract comparisons."""
import hashlib
import json
from pathlib import Path

from core.option_pcr import add_bands
from .research_cffex_20_crosscheck import OUT
from .research_cffex_coverage import parse_close
from .research_cffex_official_history import compare, parse
from .research_cffex_official_series import OUT as EXCHANGE

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / 'fixtures/cffex-index-pcr-verified.json'
PREVIEW = ROOT / 'public/index-option-pcr-preview.json'


def main():
    report = json.loads((OUT / 'report.json').read_text())
    if report['errors']:
        raise ValueError('核对存在错误，不能生成历史数据')
    existing = {(r['date'], r['product']): r for r in json.loads(SEED.read_text())}
    rows = dict(existing)
    for day in report['days']:
        if not day['groups']:
            continue
        raw = (EXCHANGE / f"{day['date']}.xml").read_bytes()
        if hashlib.sha256(raw).hexdigest() != day['exchange_sha256']:
            raise ValueError('交易所响应哈希不一致')
        exchange = parse(raw, day['date'])
        for product, group in day['groups'].items():
            body = (OUT / f"{day['date']}-{product}.html").read_bytes()
            if hashlib.sha256(body).hexdigest() != group['pobo_sha256']:
                raise ValueError('收盘表响应哈希不一致')
            comparison = compare(exchange[product], parse_close(body, product, day['date']))
            if comparison['volume_mismatch'] or comparison['price_mismatch'] or any(r['exchange_volume'] for r in comparison['pobo_blank']):
                raise ValueError('逐合约对照失败')
            if any(comparison[k] != group[k] for k in ('contracts', 'call', 'put', 'pcr')):
                raise ValueError('对照报告与原始记录不一致')
            key = (day['date'], product)
            row = {'date': day['date'], 'product': product, 'call_volume': group['call'],
                   'put_volume': group['put'], 'total_volume': group['call'] + group['put'],
                   'pcr': group['pcr'], 'contracts': group['contracts'],
                   'collected_at': report['finished_at'], 'exchange_sha256': day['exchange_sha256'],
                   'pobo_sha256': group['pobo_sha256'], 'basis': '中金所日统计；第三方收盘表逐合约对照'}
            if key in existing:
                old = existing[key]
                if any(old[k] != row[k] for k in ('call_volume','put_volume','contracts','exchange_sha256')):
                    raise ValueError('已有记录与新核验结果不一致')
                row = {**row, 'collected_at': old['collected_at']}
            rows[key] = row
    output = [rows[k] for k in sorted(rows)]
    preview = {p: {'days': add_bands([r for r in output if r['product'] == p]),
                   'running': False, 'error': '', 'latest_eligible': '2026-10-30'}
               for p in ('IO','HO','MO')}
    SEED.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    PREVIEW.write_text(json.dumps(preview, ensure_ascii=False, indent=2)+'\n')
    print(f'已核对 {len(output)} 条；缺失 {len(report["catalog_missing"])} 条')


if __name__ == '__main__':
    main()
