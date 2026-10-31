"""Daily, market-wide TRIN. Independent of watchlists, signals and paper orders."""
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from .provider import CN, get, now_cn
from .paper_session import calendar

SINA = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
CODE = 'cn-ashare'
KIND = 'breadth_day_v1'
BREADTH_INTERVAL_SECONDS = 180
HISTORY = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/breadth-history-verified.json'
MA_SEED = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/ma-close-seed-v1.json.gz'
MA_CLOSE_REFERENCE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/ma-reference-2026-10-29.json.gz'
MA_CLOSE_REFERENCE_1030 = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/ma-reference-2026-10-30.json.gz'


def _next_verified_trading_day(previous):
    """Return the next exchange session only when its calendar is available."""
    for offset in range(1, 41):
        day = previous + timedelta(days=offset)
        closed = calendar(day.year)
        if closed is None:
            return None
        if day.weekday() < 5 and not any(first <= day.isoformat() <= last for first, last in closed):
            return day
    return None


def historical_available(row, as_of):
    """Do not calculate with history that had not yet been collected."""
    try:
        collected = datetime.fromisoformat(row['collected_at'])
        if collected.tzinfo is None or collected.utcoffset() is None or as_of.tzinfo is None or as_of.utcoffset() is None:
            return False
        collected, as_of = collected.astimezone(CN), as_of.astimezone(CN)
        day = date.fromisoformat(row['date'])
        return (row.get('historical') is True and row.get('status') == 'closed'
                and collected <= as_of and collected.date() >= day
                and (collected.date() > day or collected.strftime('%H:%M') >= '15:00'))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def add_standard_mcclellan(rows):
    """Independent research indicator; never bridge gaps, partial data or source changes.

    The first valid advance-minus-decline value seeds both EMAs. 39 consecutive
    complete closes are required; early values are initialization-sensitive.
    This is not the author's unverified MCL or a trading signal.
    """
    result, previous, source = [], None, None
    fast = slow = None
    count = 0
    for row in rows:
        item = dict(row)
        item['mcl_standard'] = None
        item['mcl_samples'] = 0
        try:
            current = date.fromisoformat(item['date'])
            a, d = item['advance'], item['decline']
            closed = calendar(current.year)
            expected, covered = item.get('expected'), item.get('covered')
            valid = (closed is not None and current.weekday() < 5
                     and not any(first <= item['date'] <= last for first, last in closed)
                     and item.get('status') == 'closed'
                     and item.get('missing') == 0 and item.get('covered') == item.get('expected')
                     and type(expected) is int and type(covered) is int and expected > 0
                     and type(a) is int and type(d) is int and a >= 0 and d >= 0 and a + d > 0
                     and a + d <= covered
                     and bool(item.get('source')) and bool(item.get('universe')))
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            previous = source = fast = slow = None
            count = 0
            result.append(item)
            continue
        identity = (item['source'], item['universe'])
        if previous is None or _next_verified_trading_day(previous) != current or source != identity:
            fast = slow = float(a - d)
            count = 1
        else:
            fast = .10 * (a - d) + .90 * fast
            slow = .05 * (a - d) + .95 * slow
            count += 1
        previous, source = current, identity
        item['mcl_samples'] = count
        if count >= 39:
            item['mcl_standard'] = fast - slow
        result.append(item)
    return result


def add_advance_decline(rows):
    """Independent daily breadth reference with a clearly bounded ADL origin.

    ADL starts from zero at the first row of each contiguous, same-source run;
    ADR is that day's advances divided by declines. A provisional row can be
    displayed but cannot serve as the starting state for a subsequent day.
    """
    result = []
    previous = identity = start = None
    cumulative = count = 0
    for row in rows:
        item = dict(row, adl=None, adr=None, adl_start=None, adl_samples=0, adl_gap_before=bool(result))
        try:
            current = date.fromisoformat(item['date'])
            closed = calendar(current.year)
            a, d = item['advance'], item['decline']
            expected, covered = item['expected'], item['covered']
            valid = (closed is not None and current.weekday() < 5
                     and not any(first <= item['date'] <= last for first, last in closed)
                     and item['status'] in ('closed', 'provisional')
                     and item.get('missing') == 0 and type(expected) is int and expected > 0
                     and type(covered) is int and expected == covered
                     and type(a) is int and type(d) is int and a >= 0 and d >= 0
                     and a + d > 0 and a + d <= covered
                     and bool(item.get('source')) and bool(item.get('universe')))
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            previous = identity = start = None
            cumulative = count = 0
            result.append(item)
            continue
        source = (item['source'], item['universe'])
        contiguous = previous is not None and _next_verified_trading_day(previous) == current and identity == source
        if not contiguous:
            cumulative, count, start = 0, 0, item['date']
        cumulative += a - d
        count += 1
        item.update(adl=cumulative, adr=a / d if d else None, adl_start=start,
                    adl_samples=count, adl_gap_before=bool(result) and not contiguous)
        if item['status'] == 'closed':
            previous, identity = current, source
        else:
            previous = identity = start = None
            cumulative = count = 0
        result.append(item)
    return result


