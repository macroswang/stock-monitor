"""Compare the published 2026-10-29 IO2703/MO2703 chains with close tables."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from core.provider import CN
from .research_cffex_coverage import Table, parse_close
from .research_pobo_option_history import OUT as POBO

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/tenagent-pobo-20261031'
URL = 'https://www.ten-agent.cn/options.html'


def compare(raw, prefix, pobo):
    text = raw.decode('utf8')
    if '数据截止 2026-10-29 收盘' not in text or 'IO2703' not in text or 'MO2703' not in text:
        raise ValueError('第三方行情日期或合约月份不符')
    table = Table()
    table.feed(text)
    rows = [r for r in table.rows if len(r) == 21 and r[10].replace(',', '').isdigit()]
    if len(rows) != 41 or prefix not in ('IO', 'MO'):
        raise ValueError('第三方行情档位数异常')
    selected = rows[:18] if prefix == 'IO' else rows[18:]
    result = []
    for row in selected:
        for side, idx in (('C', 6), ('P', 14)):
            code = f"{prefix}2703-{side}-{row[10].replace(',', '')}"
            raw_volume = row[idx].replace(',', '')
            if code not in pobo or not raw_volume.isdigit():
                raise ValueError('第三方合约或成交量异常')
            value, other = int(raw_volume), pobo[code]['volume']
            result.append({'code': code, 'tenagent': value, 'pobo': other})
    if len({r['code'] for r in result}) != len(result):
        raise ValueError('第三方期权合约重复')
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with urlopen(Request(URL, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
        raw = response.read(3_000_000)
    report = {'observed_at': datetime.now(CN).isoformat(), 'quote_date': '2026-10-29',
              'source': URL, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'groups': {}}
    for prefix in ('IO', 'MO'):
        pobo_raw = (POBO / f'2026-10-29-{prefix}.html').read_bytes()
        rows = compare(raw, prefix, parse_close(pobo_raw, prefix, '2026-10-29'))
        report['groups'][prefix] = {'pobo_sha256': hashlib.sha256(pobo_raw).hexdigest(), 'rows': rows}
    report['note'] = '仅比较一个到期月份和页面显示行权价；来源可能共享上游，不能推定未展示合约。'
    (OUT / 'tenagent.html').write_bytes(raw)
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    for prefix, group in report['groups'].items():
        rows = group['rows']
        print(prefix, '合约', len(rows), '一致', sum(r['tenagent'] == r['pobo'] for r in rows),
              '收盘表空白且报价为零', sum(r['pobo'] is None and r['tenagent'] == 0 for r in rows))


if __name__ == '__main__':
    main()
