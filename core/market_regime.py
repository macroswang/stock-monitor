"""Dated CSI 300 daily close versus its 250-day line.

The strong annual-line signal needs a market-regime fact that is not derived
from the stock itself. One 2,000-bar snapshot is refreshed after the close and
cached under a fixed key; missing data never counts as "above".
"""
import json, math, threading, time
from datetime import date
from urllib.parse import urlencode

from .ma250_sessions import eligible_sessions
from .provider import get, now_cn

CODE = 'sh000300'
KIND = 'index_regime_v1'
SOURCE = '腾讯公开沪深300日线'
START = '2018-08-01'
RETRY_SECONDS = 300


def parse(payload):
    try:
        raw = payload['data'][CODE]['day']
    except (KeyError, TypeError):
        raise ValueError('沪深300日线数据不可用') from None
    if not isinstance(raw, list) or not raw:
        raise ValueError('沪深300日线为空')
    rows, previous = [], None
    for item in raw:
        try:
            if not isinstance(item, list) or len(item) < 6:
                raise ValueError
            day = date.fromisoformat(item[0])
            if day.isoformat() != item[0] or (previous and day <= previous):
                raise ValueError
            values = [float(value) for value in item[1:6]]
            if not all(math.isfinite(value) for value in values):
                raise ValueError
            open_, close, high, low, volume = values
            if min(open_, close, high, low) <= 0 or volume < 0 or high < max(open_, close) or low > min(open_, close):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValueError('沪深300日线日期或价格异常') from None
        previous = day
        if day.isoformat() >= START:
            rows.append(dict(date=day.isoformat(), open=open_, close=close, high=high, low=low, volume=volume))
    if not rows:
        raise ValueError('沪深300日线为空')
    return rows


def fetch(end):
    errors = []
    for path in ('kline/kline', 'fqkline/get'):
        try:
            url = 'https://web.ifzq.gtimg.cn/appstock/app/' + path + '?' + urlencode(
                {'param': f'{CODE},day,{START},{end},2000,'})
            return parse(json.loads(get(url)))
        except Exception as error:
            errors.append(type(error).__name__)
    raise ValueError('沪深300日线来源不可用（' + '/'.join(errors) + '）')


def sma(rows, period=250):
    closes = [row['close'] for row in rows]
    out, total = [], 0.0
    for index, close in enumerate(closes):
        total += close
        if index >= period:
            total -= closes[index - period]
        out.append(total / period if index + 1 >= period else None)
    return out


class MarketRegime:
    def __init__(self, store):
        self.store, self.lock, self.error = store, threading.Lock(), ''
        self.last_attempt = 0.0
        self._map_revision, self._map = None, {}

    def rows(self):
        saved = self.store.getcache(CODE, KIND)
        if not saved or saved[-1]['data'].get('source') != SOURCE:
            return []
        rows = saved[-1]['data'].get('rows')
        return rows if isinstance(rows, list) else []

    def above_map(self):
        revision = self.store.cache_revision(CODE, KIND)
        if revision == self._map_revision:
            return self._map
        rows = self.rows()
        line = sma(rows)
        self._map = {row['date']: (row['close'] > line[index] if line[index] is not None else None)
                     for index, row in enumerate(rows)}
        self._map_revision = revision
        return self._map

    def view(self):
        saved = self.store.getcache(CODE, KIND)
        data = saved[-1]['data'] if saved and saved[-1]['data'].get('source') == SOURCE else {}
        rows = data.get('rows') if isinstance(data.get('rows'), list) else []
        ma250, above = data.get('ma250'), data.get('above')
        if rows and ma250 is None:
            line = sma(rows)
            ma250 = line[-1]
            above = rows[-1]['close'] > ma250 if ma250 is not None else None
        expected = eligible_sessions(now_cn(), 1)
        return dict(date=rows[-1]['date'] if rows else None,
                    close=rows[-1]['close'] if rows else None,
                    ma250=ma250, above=above, bars=len(rows), error=self.error,
                    expected_date=expected[-1] if expected else None,
                    stale=not rows or not expected or rows[-1]['date'] < expected[-1])

    def ensure(self, now=None):
        now = now or now_cn()
        days = eligible_sessions(now, 1)
        if not days:
            return
        rows = self.rows()
        if rows and rows[-1]['date'] >= days[-1]:
            return
        if time.monotonic() - self.last_attempt < RETRY_SECONDS:
            return
        self.refresh(now, days[-1])

    def refresh(self, now=None, end=None):
        now = now or now_cn()
        days = eligible_sessions(now, 1)
        end = end or (days[-1] if days else None)
        if not end:
            return
        with self.lock:
            self.last_attempt = time.monotonic()
            try:
                rows = fetch(end)
                if rows[-1]['date'] != end:
                    raise ValueError('沪深300日线未覆盖应取日期')
                line = sma(rows)
                self.store.cache(CODE, KIND, 'latest',
                                 dict(rows=rows, collected_at=now.isoformat(), source=SOURCE,
                                      requested_end=end, last_date=rows[-1]['date'],
                                      ma250=line[-1], above=rows[-1]['close'] > line[-1] if line[-1] is not None else None))
                self.error = ''
            except Exception as error:
                self.error = str(error) if isinstance(error, ValueError) else '沪深300日线获取失败：' + type(error).__name__
