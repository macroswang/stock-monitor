"""Independent SSE valuation versus CFETS 10-year yield, read-only."""
import json
import math
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .option_pcr import eligible_sessions
from .provider import CN, now_cn

CODE, KIND = 'sse-equity', 'equity_bond_reference_v1'
HISTORY = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/equity-bond-reference.json'
SSE_URL = 'https://query.sse.com.cn/commonQuery.do'
BOND_URL = 'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/SddsIntrRateGovYldHis'


def _number(value):
    if isinstance(value, bool):
        raise ValueError('估值或收益率无效')
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError('估值或收益率缺失') from None
    if not math.isfinite(n) or n <= 0 or n >= 10000:
        raise ValueError('估值或收益率无效')
    return n


def parse_sse(payload, day):
    rows = payload.get('result', []) if isinstance(payload, dict) else []
    rows = [r for r in rows if isinstance(r, dict) and r.get('PRODUCT_CODE') == '17']
    if len(rows) != 1 or rows[0].get('TRADE_DATE') != day.replace('-', ''):
        raise ValueError('上交所股票统计日期或范围不匹配')
    return _number(rows[0].get('AVG_PE_RATE'))


def parse_bonds(payload, start, end):
    if not isinstance(payload, dict) or str(payload.get('head', {}).get('rep_code')) != '200':
        raise ValueError('中国货币网国债数据不可用')
    meta, rows = payload.get('data', {}), payload.get('records')
    if meta.get('flagMessage') or not isinstance(rows, list) or meta.get('pageTotal', 0) > 1:
        raise ValueError('国债数据不完整')
    if meta.get('total') != len(rows):
        raise ValueError('国债数据条数不一致')
    out = {}
    for row in rows:
        day = row.get('dateString')
        try:
            if date.fromisoformat(day).isoformat() != day or not start <= day <= end or day in out:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError('国债数据日期无效或重复') from None
        out[day] = _number(row.get('tenRate'))
    return out


def fetch_bonds(start, end):
    query = urlencode(dict(lang='CN', startDate=start, endDate=end, pageNum=1, pageSize=30))
    req = Request(BOND_URL+'?'+query, method='POST', headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.chinamoney.com.cn/'})
    with urlopen(req, timeout=12) as response:
        return parse_bonds(json.load(response), start, end)


def fetch_sse(day):
    query = urlencode(dict(sqlId='COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C', PRODUCT_CODE='01,02,03,11,17', type='inParams', SEARCH_DATE=day))
    req = Request(SSE_URL+'?'+query, headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.sse.com.cn/'})
    with urlopen(req, timeout=12) as response:
        return parse_sse(json.load(response), day)


def make_row(day, pe, yield_pct, collected_at):
    pe, yield_pct = _number(pe), _number(yield_pct)
    return dict(date=day, pe=pe, bond_yield=yield_pct, spread=100 / pe - yield_pct,
                collected_at=collected_at)


def valid_row(row, now):
    try:
        day = row['date']
        if date.fromisoformat(day).isoformat() != day:
            return False
        stamp = datetime.fromisoformat(row['collected_at'])
        if stamp.tzinfo is None or stamp > now.astimezone(CN):
            return False
        expected = make_row(day, row['pe'], row['bond_yield'], row['collected_at'])['spread']
        return math.isfinite(row['spread']) and math.isclose(expected, row['spread'], rel_tol=1e-10, abs_tol=1e-10)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class EquityBond:
    def __init__(self, store):
        self.store, self.running, self.error = store, False, ''
        self.lock = threading.Lock()

    def view(self, now=None):
        now = now or now_cn()
        dates = eligible_sessions(now, 30)
        latest = dates[-1] if dates else None
        history = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else []
        combined = {r['date']:r for r in history if latest and valid_row(r, now) and r['date'] <= latest}
        for entry in self.store.getcache(CODE, KIND):
            row = entry['data']
            if latest and valid_row(row, now) and row['date'] == entry['day'] and row['date'] <= latest:
                combined[row['date']] = row
        from .breadth import _next_verified_trading_day
        days = []
        previous = None
        for key in sorted(combined):
            current = date.fromisoformat(key)
            item = dict(combined[key], gap_before=previous is not None and _next_verified_trading_day(previous) != current)
            days.append(item)
            previous = current
        return dict(days=days, running=self.running,
                    error=self.error, latest_eligible=latest)

    def refresh(self, now=None):
        now = now or now_cn()
        with self.lock:
            if self.running:
                return
            self.running = True
        try:
            dates = eligible_sessions(now, 30)
            if not dates:
                raise ValueError('缺少已核验交易日历')
            existing = {r['date'] for r in self.view(now)['days']}
            needed = [d for d in dates if d not in existing or d == dates[-1]]
            rates = {}
            # Queries span at most 20 calendar days and do not assume weekdays are sessions.
            day, end = date.fromisoformat(dates[0]), date.fromisoformat(dates[-1])
            while day <= end:
                last = min(end, day + timedelta(days=19))
                rates.update(fetch_bonds(day.isoformat(), last.isoformat()))
                day = last + timedelta(days=1)
            for day in needed:
                if day not in rates:
                    raise ValueError('国债数据缺少交易日期 ' + day)
                row = make_row(day, fetch_sse(day), rates[day], now.isoformat())
                self.store.cache(CODE, KIND, day, row)
                time.sleep(.15)
            self.error = ''
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else '股债参照获取失败：' + type(exc).__name__
        finally:
            with self.lock:
                self.running = False
