"""Breadth from a fixed stock panel: share of names above their 250-day line.

Research-only. The panel is the same fixed sample used by the MA250 study, so
the series is a sample breadth, not the exchange's official full-market count.
"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def sma(values, period=250):
    out, total = [], 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        out.append(total / period if index + 1 >= period else None)
    return out


def breadth(series):
    """Date -> {eligible, above, pct}; only completed 250-bar windows count."""
    counts = {}
    for code, bars in series.items():
        closes = [bar['close'] for bar in bars]
        line = sma(closes)
        for index, bar in enumerate(bars):
            if line[index] is None:
                continue
            item = counts.setdefault(bar['date'], [0, 0])
            item[0] += 1
            item[1] += 1 if closes[index] > line[index] else 0
    return {day: dict(eligible=total, above=above, pct=100 * above / total)
            for day, (total, above) in sorted(counts.items()) if total}


def load_panel(folder):
    series = {}
    for path in sorted(Path(folder).glob('*.json')):
        payload = json.loads(path.read_text(encoding='utf-8'))
        rows = payload.get('rows') or []
        if not rows:
            continue
        if isinstance(rows[0], list):
            bars = [dict(date=row[0], open=row[1], close=row[2], high=row[3], low=row[4], volume=row[5])
                    for row in rows]
        else:
            bars = rows
        series[path.stem] = bars
    return series


def main():
    import argparse
    parser = argparse.ArgumentParser(description='从固定股票面板计算年线广度')
    parser.add_argument('--panel', default=str(BASE / 'docs' / 'ma250-pullback' / 'data' / 'tencent'))
    parser.add_argument('--out', default=str(BASE / 'docs' / 'ma250-pullback' / 'large' / 'breadth.json'))
    args = parser.parse_args()
    series = load_panel(args.panel)
    result = breadth(series)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(dict(panel=str(args.panel), stocks=len(series), days=result),
                                         ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    last = sorted(result)[-1]
    print(f'stocks {len(series)} dates {len(result)} last {last} pct {result[last]["pct"]:.1f}%')


if __name__ == '__main__':
    main()
