"""Dated CSI 300 constituent observation, independent of orders and signals."""
import hashlib
import re
import sys
import threading
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from .breadth import CODE as BREADTH_CODE, KIND as BREADTH_KIND, summarize
from .paper_session import calendar
from .provider import CN, now_cn

CODE, KIND = 'csi300', 'members_v1'
URL = 'https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/000300cons.xls'
REFERENCE_MEMBERS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/csi300-cons-20261030.xls'
REFERENCE_MEMBERS_SHA256 = 'db36872f9ae026c222aa9a118ce411055046376234c53051a879b408ff044cb1'
REFERENCE_OBSERVED = '2026-10-31T03:14:31.055070+08:00'


def parse_members(payload, observed):
    import xlrd
    if len(payload) > 2_000_000:
        raise ValueError('指数成分文件过大')
    book = xlrd.open_workbook(file_contents=payload)
    if book.nsheets != 1:
        raise ValueError('指数成分文件结构异常')
    sheet = book.sheet_by_index(0)
    if sheet.nrows != 301 or sheet.ncols < 9:
        raise ValueError('指数成分数量异常')
    rows, days = [], set()
    for i in range(1, sheet.nrows):
        row = sheet.row_values(i)
        raw_day, index, stock, exchange = str(row[0]), str(row[1]), str(row[4]), str(row[7])
        if not re.fullmatch(r'\d{8}', raw_day) or index != '000300' or not re.fullmatch(r'\d{6}', stock):
            raise ValueError('指数成分日期或代码异常')
        day = datetime.strptime(raw_day, '%Y%m%d').date()
        if day > observed.astimezone(CN).date():
            raise ValueError('指数成分日期晚于采集时间')
        closed = calendar(day.year)
        if closed is None or day.weekday() >= 5 or any(a <= day.isoformat() <= b for a, b in closed):
            raise ValueError('指数成分日期未通过交易日历校验')
        prefix = 'sh' if exchange == '上海证券交易所' else 'sz' if exchange == '深圳证券交易所' else ''
        if not prefix or (prefix == 'sh' and not stock.startswith('6')) or (prefix == 'sz' and stock[0] not in '03'):
            raise ValueError('指数成分交易所异常')
        rows.append(prefix + stock)
        days.add(day.isoformat())
    if len(days) != 1 or len(set(rows)) != 300:
        raise ValueError('指数成分日期或代码重复')
    return dict(date=days.pop(), codes=sorted(rows), source=URL,
                collected_at=observed.astimezone(CN).isoformat(), sha256=hashlib.sha256(payload).hexdigest())


