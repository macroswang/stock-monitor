"""Read-only SSE 50ETF option volume PCR, independent of trading and monitoring."""
import json
import math
import sys
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .paper_session import calendar
from .provider import CN, now_cn

CODE = 'sse-510050'
KIND = 'option_pcr_sse50_v1'
HISTORY = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/sse50-pcr-verified.json'
ENDPOINT = 'https://query.sse.com.cn/commonQuery.do'
SOURCE_PAGE = 'https://www.sse.com.cn/assortment/options/date/'
PRODUCTS = {'510050': '上证50ETF华夏', '510300': '沪深300ETF华泰柏瑞'}
NOT_PUBLISHED = '上交所尚未返回所选日期期权统计'


def eligible_sessions(now, limit=30):
    """Use only exchange-verified calendars and post-close dates."""
    now = now.astimezone(CN)
    day = now.date()
    if now.strftime('%H:%M') < '16:30':
        day -= timedelta(days=1)
    out = []
    for _ in range(100):
        closed = calendar(day.year)
        if closed is None:
            break
        if day.weekday() < 5 and not any(a <= day.isoformat() <= b for a, b in closed):
            out.append(day.isoformat())
            if len(out) == limit:
                break
        day -= timedelta(days=1)
    return list(reversed(out))


def _whole_number(value):
    text = str(value).replace(',', '')
    if not text.isdigit():
        raise ValueError('期权统计数量无效')
    return int(text)


def parse_day(payload, day, observed_at, security_code='510050'):
    if security_code not in PRODUCTS:
        raise ValueError('不支持的期权标的')
    rows = payload.get('result') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError('上交所期权统计格式异常')
    if not rows:
        raise ValueError(NOT_PUBLISHED)
    selected = [r for r in rows if isinstance(r, dict) and r.get('SECURITY_CODE') == security_code]
    if len(selected) != 1:
        raise ValueError('指定ETF期权统计缺失或重复')
    row = selected[0]
    if row.get('TRADE_DATE') != day:
        raise ValueError('上交所期权统计日期不匹配')
    call, put, total = (_whole_number(row.get(k)) for k in ('CALL_VOLUME', 'PUT_VOLUME', 'TOTAL_VOLUME'))
    if call <= 0 or put < 0 or total != call + put:
        raise ValueError('认购、认沽和总成交量不一致')
    try:
        official = Decimal(str(row['CP_RATE']).replace(',', ''))
        calculated = Decimal(put) * 100 / Decimal(call)
        if not official.is_finite() or abs(official-calculated) > Decimal('0.0051'):
            raise ValueError('上交所认沽认购比与原始成交量不一致')
    except (KeyError, InvalidOperation):
        raise ValueError('上交所认沽认购比无效') from None
    return dict(date=day, security_code=security_code, security_name=str(row.get('SECURITY_ABBR','')),
                call_volume=call, put_volume=put, total_volume=total, pcr=put/call,
                official_percent=float(official), collected_at=observed_at,
                source='上交所每日统计', source_url=SOURCE_PAGE,
                basis=f'{PRODUCTS[security_code]}期权；全部合约成交张数；认沽成交量÷认购成交量')


