"""Cross-check CFFEX public HTTP daily XML against archived close tables.

The transport is unencrypted; independent comparisons reduce but cannot
eliminate the possibility of data alteration. Research only.
"""
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from core.provider import CN
from .research_cffex_coverage import parse_close
from .research_pobo_option_history import OUT as POBO

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/cffex-official-history-20261031'
BASE = 'http://www.cffex.com.cn/sj/hqsj/rtj/'
KINDS = ('IO', 'HO', 'MO')


def parse(raw, day):
    expected = date.fromisoformat(day).strftime('%Y%m%d')
    root = ElementTree.fromstring(raw)
    if root.tag != 'dailydatas':
        raise ValueError('中金所日行情根节点异常')
    result = {k: {} for k in KINDS}
    for row in root.findall('dailydata'):
        product, code = row.findtext('productid'), row.findtext('instrumentid')
        if product not in KINDS:
            continue
        volume = row.findtext('volume')
        if row.findtext('tradingday') != expected or not isinstance(code, str) or not re.fullmatch(product+r'\d{4}-[CP]-\d+', code):
            raise ValueError('期权合约或日期异常')
        if code in result[product] or not isinstance(volume, str) or not volume.isdigit():
            raise ValueError('期权合约重复或成交量缺失')
        result[product][code] = {'volume': int(volume), 'close': row.findtext('closeprice')}
    if any(not rows for rows in result.values()):
        raise ValueError('期权品种缺失')
    return result


def compare(group, pobo):
    if set(group) != set(pobo):
        raise ValueError('交易所与收盘表的合约集合不同')
    mismatch, blank, prices = [], [], []
    for code, row in pobo.items():
        official = group[code]
        if row['volume'] is None:
            blank.append({'code': code, 'exchange_volume': official['volume']})
            continue
        if row['volume'] != official['volume']:
            mismatch.append(code)
        try:
            if Decimal(row['close'].replace(',', '')) != Decimal(official['close']):
                prices.append(code)
        except (InvalidOperation, TypeError):
            raise ValueError('价格异常') from None
    call = sum(v['volume'] for k,v in group.items() if '-C-' in k)
    put = sum(v['volume'] for k,v in group.items() if '-P-' in k)
    return {'contracts': len(group), 'pobo_blank': blank, 'volume_mismatch': mismatch,
            'price_mismatch': prices, 'call': call, 'put': put, 'pcr': put/call if call else None}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'observed_at': datetime.now(CN).isoformat(), 'transport': 'HTTP，不提供传输完整性保证', 'days': []}
    for day in ('2026-10-28', '2026-10-29', '2026-10-30'):
        d = date.fromisoformat(day)
        url = BASE + f'{d:%Y%m}/{d:%d}/index.xml'
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError('响应超限')
        parsed = parse(raw, day)
        daily = {'date': day, 'source': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'groups': {}}
        for prefix in KINDS:
            pobo_raw = (POBO / f'{day}-{prefix}.html').read_bytes()
            result = compare(parsed[prefix], parse_close(pobo_raw, prefix, day))
            result['pobo_sha256'] = hashlib.sha256(pobo_raw).hexdigest()
            daily['groups'][prefix] = result
        (OUT / f'{day}.xml').write_bytes(raw)
        report['days'].append(daily)
        print(day, {k: {'contracts': v['contracts'], 'blank':len(v['pobo_blank']),
                        'nonzero_blank':sum(x['exchange_volume']!=0 for x in v['pobo_blank']),
                        'volume_mismatch':len(v['volume_mismatch']), 'price_mismatch':len(v['price_mismatch']),
                        'pcr':round(v['pcr'], 4)} for k,v in daily['groups'].items()}, flush=True)
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


if __name__ == '__main__':
    main()
