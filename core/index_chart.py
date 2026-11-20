"""Index chart history only; isolated from stock caches, signals and trading."""
import json
import math
import threading
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from .market import CODES, NAMES
from .index_technical import trading_day
from .provider import get, now_cn

KIND = 'index_chart_daily'


def parse_rows(payload, code):
    source = payload.get('data', {}).get(code, {}).get('day')
    if not isinstance(source, list):
        raise ValueError('指数日线为空或代码不匹配')
    rows, previous = [], ''
    for raw in source:
        try:
            day = date.fromisoformat(raw[0])
            values = [float(value) for value in raw[1:6]]
            op, close, high, low, volume = values
            if day.isoformat() != raw[0] or raw[0] <= previous or day.weekday() >= 5 or trading_day(day) is False:
                raise ValueError
            if not all(math.isfinite(value) for value in values) or min(op,close,high,low) <= 0 or volume < 0 or low > min(op,close) or high < max(op,close):
                raise ValueError
            previous = raw[0]
            rows.append(dict(date=raw[0], open=op, close=close, high=high, low=low, volume=volume*100))
        except (ValueError, TypeError, IndexError):
            raise ValueError('指数日线日期或价格异常') from None
    return rows


class IndexChart:
    def __init__(self, app):
        self.app = app
        self.lock = threading.Lock()
        self.failed = {}

    def load(self, args):
        code = args.get('code')
        if code not in CODES:
            raise ValueError('不支持的指数')
        now = now_cn()
        start, end = date.fromisoformat(args['start']), date.fromisoformat(args['end'])
        if not date(1990, 1, 1) <= start < end <= now.date() or not 90 <= (end-start).days <= 25*366:
            raise ValueError('指数历史日期范围无效')
        with self.lock:
            saved = self.app.store.getcache(code, KIND, 'history')
            cached = saved[0]['data'] if saved else None
            stamp = None
            if cached and cached.get('code') == code:
                try:
                    stamp = datetime.fromisoformat(cached['cached_at'])
                    if stamp.tzinfo is None:
                        stamp = None
                except (ValueError, KeyError, TypeError):
                    pass
            ttl = 60 if trading_day(now.date()) is True and '09:20' <= now.strftime('%H:%M') <= '15:20' else 600
            if stamp and 0 <= (now-stamp).total_seconds() < ttl and cached['start'] <= start.isoformat() and cached['end'] >= end.isoformat():
                return self.view(cached, start, end, now)
            key = (code, start, end)
            if key in self.failed and (now-self.failed[key]).total_seconds() < 60:
                raise ValueError('指数日线暂时不可用，请稍后重试')
            try:
                usable = bool(stamp and stamp <= now and cached.get('rows') and cached['end'] <= now.date().isoformat())
                rows = {row['date']:row for row in cached['rows']} if usable else {}
                windows = [(start,end)]
                first, last = start, end
                if usable:
                    first, last = min(start,date.fromisoformat(cached['start'])), max(end,date.fromisoformat(cached['end']))
                    windows = []
                    if start.isoformat() < cached['start']:
                        windows.append((start,date.fromisoformat(cached['start'])-timedelta(days=1)))
                    if end.isoformat() > cached['end'] or (now-stamp).total_seconds() >= ttl:
                        windows.append((max(first,end-timedelta(days=90)),end))
                # Cached old history stays intact; normal refresh reads only the recent tail.
                batches = []
                for lo,hi in windows:
                    count = (hi-lo).days+1
                    parts = math.ceil(count/(6*365))
                    width = math.ceil(count/parts)
                    batches.extend((lo+timedelta(days=n*width),min(hi,lo+timedelta(days=(n+1)*width-1))) for n in range(parts))
                for lo,hi in batches:
                    errors = []
                    for path in ('kline/kline', 'fqkline/get'):
                        try:
                            url = 'https://web.ifzq.gtimg.cn/appstock/app/'+path+'?'+urlencode({'param':f'{code},day,{lo},{hi},2000,'})
                            parsed = parse_rows(json.loads(get(url)), code)
                            rows.update((row['date'],row) for row in parsed if lo.isoformat() <= row['date'] <= hi.isoformat())
                            break
                        except Exception as exc:
                            errors.append(type(exc).__name__)
                    else:
                        raise ValueError('指数日线来源不可用（'+'/'.join(errors)+'）')
                if not rows:
                    raise ValueError('该区间没有指数日线')
                payload = dict(code=code, name=NAMES[code], start=str(first), end=str(last), rows=sorted(rows.values(),key=lambda row:row['date']), cached_at=now.isoformat())
                self.app.store.cache(code, KIND, 'history', payload)
                self.failed.pop(key, None)
                return self.view(payload, start, end, now)
            except Exception:
                self.failed = {key: now}
                raise

    @staticmethod
    def view(payload, start, end, now):
        rows = [dict(row, source='tencent', adjustment='none', volume_unit='shares',
                     provisional=row['date'] == now.date().isoformat() and now.strftime('%H:%M') < '15:20')
                for row in payload['rows'] if start.isoformat() <= row['date'] <= end.isoformat()]
        return dict(code=payload['code'], start=str(start), end=str(end), daily=rows, cached_at=payload['cached_at'])
