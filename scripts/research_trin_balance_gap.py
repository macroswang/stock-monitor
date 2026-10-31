"""Explain one-date TRIN discrepancy under two explicit one-variable assumptions."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'public/breadth-csi300-preview.json'
OUT = ROOT / 'docs/trin-author-table-comparison-20261029/oct23-balance-sensitivity.json'


def analyze(row, target=.93):
    if row['date'] != '2026-10-23' or row['missing'] or row['covered'] != row['expected']:
        raise ValueError('日期或覆盖异常')
    a, d = row['advance'], row['decline']
    up, down = row['advance_amount'], row['decline_amount']
    if min(a, d, up, down, target) <= 0:
        raise ValueError('家数或成交额无效')
    current = a * down / (d * up)
    if abs(current-row['trin_amount']) > 1e-9:
        raise ValueError('本机 TRIN 无法复算')
    down_target = target*d*up/a
    up_target = a*down/(target*d)
    return {'date': row['date'], 'counts': {'up': a, 'down': d},
            'up_amount_yuan': up, 'down_amount_yuan': down, 'local_trin': current,
            'video_displayed_trin': target,
            'holding_counts_and_up_fixed': {'down_target_yuan': down_target,
                'down_delta_yuan': down_target-down, 'down_delta_percent': (down_target/down-1)*100},
            'holding_counts_and_down_fixed': {'up_target_yuan': up_target,
                'up_delta_yuan': up_target-up, 'up_delta_percent': (up_target/up-1)*100},
            'limitation': '两个单变量敏感性例子不证明差异来源；作者实际家数、股票池、时点及成交字段未知。视频显示值经过舍入。'}


def main():
    rows = json.loads(DATA.read_text())['days']
    row = next(row for row in rows if row['date'] == '2026-10-23')
    result = analyze(row)
    result['input_sha256'] = hashlib.sha256(DATA.read_bytes()).hexdigest()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
