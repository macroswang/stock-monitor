"""Compare screenshot P columns to one explicit unadjusted MA breadth hypothesis.

Uses consecutive daily active bars, no imputation and no claim of author formula.
"""
import csv
import json
from collections import deque
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from core.breadth import _next_verified_trading_day

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/author-p-hypothesis-20261029'


def analyze(days, read_rows, windows=(20,60,250), next_day=_next_verified_trading_day):
    cache={}
    results=[]
    previous=None
    for index,day in enumerate(days):
        current=date.fromisoformat(day)
        if previous and next_day(previous)!=current:raise ValueError('incomplete trading calendar')
        previous=current
        rows=read_rows(day)
        today={}
        for row in rows:
            symbol=row['symbol'];code,exchange=symbol.split('.')
            if exchange not in ('SH','SZ') or (exchange=='SH' and code.startswith('689')):continue
            if symbol in today:raise ValueError('duplicate symbol')
            try:price=Decimal(row['close'])
            except (InvalidOperation, ValueError):raise ValueError('invalid price') from None
            if not price.is_finite() or price<=0:raise ValueError('invalid price')
            today[symbol]=price
        counts={w:dict(eligible=0,above=0) for w in windows}
        for symbol,price in today.items():
            last,history=cache.get(symbol,(-2,deque(maxlen=max(windows))))
            if last!=index-1:history.clear()
            history.append(price);cache[symbol]=(index,history)
            for w in windows:
                if len(history)<w:continue
                closes=list(history)[-w:]
                counts[w]['eligible']+=1
                if price*w>sum(closes):counts[w]['above']+=1
        results.append(dict(date=day,active=len(today),windows={str(w):{**c,'percent':100*c['above']/c['eligible'] if c['eligible'] else None} for w,c in counts.items()}))
    return results


def load_history(analyzer=analyze):
    earlier=json.loads((ROOT/'docs/author-mcl-history-20261029/collection.json').read_text())
    later=json.loads((ROOT/'docs/trin-sensitivity-20261028/summary.json').read_text())
    if earlier['failures'] or later['failed']:raise ValueError('source history incomplete')
    days=earlier['expected']+[r['date'] for r in later['results']]
    if len(days)!=100:raise ValueError('expected 100 dates')
    checks=json.loads((ROOT/'docs/author-mcl-history-20261029/all-crosscheck.json').read_text())+json.loads((ROOT/'docs/trin-diagnostic-20261028/continuous-crosscheck.json').read_text())
    if [r['date'] for r in checks]!=days or any(r['mismatches'] or r['only_moneytree'] or r['only_baostock'] or float(r['max_shares_difference'])>(50 if r['date']=='2026-06-08' else 0) or float(r['max_amount_difference_yuan'])>.5 for r in checks):raise ValueError('constituent cross-check incomplete')
    def read_rows(day):
        filename=day.replace('-','')+'.csv'
        candidates=[ROOT/'docs/author-mcl-history-20261029/daily'/filename,ROOT/'docs/trin-sensitivity-20261028/daily'/filename,ROOT/'docs/trin-reconstruction-20261028/money-tree'/filename]
        path=next((p for p in candidates if p.exists()),None)
        if path is None:raise FileNotFoundError(filename)
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        if len(rows)<4000 or any(r.get('trade_date')!=filename[:8] for r in rows):raise ValueError('bad date or incomplete day '+day)
        return rows
    return analyzer(days,read_rows)


def main():
    results=load_history()
    author=json.loads((ROOT/'fixtures/author-p-reference.json').read_text())
    by_date={r['date']:r for r in results}
    compare=[]
    for item in author:
        if item['date'] not in by_date:continue
        compare.append({'date':item['date'],'author':item,'hypothesis':by_date[item['date']]})
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'comparison.json').write_text(json.dumps(compare,ensure_ascii=False,indent=2)+'\n')
    lines=['# 作者 P20、P60 与均线宽度假设','',
           '假设：P20 / P60 分别是当日收盘高于该股最近 20 / 60 个连续交易日（含当日）未复权收盘价简单均线的股票比例。仅使用沪深活跃股票，排除 689；只对窗口内每天都有行情的股票计算，分母为满足窗口的股票。该假设未得到作者确认，历史底表由 Money Tree 与 BaoStock 逐日逐股交叉核对，两来源上游血缘未知；2026-06-08 成交股数有按手取整差异，但价格及涨跌家数一致。','',
           '| 日期 | 作者P20 | 本机高于20日均线 | 20日样本数 | 作者P60 | 本机高于60日均线 | 60日样本数 |','|---|---:|---:|---:|---:|---:|---:|']
    for r in compare:
        a=r['author'];w=r['hypothesis']['windows'];v=lambda x:'—' if x is None else f'{x:.1f}%'
        lines.append(f"| {r['date']} | {a['p20']:.1f}% | {v(w['20']['percent'])} | {w['20']['eligible']} | {a['p60']:.1f}% | {v(w['60']['percent'])} | {w['60']['eligible']} |")
    lines += ['','来源：作者第22集[9月截图](../author-trading-system-20261028/source-samples/chart-score-0218.png)和[10月截图](../author-trading-system-20261028/source-samples/october-score-0017.png)，数值为人工抄录并按原图精度显示。','','窗口不足时留空；100 日底表无法计算 250 日均线。复权、停牌、新股、股票池和同价处理均可能影响比较，数值接近也不能证明作者定义；不以这些数据产生交易信号。']
    (OUT/'均线假设对照.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(compare[-4:],ensure_ascii=False))


if __name__=='__main__':main()
