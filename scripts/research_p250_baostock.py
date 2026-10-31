"""Collect dated BaoStock research snapshots, without touching application data."""
import hashlib
import json
import socket
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import baostock as bs

from scripts.crosscheck_trin_continuous import read
from scripts.research_p250_history import OUT, ROOT, before


def main():
    target = OUT / 'baostock'
    target.mkdir(parents=True, exist_ok=True)
    expected = before('2026-06-01', 171)
    records = {}
    failures = {}
    socket.setdefaulttimeout(45)
    login = bs.login()
    if login.error_code != '0':
        raise RuntimeError(login.error_msg)
    try:
        for day in reversed(expected):
            path = target / f'{day}.json'
            try:
                if path.exists():
                    payload = json.loads(path.read_text(encoding='utf-8'))
                else:
                    rows = read(bs.query_daily_history_k_AStock(date=day))
                    payload = {'date': day, 'provider': 'BaoStock query_daily_history_k_AStock',
                               'fetched_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'daily': rows}
                rows = payload['daily']
                if (payload['date'] != day or len(rows) < 4000
                    or any(r.get('date') != day for r in rows)
                    or len({r.get('code') for r in rows}) != len(rows)):
                    raise ValueError('missing, duplicate, or mixed-date records')
                if not path.exists():
                    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
                    time.sleep(1)
                records[day] = {'path': str(path.relative_to(ROOT)), 'rows': len(rows),
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'fetched_at': payload['fetched_at']}
                print(day, 'OK', len(rows), flush=True)
            except Exception as exc:
                failures[day] = f'{type(exc).__name__}: {exc}'
                print(day, 'FAILED', failures[day], flush=True)
            (OUT / 'baostock-collection.json').write_text(json.dumps(
                {'expected': expected, 'records': records, 'failures': failures,
                 'source': 'BaoStock; upstream unknown'}, ensure_ascii=False, indent=2) + '\n')
            if failures:
                break
    finally:
        bs.logout()
    if failures or len(records) != len(expected):
        raise RuntimeError('incomplete research history')
    print('COMPLETE', len(records), flush=True)


if __name__ == '__main__':
    main()
