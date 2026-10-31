"""Descriptive index-vs-stock breadth check, not a trading backtest."""
import json
from datetime import date
from pathlib import Path

from core.breadth import _next_verified_trading_day

ROOT = Path(__file__).resolve().parents[1]


def analyze(breadth, index):
    previous = {}
    for before, after in zip(index, index[1:]):
        following = _next_verified_trading_day(date.fromisoformat(before['date']))
        if following and following.isoformat() == after['date']:
            previous[after['date']] = before
    prices = {row['date']: row for row in index}
    rising, examples = 0, []
    for row in breadth:
        day = row['date']
        current, before = prices.get(day), previous.get(day)
        if not current or not before or row.get('status') != 'closed' or row.get('missing') != 0:
            continue
        if current['close'] <= before['close']:
            continue
        rising += 1
        a, d, flat = row['advance'], row['decline'], row['flat']
        if a < d:
            examples.append({'date': day, 'index_change_percent': 100 * (current['close'] / before['close'] - 1),
                             'advance': a, 'decline': d, 'flat': flat,
                             'advancing_percent': 100 * a / (a + d + flat)})
    return {'up_days': rising, 'up_index_more_declines': len(examples), 'examples': examples,
            'scope': '沪深活跃股票涨跌家数与上证指数日收盘；仅完整同日及连续指数日线，样本存在日期缺口',
            'warning': '描述性观察，非择时收益、投资胜率或作者交易规则；股票与指数数据来自不同来源。'}


def main():
    breadth = json.loads((ROOT / 'fixtures/breadth-history-verified.json').read_text())
    index = json.loads((ROOT / 'fixtures/index-technical-reference.json').read_text())['rows']
    result = analyze(breadth, index)
    output = ROOT / 'docs/market-regime-research-20261029/index-breadth-divergence.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('up_days', 'up_index_more_declines')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
