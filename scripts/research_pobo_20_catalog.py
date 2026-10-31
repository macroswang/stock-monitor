"""Discover 20 sessions of public option close-table links with bounded paging."""
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.option_pcr import eligible_sessions
from core.provider import CN
from .research_pobo_option_catalog import Listing, NEXT, URL

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/pobo-20-catalog-20261031.json'


def main():
    now = datetime.now(CN)
    sessions = eligible_sessions(now, 20)
    if len(sessions) != 20 or sessions[-1] != '2026-10-30':
        raise ValueError('研究限定截至 2026-10-30 的二十个已结束交易日')
    expected = {(day, product) for day in sessions for product in ('IO', 'HO', 'MO')}
    headers = {'User-Agent': 'Mozilla/5.0'}
    with urlopen(Request(URL, headers=headers), timeout=12) as response:
        content = response.read(1_000_000).decode('utf8')
    found = {}
    for page in range(1, 81):
        listing = Listing()
        listing.feed(content)
        if listing.current != page or not listing.hidden.get('__EVENTVALIDATION'):
            raise ValueError(f'分页状态不一致：{page}')
        for row in listing.rows:
            key = (row['date'], row['kind'])
            if key in expected and key in found and found[key]['url'] != row['url']:
                raise ValueError(f'同日同品种出现不同链接：{key}')
            if key in expected:
                found[key] = row
        report = {'observed_at': now.isoformat(), 'source': URL, 'pages': page,
                  'expected': sessions, 'items': list(found.values()),
                  'missing': [list(key) for key in sorted(expected - set(found))]}
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(f'page={page} found={len(found)}/60', flush=True)
        if set(found) == expected:
            break
        listing.hidden.update(__EVENTTARGET=NEXT, __EVENTARGUMENT='')
        time.sleep(.5)
        request = Request(URL, data=urlencode(listing.hidden).encode(), headers=headers)
        with urlopen(request, timeout=12) as response:
            content = response.read(1_000_000).decode('utf8')
    print('complete=', set(found)==expected, 'output=', OUT, flush=True)


if __name__ == '__main__':
    main()
