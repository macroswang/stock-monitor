"""Independent, dated SSE Composite daily/weekly technical reference."""
import json
import math
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from .breadth import _next_verified_trading_day
from .option_pcr import eligible_sessions
from .paper_session import calendar
from .provider import CN, get, now_cn

CODE, KIND = 'sh000001', 'market_technical_v1'
HISTORY = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/index-technical-reference.json'
SOURCE = '腾讯公开上证指数日线'
URL = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'


def trading_day(day):
    closed = calendar(day.year)
    if closed is None:
        return None
    return day.weekday() < 5 and not any(a <= day.isoformat() <= b for a, b in closed)


def parse_daily(payload, start, end):
    try:
        rows = payload['data'][CODE]['day']
    except (KeyError, TypeError):
        raise ValueError('指数日线数据不可用') from None
    if not isinstance(rows, list) or not rows:
        raise ValueError('指数日线数据为空')
    out, previous = [], None
    for raw in rows:
        try:
            if not isinstance(raw, list) or len(raw) < 6:
                raise ValueError
            day = date.fromisoformat(raw[0])
            if day.isoformat() != raw[0] or (previous and day <= previous):
                raise ValueError
            previous = day
            if not start <= day.isoformat() <= end:
                continue
            if trading_day(day) is not True:
                raise ValueError
            values = [float(x) for x in raw[1:6]]
            if not all(math.isfinite(x) for x in values):
                raise ValueError
            op, close, high, low, volume = values
            if min(op, close, high, low) <= 0 or volume <= 0 or low > min(op, close) or high < max(op, close) or low > high:
                raise ValueError
            out.append(dict(date=day.isoformat(), first_date=day.isoformat(), open=op, close=close, high=high, low=low,
                            volume=volume * 100))
        except (TypeError, ValueError, OverflowError):
            raise ValueError('指数日线日期或价格异常') from None
    if not out or out[-1]['date'] != end:
        raise ValueError('指数日线缺少最新已结束交易日')
    return out


def fetch_daily(start, end):
    url = URL+'?'+urlencode({'param':f'{CODE},day,{start},{end},2000,'})
    return parse_daily(json.loads(get(url)), start, end)


def weekly(rows, last_day):
    groups = {}
    for row in rows:
        d = date.fromisoformat(row['date'])
        monday = d - timedelta(days=d.weekday())
        groups.setdefault(monday, []).append(row)
    output = []
    for monday, group in sorted(groups.items()):
        expected = []
        for offset in range(5):
            day = monday + timedelta(days=offset)
            flag = trading_day(day)
            if flag is None:
                expected = []
                break
            if flag:
                expected.append(day.isoformat())
        if not expected or expected[-1] > last_day or [r['date'] for r in group] != expected:
            continue
        volume = [r.get('volume') for r in group]
        output.append(dict(date=group[-1]['date'], first_date=group[0]['date'], open=group[0]['open'], close=group[-1]['close'],
                           high=max(r['high'] for r in group), low=min(r['low'] for r in group),
                           volume=sum(volume) if all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in volume) else None))
    return output


def indicators(rows):
    result, close_window, tp_window, vw_window, vw_ema, previous = [], [], [], [], None, None
    for raw in rows:
        row = dict(raw)
        first = date.fromisoformat(row['first_date'])
        gap = previous is not None and _next_verified_trading_day(previous) != first
        if gap:
            close_window, tp_window, vw_window, vw_ema = [], [], [], None
        previous = date.fromisoformat(row['date'])
        close_window.append(row['close']); close_window = close_window[-20:]
        tp_window.append((row['high'] + row['low'] + row['close'])/3); tp_window = tp_window[-14:]
        row.update(gap_before=gap, boll_mid=None, boll_upper=None, boll_lower=None, cci=None,
                   vw_dif=None, vw_dea=None, vw_macd=None)
        if len(close_window) == 20:
            mean = sum(close_window)/20
            sd = math.sqrt(sum((v-mean)**2 for v in close_window)/20)
            row.update(boll_mid=mean,boll_upper=mean+2*sd,boll_lower=mean-2*sd)
        if len(tp_window) == 14:
            mean = sum(tp_window)/14
            deviation = sum(abs(v-mean) for v in tp_window)/14
            if deviation:
                row['cci'] = (tp_window[-1]-mean)/(.015*deviation)
        volume = row.get('volume')
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume <= 0:
            vw_window, vw_ema = [], None
        else:
            vw_window.append((row['close'], volume)); vw_window = vw_window[-26:]
            if len(vw_window) == 26:
                def mean(window):
                    return sum(c*v for c,v in window)/sum(v for _,v in window)
                dif = mean(vw_window[-12:]) - mean(vw_window)
                vw_ema = dif if vw_ema is None else .2*dif + .8*vw_ema
                row.update(vw_dif=dif, vw_dea=vw_ema, vw_macd=2*(dif-vw_ema))
        result.append(row)
    return result


