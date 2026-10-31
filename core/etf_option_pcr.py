"""Post-close SSE/SZSE ETF option contract-count PCR, independent of orders."""
import io
import json
import math
import sys
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .option_pcr import add_bands, eligible_sessions, fetch_day, _available_at
from .provider import CN, now_cn

CODE, KIND = 'etf-options-sse-szse', 'option_pcr_etf_exchange_v1'
HISTORY = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/etf-option-pcr-verified.json'
SSE_CODES = {'510050', '510300', '510500', '588000', '588080'}
SZSE_CODES = {'159901', '159915', '159919', '159922'}
NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _integer(value):
    value = str(value).replace(',', '')
    if not value.isdigit():
        raise ValueError('期权成交量无效')
    return int(value)


def _totals(rows, expected):
    codes = [row[0] for row in rows]
    if len(codes) != len(expected) or set(codes) != expected:
        raise ValueError('期权标的缺失、重复或范围变化')
    if any(call <= 0 or put < 0 or total != call + put for _, call, put, total in rows):
        raise ValueError('期权成交量不一致')
    return sum(row[1] for row in rows), sum(row[2] for row in rows)


def parse_sse(payload, day):
    rows = []
    for row in payload.get('result', []):
        if row.get('TRADE_DATE') != day:
            raise ValueError('上交所期权日期不一致')
        call, put, total = (_integer(row.get(k)) for k in ('CALL_VOLUME', 'PUT_VOLUME', 'TOTAL_VOLUME'))
        official = Decimal(str(row.get('CP_RATE', '')).replace(',', ''))
        if call <= 0 or not official.is_finite() or abs(official - Decimal(put)*100/Decimal(call)) > Decimal('.0051'):
            raise ValueError('上交所期权比例不一致')
        rows.append((row.get('SECURITY_CODE'), call, put, total))
    return _totals(rows, SSE_CODES)


def parse_szse(data):
    with ZipFile(io.BytesIO(data)) as archive:
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = [[''.join(c.itertext()).strip() for c in r.findall('x:c', NS)]
                for r in sheet.findall('.//x:row', NS)]
    if not rows or rows[0][:5] != ['合约标的代码', '合约标的名称', '成交量（张）', '认购成交量（张）', '认沽成交量（张）']:
        raise ValueError('深交所期权表头不匹配')
    return _totals([(r[0], _integer(r[3]), _integer(r[4]), _integer(r[2])) for r in rows[1:] if r], SZSE_CODES)


def collect(day, now):
    # The SZSE exported spreadsheet has no date column. Its date is anchored
    # by the request; this is explicitly disclosed on the chart.
    _, payload = fetch_day(day, now.isoformat())
    sh_call, sh_put = parse_sse(payload, day)
    query = urlencode({'SHOWTYPE': 'xlsx', 'CATALOGID': 'ysprdzb', 'TABKEY': 'tab1',
                       'txtQueryDate': day, 'random': str(time.time())})
    request = Request('https://www.szse.cn/api/report/ShowReport?' + query, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(request, timeout=10) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('深交所期权文件过大')
    sz_call, sz_put = parse_szse(data)
    call, put = sh_call + sz_call, sh_put + sz_put
    collected = max(now, now_cn())
    return {'date': day, 'call_volume': call, 'put_volume': put, 'total_volume': call + put,
            'pcr': put / call, 'sse_call': sh_call, 'sse_put': sh_put,
            'szse_call': sz_call, 'szse_put': sz_put, 'collected_at': collected.isoformat()}


def valid(row, now):
    try:
        day = row['date']
        if date.fromisoformat(day).isoformat() != day or not _available_at(row, now):
            return False
        stamp = datetime.fromisoformat(row['collected_at']).astimezone(CN)
        if stamp.date().isoformat() < day or (stamp.date().isoformat() == day and stamp.strftime('%H:%M') < '16:30'):
            return False
        names = ('call_volume', 'put_volume', 'total_volume', 'sse_call', 'sse_put', 'szse_call', 'szse_put')
        if any(type(row[k]) is not int or row[k] < 0 for k in names):
            return False
        call, put = row['call_volume'], row['put_volume']
        ratio = row['pcr']
        return (call > 0 and row['sse_call'] > 0 and row['szse_call'] > 0
                and call == row['sse_call'] + row['szse_call']
                and put == row['sse_put'] + row['szse_put']
                and row['total_volume'] == call + put
                and isinstance(ratio, (int, float)) and not isinstance(ratio, bool)
                and math.isfinite(ratio) and math.isclose(ratio, put/call, rel_tol=1e-10, abs_tol=1e-12))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class ETFOptionPCR:
    security_code = 'etf-exchanges'

    def __init__(self, store):
        self.store, self.lock = store, threading.Lock()
        self.error, self.running = '', False

    def view(self, now=None):
        now = now or now_cn()
        dates = eligible_sessions(now, 1)
        latest = dates[-1] if dates else None
        history = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else []
        rows = {r['date']: r for r in history if latest and valid(r, now) and r['date'] <= latest}
        for item in self.store.getcache(CODE, KIND):
            row = item['data']
            if latest and isinstance(row, dict) and row.get('date') == item['day'] and item['day'] <= latest and valid(row, now):
                rows[item['day']] = row
        return {'days': add_bands([rows[d] for d in sorted(rows)]), 'error': self.error,
                'running': self.running, 'latest_eligible': latest}

    def refresh(self, now=None):
        now = now or now_cn()
        with self.lock:
            if self.running:
                return
            self.running = True
        try:
            days = eligible_sessions(now, 1)
            if not days:
                raise ValueError('缺少交易日历')
            row = collect(days[-1], now)
            if not valid(row, max(now, now_cn())):
                raise ValueError('期权统计校验失败')
            self.store.cache(CODE, KIND, days[-1], row)
            self.error = ''
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else '沪深ETF期权统计获取失败：' + type(exc).__name__
        finally:
            with self.lock:
                self.running = False
