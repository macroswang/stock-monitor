"""Check one 300ETF volume example; not a reconstruction of author rules."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/market-regime-research-20261029'


def main():
    tencent = DATA / 'tencent-etf-raw.json'
    sina = DATA / 'sina-etf.json'
    tx = json.loads(tencent.read_text())['data']['sh510300']['day']
    sn = {x['day']: x for x in json.loads(sina.read_text())}
    within = [x for x in tx if '2026-01-01' <= x[0] <= '2026-10-15']
    current = next(x for x in within if x[0] == '2026-10-15')
    year_high = max(within, key=lambda x: Decimal(x[5]))
    summer_high = max((x for x in within if '2026-07-01' <= x[0] <= '2026-09-30'), key=lambda x: Decimal(x[5]))
    out = []
    for row in (current, year_high, summer_high):
        day, volume = row[0], Decimal(row[5]) * 100
        other = Decimal(sn[day]['volume'])
        if abs(volume - other) > 50:
            raise ValueError(f'{day} 腾讯按手换算与新浪股数超过半手')
        out.append({'date': day, 'tencent_volume_shares': str(volume), 'sina_volume_shares': str(other)})
    current_volume = Decimal(out[0]['sina_volume_shares'])
    result = {'symbol': 'sh510300', 'observations': out,
              'versus_year_high_percent': float(current_volume / Decimal(out[1]['sina_volume_shares']) * 100),
              'versus_july_september_high_percent': float(current_volume / Decimal(out[2]['sina_volume_shares']) * 100),
              'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tencent, sina)},
              'scope': '仅华泰柏瑞沪深300ETF；所选峰值为本机研究窗口，未确认视频标的或箭头日期；不是资金净流向。'}
    target = ROOT / 'docs/author-trading-system-20261028/episode11-etf-volume-check.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
