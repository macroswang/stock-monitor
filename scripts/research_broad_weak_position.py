"""Explore a broad weak-market description; no trading or account access.

This is an ex-post experiment, not the author's rules or a recommendation.
Compare 510300 ETF risk reduction with holding using the same assumptions as
research_etf_position; report overlapping and chronologically separated cases.
"""
import json
from decimal import Decimal

from scripts.research_etf_position import OUT, ROOT, compare, load_etf, non_overlapping, within_day
from scripts.research_market_regime_extended import load_breadth, load_index


def summarize(rows):
    values=[Decimal(r['difference_yuan']) for r in rows]
    return dict(n=len(values),better=sum(v>0 for v in values),worse=sum(v<0 for v in values),
                equal=sum(v==0 for v in values),
                mean=str((sum(values)/len(values)).quantize(Decimal('0.01'))) if values else None)


def calculate(index, etf, breadth):
    if len({r['date'] for r in breadth})!=len(breadth):raise ValueError('重复的广度日期')
    positions={r['date']:i for i,r in enumerate(index)}
    result=[];skipped=[]
    for item in breadth:
        day=item['date']; i=positions.get(day)
        if day<'2026-01-19' or i is None or i+6>=len(index) or index[i]['ma20'] is None:continue
        if not isinstance(item['advance'],int) or not isinstance(item['decline'],int) or min(item['advance'],item['decline'])<0:
            raise ValueError('涨跌家数无效：'+day)
        sold,bought=index[i+1]['date'],index[i+6]['date']
        calc=compare(etf[sold][1],etf[bought][1])
        if not within_day(calc['sell_price'],etf[sold]) or not within_day(calc['buy_price'],etf[bought]):
            skipped.append(day);continue
        result.append({'signal_date':day,'sell_date':sold,'buy_date':bought,
                       'breadth':item['breadth'],'advance':item['advance'],'decline':item['decline'],
                       'close':index[i]['close'],'ma20':index[i]['ma20'],
                       'condition':item['advance']<item['decline'] and index[i]['close']<index[i]['ma20'],
                       **calc})
    return result,skipped


def main():
    index=load_index();etf=load_etf(index)
    breadth,_=load_breadth()
    rows=[breadth[r['date']] for r in json.loads((OUT/'extended-results.json').read_text())['rows']]
    events,skipped=calculate(index,etf,rows)
    groups={}
    for label,part in [('all',events),('before_2026_06_01',[r for r in events if r['signal_date']<'2026-06-01']),
                       ('from_2026_06_01',[r for r in events if r['signal_date']>='2026-06-01'])]:
        selected=[r for r in part if r['condition']]
        groups[label]={'baseline':summarize(part),'condition':summarize(selected),
                       'condition_non_overlapping':summarize(non_overlapping(selected))}
    output={'rule':'收盘时下跌家数多于上涨家数，且上证收盘低于20日均线；T+1开盘卖出5000份510300，T+6开盘买回，与一直持有比较。',
            'warning':'事后探索，非作者规则；成本和逐笔成交均为假设，事件可能重叠，历史数据可得性未核实。仅用于检验该宽松条件，不代表可预测或适用于其他股票。',
            'start':events[0]['signal_date'] if events else None,'end':events[-1]['signal_date'] if events else None,
            'summary':groups,'skipped':skipped,'events':events}
    (OUT/'broad-weak-etf-experiment.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    fixture={'start':output['start'],'end':output['end'],**groups['all']}
    (ROOT/'fixtures/broad-weak-position-experiment.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:output[k] for k in ('start','end','summary','skipped')},ensure_ascii=False))


if __name__=='__main__':main()