def compare(members, raw, recorded):
    day = members.get('date')
    codes = members.get('codes')
    if (not isinstance(codes, list) or len(codes) != 300 or len(set(codes)) != 300
        or members.get('source') != URL or raw.get('date') != day or recorded.get('date') != day
        or recorded.get('source') != '腾讯逐股报价；新浪全市场代码表'
        or recorded.get('status') not in ('closed', 'provisional')):
        raise ValueError('成分或行情日期不一致')
    try:
        member_stamp = datetime.fromisoformat(members['collected_at'])
        quote_stamp = datetime.fromisoformat(raw['collected_at'])
        if (member_stamp.tzinfo is None or member_stamp.utcoffset() is None
            or quote_stamp.tzinfo is None or quote_stamp.utcoffset() is None
            or member_stamp.astimezone(CN).date().isoformat() < day):
            raise ValueError('成分采集时间异常')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('成分或行情采集时间异常') from exc
    checked = summarize(raw['quotes'], raw['codes'], day, raw['collected_at'], raw['suspended'])
    for key in ('status', 'advance', 'decline', 'flat', 'expected', 'covered', 'missing',
                'advance_amount', 'decline_amount', 'trin_amount', 'first_quote', 'last_quote', 'collected_at', 'universe'):
        if checked.get(key) != recorded.get(key):
            raise ValueError('原始行情与全市场统计不一致')
    if checked['missing'] or checked['covered'] != checked['expected'] or checked['advance_amount'] is None:
        raise ValueError('全市场行情不完整')
    quotes = {row['code']: row for row in raw['quotes']}
    suspended = set(raw['suspended']) | {row['code'] for row in raw['quotes'] if Decimal(str(row['volume'])) == 0}
    if any(code not in quotes and code not in suspended for code in codes):
        raise ValueError('指数成分行情不完整')
    groups = {key: {'count': 0, 'amount': Decimal(0)} for key in ('advance', 'decline', 'flat')}
    for code in codes:
        if code in suspended:
            continue
        row = quotes[code]
        price, base = Decimal(row['price']), Decimal(row['previous_close'])
        key = 'advance' if price > base else 'decline' if price < base else 'flat'
        groups[key]['count'] += 1
        groups[key]['amount'] += Decimal(row['amount_yuan'])
    up_amount, total_up = groups['advance']['amount'], Decimal(str(checked['advance_amount']))
    down_amount, total_down = groups['decline']['amount'], Decimal(str(checked['decline_amount']))
    if total_up <= 0 or total_down < 0 or up_amount > total_up or down_amount > total_down:
        raise ValueError('指数成分成交额异常')
    return dict(date=day, member_date=day, collected_at=raw['collected_at'],
                member_collected_at=member_stamp.astimezone(CN).isoformat(),
                available_at=max(member_stamp, quote_stamp).astimezone(CN).isoformat(), status=checked['status'],
                advance=groups['advance']['count'], decline=groups['decline']['count'],
                flat=groups['flat']['count'], suspended=len(set(codes) & suspended),
                advance_amount=float(up_amount), market_advance_amount=float(total_up),
                advance_amount_percent=float(100 * up_amount / total_up),
                decline_amount=float(down_amount), market_decline_amount=float(total_down),
                decline_amount_percent=float(100 * down_amount / total_down) if total_down else None, source=URL)


class CSI300:
    def __init__(self, store):
        self.store, self.lock = store, threading.Lock()
        self.error = ''
        self.reference_1030_cached = None

    def reference_1030(self):
        # Both the official membership file and the raw quote snapshot were
        # already collected by this time; never expose them earlier.
        observed = datetime.fromisoformat(REFERENCE_OBSERVED)
        if now_cn() < observed:
            return None
        if self.reference_1030_cached is not None:
            return self.reference_1030_cached
        from .breadth import Breadth
        try:
            payload = REFERENCE_MEMBERS.read_bytes()
            if hashlib.sha256(payload).hexdigest() != REFERENCE_MEMBERS_SHA256:
                return None
            members = parse_members(payload, observed)
            reference = Breadth(self.store).reference_close_1030()
            if not reference or members['date'] != '2026-10-30':
                return None
            self.reference_1030_cached = compare(members, reference[0], reference[1])
            return self.reference_1030_cached
        except (OSError, KeyError, ValueError, TypeError, ArithmeticError):
            return None

    def refresh(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            req = Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(req, timeout=10) as response:
                payload = response.read(2_000_001)
            data = parse_members(payload, now_cn())
            self.store.cache(CODE, KIND, data['date'], data)
            self.error = ''
        except Exception as exc:
            self.error = '沪深300成分获取失败：' + type(exc).__name__
        finally:
            self.lock.release()

    def view(self, day):
        if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            return None
        members = self.store.getcache(CODE, KIND, day)
        raw = self.store.getcache(BREADTH_CODE, 'breadth_raw_v1', day)
        recorded = self.store.getcache(BREADTH_CODE, BREADTH_KIND, day)
        if not members or not raw or not recorded:
            return self.reference_1030() if day == '2026-10-30' else None
        try:
            observed = datetime.fromisoformat(members[0]['data']['collected_at'])
            if observed.tzinfo is None or observed > now_cn():
                return None
            return compare(members[0]['data'], raw[0]['data'], recorded[0]['data'])
        except (KeyError, ValueError, TypeError, ArithmeticError):
            return None
