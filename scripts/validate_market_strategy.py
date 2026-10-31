"""固定假设按时间回放；研究比较，不产生实时信号或修改交易账户。"""
import hashlib
import json
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
CENT = D('0.01')


def fee(amount):
    return max(D('5'), amount * D('0.0002')).quantize(CENT, rounding=ROUND_HALF_UP)


def run(days, breadth, start, end, mode, capital=D('100000')):
    if mode not in ('cash', 'hold', 'trend', 'breadth_trin'):
        raise ValueError('未知策略')
    if any(days[i]['date'] >= days[i+1]['date'] for i in range(len(days)-1)):
        raise ValueError('行情日期重复或倒序')
    close_history = []
    records = []
    for bar in days:
        close_history.append(D(bar['index_close']))
        records.append({**bar, 'ma20': sum(close_history[-20:])/20 if len(close_history)>=20 else None})
    cash, units, basis = capital, 0, D(0)
    trades, skipped, equity, completed = [], [], [], []
    for i, bar in enumerate(records):
        day = bar['date']
        if day < start or day > end:
            continue
        if i == 0 or records[i-1]['ma20'] is None:
            raise ValueError('缺少上一交易日均线')
        prev = records[i-1]
        if mode == 'breadth_trin':
            b = breadth.get(prev['date'])
            if not b or b.get('status') != 'closed' or b.get('missing') != 0 or b.get('covered') != b.get('expected'):
                raise ValueError('缺少完整的上一交易日广度: '+prev['date'])
            if not (isinstance(b.get('advance'), int) and isinstance(b.get('decline'), int)
                    and b['advance']>0 and b['decline']>0 and b.get('trin_amount') is not None):
                raise ValueError('广度或 TRIN 无效: '+prev['date'])
            desired = D(prev['index_close']) > prev['ma20'] and b['advance'] > b['decline'] and D(str(b['trin_amount'])) <= 1
        else:
            desired = mode == 'hold' or (mode == 'trend' and D(prev['index_close']) > prev['ma20'])
        direction = 'buy' if desired and not units else 'sell' if not desired and units else None
        if direction:
            price = D(bar['etf_open']) + (D('0.001') if direction == 'buy' else -D('0.001'))
            if price <= 0 or not D(bar['etf_low']) <= price <= D(bar['etf_high']):
                skipped.append({'date': day, 'direction': direction, 'reason': '假设价格超出日内区间'})
            else:
                count = int((cash / (price * 100)).to_integral_value(rounding=ROUND_DOWN))*100 if direction == 'buy' else units
                if direction == 'buy':
                    while count and price*count + fee(price*count) > cash:
                        count -= 100
                if count:
                    costs = fee(price*count)
                    if direction == 'buy':
                        basis = price*count + costs
                        cash -= basis
                        units = count
                    else:
                        proceeds = price*count - costs
                        completed.append(proceeds-basis)
                        cash += proceeds
                        units, basis = 0, D(0)
                    trades.append({'signal_date': prev['date'], 'date': day, 'direction': direction,
                                   'units': count, 'price': str(price), 'fee': str(costs)})
        value = cash + units * D(bar['etf_close'])
        equity.append({'date': day, 'value': str(value.quantize(CENT)), 'units': units})
    if not equity:
        raise ValueError('没有交易日')
    peak, max_drawdown = capital, D(0)
    for row in equity:
        value = D(row['value'])
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak-value)/peak)
    wins = [p for p in completed if p > 0]
    losses = [p for p in completed if p < 0]
    win_loss = (sum(wins)/len(wins))/(-sum(losses)/len(losses)) if wins and losses else None
    return {'net_return_percent': float(((D(equity[-1]['value'])/capital-1)*100).quantize(CENT)),
            'max_drawdown_percent': float((max_drawdown*100).quantize(CENT)),
            'closed_trades': len(completed), 'wins': len(wins), 'losses': len(losses), 'flat': sum(p == 0 for p in completed),
            'win_rate_percent': float((D(len(wins))/len(completed)*100).quantize(CENT)) if completed else None,
            'profit_loss_ratio': float(win_loss.quantize(CENT)) if win_loss is not None else None,
            'open_units': units, 'trade_count': len(trades), 'skipped': skipped, 'trades': trades, 'equity': equity}


def main():
    paths = [ROOT/'fixtures/market-validation-inputs.json', ROOT/'fixtures/breadth-history-verified.json']
    raw = [p.read_bytes() for p in paths]
    data, history = (json.loads(x) for x in raw)
    breadth = {r['date']: r for r in history}
    if len(breadth) != len(history):
        raise ValueError('广度日期重复')
    windows = [('全部', '2026-03-24', '2026-10-29'), ('前段', '2026-03-24', '2026-06-30'), ('后段', '2026-07-01', '2026-10-29')]
    modes = [('持币', 'cash'), ('买入持有', 'hold'), ('均线参考', 'trend'), ('均线＋广度＋TRIN', 'breadth_trin')]
    result = {'description': '上证前日收盘、均线及广度生成信号，次日开盘模拟交易 510300。',
              'limitations': '事后采集、事后规则及分段，非独立样本外验证；价格为假设，不保证成交；未模拟排队、流动性、停牌或冲击；ETF 不代表个股。',
              'cost': '初始10万元；每笔佣金万2最低5元，单边滑点0.001元；按收盘净值计算回撤，期末未强制清仓。',
              'sources': {p.name: hashlib.sha256(v).hexdigest() for p,v in zip(paths,raw)},
              'windows': []}
    for name, start, end in windows:
        result['windows'].append({'name':name,'start':start,'end':end,'strategies':[
            {'name': label, 'mode': mode, **run(data['days'],breadth,start,end,mode)} for label,mode in modes]})
    (ROOT/'fixtures/market-validation-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for part in result['windows']:
        print(part['name'], [(x['name'],x['net_return_percent'],x['max_drawdown_percent'],x['closed_trades']) for x in part['strategies']])


if __name__ == '__main__':
    main()
