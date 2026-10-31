"""Compare hand-transcribed author screenshots with audited daily market data.

The author values are already rounded in the screenshots. This is descriptive,
not proof that the author used any particular data source, universe, or formula.
Does not read or write the application database.
"""
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
AUTHORS=json.loads((ROOT/'fixtures/author-trin-reference.json').read_text(encoding='utf-8'))


def compare(history):
    by_day={r['date']:r for r in history}
    rows=[]
    for entry in AUTHORS:
        day,author_adv,author_trin=entry['date'],entry['advance_percent'],entry['trin']
        r=by_day[day]
        if not r.get('historical') or r.get('status')!='closed' or r.get('missing')!=0:
            raise ValueError(f'{day}: no complete cross-checked daily snapshot')
        volume,amount=float(r['trin']),float(r['trin_amount'])
        rows.append(dict(date=day,author_adv=author_adv,ours_adv=r['advancing_percent'],
                         author_trin=author_trin,shares_trin=volume,amount_trin=amount,
                         shares_error=abs(volume-author_trin),amount_error=abs(amount-author_trin)))
    return rows


def main():
    rows=compare(json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text(encoding='utf-8')))
    out=ROOT/'docs/trin-author-table-comparison-20261029';out.mkdir(parents=True,exist_ok=True)
    stats=dict(n=len(rows),mean_absolute_error_shares=statistics.mean(r['shares_error'] for r in rows),
               mean_absolute_error_amount=statistics.mean(r['amount_error'] for r in rows),
               amount_closer=sum(r['amount_error']<r['shares_error'] for r in rows))
    (out/'comparison.json').write_text(json.dumps(dict(rows=rows,summary=stats),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 作者截图与独立口径对照', '',
           '作者数值人工抄录自 [9月表格](../author-trading-system-20261028/source-samples/chart-score-0218.png)及[10月表格](../author-trading-system-20261028/source-samples/october-score-0017.png)，原表已四舍五入；历史底表来自 BaoStock 与 Money Tree 逐股对照，详见既有校验记录。两方股票范围、精度与时间未证实一致。', '',
           '| 日期 | 作者红盘率 | 独立红盘率 | 作者 TRIN | 股数口径 | 成交额口径 |', '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['date']} | {r['author_adv']:.1f}% | {r['ours_adv']:.1f}% | {r['author_trin']:.2f} | {r['shares_trin']:.3f} | {r['amount_trin']:.3f} |")
    lines += ['',f"这 {stats['n']} 个作者截图日期中，成交额口径有 {stats['amount_closer']} 天更接近作者数值；平均绝对差分别为成交股数 {stats['mean_absolute_error_shares']:.3f}、成交额 {stats['mean_absolute_error_amount']:.3f}。",'',
              '这支持将成交额列为优先核查假设，不足以确认作者实际使用成交额，亦不能推导其股票范围、时间、评分、P20/P60/P250 或模型。截图是作者选取的有限样本，不是无偏抽样，也不能用于判断交易胜率。作者先前说法与后续公式存在矛盾；作者采用了什么口径仍需原始底表或明确说明。','']
    (out/'对照分析.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False))


if __name__=='__main__':main()