def valid_snapshot(snapshot, now, latest):
    try:
        stamp = datetime.fromisoformat(snapshot['collected_at'])
        rows = snapshot['rows']
        if stamp.tzinfo is None or stamp > now.astimezone(CN) or not isinstance(rows,list) or not rows:
            return False
        last = date.fromisoformat(rows[-1]['date'])
        observed = stamp.astimezone(CN)
        if observed.date() < last or (observed.date() == last and observed.strftime('%H:%M') < '16:30'):
            return False
        # Re-run the same strict date and OHLC validation on stored data.
        # Older snapshots predate volume retention and remain usable for price-only indicators.
        data = [[r['date'],r['open'],r['close'],r['high'],r['low'],r['volume']/100 if r.get('volume') is not None else 1] for r in rows]
        parsed = parse_daily({'data':{CODE:{'day':data}}},rows[0]['date'],rows[-1]['date'])
        return (len(parsed)==len(rows) and all(r.get('first_date')==r['date'] for r in rows)
                and rows[-1]['date'] <= latest and snapshot.get('source')==SOURCE)
    except (KeyError, TypeError, ValueError):
        return False


class IndexTechnical:
    def __init__(self, store):
        self.store, self.error, self.running = store, '', False
        self.lock = threading.Lock()

    def view(self, now=None):
        now = now or now_cn()
        days = eligible_sessions(now,1)
        latest = days[-1] if days else None
        snapshots = []
        if HISTORY.exists():
            snapshots.append(json.loads(HISTORY.read_text(encoding='utf-8')))
        snapshots.extend(x['data'] for x in self.store.getcache(CODE,KIND))
        valid = [s for s in snapshots if latest and valid_snapshot(s,now,latest)]
        if not valid:
            return dict(daily=[], weekly=[], error=self.error, running=self.running, latest_eligible=latest)
        selected = max(valid,key=lambda s:(s['rows'][-1]['date'],s['collected_at']))
        daily = selected['rows']
        return dict(daily=indicators(daily),weekly=indicators(weekly(daily,latest)),source=SOURCE,
                    collected_at=selected['collected_at'],error=self.error,running=self.running,latest_eligible=latest)

    def refresh(self, now=None):
        now = now or now_cn()
        with self.lock:
            if self.running:return
            self.running = True
        try:
            days = eligible_sessions(now,1)
            if not days:raise ValueError('缺少已核验交易日历')
            end = days[-1]
            # Preserve the prior year's warm-up only when its exchange calendar
            # is available. Otherwise do not guess which dates were sessions.
            year = int(end[:4])
            start_year = year - 1 if calendar(year - 1) is not None else year
            start = f'{start_year:04d}-01-01'
            rows = fetch_daily(start,end)
            snapshot = dict(rows=rows,collected_at=now.isoformat(),source=SOURCE)
            self.store.cache(CODE,KIND,end,snapshot)
            self.error = ''
        except Exception as exc:
            self.error = str(exc) if isinstance(exc,ValueError) else '指数日线获取失败：'+type(exc).__name__
        finally:
            with self.lock:self.running = False
