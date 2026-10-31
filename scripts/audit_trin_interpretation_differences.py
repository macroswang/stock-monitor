"""Compare shown video TRIN values with local amount-based interpretation.

This is a retrospective comparison of rounded screenshots and local historical
summaries, not a reconstruction of the unknown source universe or trade rules.
"""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'docs/trin-author-table-comparison-20261029'
INPUTS = (DIRECTORY / 'comparison.json', DIRECTORY / 'march-comparison.json')
OUTPUT = DIRECTORY / 'interpretation-boundaries-20261031.json'


def chart_band(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('无效 TRIN')
    if value < .5:
        return '低于0.5'
    if value < .6:
        return '0.5至0.6'
    if value < .7:
        return '0.6至0.7'
    if value < .9:
        return '0.7至0.9'
    if value <= 1.1:
        return '0.9至1.1'
    return '高于1.1'


def compare(inputs):
    output = []
    for group in inputs:
        for row in group:
            author = float(row.get('author_trin', row.get('author_trin_shown')))
            local = float(row['amount_trin'])
            source_band, local_band = chart_band(author), chart_band(local)
            output.append({'date': row['date'], 'video_shown': author, 'local_amount': local,
                           'video_chart_band': source_band, 'local_chart_band': local_band,
                           'chart_band_differs': source_band != local_band,
                           'one_boundary_differs': (author <= 1) != (local <= 1)})
    if len({r['date'] for r in output}) != len(output):
        raise ValueError('重复日期')
    return sorted(output, key=lambda row: row['date'])


def main():
    rows = compare([json.loads(path.read_text())['rows'] for path in INPUTS])
    result = {'inputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS},
              'warning': '视频数值按画面显示精度记录；界面分类与1.0比较为本机规则，不代表作者完整仓位规则。',
              'rows': rows, 'chart_band_differences': [r['date'] for r in rows if r['chart_band_differs']],
              'one_boundary_differences': [r['date'] for r in rows if r['one_boundary_differs']]}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('chart_band_differences', 'one_boundary_differences')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
