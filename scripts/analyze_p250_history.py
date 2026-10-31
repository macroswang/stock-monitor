"""Compare P250 against an unadjusted 250-session MA hypothesis in isolation."""
import csv
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from scripts.research_author_p_hypothesis import analyze
from scripts.research_ma_quote_bridge import ROOT, rows_for_day
from scripts.research_p250_history import OUT, calendar


def next_research_day(previous):
    dates=calendar()
    for offset in range(1,41):
        day=previous+timedelta(days=offset);ranges=dates.get(day.year)
        if ranges is None:return None
        if day.weekday()<5 and not any(a<=day.isoformat()<=b for a,b in ranges):return day
    return None


def main():
    collection=json.loads((OUT/'collection.json').read_text())
    earlier=json.loads((ROOT/'docs/author-mcl-history-20261029/collection.json').read_text())
    later=json.loads((ROOT/'docs/trin-sensitivity-20261028/summary.json').read_text())
    expected=collection['expected']
    if collection['failures'] or len(collection['records'])!=171 or len(expected)!=171 or any(d not in collection['records'] for d in expected):raise ValueError('P250 research history incomplete')
    if earlier['failures'] or later['failed']:raise ValueError('existing history incomplete')
    days=expected+earlier['expected']+[r['date'] for r in later['results']]
    if len(days)!=271:raise ValueError('expected 271 consecutive dates')
    def read_rows(day):
        record=collection['records'].get(day)
        if not record:return rows_for_day(day)
        path=ROOT/record['path'];data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError(day+': source file changed')
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        if not rows or any(r.get('trade_date')!=day.replace('-','') for r in rows):raise ValueError(day+': mixed dates')
        return rows
    history=analyze(days,read_rows,windows=(250,),next_day=next_research_day)
    by_date={r['date']:r for r in history}
    author=json.loads((ROOT/'fixtures/author-p-reference.json').read_text())
    out=[]
    for item in author:
        row=by_date.get(item['date'])
        if not row:continue
        w=row['windows']['250'];out.append(dict(date=item['date'],author_p250=item['p250'],**w))
    if len(out)!=9 or any(r['percent'] is None for r in out):raise ValueError('screenshot comparison incomplete')
    (OUT/'comparison.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    lines=['# 作者 P250 与 250 日均线宽度假设','','使用当日收盘价高于过去 250 个连续交易日（含当日）未复权简单均线的股票占比。仅沪深活跃股票，排除 689；对停牌、新股或缺失导致窗口不完整的股票不计入该日分母。2025 年交易日依据[上交所休市安排](https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20241223_10767110.shtml)，2026 年使用既有已核对日历。更早 171 日为 Money Tree 单来源，尚未全量逐股交叉核验；此表仅用于研究，不是正式观量数据。','',
           '| 日期 | 作者 P250 | 本机 250 日参照 | 有效样本数 |','|---|---:|---:|---:|']
    for r in out:lines.append(f"| {r['date']} | {r['author_p250']:.1f}% | {r['percent']:.2f}% | {r['eligible']} |")
    lines += ['','作者数据来自[视频截图 9 月](../author-trading-system-20261028/source-samples/chart-score-0218.png)与[10 月](../author-trading-system-20261028/source-samples/october-score-0017.png)。作者股票池、复权及停牌处理未知，截图并非随机样本；结果接近不能证明作者的公式。历史均线未处理除权等价格不连续，不可当作盈利或交易信号。']
    (OUT/'P250假设对照.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':main()
