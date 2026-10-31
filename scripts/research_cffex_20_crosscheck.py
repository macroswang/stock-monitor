"""Cross-check 20 archived exchange days against dated public close tables."""
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from core.provider import CN
from .research_cffex_coverage import fetch, parse_close
from .research_cffex_official_history import compare, parse
from .research_cffex_official_series import OUT as EXCHANGE
from .research_pobo_20_catalog import OUT as CATALOG

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/cffex-20-crosscheck-20261031'


def main():
    catalog = json.loads(CATALOG.read_text(encoding='utf8'))
    exchange = json.loads((EXCHANGE / 'report.json').read_text(encoding='utf8'))
    if not catalog['items']:
        raise ValueError('第三方目录没有可核对的交易日')
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(CN).isoformat(), 'days': [], 'errors': [],
              'catalog_missing': catalog['missing']}
    by_day = {row['date']: row for row in exchange['records']}
    entries = {(row['date'],row['kind']): row for row in catalog['items']}
    for day in catalog['expected']:
        raw = (EXCHANGE / f'{day}.xml').read_bytes()
        if hashlib.sha256(raw).hexdigest() != by_day[day]['sha256']:
            raise ValueError('中金所原始响应哈希不一致')
        group = parse(raw, day)
        result = {'date': day, 'exchange_sha256': by_day[day]['sha256'], 'groups': {}}
        for prefix in ('IO', 'HO', 'MO'):
            if (day, prefix) not in entries:
                continue
            try:
                entry = entries[(day,prefix)]
                body = fetch(entry['url'])
                comparison = compare(group[prefix], parse_close(body, prefix, day))
                if comparison['volume_mismatch'] or comparison['price_mismatch'] or any(r['exchange_volume'] for r in comparison['pobo_blank']):
                    raise ValueError('成交量、收盘价或空白量不一致')
                (OUT / f'{day}-{prefix}.html').write_bytes(body)
                result['groups'][prefix] = {'source':entry['url'], 'pobo_sha256':hashlib.sha256(body).hexdigest(),
                                            'contracts':comparison['contracts'], 'call':comparison['call'],
                                            'put':comparison['put'], 'pcr':comparison['pcr'],
                                            'blank_count':len(comparison['pobo_blank'])}
            except Exception as exc:
                report['errors'].append({'date':day,'product':prefix,'error':type(exc).__name__+': '+str(exc)})
            time.sleep(.2)
        report['days'].append(result)
        report['finished_at'] = datetime.now(CN).isoformat()
        (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(day, f"matched={len(result['groups'])}/3 errors={len(report['errors'])}", flush=True)
    print('saved', len(report['days']), 'days', len(report['errors']), 'errors', flush=True)


if __name__ == '__main__':
    main()
