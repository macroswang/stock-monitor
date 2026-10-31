"""Examine MCL start-date sensitivity without modifying application data."""
import json
from datetime import date
from pathlib import Path

from core.breadth import _next_verified_trading_day

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/author-mcl-history-20261029'


def run(rows, start):
    rows=[r for r in rows if r['date']>=start]
    if not rows or rows[0]['date']!=start:raise ValueError('start date missing')
    fast=slow=None
    result={}
    previous=None
    for i,r in enumerate(rows):
        current=date.fromisoformat(r['date'])
        if previous and _next_verified_trading_day(previous)!=current:raise ValueError('missing or duplicated trading day')
        value=r['advance']-r['decline']
        if fast is None:fast=slow=value
        else:fast=.10*value+.90*fast;slow=.05*value+.95*slow
        result[r['date']]=dict(mcl=fast-slow,samples=i+1)
        previous=current
    return result


def main():
    collection=json.loads((OUT/'collection.json').read_text())
    checks=json.loads((OUT/'all-crosscheck.json').read_text())
    later=json.loads((ROOT/'docs/trin-sensitivity-20261028/summary.json').read_text())
    if collection['failures'] or len(collection['records'])!=len(collection['expected']) or [r['date'] for r in collection['records']]!=collection['expected']:
        raise ValueError('earlier history incomplete')
    if len(checks)!=60 or [r['date'] for r in checks]!=collection['expected'] or any(r['mismatches'] or r['only_moneytree'] or r['only_baostock'] or float(r['max_shares_difference'])>(50 if r['date']=='2026-06-08' else 0) or float(r['max_amount_difference_yuan'])>.5 for r in checks):
        raise ValueError('earlier history not fully reconciled')
    if later['failed'] or later['expected']!=40 or len(later['results'])!=40:raise ValueError('later history incomplete')
    rows=collection['records']+later['results']
    if len(rows)!=100:raise ValueError('expected 100 trading days')
    snapshots=json.loads((ROOT/'fixtures/author-mcl-reference.json').read_text())
    starts=['2026-06-01','2026-07-01','2026-08-25']
    models={start:run(rows,start) for start in starts}
    comparison=[]
    for author in snapshots:
        if author['date'] not in models[starts[0]]:continue
        item={'date':author['date'],'author':author['mcl']}
        for start in starts:item[start]=models[start][author['date']]
        comparison.append(item)
    output={'source':'Money Tree daily CSV, upstream lineage unknown','rows':len(rows),'from':rows[0]['date'],'to':rows[-1]['date'],
            'initialization':'fast EMA = slow EMA = first observed advancing minus declining count',
            'starts':starts,'comparison':comparison}
    (OUT/'warmup-comparison.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    lines=['# MCL 历史起点敏感性','',
           '使用 Money Tree 公开历史日线统计沪深上涨、下跌家数（排除 689），2026-06-01 至 10-27 共 100 个连续交易日。来源上游不可确认；新增的 60 日已与 BaoStock 逐日逐股交叉验证，2026-06-08 成交股数存在按手取整的差异，但价格和涨跌家数一致。每个序列起点均令快慢两条指数平滑值等于首日涨跌家数差，其后按 0.10 和 0.05 平滑，未使用作者数值作为初始化。作者值摘自[9月截图](../author-trading-system-20261028/source-samples/chart-score-0218.png)及[10月截图](../author-trading-system-20261028/source-samples/october-score-0017.png)。','',
           '| 日期 | 作者 MCL | 6月1日起算 | 7月1日起算 | 8月25日起算 |','|---|---:|---:|---:|---:|']
    lines += [f"| {r['date']} | {r['author']} | {r[starts[0]]['mcl']:.1f} | {r[starts[1]]['mcl']:.1f} | {r[starts[2]]['mcl']:.1f} |" for r in comparison]
    lines += ['','更长历史起点的结果在本次截图样本中更接近作者，但不能据此认定作者起点、股票池及公式。不同起点并非独立数据源；截图由作者选择，且作者数值已取整，不能用于估计预测收益。2026-10-27 虽可用于此单来源研究，正式产品的来源衔接仍须验证，不能静默拼接。','',
              '采集清单和文件哈希见 collection.json，逐日比对结果见 all-crosscheck.json，6月8日股数采用按手取整的误差范围，其余日期股数精确一致。两来源可能有相同上游，不能称为完全独立行情数据。正式图表继续保留来源边界。']
    (OUT/'起点敏感性.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'dates':len(rows),'comparisons':len(comparison),'oct26':next(r for r in comparison if r['date']=='2026-10-26')},ensure_ascii=False))


if __name__=='__main__':main()