def fetch_day(day, observed_at, security_code='510050'):
    params = urlencode({'isPagination':'false', 'sqlId':'COMMON_SSE_ZQPZ_YSP_QQ_SJTJ_MRTJ_CX',
                        'tradeDate':day.replace('-', '')})
    request = Request(ENDPOINT+'?'+params, headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.sse.com.cn/'})
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return parse_day(payload, day, observed_at, security_code), payload


def add_bands(rows):
    """20 observed, consecutive sessions; no interpolation, no future observations."""
    out, window = [], []
    previous = None
    for row in rows:
        item = dict(row)
        item['band_mid'] = item['band_upper'] = item['band_lower'] = None
        item['gap_before'] = bool(out)
        try:
            current = date.fromisoformat(item['date'])
            ratio = item['pcr']
            valid = isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and math.isfinite(ratio) and ratio >= 0
            if previous is not None:
                # Lazy import avoids duplicating the verified holiday handling.
                from .breadth import _next_verified_trading_day
                item['gap_before'] = _next_verified_trading_day(previous) != current
                if item['gap_before']:
                    window = []
            if not valid:
                window = []
                previous = None
            else:
                window.append(float(ratio))
                window = window[-20:]
                previous = current
                if len(window) == 20:
                    mean = sum(window) / 20
                    sd = math.sqrt(sum((x-mean)**2 for x in window) / 20)
                    item.update(band_mid=mean, band_upper=mean+2*sd, band_lower=mean-2*sd)
        except (KeyError, TypeError, ValueError):
            window = []
            previous = None
        out.append(item)
    return out


def _available_at(row, now):
    try:
        stamp = datetime.fromisoformat(row['collected_at'])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return False
        observed = stamp.astimezone(CN)
        day = date.fromisoformat(row['date'])
        return (observed <= now.astimezone(CN) and observed.date() >= day
                and (observed.date() > day or observed.strftime('%H:%M') >= '15:00'))
    except (KeyError, TypeError, ValueError):
        return False


def _valid_record(row, security_code='510050'):
    """Do not display corrupt or foreign records from a cache or fixture."""
    try:
        if not isinstance(row, dict) or row.get('security_code') != security_code:
            return False
        day = row['date']
        if date.fromisoformat(day).isoformat() != day:
            return False
        call, put, total = (row[k] for k in ('call_volume', 'put_volume', 'total_volume'))
        if any(type(n) is not int for n in (call, put, total)):
            return False
        ratio = row['pcr']
        return (call > 0 and put >= 0 and total == call + put
                and isinstance(ratio, (int, float)) and not isinstance(ratio, bool)
                and math.isfinite(ratio) and math.isclose(ratio, put / call, rel_tol=1e-10, abs_tol=1e-12))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class OptionPCR:
    def __init__(self, store, security_code='510050'):
        if security_code not in PRODUCTS:
            raise ValueError('不支持的期权标的')
        self.store = store
        self.security_code = security_code
        self.code = 'sse-' + security_code
        self.history = HISTORY if security_code == '510050' else HISTORY.with_name('sse300-pcr-verified.json')
        self.lock = threading.Lock()
        self.error = ''
        self.running = False

    def view(self, now=None):
        now = now or now_cn()
        sessions = eligible_sessions(now, 30)
        latest = sessions[-1] if sessions else None
        history = json.loads(self.history.read_text(encoding='utf-8')) if self.history.exists() else []
        combined = {r['date']:r for r in history if latest and _valid_record(r, self.security_code) and r['date'] <= latest and _available_at(r, now)}
        for cached in self.store.getcache(self.code, KIND):
            row = cached['data']
            if latest and _valid_record(row, self.security_code) and cached['day'] <= latest and row['date'] == cached['day'] and _available_at(row, now):
                combined[cached['day']] = row
        return dict(days=add_bands([combined[d] for d in sorted(combined)]), running=self.running,
                    error=self.error, latest_eligible=latest, source_url=SOURCE_PAGE)

    def refresh(self, now=None):
        now = now or now_cn()
        with self.lock:
            if self.running:
                return
            self.running = True
        try:
            dates = eligible_sessions(now, 30)
            if not dates:
                raise ValueError('缺少已核验交易日历，无法确定期权统计日期')
            existing = {r['date'] for r in self.view(now)['days']}
            # Refresh the latest day to detect revisions; retain cache on failure.
            needed = [d for d in dates if d not in existing or d == dates[-1]]
            for day in needed:
                data, _ = fetch_day(day, now.isoformat()) if self.security_code == '510050' else fetch_day(day, now.isoformat(), self.security_code)
                self.store.cache(self.code, KIND, day, data)
                time.sleep(.15)
            self.error = ''
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else '上交所期权统计获取失败：'+type(exc).__name__
        finally:
            with self.lock:
                self.running = False
