"""Fixed exploratory market condition, evaluated on available historical closes.

Signal on close t: breadth below 20% AND SSE close below its 20-day simple
average. Outcome is the *index proxy* from next open to next or fifth close.
It is not the author's formula, a trading strategy, or a cost-adjusted return.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/market-regime-research-20261029'


def calculate(breadth, index):
    if len({x['date'] for x in breadth}) != len(breadth):
        raise ValueError('重复广度日期')
    days = [x['date'] for x in index]
    if days != sorted(set(days)):
        raise ValueError('指数日期重复或无序')
    by_date = {r['date']:i for i,r in enumerate(index)}
    results = []
    for day in breadth:
        i = by_date.get(day['date'])
        if (i is None or i+5 >= len(index) or day.get('status') != 'closed'
                or day.get('missing') != 0 or day.get('advancing_percent') is None):
            continue
        current, future = index[i], index[i+1:i+6]
        if current.get('boll_mid') is None or any(x.get('gap_before') for x in future):
            continue
        if any(x[k] <= 0 for x in future for k in ('open','close')):
            raise ValueError('指数价格无效')
        if not (0 <= day['advancing_percent'] <= 100):
            raise ValueError('上涨比例无效')
        results.append({'date':day['date'], 'next_date':future[0]['date'],
                        'breadth':day['advancing_percent'], 'close':current['close'], 'ma20':current['boll_mid'],
                        'weak':day['advancing_percent'] < 20 and current['close'] < current['boll_mid'],
                        'one_day':(future[0]['close']/future[0]['open']-1)*100,
                        'five_day':(future[4]['close']/future[0]['open']-1)*100})
    return results


def summary(rows):
    return {key: {'n':len(rows), 'positive':sum(r[key] > 0 for r in rows),
                  'mean':statistics.mean(r[key] for r in rows) if rows else None,
                  'median':statistics.median(r[key] for r in rows) if rows else None}
            for key in ('one_day','five_day')}


def main():
    breadth=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text())
    index=json.loads((ROOT/'public/index-technical-preview.json').read_text())['daily']
    rows=calculate(breadth,index)
    if len(rows)<2: raise ValueError('可比较样本不足')
    split=len(rows)//2
    data={'method':'当日收盘上涨家数占比<20%且上证收盘<20日均线；之后首日开盘至首日或第5个交易日收盘；上证指数代理，无成本',
          'warning':'事后探索，参数未预注册；补采不代表当时已可获取；样本短且窗口重叠，指数不能直接交易；不能证明作者策略或判断仓位收益。',
          'summary':{name:{'all':summary(part),'weak':summary([x for x in part if x['weak']])} for name,part in
                     [('all',rows),('earlier',rows[:split]),('later',rows[split:])]},'rows':rows}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'start':rows[0]['date'],'end':rows[-1]['date'],'summary':data['summary']},ensure_ascii=False))


if __name__=='__main__':main()
