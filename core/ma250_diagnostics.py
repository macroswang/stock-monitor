"""Read-only explanations for existing readiness results; never a detector."""
from datetime import date, timedelta

from .ma250_pullback import PERIOD, PARAMETERS, QUALITY, prepare


def describe(code, name, bars, report):
    last = report.get('latest') or {}
    state = 'invalid' if report.get('error') else last.get('readiness', 'insufficient')
    result = dict(code=code, name=name, state=state, bars=last.get('bars', len(bars)),
                  minimum_bars=PERIOD+PARAMETERS['slope_days'], reasons=[], repair_ranges=[])
    if report.get('error'):
        result['reasons'] = [report['error']]
        return result
    try:
        rows = prepare(bars)['rows']
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        result['reasons'] = ['日线正在更新或已变化，请刷新后查看原因']
        return result
    result.update(first_date=rows[0]['date'] if rows else None,
                  last_date=rows[-1]['date'] if rows else None)
    if state == 'insufficient':
        result['reasons'].append(f"仅{len(rows)}根日线，需要{result['minimum_bars']}根")
        result['suggestion'] = '可尝试补充更早历史；若来源已无更早记录，需要继续积累交易日。'
        if rows:
            start = date.fromisoformat(rows[-1]['date'])-timedelta(days=3*365)
            end = date.fromisoformat(rows[0]['date'])-timedelta(days=1)
            if start <= end:
                result['repair_ranges'].append(dict(start=start.isoformat(), end=end.isoformat(), kind='history'))
        return result
    if state != 'quality_blocked':
        return result
    seen, ranges = set(), {}
    # Exactly the current and 60-bars-prior windows used by readiness.
    for at in (len(rows)-1, len(rows)-PARAMETERS['slope_days']-1):
        if at < PERIOD-1:
            continue
        window = rows[at-PERIOD+1:at+1]
        span = (date.fromisoformat(window[-1]['date'])-date.fromisoformat(window[0]['date'])).days
        if span > QUALITY['maximum_window_days']:
            seen.add(f"250根日线跨度{span}天，超过{QUALITY['maximum_window_days']}天")
        for previous, row in zip(window, window[1:]):
            gap = (date.fromisoformat(row['date'])-date.fromisoformat(previous['date'])).days
            if gap > QUALITY['maximum_gap_days']:
                seen.add(f"{previous['date']}至{row['date']}间隔{gap}天，超过{QUALITY['maximum_gap_days']}天")
                start = (date.fromisoformat(previous['date'])+timedelta(days=1)).isoformat()
                end = (date.fromisoformat(row['date'])-timedelta(days=1)).isoformat()
                ranges[(start, end)] = dict(start=start, end=end, kind='gap')
            change = max(abs(row['open']/previous['close']-1), abs(row['close']/previous['close']-1))*100
            if change > QUALITY['maximum_jump_pct']:
                seen.add(f"{row['date']}未复权价格跳变{change:.1f}%，超过{QUALITY['maximum_jump_pct']:g}%")
    result['reasons'] = sorted(seen) or ['当前或60根前的年线窗口未通过既有数据检查']
    result['repair_ranges'] = list(ranges.values())
    result['suggestion'] = ('可尝试补齐区间日线；停牌期间可能没有数据。补齐后重新计算指标和历史信号。' if ranges else
                            '核对除权、重组或行情口径；重复刷新不会消除真实跳变，不自动切换复权或放宽规则。')
    return result
