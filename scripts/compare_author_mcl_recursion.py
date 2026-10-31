"""Test a fixed McClellan recurrence against values visible in author screenshots.

This is a conditional consistency check using the author's two preceding values,
not an independently reconstructed historical MCL or a predictive backtest.
"""
import json
from datetime import date
from pathlib import Path

from core.breadth import _next_verified_trading_day

ROOT = Path(__file__).resolve().parents[1]


def compare(author, breadth):
    author = sorted(author, key=lambda r: r['date'])
    breadth = {r['date']: r for r in breadth}
    comparisons = []
    for i in range(2, len(author)):
        a, b, c = author[i-2:i+1]
        if (_next_verified_trading_day(date.fromisoformat(a['date'])) != date.fromisoformat(b['date']) or
            _next_verified_trading_day(date.fromisoformat(b['date'])) != date.fromisoformat(c['date'])):
            continue
        prior, current = breadth.get(b['date']), breadth.get(c['date'])
        if not prior or not current or any(r.get('status') != 'closed' or r.get('missing') != 0 for r in (prior,current)):
            continue
        for row in (prior,current):
            if not all(isinstance(row.get(k), int) and row[k] >= 0 for k in ('advance','decline')):
                raise ValueError('invalid breadth counts: '+row['date'])
        delta = (current['advance']-current['decline']) - (prior['advance']-prior['decline'])
        estimate = 1.85*b['mcl'] - .855*a['mcl'] + .05*delta
        comparisons.append(dict(date=c['date'],author=c['mcl'],conditional=estimate,
                                difference=estimate-c['mcl'],prior_author_dates=[a['date'],b['date']],
                                prior_breadth_source=prior['source'],current_breadth_source=current['source']))
    return comparisons


def main():
    author = json.loads((ROOT/'fixtures/author-mcl-reference.json').read_text())
    rows = json.loads((ROOT/'public/breadth-preview.json').read_text())['days']
    result = compare(author,rows)
    if len(result) != 6:
        raise ValueError(f'expected six adjacent-date comparisons, got {len(result)}')
    output = ROOT/'docs/author-mcl-comparison-20261029'
    output.mkdir(parents=True, exist_ok=True)
    (output/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines=['# 作者 MCL 表格与标准递推的对照','',
           '作者数值人工抄自[9月截图](../author-trading-system-20261028/source-samples/chart-score-0218.png)和[10月截图](../author-trading-system-20261028/source-samples/october-score-0017.png)，均为整数显示。输入涨跌家数使用已核验的本地收盘记录；2026-10-27 与前后日期来源不同，股票范围亦不完全相同。','',
           '标准麦克莱伦差值定义为对涨跌家数差 X 分别进行平滑系数 0.10、0.05 的指数平滑后相减。由此可消去两个平滑状态：M(t) = 1.85 M(t−1) − 0.855 M(t−2) + 0.05 [X(t) − X(t−1)]。下表用作者前两日显示值和本地两日家数代入，比较当日作者值。','',
           '| 日期 | 作者 MCL | 条件递推值 | 递推值减作者值 |','|---|---:|---:|---:|']
    lines += [f"| {r['date']} | {r['author']} | {r['conditional']:.3f} | {r['difference']:+.3f} |" for r in result]
    lines += ['','这 6 次条件检查的最大绝对差为 '+f"{max(abs(r['difference']) for r in result):.3f}"+'；作者整数取整、股票池及输入来源不同均会影响误差。结果支持作者数列与标准递推关系相容，不能证明作者的股票池、历史起点、初始化或完整公式与本地完全相同。','',
              '此检查每次使用作者前两天的数值，不能当作独立重算、预测或收益验证。10月28日历史收盘记录为事后补采，10月27日与其来源及范围不同；条件递推的接近不能证明两者可无条件拼接。']
    (output/'对照分析.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'comparisons':len(result),'max_abs_difference':max(abs(r['difference']) for r in result)},ensure_ascii=False))


if __name__ == '__main__':
    main()
