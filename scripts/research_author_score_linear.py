"""Assess whether a simple linear score extrapolates to later author screenshots.

This is exploratory curve fitting, not reconstruction of the author's model.
"""
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path

from scripts.check_author_score_hypotheses import compare

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/author-score-hypotheses-20261029'


def fit(rows):
    if len(rows) < 4:
        raise ValueError('至少需要四行')
    with localcontext() as context:
        context.prec = 40
        x = [[Decimal(1)] + [Decimal(str(row[k])) for k in ('p20', 'p60', 'p250')] for row in rows]
        y = [Decimal(str(row['score'])) for row in rows]
        aug = [[sum((v[i] * v[j] for v in x), Decimal(0)) for j in range(4)] +
               [sum((v[i] * t for v, t in zip(x, y)), Decimal(0))] for i in range(4)]
        for col in range(4):
            pivot = max(range(col, 4), key=lambda r: abs(aug[r][col]))
            if abs(aug[pivot][col]) < Decimal('1e-20'):
                raise ValueError('特征无法唯一确定线性系数')
            aug[col], aug[pivot] = aug[pivot], aug[col]
            divisor = aug[col][col]
            aug[col] = [v / divisor for v in aug[col]]
            for row in range(4):
                if row != col:
                    multiplier = aug[row][col]
                    aug[row] = [a - multiplier * b for a, b in zip(aug[row], aug[col])]
        return [aug[i][-1] for i in range(4)]


def predict(model, row):
    return sum((model[i] * value for i, value in enumerate(
        [Decimal(1)] + [Decimal(str(row[k])) for k in ('p20', 'p60', 'p250')])), Decimal(0))


def evaluate(rows):
    rows = sorted(rows, key=lambda row: row['date'])
    if len(rows) != 10 or len({r['date'] for r in rows}) != 10:
        raise ValueError('需要 10 个不重复截图日期')
    full = fit(rows)
    first = fit(rows[:5])
    results = []
    for i, row in enumerate(rows):
        loo = fit(rows[:i] + rows[i+1:])
        score = Decimal(str(row['score']))
        results.append({'date': row['date'], 'actual': float(score),
                        'full_fit': float(predict(full, row)),
                        'leave_one_out': float(predict(loo, row)),
                        'first_five_to_later': float(predict(first, row)) if i >= 5 else None})
    def mae(items, key):
        return sum(abs(Decimal(str(r[key])) - Decimal(str(r['actual']))) for r in items) / len(items)
    return {'coefficients_full': [float(x) for x in full],
            'coefficients_first_five': [float(x) for x in first],
            'full_fit_mae': float(mae(results, 'full_fit')),
            'leave_one_out_mae': float(mae(results, 'leave_one_out')),
            'first_five_to_later_mae': float(mae(results[5:], 'first_five_to_later')),
            'rows': results}


def main():
    paths = [ROOT/'fixtures/author-chart-reference.json', ROOT/'fixtures/author-p-reference.json']
    rows = compare(*(json.loads(path.read_text()) for path in paths))
    result = evaluate(rows)
    result['input_hashes'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['warning'] = '仅10个作者选择的截图日期；四参数拟合及事后留一比较不能识别真实公式、复现评分或预测行情。'
    (OUT/'linear-fit-experiment.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('full_fit_mae','leave_one_out_mae','first_five_to_later_mae','coefficients_full','coefficients_first_five')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
