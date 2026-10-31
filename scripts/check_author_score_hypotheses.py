"""Compare two fixed score hypotheses against the author's rounded screenshots.

This is observational research only: no fitting, backtest or trading signal.
"""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/author-score-hypotheses-20261029'


def compare(scores, p_values):
    def index(rows):
        out = {}
        for row in rows:
            day = row['date']
            if day in out:
                raise ValueError('截图日期重复：' + day)
            out[day] = row
        return out
    scores, p_values = index(scores), index(p_values)
    if not scores or scores.keys() != p_values.keys():
        raise ValueError('截图评分和 P 指标日期不一致')
    rows = []
    for day in sorted(scores):
        values = [Decimal(str(p_values[day][key])) for key in ('p20', 'p60', 'p250')]
        score = Decimal(str(scores[day]['score']))
        if not all(x.is_finite() and 0 <= x <= 100 for x in [score, *values]):
            raise ValueError('截图数值无效：' + day)
        two = (values[0] + values[1]) / 2
        three = sum(values) / 3
        rows.append(dict(date=day, score=float(score), p20=float(values[0]), p60=float(values[1]),
                         p250=float(values[2]), mean_two=float(two), mean_three=float(three),
                         error_two=float(two-score), error_three=float(three-score)))
    return rows


def metrics(rows, key):
    errors = [abs(Decimal(str(row[key]))) for row in rows]
    return {'mae': float(sum(errors) / len(errors)), 'max_abs_error': float(max(errors))}


def main():
    scores = json.loads((ROOT / 'fixtures/author-chart-reference.json').read_text())
    p_values = json.loads((ROOT / 'fixtures/author-p-reference.json').read_text())
    rows = compare(scores, p_values)
    if len(rows) != 10:
        raise ValueError('预期 10 个共同截图日期')
    result = {'source': '作者视频表格手工抄录，数值为截图显示精度',
              'hypotheses': ['(P20 + P60) / 2', '(P20 + P60 + P250) / 3'],
              'two': metrics(rows, 'error_two'), 'three': metrics(rows, 'error_three'), 'rows': rows,
              'limitations': '截图日期由作者选择；没有公式、成分权重、历史连续样本或时间信息。两种平均值不匹配，不排除其他公式。'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# 作者评分：两个固定平均假设', '',
             '输入是作者第 22 集 9 月和 10 月表格的 10 个日期，评分与 P 数字均按截图精度抄录。未拟合参数，也未使用本机市场行情替代作者输入。', '',
             '| 日期 | 作者评分 | P20 | P60 | P250 | 两项平均 | 三项平均 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    lines += [f"| {r['date']} | {r['score']:.1f} | {r['p20']:.1f} | {r['p60']:.1f} | {r['p250']:.1f} | {r['mean_two']:.2f} | {r['mean_three']:.2f} |" for r in rows]
    lines += ['', f"两项平均与截图评分的平均绝对差 {result['two']['mae']:.3f}，最大差 {result['two']['max_abs_error']:.3f}；三项平均分别为 {result['three']['mae']:.3f} 和 {result['three']['max_abs_error']:.3f}。", '',
              '两个固定假设均不能与截图评分对应。这不排除其他权重、指标、归一化或隐藏状态；样本仅十天，无法唯一确定作者公式，不可将拟合值当作作者评分、实时信号或收益证明。', '',
              '数据来源：[9 月截图](../author-trading-system-20261028/source-samples/chart-score-0218.png)、[10 月截图](../author-trading-system-20261028/source-samples/october-score-0017.png)。']
    (OUT / '评分对照.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'dates': len(rows), 'two': result['two'], 'three': result['three']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
