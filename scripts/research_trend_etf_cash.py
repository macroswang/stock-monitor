"""Research only: a continuously held index/ETF trend proxy, never an author rule."""
import hashlib
import json
from decimal import Decimal, ROUND_DOWN

from scripts.research_market_regime_extended import load_index
from scripts.research_etf_position import OUT, load_etf, fee, within_day

D = Decimal


def simulate(index, etf, first, last, trend=True, capital=D('100000'), slip=D('0.001')):
    cash, units, trades, skipped, equity = capital, 0, [], [], []
    for i, bar in enumerate(index):
        day = bar['date']
        if day < first or day > last:
            continue
        if i == 0 or index[i-1]['ma20'] is None or day not in etf:
            raise ValueError('缺少前日信号或 ETF 日线：'+day)
        prev = index[i-1]
        desired = (prev['close'] > prev['ma20']) if trend else True
        raw = etf[day]
        direction = 'buy' if desired and not units else 'sell' if not desired and units else None
        if direction:
            price = D(str(raw[1])) + (slip if direction == 'buy' else -slip)
            if price <= 0 or not within_day(price, raw):
                skipped.append({'date': day, 'direction': direction, 'reason': '滑点后价格超出当日范围'})
            else:
                if direction == 'buy':
                    quantity = int((cash / (price * 100)).to_integral_value(rounding=ROUND_DOWN)) * 100
                    while quantity and price*quantity + fee(price*quantity) > cash:
                        quantity -= 100
                else:
                    quantity = units
                if quantity:
                    cost = fee(price*quantity)
                    cash += (-1 if direction == 'buy' else 1) * price*quantity - cost
                    units += quantity if direction == 'buy' else -quantity
                    if cash < 0 or units < 0:
                        raise ValueError('现金或持仓为负')
                    trades.append({'signal_date':prev['date'],'date':day,'direction':direction,
                                   'quantity':quantity,'price':str(price),'commission':str(cost)})
        value = cash + units*D(str(raw[2]))
        equity.append({'date':day,'value':str(value),'cash':str(cash),'units':units})
    if not equity:
        raise ValueError('没有可比较的交易日')
    peak = capital
    drawdown = D(0)
    for row in equity:
        value = D(row['value'])
        peak = max(peak, value)
        drawdown = max(drawdown, (peak-value)/peak)
    return {'final_value':str(D(equity[-1]['value']).quantize(D('.01'))),
            'return_percent':str(((D(equity[-1]['value'])/capital-1)*100).quantize(D('.01'))),
            'max_drawdown_percent':str((drawdown*100).quantize(D('.01'))),
            'trade_count':len(trades),'skipped':skipped,'trades':trades,'equity':equity}


def main():
    index=load_index();etf=load_etf(index)
    first,last='2026-01-19',index[-1]['date']
    result={'period':[first,last], 'initial_cash':'100000',
            'rule':'前一交易日上证收盘高于20日均线则次日开盘买入，否则卖出并持有现金。',
            'cost':'每笔佣金万2最低5元，单边滑点0.001元；收盘按持有份额市值计，不假设末日清仓。',
            'warning':'事后研究假设，不是作者公式；开盘成交、滑点与资金条件均为模拟，不含现金利息。ETF不可买卖、涨跌停和实际成交量未建模，ETF与上证指数并非同一资产；固定窗口、参数未预注册，无样本外验证。',
            'trend':simulate(index,etf,first,last), 'buy_and_hold':simulate(index,etf,first,last,trend=False)}
    result['segments']=[{'period':[start,end], 'trend':simulate(index,etf,start,end),
                         'buy_and_hold':simulate(index,etf,start,end,trend=False)}
                        for start,end in [('2026-01-19','2026-06-30'),('2026-07-01',last)]]
    result['input_sha256']={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in
        ('tencent-index-2025-2026.json','sina-index-2025-2026.json','tencent-etf-raw.json','tencent-etf-qfq.json','sina-etf.json')}
    (OUT/'trend-etf-cash-experiment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    summary={'period':result['period'],'initial_cash':result['initial_cash'],
             **{key:{q:v for q,v in result[key].items() if q not in ('trades','equity','skipped')}
                for key in ('trend','buy_and_hold')}}
    summary['segments']=[{'period':part['period'], **{key:{q:v for q,v in part[key].items() if q not in ('trades','equity','skipped')}
                         for key in ('trend','buy_and_hold')}} for part in result['segments']]
    (OUT.parent.parent/'fixtures/trend-etf-cash-experiment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:{q:v for q,v in result[k].items() if q not in ('trades','equity')} for k in ('trend','buy_and_hold')},ensure_ascii=False))


if __name__ == '__main__':main()