def attach_historical_ad_reference(rows, historical):
    """Expose independently calculated same-day historical lines, never splice feeds."""
    references = {row['date']: row for row in add_advance_decline(historical)}
    result = []
    for row in rows:
        item = dict(row)
        item.pop('ad_history', None)
        reference = references.get(item['date'])
        if item.get('historical') and reference and reference.get('historical'):
            item.update({key: reference.get(key) for key in
                         ('adl', 'adr', 'adl_start', 'adl_samples', 'adl_gap_before')})
        if (item.get('status') == 'closed' and not item.get('historical') and reference
                and reference.get('historical') and reference.get('adl') is not None):
            item['ad_history'] = {key: reference.get(key) for key in
                                  ('adl', 'adr', 'adl_start', 'adl_samples', 'adl_gap_before', 'source', 'universe')}
        result.append(item)
    return result


def attach_historical_mcl_reference(rows, historical):
    """Attach same-date historical MCL without joining it to live-source EMAs."""
    calculated = {r['date']: r for r in add_standard_mcclellan(historical)}
    result = []
    for row in rows:
        item = dict(row)
        item.pop('mcl_history', None)
        item.pop('ma_history', None)
        reference = calculated.get(item['date'])
        if (item.get('status') == 'closed' and reference and reference.get('historical') and reference['mcl_standard'] is not None
                and (not item.get('historical') or item.get('mcl_standard') is None)):
            item['mcl_history'] = dict(date=reference['date'], value=reference['mcl_standard'],
                                       samples=reference['mcl_samples'], source=reference['source'],
                                       universe=reference['universe'], collected_at=reference.get('collected_at'))
        if item.get('status') == 'closed' and not item.get('historical') and reference and reference.get('historical') and reference.get('ma_breadth'):
            item['ma_history'] = reference['ma_breadth']
        result.append(item)
    return result


def is_a_share(code):
    return bool(re.fullmatch(r'(sh(?:60|68)\d{4}|sz(?:00|30)\d{4})', code))


def number(value):
    try:
        out = Decimal(str(value))
        if out.is_finite():
            return out
    except (InvalidOperation, ValueError):
        pass
    raise ValueError('广度数据包含无效数值')


