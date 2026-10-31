"""Research price-discontinuity adjustment; it is not an official factor series."""
import json
from collections import deque
from datetime import date
from decimal import Decimal, InvalidOperation

from core.breadth import _next_verified_trading_day
from scripts.research_author_p_hypothesis import ROOT, load_history

OUT=ROOT/'docs/adjusted-ma-research-20261029'


def analyze_adjusted(days, read_rows, windows=(20,60,250)):
    cache={};results=[];previous=None
    for index,day in enumerate(days):
        current=date.fromisoformat(day)
        if previous and _next_verified_trading_day(previous)!=current:raise ValueError('incomplete trading calendar')
        previous=current
        today={}
        for row in read_rows(day):
            symbol=row['symbol'];code,exchange=symbol.split('.')
            if exchange not in ('SH','SZ') or (exchange=='SH' and code.startswith('689')):continue
            if symbol in today:raise ValueError('duplicate symbol')
            try:price,base=Decimal(row['close']),Decimal(row['pre_close'])
            except (InvalidOperation, ValueError):raise ValueError('invalid price') from None
            if not price.is_finite() or not base.is_finite() or min(price,base)<=0:raise ValueError('invalid price')
            today[symbol]=(price,base)
        counts={w:dict(eligible=0,above=0) for w in windows};adjusted=0
        for symbol,(price,base) in today.items():
            last,history=cache.get(symbol,(-2,deque(maxlen=max(windows))))
            if last!=index-1:history.clear()
            elif history and history[-1]!=base:
                # Adjust prior prices to today's price basis using the data
                # provider's previous-close ratio. Not verified ex-right data.
                factor=base/history[-1]
                history=deque((v*factor for v in history),maxlen=max(windows));adjusted+=1
            history.append(price);cache[symbol]=(index,history)
            for w in windows:
                if len(history)<w:continue
                closes=list(history)[-w:];counts[w]['eligible']+=1
                if price*w>sum(closes):counts[w]['above']+=1
        results.append(dict(date=day,active=len(today),adjusted_stocks=adjusted,windows={str(w):{**v,'percent':100*v['above']/v['eligible'] if v['eligible'] else None} for w,v in counts.items()}))
    return results


def main():
    unadjusted=load_history();adjusted=load_history(analyze_adjusted)
    author=json.loads((ROOT/'fixtures/author-p-reference.json').read_text())
    raw_by_date={x['date']:x for x in unadjusted};adj_by_date={x['date']:x for x in adjusted}
    comparison=[]
    for a in author:
        d=a['date']
        if d in raw_by_date:comparison.append({'date':d,'author':a,'unadjusted':raw_by_date[d],'adjusted':adj_by_date[d]})
    if len(comparison)!=9:raise ValueError('expected nine screenshot dates')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+'\n')
    def fmt(v):return '—' if v is None else f'{v:.2f}%'
    lines=['# 前收盘比例调整与未复权对照','',
           '针对股票每个连续交易日，若当日昨收与前一日未复权收盘不同，按两者之比把更早收盘价调整到当日价格尺度；股票停牌或缺数据时重新累计窗口。按收盘价严格大于均线计算，仅用于研究。此比例由行情字段推导，尚未与正式除权因子逐项核对；昨收可能经取整或受数据差异影响，不能称作准确复权。截图股票范围、作者指标定义及其复权处理仍未知。','',
           '| 日期 | 作者P20 | 未复权20日 | 比例调整20日 | 作者P60 | 未复权60日 | 比例调整60日 |','|---|---:|---:|---:|---:|---:|---:|']
    for r in comparison:
        a=r['author'];u=r['unadjusted']['windows'];v=r['adjusted']['windows']
        lines.append(f"| {r['date']} | {a['p20']:.1f}% | {fmt(u['20']['percent'])} | {fmt(v['20']['percent'])} | {a['p60']:.1f}% | {fmt(u['60']['percent'])} | {fmt(v['60']['percent'])} |")
    for period in ('20','60'):
        def mae(kind):return sum(abs(r[kind]['windows'][period]['percent']-r['author']['p'+period]) for r in comparison)/len(comparison)
        lines.append(f"\n这 {len(comparison)} 个日期中，{period} 日未复权口径平均绝对差 {mae('unadjusted'):.3f} 个百分点，比例调整口径为 {mae('adjusted'):.3f} 个百分点。")
    samples_file=OUT/'baostock-adjusted-samples.json'
    samples=json.loads(samples_file.read_text()) if samples_file.exists() else []
    valid=len(samples)==3 and all(s['dates']==100 and s['end']=='2026-10-27' for s in samples)
    sample_note=(f"三只股票共 300 根日线与 BaoStock 前复权结果抽样比较见 [baostock-adjusted-samples.json](baostock-adjusted-samples.json)，统一末日价格后最大绝对差 {max(s['max_abs_price_error'] for s in samples):.8f} 元，仅为同源方法的少量样本。" if valid else '尚无完整的三只股票前复权样本对照。')
    lines += ['',f'截图样本由作者选取，不能以数值更接近来认定作者算法；未核对完整除权原因或全部股票的正式复权因子。{sample_note}没有足够数据计算 250 日均线。截图来源为作者第22集的[9月](../author-trading-system-20261028/source-samples/chart-score-0218.png)与[10月](../author-trading-system-20261028/source-samples/october-score-0017.png)表格，原始历史为 Money Tree 和 BaoStock 逐股核对，上游血缘未知。']
    (OUT/'比例调整对照.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(comparison[-1],ensure_ascii=False))


if __name__=='__main__':main()
