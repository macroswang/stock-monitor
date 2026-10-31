"""Archive a bounded historical CFFEX index-option series for research only."""
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from core.option_pcr import eligible_sessions
from core.provider import CN
from .research_cffex_official_history import BASE, parse

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/cffex-30-session-20261031'


def totals(groups):
    rows = {}
    for prefix, group in groups.items():
        call = sum(v['volume'] for code, v in group.items() if '-C-' in code)
        put = sum(v['volume'] for code, v in group.items() if '-P-' in code)
        if call <= 0:
            raise ValueError('认购成交量为零')
        rows[prefix] = {'contracts': len(group), 'call': call, 'put': put, 'pcr': put/call}
    return rows


def main():
    now = datetime.now(CN)
    days = eligible_sessions(now, 30)
    if len(days) != 30 or days[-1] != '2026-10-30':
        raise ValueError('本次研究限定截至 2026-10-30 的 30 个已结束交易日')
    OUT.mkdir(parents=True, exist_ok=True)
    records, errors = [], []
    for day in days:
        d = date.fromisoformat(day)
        url = BASE + f'{d:%Y%m}/{d:%d}/index.xml'
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
                raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError('响应超限')
            groups = totals(parse(raw, day))
            (OUT / f'{day}.xml').write_bytes(raw)
            records.append({'date': day, 'sha256': hashlib.sha256(raw).hexdigest(), 'groups': groups})
            print(day, 'ok', flush=True)
        except Exception as exc:
            errors.append({'date': day, 'error': type(exc).__name__ + ': ' + str(exc)})
            print(day, 'failed', type(exc).__name__, flush=True)
        time.sleep(.2)
    report = {'started_at': now.isoformat(), 'finished_at': datetime.now(CN).isoformat(), 'expected': days,
              'records': records, 'errors': errors,
              'note': 'HTTP 无传输完整性保证；仅 IO/HO/MO，历史补采不代表当时可得。'}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('saved', len(records), 'failed', len(errors), flush=True)


if __name__ == '__main__':
    main()
