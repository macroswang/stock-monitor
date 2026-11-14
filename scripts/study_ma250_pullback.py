"""Exploratory study of the frozen daily MA250 pullback rule on local cache.

Reads the client's SQLite cache read-only. It never fetches quotes, writes
events, sends notifications or changes the watchlist. The sample is whatever
daily history happens to be cached, so it is selected and not a market-wide
test; the report says so next to every number.
"""
import argparse, json, sqlite3, statistics, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.ma250_pullback import PARAMETERS, VERSION, analyze
from research.ma250_execution import forward_outcomes

HORIZONS = (5, 10, 20, 60)
DEFAULT_DB = Path.home() / 'Library' / 'Application Support' / 'com.xreddot.stockmonitor' / 'monitor.sqlite3'
WARNINGS = [
    '样本只包含本机已缓存的股票，存在事后选股与存活者偏差，不是全市场检验。',
    '价格未复权，除权除息会扭曲年线；本研究不修正公司行为。',
    '收益使用统一成交模块：次日开盘、持有N日含买入日、T+1、买卖各0.15%成本；未到期/无法成交保留。',
    '参数按形态含义固定、不是网格优化；但同一样本曾用于检查参数行为，且没有样本外验证，样本量不足以证明胜率或收益。',
    '信号只用于提醒与复盘，不进入自动交易、委托或仓位计算。',
]


def load(path, minimum):
    connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    names = {row['code']: row['name'] for row in connection.execute('SELECT code,name FROM instruments')}
    codes = [row['code'] for row in connection.execute(
        "SELECT code FROM cache WHERE kind='daily' GROUP BY code HAVING count(*)>=? ORDER BY code", (minimum,))]
    series = {}
    for code in codes:
        rows = connection.execute("SELECT day,payload FROM cache WHERE code=? AND kind='daily' ORDER BY day", (code,)).fetchall()
        bars = []
        for row in rows:
            data = json.loads(row['payload'])
            bars.append(dict(date=row['day'], open=float(data['open']), close=float(data['close']),
                             high=float(data['high']), low=float(data['low'])))
        series[code] = bars
    connection.close()
    return names, series


def forward(bars,index,horizon):
    return forward_outcomes('',bars,index)['forward'][str(horizon)]


def excursion(bars, index, horizon=20):
    window = bars[index:index + horizon + 1]
    if len(window) < 2:
        return None, None
    entry = window[0]['close']
    return ((min(item['low'] for item in window) / entry) - 1) * 100, ((max(item['high'] for item in window) / entry) - 1) * 100


