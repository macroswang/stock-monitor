"""Explore a fixed low-TRIN entry hypothesis, using isolated historical data.

No account, order or market-monitor settings are accessed. Outputs are
retrospective comparisons, not a production trading rule.
"""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from scripts.research_etf_position import compare, load_etf, within_day
from scripts.research_market_regime_extended import load_index

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/market-regime-research-20261029'


def summarize(events):
    values = [Decimal(e['net_yuan']) for e in events]
    mean = sum(values, Decimal(0)) / len(values) if values else None
    return {'n': len(values), 'positive': sum(x > 0 for x in values),
            'nonpositive': sum(x <= 0 for x in values),
            'average_net_yuan': str(mean.quantize(Decimal('0.01'))) if mean is not None else None}


def non_overlapping(events):
    selected = []
    for event in sorted(events, key=lambda e: e['signal_date']):
        if not selected or event['signal_date'] >= selected[-1]['exit_date']:
            selected.append(event)
    return selected


def evaluate(rows, index, etf):
    positions = {row['date']: i for i, row in enumerate(index)}
    if len(positions) != len(index) or len({r['date'] for r in rows}) != len(rows):
        raise ValueError('重复日期')
    events, skipped = [], []
    for row in sorted(rows, key=lambda r: r['date']):
        day = row['date']
        i = positions.get(day)
        if not row['weak_low_trin'] or day < '2026-01-19' or i is None or i + 6 >= len(index):
            continue
        entry, exit_ = index[i + 1]['date'], index[i + 6]['date']
        if entry not in etf or exit_ not in etf:
            raise ValueError('ETF 交易日期缺失')
        # compare calculates sell proceeds minus buy cost after fees/slippage.
        result = compare(etf[exit_][1], etf[entry][1])
        if not within_day(result['buy_price'], etf[entry]) or not within_day(result['sell_price'], etf[exit_]):
            skipped.append({'signal_date': day, 'entry_date': entry, 'exit_date': exit_,
                            'reason': '滑点后假设价格超出当日最高最低范围'})
            continue
        events.append({'signal_date': day, 'entry_date': entry, 'exit_date': exit_,
                       'breadth': row['breadth'], 'trin_amount': row['trin'],
                       'entry_price': result['buy_price'], 'exit_price': result['sell_price'],
                       'net_yuan': result['difference_yuan']})
    separated = non_overlapping(events)
    return {'all': summarize(events), 'non_overlapping': summarize(separated),
            'non_overlapping_signal_dates': [e['signal_date'] for e in separated],
            'events': events, 'skipped': skipped}


def main():
    input_path = OUT / 'extended-results.json'
    source = json.loads(input_path.read_text())
    index = load_index()
    result = evaluate(source['rows'], index, load_etf(index))
    result.update({'symbol': '510300', 'units': 5000, 'signal': '收盘上涨家数占比<20%，上证收盘<20日均线，成交额 TRIN<0.7',
                   'execution': 'T+1开盘买入，T+6开盘卖出；佣金每笔万2最低5元、单边滑点0.001元',
                   'warning': '事后探索、非作者原规则；样本重叠、早期底数部分未独立核验，开盘假设不保证成交；不代表个股或未来表现。',
                   'input_sha256': hashlib.sha256(input_path.read_bytes()).hexdigest()})
    (OUT / 'low-trin-entry-events.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    fixture = {key: result[key] for key in ('all', 'non_overlapping', 'units')}
    fixture.update(start=result['events'][0]['signal_date'], end=result['events'][-1]['signal_date'],
                   skipped=len(result['skipped']))
    (ROOT / 'fixtures/low-trin-entry-experiment.json').write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('all', 'non_overlapping', 'skipped')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
