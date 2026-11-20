"""Reconcile stock minute caches with the official Tencent daily close."""
import json
import sys
from decimal import Decimal, InvalidOperation

from .index_technical import trading_day
from .ma250_sessions import eligible_sessions
from .provider import now_cn
from .validated_engine import MINUTES


SESSION = ['09:30', *MINUTES, '14:57', '14:58', '14:59', '15:00']
SESSION_WITH_LUNCH = [*SESSION[:121], '13:00', *SESSION[121:]]


def minute_close(group, day):
    if (not group or group.get('date') != day or group.get('source') != 'tencent'
            or group.get('volume_unit') != 'shares'):
        return None
    bars = group.get('bars') or []
    times = [bar.get('time') for bar in bars]
    if times not in (SESSION, SESSION_WITH_LUNCH):
        return None
    total = 0
    try:
        for bar in bars:
            price, volume = Decimal(str(bar.get('close'))), bar.get('volume')
            if (bar.get('complete') is not True or not price.is_finite() or price <= 0
                    or type(volume) is not int or volume < 0):
                return None
            total += volume
    except InvalidOperation:
        return None
    return price, total


def close_reference(day, daily=None, quote=None):
    if (daily and daily.get('date') == day and daily.get('source') == 'tencent'
            and daily.get('adjustment') == 'none' and daily.get('volume_unit') == 'shares'
            and str(daily.get('cached_at', '')) >= day+'T15:15' and not daily.get('provisional')):
        data, price_key, source = daily, 'close', 'daily'
    elif (quote and quote.get('date') == day and quote.get('source') == 'tencent'
          and quote.get('volume_unit') == 'shares' and quote.get('timestamp', '')[:10] == day
          and quote.get('timestamp', '')[11:19] >= '15:00:00'):
        data, price_key, source = quote, 'price', 'quote'
    else:
        return None
    try:
        price = Decimal(str(data.get(price_key)))
        volume = Decimal(str(data.get('volume')))
        if price.is_finite() and price > 0 and volume.is_finite() and volume >= 0 and volume == volume.to_integral_value():
            return (price, int(volume)), source
    except InvalidOperation:
        pass
    return None


def checked_group(group, day, reference):
    actual = minute_close(group, day)
    if not actual or not reference or actual[0] != reference[0][0]:
        return None
    data = dict(group, session_closed=True)
    data.pop('close_verified', None)
    data.pop('close_volume_difference', None)
    difference = actual[1] - reference[0][1]
    if difference:
        data['close_volume_difference'] = difference
    else:
        data['close_verified'] = reference[1]
    return data


TARGETS = """
    SELECT code, min(priority) AS priority FROM (
        SELECT code, 0 AS priority FROM watch
        UNION ALL
        SELECT p.code, 1 FROM pool p LEFT JOIN cache c
          ON c.code=p.code AND c.kind='minute' AND c.day=?
        WHERE (COALESCE(CAST(p.archived AS INTEGER),0)=0 AND p.added_day<=?) OR c.code IS NOT NULL
    ) GROUP BY code ORDER BY priority, code
"""


class StockClose:
    def __init__(self, app):
        self.app = app

    def cached(self, code, kind, day):
        rows = self.app.store.getcache(code, kind, day)
        return rows[0]['data'] if rows else None

    def run(self):
        while not self.app.stop.is_set():
            now = now_cn()
            if self.intraday(now):
                self.app.stop.wait(30)
                continue
            sessions = eligible_sessions(now, 1)
            if sessions:
                try:
                    self.refresh(sessions[-1])
                except Exception as exc:
                    print('stock close: '+type(exc).__name__, file=sys.stderr, flush=True)
            self.app.stop.wait(300 if '15:20' <= now.strftime('%H:%M') < '16:00' else 1800)

    @staticmethod
    def intraday(now):
        return trading_day(now.date()) is True and '09:15' <= now.strftime('%H:%M') < '15:20'

    def reconcile(self, code, day, reference):
        if reference is None or self.app.stop.is_set():
            return False
        current = self.cached(code, 'minute', day)
        checked = checked_group(current, day, reference)
        if checked and checked.get('close_verified'):
            if checked != current:
                self.app.cache_minutes(code, checked)
            return True
        group = next((row for row in self.app.provider.minutes(code) if row.get('date') == day), None)
        fresh = checked_group(group, day, reference)
        if fresh and not self.app.stop.is_set():
            if fresh.get('close_verified') or not checked or fresh['bars'] != checked['bars']:
                self.app.cache_minutes(code, fresh)
            elif current != checked:
                self.app.cache_minutes(code, checked)
            return bool(fresh.get('close_verified'))
        return False

    def refresh(self, day):
        pending = self.app.store.query('''SELECT target.code, d.payload AS daily
            FROM ('''+TARGETS+''') target
            LEFT JOIN cache m ON m.code=target.code AND m.kind='minute' AND m.day=?
            LEFT JOIN cache d ON d.code=target.code AND d.kind='daily' AND d.day=?
            WHERE json_extract(m.payload,'$.close_verified') IS NULL
            ORDER BY target.priority, target.code''', (day, day, day, day))
        for offset in range(0, len(pending), 50):
            if self.app.stop.is_set() or self.intraday(now_cn()):
                return
            batch = {row['code']: close_reference(day, json.loads(row['daily']) if row['daily'] else None)
                     for row in pending[offset:offset+50]}
            missing = [code for code, reference in batch.items() if reference is None]
            try:
                quotes = self.app.provider.watch_quotes(missing) if missing else {}
            except Exception:
                quotes = {}
            for code, reference in batch.items():
                if self.app.stop.is_set() or self.intraday(now_cn()):
                    return
                try:
                    self.reconcile(code, day, reference or close_reference(day, quote=quotes.get(code)))
                except Exception:
                    pass  # Leave the row pending. The next sweep can retry it.
                if self.app.stop.wait(.3):
                    return