def summarize(values):
    if not values:
        return dict(samples=0, mean=None, median=None, positive=None, p10=None, p90=None)
    ordered = sorted(values)
    return dict(samples=len(values), mean=statistics.mean(values), median=statistics.median(values),
                positive=sum(value > 0 for value in values) / len(values),
                p10=ordered[len(ordered) // 10], p90=ordered[int(len(ordered) * 0.9)])


def trend_baseline(bars):
    """Every close above a rising annual line: the setup's opportunity cost."""
    closes = [item['close'] for item in bars]
    line, total = [], 0.0
    for index, close in enumerate(closes):
        total += close
        if index >= 250:
            total -= closes[index - 250]
        line.append(total / 250 if index + 1 >= 250 else None)
    out = []
    for index in range(309, len(bars)):
        if line[index] is None or closes[index] <= line[index]:
            continue
        if line[index] < line[index - 60] * (1 + PARAMETERS['minimum_slope_pct'] / 100):
            continue
        out.append(index)
    return out


def study(path, minimum):
    names, series = load(path, minimum)
    signals, baseline, per_stock = [], [], []
    for code, bars in series.items():
        report = analyze(bars)
        if report['error']:
            per_stock.append(dict(code=code, name=names.get(code, code), error=report['error'], signals=0))
            continue
        positions = {item['date']: index for index, item in enumerate(bars)}
        rows = []
        for signal in report['signals']:
            index = positions[signal['date']]
            row = dict(code=code, name=names.get(code, code), **signal,
                       forward={str(h): forward(bars, index, h) for h in HORIZONS})
            row['adverse_20d_pct'], row['favorable_20d_pct'] = excursion(bars, index)
            signals.append(row)
            rows.append(row)
        per_stock.append(dict(code=code, name=names.get(code, code), bars=len(bars),
                              signals=len(rows), error=None, dates=[row['date'] for row in rows]))
        for index in trend_baseline(bars):
            baseline.append({str(h): forward(bars, index, h) for h in HORIZONS})
    aggregate = {str(h): summarize([row['forward'][str(h)] for row in signals
                                    if row['forward'][str(h)] is not None]) for h in HORIZONS}
    control = {str(h): summarize([row[str(h)] for row in baseline if row[str(h)] is not None]) for h in HORIZONS}
    return dict(version=VERSION, parameters=PARAMETERS, generated_at=datetime.now().astimezone().isoformat(),
                database=str(path).replace(str(Path.home()), '~'), minimum_bars=minimum,
                stocks=len(series), signal_count=len(signals),
                baseline_samples=len(baseline), aggregate=aggregate, baseline=control,
                adverse_20d=summarize([row['adverse_20d_pct'] for row in signals if row['adverse_20d_pct'] is not None]),
                favorable_20d=summarize([row['favorable_20d_pct'] for row in signals if row['favorable_20d_pct'] is not None]),
                per_stock=per_stock, signals=sorted(signals, key=lambda row: (row['date'], row['code'])),
                warnings=WARNINGS)


def percent(value):
    return '—' if value is None else f'{value:+.2f}%'


def ratio(value):
    return '—' if value is None else f'{value * 100:.0f}%'


def markdown(report):
    lines = ['# 日线年线（MA250）回踩站稳 · 本机缓存研究', '',
             f'生成：{report["generated_at"]}；规则版本 {report["version"]}；样本 {report["stocks"]} 只、信号 {report["signal_count"]} 次。', '',
             '## 口径', '',
             '年线为 250 个交易日简单收盘均值（未复权）。信号日必须同时满足：年线 60 日斜率不低于 +0.5%；此前 30 日内最高价高于年线 10% 以上；',
             '最近 10 日内最低价触及年线 -15% 至 +1.5% 的区间；自 60 日高点回撤 8%–35%；当日收盘站上年线 1% 以上但不超过 15%；',
             '收盘高于 MA5、高于前收且收阳。同一次回踩在 15 个交易日内不重复触发。', '',
             '## 结果（次日开盘、持有N个交易日的净价格收益代理）', '',
             '|周期|信号样本|均值|中位数|上涨比例|第10百分位|第90百分位|趋势基线均值|基线样本|',
             '|---|---|---|---|---|---|---|---|---|']
    for horizon in HORIZONS:
        item, base = report['aggregate'][str(horizon)], report['baseline'][str(horizon)]
        lines.append(f'|{horizon}日|{item["samples"]}|{percent(item["mean"])}|{percent(item["median"])}|'
                     f'{ratio(item["positive"])}|{percent(item["p10"])}|{percent(item["p90"])}|'
                     f'{percent(base["mean"])}|{base["samples"]}|')
    lines += ['', '趋势基线为同一样本内“收盘位于上升年线上方”的全部交易日，用来区分回踩择时与单纯顺趋势暴露；两者均为日线成交假设下的价格收益代理。', '',
              '## 风险描述', '',
              f'信号后 20 个交易日内，相对信号收盘的平均最大不利波动 {percent(report["adverse_20d"]["mean"])}，'
              f'第 10 百分位 {percent(report["adverse_20d"]["p10"])}；平均最大有利波动 {percent(report["favorable_20d"]["mean"])}。', '',
              '## 全部信号', '',
              '|股票|代码|信号日|收盘|年线|回踩日|回踩低点|回撤|10日|20日|60日|',
              '|---|---|---|---|---|---|---|---|---|---|---|']
    for row in report['signals']:
        lines.append(f'|{row["name"]}|{row["code"]}|{row["date"]}|{row["close"]:.2f}|{row["ma250"]:.2f}|'
                     f'{row["touch_date"]}|{row["touch_low"]:.2f}|{row["pullback_pct"]:.1f}%|'
                     f'{percent(row["forward"]["10"])}|{percent(row["forward"]["20"])}|{percent(row["forward"]["60"])}|')
    lines += ['', '## 边界', ''] + [f'- {warning}' for warning in report['warnings']]
    lines += ['', '个股明细见同目录 report.json；本报告不写入事件、消息或推送队列。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description='年线回踩站稳规则的本机缓存研究')
    parser.add_argument('--db', default=str(DEFAULT_DB), help='客户端 monitor.sqlite3 路径（只读）')
    parser.add_argument('--out', default='docs/ma250-pullback', help='报告目录')
    parser.add_argument('--minimum-bars', type=int, default=320, help='参与统计的最少日线根数')
    args = parser.parse_args()
    if not Path(args.db).exists():
        raise SystemExit(f'找不到数据库：{args.db}')
    report = study(Path(args.db), args.minimum_bars)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (out / 'report.md').write_text(markdown(report), encoding='utf-8')
    print(f'股票 {report["stocks"]} 只，信号 {report["signal_count"]} 次，基线 {report["baseline_samples"]} 日')
    for horizon in HORIZONS:
        item = report['aggregate'][str(horizon)]
        if item['samples']:
            print(f'  {horizon}日：n={item["samples"]} 均值 {item["mean"]:+.2f}% 中位 {item["median"]:+.2f}% '
                  f'上涨比例 {item["positive"] * 100:.0f}%')
    print(f'报告：{out / "report.md"}')


if __name__ == '__main__':
    main()
