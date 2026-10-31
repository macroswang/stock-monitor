"""Recompute a limited 5% turnover breadth reference from saved daily inputs.

This is an after-the-fact single-source study, not a live signal or a claim
that the video's stock universe or turnover calculation has been recovered.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'docs/trin-reconstruction-20261028/baostock'
OUTPUT = ROOT / 'docs/author-trading-system-20261028/turnover-five-study-20261031.json'
DATES = ('2026-10-22', '2026-10-23', '2026-10-27')


def analyze(payload):
    day = payload['date']
    rows = [r for r in payload['daily'] if r.get('code', '').startswith(('sh.60', 'sh.68', 'sz.00', 'sz.30'))]
    if not rows or len({r['code'] for r in rows}) != len(rows) or any(r.get('date') != day for r in rows):
        raise ValueError('日期、名单为空或代码重复')
    if any(r.get('tradestatus') not in ('0', '1') for r in rows):
        raise ValueError('交易状态缺失')
    active = [r for r in rows if r['tradestatus'] == '1']
    if not active:
        raise ValueError('没有交易中的股票')
    valid = []
    for row in active:
        try:
            value = Decimal(row['turn'])
            if not value.is_finite() or value < 0:
                raise ValueError
            valid.append(value)
        except (KeyError, InvalidOperation, ValueError):
            continue
    ge5 = sum(value >= 5 for value in valid)
    gt5 = sum(value > 5 for value in valid)
    missing = len(active)-len(valid)
    return {'date': day, 'collected_at': payload['fetched_at'], 'listed_rows': len(rows),
            'active': len(active), 'suspended': len(rows)-len(active), 'missing_turnover': missing,
            'at_least_5_count': ge5, 'above_5_count': gt5,
            'active_share_percent': 100 * ge5 / len(active) if not missing else None,
            'listed_share_percent': 100 * ge5 / len(rows) if not missing else None}


def main():
    rows = []
    for day in DATES:
        raw = (INPUT / f'{day}.json').read_bytes()
        result = analyze(json.loads(raw))
        result['input_sha256'] = hashlib.sha256(raw).hexdigest()
        rows.append(result)
    report = {'scope': 'BaoStock 沪深股票日线，含689类；5%以上按不小于5%计算',
              'warning': '历史事后补采，换手率未独立逐股核对；视频的股票池、分母及等于5%处理未知，不是作者指标或盘中数据。',
              'rows': rows}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
