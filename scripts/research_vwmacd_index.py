"""Read-only source comparison for the observed VW-MACD formula; not a signal."""
import hashlib
import json
from pathlib import Path

from core.index_technical import CODE, parse_daily, weekly
from core.provider import get, now_cn
from core.breadth import _next_verified_trading_day
from datetime import date

TENCENT = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,2026-01-01,2026-10-30,2000,'
SINA = 'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=1023'
OUT = Path('docs/author-trading-system-20261028/vwmacd-source-20261031.json')


def compute(rows):
    """Full rolling windows; EMA seeded by first full-window DIF, reset on gaps."""
    window, previous, ema, out = [], None, None, []
    for row in rows:
        if previous and _next_verified_trading_day(previous) != date.fromisoformat(row['first_date']):
            window, ema = [], None
        previous = date.fromisoformat(row['date'])
        window.append(row)
        window = window[-26:]
        if len(window) < 26:
            continue
        def mean(w):
            return sum(r['close'] * r['volume'] for r in w) / sum(r['volume'] for r in w)
        dif = mean(window[-12:]) - mean(window)
        ema = dif if ema is None else .2 * dif + .8 * ema
        out.append({'date': row['date'], 'dif': dif, 'dea': ema, 'histogram': 2 * (dif - ema)})
    return out


def main():
    t_raw, s_raw = get(TENCENT), get(SINA)
    t_payload = json.loads(t_raw)
    t = t_payload['data'][CODE]['day']
    s_list = json.loads(s_raw)
    s = {r['day']: r for r in s_list}
    validated = parse_daily(t_payload, '2026-01-01', '2026-10-30')
    if len(s) != len(s_list) or len(validated) != len(t) or any(r[0] not in s for r in t):
        raise ValueError('日线缺失或日期重复')
    differences = [{'date': r[0], 'close': abs(float(r[2]) - float(s[r[0]]['close'])),
                    'shares': abs(float(r[5]) * 100 - float(s[r[0]]['volume']))} for r in t]
    if any(x['close'] > .00501 or x['shares'] != 0 for x in differences):
        raise ValueError('两来源价格或成交量不一致')
    def with_volume(source):
        daily = []
        for r in validated:
            sr = s[r['date']]
            tr = next(x for x in t if x[0] == r['date'])
            daily.append({**r, 'close': float(sr['close']) if source == 'sina' else r['close'],
                          'volume': float(sr['volume']) if source == 'sina' else float(tr[5]) * 100})
        weeks = weekly(daily, '2026-10-30')
        for w in weeks:
            w['volume'] = sum(r['volume'] for r in daily if w['first_date'] <= r['date'] <= w['date'])
        return daily, weeks
    td, tw = with_volume('tencent')
    sd, sw = with_volume('sina')
    t_daily, s_daily = compute(td), compute(sd)
    case_dates = {'2026-09-21', '2026-09-22'}
    report = {'observed_at': now_cn().isoformat(), 'tencent_url': TENCENT, 'sina_url': SINA,
              'tencent_sha256': hashlib.sha256(t_raw.encode()).hexdigest(),
              'sina_sha256': hashlib.sha256(s_raw.encode()).hexdigest(),
              'first': t[0][0], 'last': t[-1][0], 'daily_count': len(t), 'weekly_count': len(tw),
              'max_close_difference': max(x['close'] for x in differences),
              'max_share_difference': max(x['shares'] for x in differences),
              'assumptions': '周量为完整交易周各日股数之和；EMA从首个完整26周期DIF起算；缺口后重置。与画面值及作者初始化尚未核对，非交易信号。',
              'tencent_daily': t_daily[-1], 'sina_daily': s_daily[-1],
              'case_daily_tencent': [r for r in t_daily if r['date'] in case_dates],
              'case_daily_sina': [r for r in s_daily if r['date'] in case_dates],
              'tencent_weekly': compute(tw)[-1], 'sina_weekly': compute(sw)[-1]}
    OUT.with_name('vwmacd-tencent-20261031.json').write_text(t_raw, encoding='utf-8')
    OUT.with_name('vwmacd-sina-20261031.json').write_text(s_raw, encoding='utf-8')
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