def universe():
    """Sina supplies identifiers only; dated price/volume comes from Tencent."""
    def fetch_json(url):
        for attempt in range(2):
            try:
                return json.loads(get(url))
            except (OSError, TimeoutError, json.JSONDecodeError):
                if attempt:
                    raise
                time.sleep(.5)

    def count():
        return int(fetch_json(SINA + 'Market_Center.getHQNodeStockCount?node=hs_a'))

    total = count()
    if not 1000 <= total <= 20000:
        raise ValueError('全市场股票总数异常')

    def page(n):
        time.sleep(.05)
        args = dict(page=n, num=80, sort='symbol', asc=1, node='hs_a', symbol='', _s_r_a='page')
        expected = min(80, total - (n - 1) * 80)
        for attempt in range(3):
            # A short response can be cached by intermediaries; vary only the
            # retry URL while keeping page, ordering and stock universe fixed.
            request_args = {**args, '_': str(time.time_ns())} if attempt else args
            url = SINA + 'Market_Center.getHQNodeData?' + urlencode(request_args)
            rows = fetch_json(url)
            if not isinstance(rows, list):
                raise ValueError('全市场代码表分页缺失')
            # A valid JSON response can still omit an entire page during trading.
            # Retry only that page; the aggregate count and uniqueness gates below
            # remain mandatory and reject persistent or inconsistent responses.
            if len(rows) >= expected or attempt == 2:
                break
            time.sleep(.5)
        return rows

    with ThreadPoolExecutor(max_workers=2) as pool:
        pages = list(pool.map(page, range(1, (total + 79) // 80 + 1)))
    rows = [row for group in pages for row in group]
    codes = [r['symbol'] for r in rows]
    if len(rows) != total:
        raise ValueError(f'全市场代码表不完整：预计 {total} 条，分页返回 {len(rows)} 条，未生成大盘统计')
    if len(set(codes)) != total:
        raise ValueError(f'全市场代码表分页重复：{total} 条中仅 {len(set(codes))} 个不同代码，未生成大盘统计')
    final_total = count()
    if final_total != total:
        raise ValueError(f'全市场代码表采集期间总数变化：{total} → {final_total}，未生成大盘统计')
    return {r['symbol']: r for r in rows if is_a_share(r['symbol'])}


def parse_quotes(text, requested):
    result = {}
    for code, body in re.findall(r'v_(\w+)="([^"]*)"', text):
        if code not in requested:
            continue
        if code in result:
            raise ValueError('大盘报价返回重复股票')
        f = body.split('~')
        if len(f) < 38 or f[2] != code[2:]:
            continue
        try:
            stamp = datetime.strptime(f[30], '%Y%m%d%H%M%S').replace(tzinfo=CN)
            price, previous, raw_volume = (number(f[i]) for i in (3, 4, 6))
            if min(price, previous) <= 0 or raw_volume < 0:
                continue
            shares = raw_volume * (1 if code.startswith(('sh688', 'sh689')) else 100)
            amount = number(f[37]) * 10000
            # Tencent ordinary A shares use hands; STAR shares use shares.
            # Check the conversion against turnover and actual daily price range.
            if shares > 0:
                low, high = number(f[34]), number(f[33])
                if min(low, high) <= 0 or not low * Decimal('.75') <= amount / shares <= high * Decimal('1.25'):
                    continue
            result[code] = dict(code=code, price=str(price), previous_close=str(previous),
                                volume=int(shares), amount_yuan=str(amount), timestamp=stamp.isoformat(), raw_volume=f[6],
                                raw_volume_unit='shares' if code.startswith(('sh688','sh689')) else 'hands',
                                raw_turnover_wan=f[37], day_low=f[34], day_high=f[33])
        except (ValueError, InvalidOperation, IndexError):
            continue
    return result


def summarize(rows, expected, day, observed_at, suspended=()):
    """Group whole-stock daily volume by change vs the same day's previous close."""
    expected, suspended = set(expected), set(suspended)
    observed = datetime.fromisoformat(observed_at)
    if observed.tzinfo is None:
        raise ValueError('采集时间缺少时区')
    if not suspended <= expected:
        raise ValueError('停牌名单超出统计范围')
    groups = {k: dict(count=0, volume=0, amount=Decimal(0)) for k in ('advance', 'decline', 'flat')}
    amount_complete = True
    seen, stamps = set(), []
    for row in rows:
        code = row['code']
        if code not in expected or code in seen or code in suspended:
            raise ValueError('股票重复或统计范围不一致')
        seen.add(code)
        stamp = datetime.fromisoformat(row['timestamp'])
        if stamp.tzinfo is None or stamp.astimezone(CN).date().isoformat() != day or stamp > observed:
            raise ValueError('广度报价交易日期不一致')
        p, base, volume = number(row['price']), number(row['previous_close']), number(row['volume'])
        if min(p, base) <= 0 or volume < 0 or volume != int(volume):
            raise ValueError('广度价格或成交股数异常')
        if volume == 0:
            suspended.add(code)
            continue
        key = 'advance' if p > base else 'decline' if p < base else 'flat'
        groups[key]['count'] += 1
        groups[key]['volume'] += int(volume)
        if row.get('amount_yuan') is None:
            amount_complete = False
        else:
            try:
                amount = number(row['amount_yuan'])
                if amount <= 0:
                    amount_complete = False
                else:
                    groups[key]['amount'] += amount
            except ValueError:
                amount_complete = False
        stamps.append(stamp.astimezone(CN).isoformat())
    missing = sorted(expected - seen - suspended)
    a, d, flat = (groups[k] for k in ('advance', 'decline', 'flat'))
    active = a['count'] + d['count'] + flat['count']
    ready = not missing
    defined = ready and a['count'] > 0 and d['count'] > 0 and a['volume'] > 0 and d['volume'] > 0
    trin = (a['count'] * d['volume'] / (d['count'] * a['volume'])) if defined else None
    amount_defined = ready and amount_complete and a['count'] > 0 and d['count'] > 0 and a['amount'] > 0 and d['amount'] > 0
    trin_amount = float(a['count'] * d['amount'] / (d['count'] * a['amount'])) if amount_defined else None
    anchor = observed.astimezone(CN)
    finalized = ready and bool(stamps) and all(t[11:16] >= '15:00' for t in stamps) and (day < anchor.date().isoformat() or anchor.strftime('%H:%M') >= '15:15')
    return dict(date=day, trin=trin, advance=a['count'], decline=d['count'], flat=flat['count'],
                advance_volume=a['volume'], decline_volume=d['volume'], flat_volume=flat['volume'],
                trin_amount=trin_amount,
                advance_amount=float(a['amount']) if amount_complete else None,
                decline_amount=float(d['amount']) if amount_complete else None,
                advancing_amount_percent=float(100 * a['amount'] / (a['amount'] + d['amount'])) if amount_complete and a['amount'] + d['amount'] else None,
                advancing_percent=100 * a['count'] / active if active else None,
                advancing_volume_percent=100 * a['volume'] / (a['volume'] + d['volume']) if a['volume'] + d['volume'] else None,
                expected=len(expected), covered=len(expected) - len(missing), suspended=len(suspended),
                missing=len(missing), missing_codes=missing, status='closed' if finalized else 'provisional' if ready else 'incomplete',
                first_quote=min(stamps) if stamps else None, last_quote=max(stamps) if stamps else None,
                collected_at=observed_at, volume_unit='shares', universe='新浪沪深股票列表（含科创板；部分存托凭证可能不在列表中）',
                source='腾讯逐股报价；新浪全市场代码表',
                undefined_reason='' if defined else '缺失股票未补齐' if missing else '上涨或下跌组为空，TRIN无定义')


def collect():
    started = now_cn()
    anchor_raw = get('https://qt.gtimg.cn/q=sh000001', 'gb18030')
    m = re.search(r'v_sh000001="([^"]+)"', anchor_raw)
    if not m:
        raise ValueError('缺少有日期的市场报价，无法锚定交易日')
    anchor = datetime.strptime(m[1].split('~')[30], '%Y%m%d%H%M%S').replace(tzinfo=CN)
    if anchor > started or (started.date() - anchor.date()).days > 15:
        raise ValueError('市场报价日期异常，保留已有统计')
    day = anchor.date().isoformat()
    identifiers = universe()
    codes = sorted(identifiers)

    def batch(part):
        time.sleep(.1)
        for attempt in range(2):
            try:
                return parse_quotes(get('https://qt.gtimg.cn/q=' + ','.join(part), 'gb18030'), set(part))
            except Exception:
                if attempt:
                    raise
                time.sleep(.5)

    quotes = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for group in pool.map(batch, [codes[i:i + 160] for i in range(0, len(codes), 160)]):
            quotes.update(group)
        missing_codes = [c for c in codes if c not in quotes]
        for group in pool.map(batch, [missing_codes[i:i + 160] for i in range(0, len(missing_codes), 160)]):
            quotes.update(group)
    rows, suspended = [], []
    for code in codes:
        q, info = quotes.get(code), identifiers[code]
        # A prior-session price is never included as this session's volume.
        if q and q['timestamp'][:10] == day:
            if day == started.date().isoformat() and '09:30' <= started.strftime('%H:%M') <= '15:00' and (anchor - datetime.fromisoformat(q['timestamp'])).total_seconds() > 300:
                continue
            rows.append(q)
        elif q and number(info.get('volume', -1)) == 0 and number(info.get('open', -1)) == 0:
            suspended.append(code)
    result = summarize(rows, codes, day, now_cn().isoformat(), suspended)
    result.update(collection_started=started.isoformat(), anchor_timestamp=anchor.isoformat())
    raw = dict(date=day, codes=codes, suspended=suspended, quotes=rows, anchor=anchor.isoformat(), collected_at=result['collected_at'])
    return result, raw


def valid_closed_breadth(result, day, as_of):
    """A cached close is usable only if its counts and quote times agree."""
    if not isinstance(result, dict):
        return False
    counts = [result.get(k) for k in ('advance', 'decline', 'flat', 'suspended')]
    expected, covered = result.get('expected'), result.get('covered')
    if not (result.get('status') == 'closed' and result.get('date') == day
            and type(expected) is int and expected > 0 and type(covered) is int
            and covered == expected and result.get('missing') == 0
            and all(type(n) is int and n >= 0 for n in counts) and sum(counts) == covered):
        return False
    try:
        first, last, collected = [datetime.fromisoformat(result[k]) for k in
                                  ('first_quote', 'last_quote', 'collected_at')]
        if any(t.tzinfo is None or t.utcoffset() is None for t in (first, last, collected, as_of)):
            return False
        first, last, collected, as_of = (t.astimezone(CN) for t in (first, last, collected, as_of))
        return (first.date().isoformat() == day and last.date().isoformat() == day
                and first.strftime('%H:%M') >= '15:00' and first <= last <= collected <= as_of)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class Breadth:
    def __init__(self, store):
        self.store, self.lock = store, threading.Lock()
        self.running, self.error, self.last_attempt = False, '', 0.0
        self.ma_lock, self.ma_cached, self.ma_note = threading.Lock(), None, ''
        self.reference_cached = None
        self.reference_1030_cached = None
        self.ma_reference_dates = None

    def reference_close(self):
        from .ma_reference import load_close_reference
        now = now_cn()
        if self.reference_cached:
            return self.reference_cached if datetime.fromisoformat(self.reference_cached[0]['collected_at']) <= now else None
        if not MA_CLOSE_REFERENCE.exists():
            return None
        try:
            self.reference_cached = load_close_reference(MA_CLOSE_REFERENCE, as_of=now, summarize=summarize)
            return self.reference_cached
        except (OSError, KeyError, TypeError, ValueError, ArithmeticError):
            return None

    def reference_close_1030(self):
        from .ma_reference import load_close_reference
        now = now_cn()
        if self.reference_1030_cached:
            return self.reference_1030_cached if datetime.fromisoformat(self.reference_1030_cached[0]['collected_at']) <= now else None
        if not MA_CLOSE_REFERENCE_1030.exists():
            return None
        try:
            self.reference_1030_cached = load_close_reference(MA_CLOSE_REFERENCE_1030, as_of=now, summarize=summarize, expected_date='2026-10-30')
            return self.reference_1030_cached
        except (OSError, KeyError, TypeError, ValueError, ArithmeticError):
            return None

    def refresh(self, force=False):
        with self.lock:
            if self.running or (not force and time.monotonic() - self.last_attempt < BREADTH_INTERVAL_SECONDS):
                return
            self.running, self.last_attempt = True, time.monotonic()
        try:
            result, raw = collect()
            old = self.store.getcache(CODE, KIND, result['date'])
            # Never replace a complete daily observation with a failed/partial scan.
            if result['missing']:
                raise ValueError(f"{result['covered']}/{result['expected']}只股票日期和量价有效，缺{result['missing']}只；未生成TRIN柱")
            if old and valid_closed_breadth(old[0]['data'], result['date'], now_cn()) and result['status'] != 'closed':
                raise ValueError('新采样未达到已有收盘完整度，保留收盘统计')
            if result['status'] == 'closed' and not valid_closed_breadth(result, result['date'], now_cn()):
                raise ValueError('收盘数据的覆盖或时间异常，保留已有统计')
            records=[(CODE,kind,result['date'],json.dumps(data,ensure_ascii=False))
                     for kind,data in [('breadth_raw_v1',raw),(KIND,result)]]
            with self.store.lock,self.store.db:
                self.store.db.executemany('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',records)
            with self.ma_lock:
                self.ma_cached = None
            self.error = ''
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else '全市场数据获取失败：' + type(exc).__name__
        finally:
            with self.lock:
                self.running = False

    def ma_close_references(self):
        """Compute once per successful refresh; no extra network or database writes."""
        from .ma_reference import calculate, load_seed
        reference = self.reference_close()
        reference_1030 = self.reference_close_1030()
        reference_dates = tuple(ref[0]['date'] for ref in (reference, reference_1030) if ref)
        with self.ma_lock:
            if reference_dates != self.ma_reference_dates:
                self.ma_cached = None
                self.ma_reference_dates = reference_dates
            if self.ma_cached is None:
                try:
                    seed = load_seed(MA_SEED)
                    cached = self.store.getcache(CODE, 'breadth_raw_v1')
                    snapshots = []
                    bad_cache = False
                    for item in cached:
                        if item['day'] <= seed['end_date']:
                            continue
                        if item['data'].get('date') != item['day']:
                            bad_cache = True
                            break
                        snapshots.append(item['data'])
                    if reference and seed.get('version') == 1 and seed['end_date'] == '2026-10-28':
                        # Prefer a complete valid cached close; otherwise fill this
                        # one specific missing day from the separately dated sample.
                        fixed = reference[0]
                        cached_close = next((r for r in snapshots if r['date'] == fixed['date']), None)
                        if cached_close is None or not calculate(seed, [cached_close], _next_verified_trading_day, summarize, as_of=now_cn()):
                            snapshots = [r for r in snapshots if r['date'] != fixed['date']]
                            snapshots.append(fixed)
                            snapshots.sort(key=lambda r: r['date'])
                    if reference_1030 and reference and seed.get('version') == 1 and seed['end_date'] == '2026-10-28':
                        fixed = reference_1030[0]
                        cached_close = next((r for r in snapshots if r['date'] == fixed['date']), None)
                        prefix = [r for r in snapshots if r['date'] < fixed['date']]
                        checked = calculate(seed, prefix + ([cached_close] if cached_close else []), _next_verified_trading_day, summarize, as_of=now_cn())
                        if cached_close is None or not checked or checked[-1]['date'] != fixed['date']:
                            snapshots = [r for r in snapshots if r['date'] != fixed['date']]
                            snapshots.append(fixed)
                            snapshots.sort(key=lambda r: r['date'])
                    self.ma_cached = calculate(seed, snapshots, _next_verified_trading_day, summarize, as_of=now_cn())
                    self.ma_note = ''
                    if bad_cache:
                        self.ma_note = '历史样本日期不一致，均线宽度暂未更新'
                    elif snapshots and (not self.ma_cached or self.ma_cached[-1]['date'] != snapshots[-1]['date']):
                        latest = date.fromisoformat(self.ma_cached[-1]['date'] if self.ma_cached else seed['end_date'])
                        expected = _next_verified_trading_day(latest)
                        pending = next((r for r in snapshots if r['date'] > latest.isoformat()), None)
                        if expected and pending and pending['date'] > expected.isoformat():
                            self.ma_note = f'缺少 {expected.isoformat()} 的完整收盘样本，均线宽度暂未更新；缺失日期目前不会自动补齐'
                        else:
                            self.ma_note = '盘中或收盘样本校验未通过，均线宽度暂未更新'
                except (OSError, KeyError, TypeError, ValueError, ArithmeticError):
                    self.ma_cached = []
                    self.ma_note = '均线宽度基准或历史样本校验失败，未生成新结果'
            return {row['date']: row for row in self.ma_cached}

    def view(self):
        records = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else []
        as_of = now_cn()
        historical = [row for row in records if historical_available(row, as_of)]
        rows = {r['date']: r for r in historical}
        reference = self.reference_close()
        if reference and reference[1]['date'] not in rows:
            rows[reference[1]['date']] = reference[1]
        reference_1030 = self.reference_close_1030()
        if reference_1030 and reference_1030[1]['date'] not in rows:
            rows[reference_1030[1]['date']] = reference_1030[1]
        for item in self.store.getcache(CODE, KIND):
            result = item['data']
            # A complete live close wins; an incomplete scan cannot mask a checked historical day.
            valid_close = valid_closed_breadth(result, item['day'], now_cn())
            if item['day'] not in rows or valid_close:
                rows[item['day']] = result
        rows = add_standard_mcclellan([rows[day] for day in sorted(rows)])
        rows = add_advance_decline(attach_historical_mcl_reference(rows, historical))
        rows = attach_historical_ad_reference(rows, historical)
        ma_daily = self.ma_close_references()
        for row in rows:
            if row['date'] in ma_daily:
                row['ma_daily'] = ma_daily[row['date']]
        return dict(days=rows, running=self.running, error=self.error, interval_seconds=BREADTH_INTERVAL_SECONDS, universe='新浪沪深股票列表（含科创板；部分存托凭证可能不在列表中）',
                    ma_note=self.ma_note,
                    formula='TRIN = (上涨家数 × 下跌股成交量) ÷ (下跌家数 × 上涨股成交量)',
                    history_note='历史复核数据与每日采集分开标示；未取得的交易日不显示。')
