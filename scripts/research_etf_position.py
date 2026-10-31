"""Independent event comparisons; does not place trades or touch accounts.

Each event starts with the same assumed existing 10,000 ETF units. On the next
open sell 5,000, then buy the same 5,000 at the open six sessions after the
signal. Compare with holding throughout, after hypothetical execution costs.
Events are separate and may overlap, so their results cannot be added.
"""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from scripts.research_market_regime_extended import load_index

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/market-regime-research-20261029'
D=Decimal


def fee(amount):
    return max(D('5'),amount*D('0.0002')).quantize(D('0.01'),rounding=ROUND_HALF_UP)


def compare(sell_open,buy_open,units=5000,slip=D('0.001')):
    sell,buy=D(str(sell_open))-slip,D(str(buy_open))+slip
    if min(sell,buy)<=0 or units<=0 or units%100:raise ValueError('ETF价格或份额无效')
    sell_amount=sell*units;buy_amount=buy*units
    sell_fee,buy_fee=fee(sell_amount),fee(buy_amount)
    return {'sell_price':str(sell),'buy_price':str(buy),'sell_fee':str(sell_fee),'buy_fee':str(buy_fee),
            'difference_yuan':str((sell_amount-buy_amount-sell_fee-buy_fee).quantize(D('0.01')))}


def within_day(price,bar):
    """Reject hypothetical prices outside the observed day's high/low."""
    return D(bar[4])<=D(price)<=D(bar[3])


def non_overlapping(events):
    """Choose chronologically; next signal may be on the prior rebuy day close."""
    chosen=[]
    for event in sorted(events,key=lambda row:row['signal_date']):
        if not chosen or event['signal_date']>=chosen[-1]['buy_date']:
            chosen.append(event)
    return chosen


def load_etf(index):
    raw=json.loads((OUT/'tencent-etf-raw.json').read_text())['data']['sh510300']['day']
    adj=json.loads((OUT/'tencent-etf-qfq.json').read_text())['data']['sh510300']['qfqday']
    sina=json.loads((OUT/'sina-etf.json').read_text())
    s={r['day']:r for r in sina};a={r[0]:r for r in adj}
    if len(s)!=len(sina) or len(a)!=len(adj) or [r[0] for r in raw]!=[r['date'] for r in index]:
        raise ValueError('ETF 日期缺失或重复')
    for r in raw:
        day=r[0]
        if day not in s or day not in a or any(D(r[i])!=D(s[day][key]) for i,key in ((1,'open'),(2,'close'))):
            raise ValueError('ETF 开收盘双源不一致：'+day)
        if day>='2026-01-19' and any(D(r[i])!=D(a[day][i]) for i in (1,2,3,4)):
            raise ValueError('研究窗口发现复权调整：'+day)
        if min(D(r[i]) for i in (1,2,3,4,5))<=0:raise ValueError('ETF日线无效：'+day)
    return {r[0]:r for r in raw}


def main():
    idx=load_index();etf=load_etf(idx);positions={r['date']:i for i,r in enumerate(idx)}
    research=json.loads((OUT/'extended-results.json').read_text())
    events=[];skipped=[]
    for item in research['rows']:
        day=item['date'];i=positions.get(day)
        if not item['weak'] or day<'2026-01-19' or i is None or i+6>=len(idx):continue
        sold,bought=idx[i+1]['date'],idx[i+6]['date']
        calc=compare(etf[sold][1],etf[bought][1])
        if not within_day(calc['sell_price'],etf[sold]) or not within_day(calc['buy_price'],etf[bought]):
            skipped.append({'signal_date':day,'sell_date':sold,'buy_date':bought,
                            'reason':'滑点后假设价格超出当日最高最低范围'})
            continue
        event={'signal_date':day,'sell_date':sold,'buy_date':bought,'trin':item['trin'],**calc}
        events.append(event)
    if not events:raise ValueError('没有可比较的事件')
    amounts=[D(r['difference_yuan']) for r in events]
    separated=non_overlapping(events)
    separated_amounts=[D(r['difference_yuan']) for r in separated]
    result={'symbol':'510300','assumed_existing_units':10000,'sell_and_rebuy_units':5000,
            'commission':'每笔万2，最低5元','slippage':'每边0.001元','stamp_tax':'ETF二级市场假设免印花税',
            'rule':'T日收盘条件：上涨家数占比<20%且上证收盘低于20日均线；T+1开盘卖出5000份，T+6开盘买回5000份，与一直持有比较',
            'warning':'独立假设，非作者规则；开盘价并不保证成交。事件可能重叠，不可相加；未核验当时信息可得性和全部交易约束；先卖后买需要已有可卖份额及潜在额外现金。',
            'n':len(events),'better':sum(x>0 for x in amounts),'worse':sum(x<0 for x in amounts),'skipped':skipped,
            'average_difference_yuan':str((sum(amounts)/len(amounts)).quantize(D('0.01'))),
            'sources':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ['tencent-etf-raw.json','tencent-etf-qfq.json','sina-etf.json']},
            'events':events,
            'non_overlapping':{'n':len(separated),'better':sum(x>0 for x in separated_amounts),
                               'worse':sum(x<0 for x in separated_amounts),
                               'average_difference_yuan':str((sum(separated_amounts)/len(separated_amounts)).quantize(D('0.01'))),
                               'selection':'按信号日先后，前次买回日收盘及以后才接受下一个信号；排除时间重叠但不代表统计独立',
                               'signal_dates':[r['signal_date'] for r in separated]}}
    (OUT/'etf-position-events.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    fixture={key:result[key] for key in ('n','better','worse','average_difference_yuan','assumed_existing_units','sell_and_rebuy_units')}
    fixture.update(start=events[0]['signal_date'],end=events[-1]['signal_date'])
    fixture['non_overlapping']={key:result['non_overlapping'][key] for key in ('n','better','worse','average_difference_yuan')}
    (ROOT/'fixtures/market-position-experiment.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('n','better','worse','average_difference_yuan')},ensure_ascii=False))


if __name__=='__main__':main()
