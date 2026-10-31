"""Reproduce a dated market-cap proxy comparison from archived public data.

This is a descriptive research check, not the author's market-cap universe,
an institutional trading measure, or a trading signal.
"""
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'docs/trin-reconstruction-20261028/baostock/2026-03-23.json'
HISTORY = ROOT / 'fixtures/breadth-history-verified.json'
OUT = ROOT / 'docs/author-trading-system-20261028/march-size-distribution-20261031.json'


def analyze(payload, expected):
    rows, skipped = [], []
    for item in payload['daily']:
        code = item.get('code', '')
        if not (code.startswith(('sh.', 'sz.')) and not code.startswith('sh.689')):
            continue
        if item.get('tradestatus') != '1':
            continue
        try:
            volume, turnover, close, preclose, amount = (Decimal(item[k]) for k in
                ('volume', 'turn', 'close', 'preclose', 'amount'))
            if not all(v.is_finite() for v in (volume, turnover, close, preclose, amount)) or min(volume, turnover, close, preclose) <= 0 or amount < 0:
                raise ValueError('invalid numeric field')
            rows.append({'code': code, 'rising': close > preclose,
                         'float_cap_proxy': volume / turnover * 100 * close,
                         'amount': amount})
        except (KeyError, InvalidOperation, ValueError):
            skipped.append(code)
    if len(rows) != expected['advance'] + expected['decline'] + expected['flat'] or sum(r['rising'] for r in rows) != expected['advance']:
        raise ValueError('有效样本或上涨家数与已核验底表不一致')
    ranked = sorted(rows, key=lambda r: (-r['float_cap_proxy'], r['code']))
    large = {r['code'] for r in ranked[:math.ceil(len(ranked)*.1)]}
    rising = [r for r in rows if r['rising']]
    large_up = [r for r in rising if r['code'] in large]
    up_amount = sum(r['amount'] for r in rising)
    if not up_amount:
        raise ValueError('上涨组成交额为零')
    return {'eligible':len(rows), 'excluded_active':skipped, 'rising':len(rising),
            'top_decile_size':len(large), 'top_decile_rising':len(large_up),
            'top_decile_rising_share_percent':100*len(large_up)/len(rising),
            'top_decile_rising_turnover_share_percent':float(100*sum(r['amount'] for r in large_up)/up_amount),
            'top_decile_cutoff_proxy_yi':float(ranked[len(large)-1]['float_cap_proxy']/Decimal(10**8)),
            'bottom_rising_examples':[{'code':r['code'],'float_cap_proxy_yi':float(r['float_cap_proxy']/Decimal(10**8))}
                                      for r in sorted(rising,key=lambda r:r['float_cap_proxy'])[:5]]}


def main():
    source = SOURCE.read_bytes()
    payload = json.loads(source)
    expected = next(r for r in json.loads(HISTORY.read_text()) if r['date']=='2026-03-23')
    result = analyze(payload, expected)
    report = {'date':'2026-03-23', 'collected_at':payload['fetched_at'],
              'source_sha256':hashlib.sha256(source).hexdigest(),
              'basis':'沪深股票，不含北交所及689类；未复权收盘价高于昨收为上涨',
              'cap_method':'按成交股数 ÷ 换手率 × 100 × 收盘价估算流通市值，并取样本前10%；换手率有精度误差',
              'limitations':'流通市值估算仅为规模代理，不是作者权重股定义或当时指数成分；不得推断投资者身份、主动买入或资金净流入。',
              'result':result}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
