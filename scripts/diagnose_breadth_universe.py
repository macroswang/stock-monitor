"""Read-only diagnostics for an incomplete public stock-list snapshot."""
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from core.breadth import SINA, get
from scripts.research_p250_history import OUT


def main():
    now = lambda: datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    started = now()
    url = SINA + 'Market_Center.getHQNodeStockCount?node=hs_a'
    first = int(json.loads(get(url)))
    if not 1000 <= first <= 20000:
        raise ValueError('unexpected starting total')

    def page(n):
        time.sleep(.05)
        query = urlencode(dict(page=n, num=80, sort='symbol', asc=1, node='hs_a', symbol='', _s_r_a='page'))
        try:
            response = json.loads(get(SINA + 'Market_Center.getHQNodeData?' + query))
            if not isinstance(response, list):
                return {'page': n, 'error': 'not a list', 'rows': []}
            return {'page': n, 'rows': response}
        except Exception as exc:
            return {'page': n, 'error': f'{type(exc).__name__}: {exc}', 'rows': []}

    with ThreadPoolExecutor(max_workers=2) as pool:
        pages = list(pool.map(page, range(1, (first + 79) // 80 + 1)))
    final = int(json.loads(get(url)))
    records = [r for p in pages for r in p['rows']]
    counts = Counter(r.get('symbol', '') for r in records)
    duplicates = {k: v for k, v in counts.items() if k and v > 1}
    report = {'started_at': started, 'finished_at': now(), 'count_before': first, 'count_after': final,
              'rows_returned': len(records), 'unique_nonempty_codes': len(counts) - ('' in counts),
              'empty_symbols': counts.get('', 0), 'duplicates': duplicates,
              'pages': [{'page': p['page'], 'rows': len(p['rows']), 'error': p.get('error')} for p in pages]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'universe-diagnostic.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'pages'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
