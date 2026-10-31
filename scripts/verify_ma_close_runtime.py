"""Validate an actual closed sample in a temporary account-free local database."""
import argparse
import hashlib
import json
import tempfile
import time
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from core.breadth import Breadth, _next_verified_trading_day, collect, summarize
from core.store import Store
from scripts.research_ma_quote_bridge import rows_for_day
from scripts.research_p250_history import OUT, ROOT
from scripts.research_p250_quote_bridge import replay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-date', required=True)
    parser.add_argument('--recheck-saved', action='store_true')
    args = parser.parse_args()
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    if now.date().isoformat() != args.expected_date or now.strftime('%H:%M') < '15:15':
        raise ValueError('must be the expected date and at or after 15:15 Beijing time')
    raw_path = OUT / (args.expected_date + '.closed-raw.json')
    if args.recheck_saved:
        raw = json.loads(raw_path.read_text())
        result = summarize(raw['quotes'], raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])
    else:
        result, raw = collect()
    if result['date'] != args.expected_date or result['status'] != 'closed' or result['missing']:
        raise ValueError('not a complete closed snapshot for the expected date')
    if not args.recheck_saved:
        raw_path.write_text(json.dumps(raw, ensure_ascii=False) + '\n')
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        store = Store(directory + '/isolated.sqlite3')
        service = Breadth(store)
        with patch('core.breadth.collect', return_value=(result, raw)):
            service.refresh(force=True)
        if service.error:
            raise ValueError('isolated service failed: ' + service.error)
        view = service.view()
        day = next(x for x in view['days'] if x['date'] == args.expected_date)
        if 'ma_daily' not in day or day['ma_daily']['status'] != 'closed':
            raise ValueError('service did not produce a closed MA reference')
        if store.query('SELECT * FROM watch') or store.query('SELECT * FROM events'):
            raise ValueError('isolated validation changed watch or events')
        elapsed = time.perf_counter() - start
        store.db.close()
    collection = json.loads((OUT / 'baostock-collection.json').read_text())
    early = json.loads((ROOT / 'docs/author-mcl-history-20261029/collection.json').read_text())
    later = json.loads((ROOT / 'docs/trin-sensitivity-20261028/summary.json').read_text())
    days = collection['expected'] + early['expected'] + [r['date'] for r in later['results']] + ['2026-10-28']

    def reader(d):
        record = collection['records'].get(d)
        if not record:
            return rows_for_day(d)
        payload = json.loads((ROOT / record['path']).read_text())
        return [{'symbol': r['code'][3:] + '.' + r['code'][:2].upper(),
                 'close': r['close'], 'pre_close': r['preclose']}
                for r in payload['daily'] if r['tradestatus'] == '1' and int(r['volume'] or 0) > 0]
    independent, _ = replay(days, reader, raw, 'closed')
    if day['ma_daily']['windows'] != independent['models']['unadjusted_prevclose_checked']:
        raise ValueError('isolated service and independent replay disagree')
    report = {'date': result['date'], 'status': result['status'], 'expected': result['expected'],
              'covered': result['covered'], 'missing': result['missing'], 'first_quote': result['first_quote'],
              'last_quote': result['last_quote'], 'collected_at': result['collected_at'],
              'ma': day['ma_daily'], 'isolated_service_seconds': round(elapsed, 3),
              'replay_models_match': True, 'raw_path': str(raw_path.relative_to(ROOT)),
              'raw_sha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(),
              'note': 'One actual post-close sample; no guarantee of later availability or author formula.'}
    (OUT / (args.expected_date + '.closed-validation.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
