"""Compare one dated third-party IO close table with Sina's current chains.

Read-only research; a current chain is not proof of a historical contract list.
"""
import hashlib
import json
import re
import time
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/author-trading-system-20261028/cffex-coverage-20261031'
POBO = 'https://webnewslt1.pobo.net.cn/DATA/STOCK/6806310.HTML'
SINA = 'https://stock.finance.sina.com.cn/futures/api/openapi.php/OptionService.getOptionData'
MONTHS = ('io2611', 'io2612', 'io2701', 'io2703', 'io2706', 'io2709')
CODE = re.compile(r'IO(\d{4})-([CP])-(\d+)')


class Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.cell = None
        self.row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.inside, self.row = True, []
        elif tag == 'td' and self.inside:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.row.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.inside:
            if self.row:
                self.rows.append(self.row)
            self.inside = False


def parse_close(payload, prefix='IO', day='2026-10-30'):
    text = payload.decode('utf-8')
    try:
        d = date.fromisoformat(day)
    except (TypeError, ValueError):
        raise ValueError('交易日期无效') from None
    if d.isoformat() != day or prefix not in ('IO', 'HO', 'MO') or f'中国金融期货交易所{d:%m}月{d:%d}日{prefix}期权收盘行情' not in text or f'{d:%Y}年{d:%m}月{d:%d}日' not in text:
        raise ValueError('收盘表标题或交易日期不符')
    table = Table()
    table.feed(text)
    out = {}
    for row in table.rows:
        if not row or not re.fullmatch(prefix+r'\d{4}-[CP]-\d+', row[0]):
            continue
        if len(row) != 9 or row[0] in out or (row[6] and not re.fullmatch(r'[\d,]+', row[6])):
            raise ValueError('收盘表合约重复或成交量异常')
        out[row[0]] = {'close': row[4], 'volume': int(row[6].replace(',', '')) if row[6] else None}
    if not out:
        raise ValueError('收盘表没有识别到对应合约')
    return out


def parse_chain(payload, month):
    data = json.loads(payload)['result']['data']
    codes = []
    for side, letter in (('up', 'C'), ('down', 'P')):
        entries = data[side]
        if not isinstance(entries, list) or not entries:
            raise ValueError('期权链缺失')
        for item in entries:
            if not isinstance(item, list) or len(item) not in (8, 9) or not isinstance(item[-1], str):
                raise ValueError('期权链字段异常')
            symbol = item[-1]
            match = re.fullmatch(month + letter + r'(\d+)', symbol, flags=re.I)
            if not match:
                raise ValueError('期权链合约代码异常')
            codes.append(f'IO{month[2:]}-{letter}-{match.group(1)}')
    if len(set(codes)) != len(codes):
        raise ValueError('期权链合约重复')
    return set(codes)


def fetch(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://stock.finance.sina.com.cn/'})
    with urlopen(req, timeout=12) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('响应过大')
    return data


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw = fetch(POBO)
    closed = parse_close(raw)
    (OUTPUT / 'pobo-20261030.html').write_bytes(raw)
    hashes = {'pobo-20261030.html': hashlib.sha256(raw).hexdigest()}
    chains = set()
    for month in MONTHS:
        query = urlencode({'type': 'futures', 'product': 'io', 'exchange': 'cffex', 'pinzhong': month})
        payload = fetch(SINA + '?' + query)
        codes = parse_chain(payload, month)
        if chains & codes:
            raise ValueError('不同月份存在重复合约')
        chains.update(codes)
        filename = month + '.json'
        (OUTPUT / filename).write_bytes(payload)
        hashes[filename] = hashlib.sha256(payload).hexdigest()
        time.sleep(.25)
    # Compare only archived, separately captured daily bars; a mismatch is an
    # observation, not a reason to prefer either source.
    from .research_cffex_sina_probe import parse_dayline
    probe_dir = ROOT / 'docs/author-trading-system-20261028/cffex-sina-probe-20261031'
    sample = json.loads((probe_dir / 'report.json').read_text(encoding='utf-8'))
    comparisons = []
    for item in sample['rows']:
        payload = (probe_dir / item['file']).read_bytes()
        if hashlib.sha256(payload).hexdigest() != item['sha256']:
            raise ValueError('已保存的新浪日线哈希不一致')
        daily = parse_dayline(payload.decode('utf-8'), item['symbol'])['2026-10-30']
        m = re.fullmatch(r'io(\d{4})([CP])(\d+)', item['symbol'], re.I)
        if not m:
            raise ValueError('日线合约标识异常')
        code = f'IO{m.group(1)}-{m.group(2).upper()}-{m.group(3)}'
        reference = closed[code]
        comparisons.append({'code': code, 'sina': daily, 'pobo': reference,
                            'close_equal': Decimal(daily['close']) == Decimal(reference['close']),
                            'volume_equal': daily['volume'] == reference['volume']})
    report = {
        'observed_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'close_date': '2026-10-30', 'close_source': POBO, 'chain_source': SINA,
        'months': list(MONTHS), 'close_count': len(closed), 'chain_count': len(chains),
        'only_close': sorted(set(closed) - chains), 'only_chain': sorted(chains - set(closed)),
        'same': len(chains & set(closed)), 'missing_volume': sorted(code for code, row in closed.items() if row['volume'] is None),
        'sample_comparison': comparisons,
        'files_sha256': hashes,
        'note': '第三方收盘表与次日新浪期权链的观察对照，非交易所完整名单核验。',
    }
    (OUTPUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
