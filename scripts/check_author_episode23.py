"""Independently check seven public video examples against two index feeds.

Only verifies the dated index outcomes and aggregate arithmetic. It does not
verify the author's sample-selection rule or predict future returns.
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/author-episode23-20261029'
SAMPLES = [('2024-06-12', '-3.23'), ('2024-06-26', '-2.37'), ('2024-07-16', '-3.64'),
           ('2024-08-05', '-1.74'), ('2024-08-12', '-4.26'), ('2024-08-14', '-4.52'),
           ('2024-08-26', '1.43')]


def rounded(value, precision='0.01'):
    return Decimal(value).quantize(Decimal(precision), rounding=ROUND_HALF_UP)


def quantify(values):
    values = sorted(values)
    if len(values) != 7:
        raise ValueError('需要七个完整样本')
    return {'wins': sum(value > 0 for value in values),
            'win_percent': 100 * sum(value > 0 for value in values) / len(values),
            'mean': sum(values) / len(values), 'median': values[3],
            'p25': (values[1] + values[2]) / 2, 'p75': (values[4] + values[5]) / 2}


def analyze(tencent, sina):
    trows = tencent['data']['sh000001']['day']
    t = {r[0]: Decimal(r[2]) for r in trows}
    if len(t) != len(trows) or not t:
        raise ValueError('腾讯日期重复或缺失')
    days = sorted(t)
    srows = [r for r in sina if days[0] <= r['day'] <= days[-1]]
    s = {r['day']: Decimal(r['close']) for r in srows}
    if len(s) != len(srows) or set(s) != set(t):
        raise ValueError('两来源交易日期不一致')
    if any(not x.is_finite() or x <= 0 for x in [*t.values(), *s.values()]):
        raise ValueError('指数收盘数据无效')
    difference = max(abs(t[day] - s[day]) for day in days)
    if difference > Decimal('0.0051'):
        raise ValueError('两来源收盘价超出显示精度差异')
    result = []
    for day, shown in SAMPLES:
        if day not in t or days.index(day) + 20 >= len(days):
            raise ValueError('样本日期或后续交易日缺失：' + day)
        i = days.index(day)
        entry = {'date': day, 'start_close': str(t[day]), 'video_20': shown}
        for horizon in (1, 3, 5, 10, 20):
            end = days[i + horizon]
            t_return = (t[end] / t[day] - 1) * 100
            s_return = (s[end] / s[day] - 1) * 100
            entry[str(horizon)] = {'end_date': end, 'end_close': str(t[end]),
                                   'tencent_return': str(t_return), 'sina_return': str(s_return)}
        if rounded(entry['20']['tencent_return']) != Decimal(shown):
            raise ValueError('视频 20 日期末回报不一致：' + day)
        result.append(entry)
    stats = {}
    for horizon in (1, 3, 5, 10, 20):
        q = quantify([Decimal(r[str(horizon)]['tencent_return']) for r in result])
        stats[str(horizon)] = {key: float(value) for key, value in q.items()}
    # These are the video table's 10/20 day statistics for the shown seven dates.
    expected = {'10': ('14.3', '-1.44', '-1.12', '-2.70', '-0.28'),
                '20': ('14.3', '-2.62', '-3.23', '-3.95', '-2.06')}
    for horizon, (wins, avg, med, p25, p75) in expected.items():
        q = stats[horizon]
        actual = (rounded(q['win_percent'], '0.1'), *[rounded(q[k]) for k in ('mean', 'median', 'p25', 'p75')])
        if actual != tuple(Decimal(x) for x in (wins, avg, med, p25, p75)):
            raise ValueError('视频汇总统计不一致：' + horizon)
    i = days.index('2024-08-26')
    close_low_day = min(days[i+1:i+21], key=lambda d: t[d])
    close_low = (t[close_low_day] / t[days[i]] - 1) * 100
    return {'sample_count': len(result), 'source_dates': [days[0], days[-1]], 'source_rows': len(days),
            'max_close_difference': str(difference), 'samples': result, 'stats': stats,
            'aug26_20day_low_close': {'date': close_low_day, 'return_from_start': str(close_low)},
            'note': '两个数据源日期序列与收盘价格对照，不等于两个来源上游完全独立，亦不验证样本筛选及当时可得性。'}


def main():
    paths = [OUT / 'tencent-index.json', OUT / 'sina-index.json']
    result = analyze(*(json.loads(path.read_text(encoding='utf-8')) for path in paths))
    result['files'] = [{'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'fetched_at': datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo('Asia/Shanghai')).isoformat()}
                       for path in paths]
    (OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fixture = {'video_url': 'https://www.douyin.com/video/7702035535511281472',
               'video_date': '2026-10-29', 'observation_date': '2026-10-28',
               'percentiles': [{'label': label, 'value': value} for label, value in
                               [('红盘率', 82.5), ('MCL', 37.0), ('评分', 14.4),
                                ('P60', 12.3), ('P20', 13.7), ('P250', 9.4)]],
               'samples': [{'date': row['date'], 'day10': float(rounded(row['10']['tencent_return'])),
                            'day20': float(Decimal(row['video_20']))} for row in result['samples']],
               'stats': result['stats'],
               # The video's G1 curve/table. Different horizons may use different
               # sample sets; only the 10/20-day statistics match these seven.
               'video_win_percent': {'1': 41.7, '3': 45.5, '5': 30.0, '10': 14.3, '20': 14.3},
               'warning': '作者固定截图与七个历史样本的独立复算；筛选条件、股票池和历史分位窗口未知，不是当前预测或未来收益概率。'}
    (ROOT / 'fixtures/author-episode23.json').write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# 作者第 23 集：七个样本的指数回报核对', '',
             '输入为腾讯和新浪公开上证指数日线；两家在 2024-06-03 至 09-30 的 83 个日期相同，收盘价最大差 0.005 点（来源上游是否独立未知）。按两源共同的指数交易日序列，以样本日收盘为基准，向后第 N 个交易日收盘计算涨跌幅。此核验未额外核对 2024 年交易所日历。', '',
             '| 样本日期 | 第10个交易日 | 10日涨跌 | 第20个交易日 | 20日涨跌 | 视频20日 |',
             '|---|---|---:|---|---:|---:|']
    for row in result['samples']:
        lines.append(f"| {row['date']} | {row['10']['end_date']} | {rounded(row['10']['tencent_return']):+.2f}% | {row['20']['end_date']} | {rounded(row['20']['tencent_return']):+.2f}% | {Decimal(row['video_20']):+.2f}% |")
    lines += ['', '视频中的七个 20 日样本，涨跌幅均在显示精度内一致。由这七个样本独立计算，10 日、20 日的上涨比例均为 1/7 ≈ 14.3%；平均、中位数及以线性插值计算的上下四分位也分别与视频两行一致。', '',
              '2024-08-26 样本第 10 个交易日回报约 −4.17%，第 20 个约 +1.43%；20 日范围内最低收盘发生于 2024-09-13，较样本日收盘约 −5.30%。视频所说“先跌 −4.17%”与第 10 日回报相符，不应理解为该期间最大回撤。', '',
              '使用同样七个日期重新算出的 1、3、5 日上涨比例分别为 42.9%、71.4%、42.9%，与视频的 41.7%、45.5%、30.0% 不同，说明不能假定短周期表格也是这七个日期；其样本数、筛选和统计时点未展示，不能从图中确认原因。', '',
              '该核验不验证 G1 的选择条件、全部样本、未来可得性或盈利能力。七个样本集中在 2024 年且时间窗口重叠，不能把 1/7 当作独立样本支持的未来概率。', '',
              '来源：作者[样本图](../author-trading-system-20261028/source-samples/episode23-0225.png)与[统计表](../author-trading-system-20261028/source-samples/episode23-forward.png)；[腾讯指数接口](https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,2024-06-01,2024-10-01,2000,)和[新浪指数日线](https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=1023)。']
    (OUT / '七样本核验.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'samples': result['sample_count'], 'max_diff': result['max_close_difference'],
                      'stats_10': result['stats']['10'], 'stats_20': result['stats']['20']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
