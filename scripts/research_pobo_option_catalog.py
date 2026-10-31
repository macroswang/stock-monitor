"""Read public listing pages and record dated option-table links, without trading."""
import json
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from core.provider import CN

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/pobo-catalog-20261031.json'
URL = 'https://webnewslt1.pobo.net.cn/DaoHangList.aspx?DIR=STOCK'
NEXT = 'ctl00$MainContent$DPRepBL$ctl02$ctl00'


class Listing(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden, self.rows, self.current, self._current = {}, [], None, False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('type') == 'hidden' and attrs.get('name'):
            self.hidden[attrs['name']] = attrs.get('value', '')
        if tag == 'span' and attrs.get('class') == 'current':
            self._current = True
        if tag == 'a':
            title, href = attrs.get('title', ''), attrs.get('href', '')
            match = re.fullmatch(r'中国金融期货交易所(\d{2})月(\d{2})日(IO|HO|MO)期权收盘行情', title)
            if match and re.fullmatch(r'DATA/STOCK/\d+\.HTML', href, re.I):
                self.rows.append({'date': f'2026-{match[1]}-{match[2]}', 'kind': match[3], 'url': urljoin(URL, href)})

    def handle_data(self, data):
        if self._current and data.isdigit():
            self.current = int(data)

    def handle_endtag(self, tag):
        if tag == 'span':
            self._current = False


def main():
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = urlopen(Request(URL, headers=headers), timeout=12)
    text = response.read(1_000_000).decode('utf8')
    rows = []
    for page in range(1, 26):
        listing = Listing()
        listing.feed(text)
        if listing.current != page or not listing.hidden.get('__EVENTVALIDATION'):
            raise ValueError('分页状态不一致')
        rows.extend(listing.rows)
        print(f'page={page} option_links={len(rows)}', flush=True)
        if {r['date'] for r in rows} >= {'2026-10-28', '2026-10-29', '2026-10-30'}:
            break
        listing.hidden.update(__EVENTTARGET=NEXT, __EVENTARGUMENT='')
        time.sleep(.5)
        request = Request(URL, data=urlencode(listing.hidden).encode(), headers=headers)
        with urlopen(request, timeout=12) as response:
            text = response.read(1_000_000).decode('utf8')
    if len({r['url'] for r in rows}) != len(rows):
        raise ValueError('分页结果重复')
    OUT.write_text(json.dumps({'observed_at': datetime.now(CN).isoformat(), 'pages': page,
                               'source': URL, 'items': rows}, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('saved', OUT)


if __name__ == '__main__':
    main()
