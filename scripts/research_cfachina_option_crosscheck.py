"""Archive a dated CFA delayed option snapshot and compare a saved Eastmoney snapshot.

Research only. A delayed snapshot is not an exchange settlement record and
must not be used as the author's unidentified whole-market PCR.
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.provider import CN

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/cfachina-crosscheck-20261031'
EAST = ROOT / 'docs/author-trading-system-20261028/cffex-eastmoney-probe-20261031/eastmoney.json'
KINDS = {'IO': '沪深300股指', 'HO': '上证50股指', 'MO': '中证1000股指'}
ENDPOINT = 'https://www.cfachina.org/report/api/variety/optionData?'


def parse(payload, prefix, day):
    data = payload.get('data') if isinstance(payload, dict) and payload.get('errcode') == 0 else None
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list) and data[k] for k in ('finList', 'delayList')):
        raise ValueError('协会响应缺少合约或延时行情')
    result = {}
    for row in data['delayList']:
        code = row.get('tradeCode') if isinstance(row, dict) else None
        volume = row.get('volume') if isinstance(row, dict) else None
        if not isinstance(code, str) or not re.fullmatch(prefix+r'\d{4}-[CP]-\d+', code) or code in result:
            raise ValueError('合约代码异常或重复')
        if row.get('tradeDate') != day or not isinstance(volume, str) or not volume.isdigit():
            raise ValueError('交易日或成交量异常')
        result[code] = int(volume)
    contracts = [row.get('tradeCode') for row in data['finList'] if isinstance(row, dict) and row.get('tradeDate') == day]
    if len(contracts) != len(data['finList']) or len(set(contracts)) != len(contracts) or set(contracts) != set(result):
        raise ValueError('合约信息与延时行情不一致')
    return result


def compare(group, east):
    if set(group) != set(east):
        raise ValueError('来源合约集合不一致')
    mismatch = [code for code in group if group[code] != east[code]]
    call = sum(v for k, v in group.items() if '-C-' in k)
    put = sum(v for k, v in group.items() if '-P-' in k)
    return {'contracts': len(group), 'zero_volume': sum(v == 0 for v in group.values()),
            'volume_mismatch': mismatch, 'call': call, 'put': put,
            'pcr': put / call if call else None}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw_east = EAST.read_bytes()
    snapshot = json.loads(raw_east)
    if not isinstance(snapshot.get('list'), list) or snapshot.get('total') != len(snapshot['list']):
        raise ValueError('东方财富快照不完整')
    rows = snapshot['list']
    summary = {}
    for prefix, kind in KINDS.items():
        url = ENDPOINT + urlencode({'kind': kind, 'flag': 1})
        request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cfachina.org/servicesupport/sspz/?type=5'})
        with urlopen(request, timeout=10) as response:
            raw = response.read(4_000_000)
        payload = json.loads(raw)
        group = parse(payload, prefix, '2026-10-30')
        matching = [row for row in rows if isinstance(row.get('dm'), str) and row['dm'].startswith(prefix)]
        east = {row['dm']: row['vol'] for row in matching}
        if len(east) != len(matching) or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in east.values()):
            raise ValueError('东方财富合约重复或成交量异常')
        item = compare(group, east)
        item.update(source=url, sha256=hashlib.sha256(raw).hexdigest())
        summary[prefix] = item
        (OUT / f'{prefix}.json').write_bytes(raw)
    result = {'observed_at': datetime.now(CN).isoformat(), 'association_quote_date': '2026-10-30',
              'eastmoney_sha256': hashlib.sha256(raw_east).hexdigest(), 'groups': summary,
              'note': '协会为带日期的延时快照；东财快照无日期；来源可能共享上游，非交易所结算文件。'}
    (OUT / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
