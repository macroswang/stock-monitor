"""市场机会 v2 数据层：市场温度、资金、人气、热点。

只读公开行情；每个数值都带来源、日期和完整性核对，取不到就留空并写入 warnings。
不参与自动交易、不写自选、不发通知。口径与契约见 docs/opportunity-v2-20261108/CONTRACT.md。
"""
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from .provider import CN, get, now_cn
from .index_technical import trading_day
from . import theme_discovery

LIMIT_UP_URL = 'https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool'
LIMIT_UP_SOURCE = '同花顺涨停池'
# The canonical Web host is WAF-limited under bursts; the identical-data host is tried first second.
KLINE_HOSTS = ('web.ifzq.gtimg.cn', 'ifzq.gtimg.cn')
SINA_KLINE_URL = 'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData'
INDEX_KLINE_SOURCE = '腾讯指数日线'
SINA_KLINE_SOURCE = '新浪日线'
STOCK_KLINE_SOURCE = '腾讯个股日线'
INDEXES = (('sh000001', '上证指数'), ('sz399001', '深证成指'), ('sz399006', '创业板指'))
LIMIT_UP_CODE, LIMIT_UP_KIND = 'limit-up', 'limit_up_pool_v1'
INDEX_LEVELS_KIND = 'index_daily_v1'
LEVELS_CODE, LEVELS_KIND = 'opportunity-levels', 'stock_daily_v1'
BREADTH_CODE, BREADTH_KIND = 'cn-ashare', 'breadth_day_v1'
INDUSTRY_CACHE, CONCEPT_CACHE, FLOW_KIND = 'eastmoney-industry', 'sina-concept', 'sector_flow_v1'
POOL_FIELDS = 'code,name,reason_type,high_days,high_days_value,is_again_limit,limit_up_type,order_amount'
NON_BUSINESS = re.compile('重仓|参股|解禁|ST|央企50|融资融券|整体上市|改革|持股|沪深300|次新|上证|深证|三板|举牌|增持|破净|送转|预盈|预增|低价股|高价股|资产注入|外资背景|地域|地区|股权|本月|B股|综合行业')


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('数值字段类型异常')
    if not math.isfinite(value):
        raise ValueError('数值字段无效')
    return float(value)


def _int(value):
    number = _num(value)
    if number != int(number):
        raise ValueError('整数字段异常')
    return int(number)


def expected_quote_day(now):
    from .sector_flow import expected_day
    return expected_day(now)


def previous_trading_day(day):
    current = date.fromisoformat(day)
    for _ in range(12):
        current -= timedelta(days=1)
        flag = trading_day(current)
        if flag is None:
            raise ValueError('交易日历不足，无法核对前一交易日')
        if flag:
            return current.isoformat()
    raise ValueError('未找到前一交易日')


def recent_trading_days(day, count=5):
    days, current = [], date.fromisoformat(day)
    while len(days) < count:
        flag = trading_day(current)
        if flag is None:
            raise ValueError('交易日历不足')
        if flag:
            days.append(current.isoformat())
        current -= timedelta(days=1)
        if (date.fromisoformat(day) - current).days > count * 3 + 20:
            raise ValueError('交易日历覆盖不足')
    return list(reversed(days))


def parse_limit_up_row(row, day):
    try:
        code = row['code']
        name = row['name']
        if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code):
            raise ValueError
        if not isinstance(name, str) or not name.strip() or len(name) > 20:
            raise ValueError
        raw_value, text = row.get('high_days_value'), row.get('high_days')
        if raw_value is None or text is None:
            # The source occasionally omits the board encoding for a confirmed limit-up.
            # It still counts in the pool totals, so keep the row with an explicit unknown board.
            if raw_value is not None or text is not None:
                raise ValueError
            boards = days = None
        else:
            value = _int(raw_value)
            if value < 0 or not isinstance(text, str) or not text:
                raise ValueError
            boards, days = value >> 16, value & 0xFFFF
            if text == '首板':
                if (boards, days) != (1, 1):
                    raise ValueError
            else:
                match = re.fullmatch(r'(\d+)天(\d+)板', text)
                if not match or int(match.group(1)) != days or int(match.group(2)) != boards:
                    raise ValueError
            if boards < 1 or days < boards or days > 60:
                raise ValueError
        # The quote for a turnover board either exists or the row is dropped;
        # the amount is a positive yuan figure when the source provides it.
        amount = row.get('order_amount')
        amount = None if amount is None else _num(amount)
        if amount is not None and amount < 0:
            raise ValueError
        flag = row.get('is_again_limit')
        if flag not in (0, 1, None):
            raise ValueError
        kind = row.get('limit_up_type')
        if kind is not None and (not isinstance(kind, str) or len(kind) > 12):
            raise ValueError
        return dict(code=('sh' if code[0] in '69' else 'sz') + code, raw_code=code, name=name.strip(),
                    reason=(row.get('reason_type') or '').strip(), boards=boards, days=days,
                    again=flag, limit_type=kind, order_amount=amount)
    except (KeyError, TypeError, ValueError):
        raise ValueError('涨停池字段或连板编码无法核对') from None


def _count_block(block):
    if not isinstance(block, dict) or not {'num', 'history_num', 'open_num', 'rate'} <= set(block):
        raise ValueError('涨停统计结构异常')
    num, attempt, opened = _int(block['num']), _int(block['history_num']), _int(block['open_num'])
    rate = _num(block['rate'])
    if num < 0 or opened < 0 or attempt != num + opened:
        raise ValueError('涨停统计分项无法核对')
    if attempt and abs(rate - num / attempt) > 1e-6:
        raise ValueError('封板率与分项不一致')
    return num, attempt, opened, rate


def split_counts(block):
    """The source reports today and yesterday together; both must reconcile."""
    if not isinstance(block, dict) or not {'today', 'yesterday'} <= set(block):
        raise ValueError('涨停统计结构异常')
    num, attempt, opened, rate = _count_block(block['today'])
    previous = _count_block(block['yesterday'])[0]
    return dict(today=num, yesterday=previous, attempt=attempt, open_num=opened,
                sealed_rate=rate if attempt else None)


def parse_limit_up_payload(payload, day):
    """One page of the pool; page identity and counts must agree."""
    data = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError('涨停池数据为空')
    if data.get('date') != day.replace('-', ''):
        raise ValueError('涨停池日期与行情日期不一致')
    if not isinstance(data.get('limit_up_count'), dict) or not isinstance(data.get('limit_down_count'), dict):
        raise ValueError('涨停池统计缺失')
    page = data.get('page')
    rows = data.get('info')
    if not isinstance(page, dict) or not isinstance(rows, list):
        raise ValueError('涨停池分页缺失')
    number, total, count, limit = (_int(page.get(key)) for key in ('page', 'total', 'count', 'limit'))
    if number < 1 or total < 0 or count < 0 or limit != 100 or number > max(count, 1):
        raise ValueError('涨停池分页异常')
    limit_up = split_counts(data['limit_up_count'])
    limit_down = split_counts(data['limit_down_count'])
    # Only the first page carries the full-day totals; later pages repeat them.
    if number == 1 and total != limit_up['today']:
        raise ValueError('涨停池总数与统计不一致')
    parsed = [parse_limit_up_row(row, day) for row in rows]
    if len({r['raw_code'] for r in parsed}) != len(parsed):
        raise ValueError('涨停池代码重复')
    return dict(date=day, page=number, pages=count, total=total, rows=parsed,
                limit_up=limit_up, limit_down=limit_down, source=LIMIT_UP_SOURCE,
                source_url='https://data.10jqka.com.cn/market/longhu/', captured_at=now_cn().isoformat())


def fetch_limit_up(day):
    pages, result, first = None, [], None
    for page in range(1, 21):
        params = dict(date=day.replace('-', ''), page=page, limit=100, filter='HS,GEM2STAR',
                      field=POOL_FIELDS, order_field='199112', order_type='0')
        payload = json.loads(get(LIMIT_UP_URL + '?' + urlencode(params)))
        current = parse_limit_up_payload(payload, day)
        if pages is None:
            pages, first = current['pages'], current
        elif current['pages'] != pages or current['total'] != first['total']:
            raise ValueError('涨停池翻页中分页数或总数变化')
        result.extend(current['rows'])
        if page >= pages:
            break
    if pages is None:
        raise ValueError('涨停池未取得分页')
    if len(result) != first['total'] or len({row['raw_code'] for row in result}) != len(result):
        raise ValueError('涨停池行数与总数不一致或代码重复')
    return dict(date=day, rows=result, limit_up=first['limit_up'], limit_down=first['limit_down'],
                total=first['total'], source=LIMIT_UP_SOURCE, source_url=first['source_url'],
                captured_at=now_cn().isoformat())


def limit_up_pool(store, day, now=None):
    """Dated pool; past sessions are immutable and cached, today is re-read while it changes."""
    now = now or now_cn()
    today = now.astimezone(CN).date().isoformat()
    cached = store.getcache(LIMIT_UP_CODE, LIMIT_UP_KIND, day) if store is not None else []
    if cached:
        saved = cached[0]['data']
        try:
            stamp = datetime.fromisoformat(saved['captured_at'])
            if saved.get('date') == day and day != today:
                return saved
            # The live pool changes through the session; only a post-close read may be reused.
            if (day == today and stamp.date().isoformat() == today
                    and stamp.strftime('%H:%M') >= '15:15' and now.strftime('%H:%M') >= '15:15'):
                return saved
        except (KeyError, TypeError, ValueError):
            pass
    pool = fetch_limit_up(day)
    if store is not None:
        store.cache(LIMIT_UP_CODE, LIMIT_UP_KIND, day, pool)
    return pool


def _pool_sealed(pool):
    return pool['limit_up']['sealed_rate']


def _ladder(pool):
    counts = {}
    for row in pool['rows']:
        if row['boards'] is not None and row['days'] == row['boards']:
            counts[row['boards']] = counts.get(row['boards'], 0) + 1
    return [dict(boards=boards, count=counts[boards]) for boards in sorted(counts, reverse=True)]


def _max_board(pool):
    known = [row for row in pool['rows'] if row['boards'] is not None]
    best = max(known, key=lambda r: (r['boards'] if r['days'] == r['boards'] else 0,
                                     r['order_amount'] or 0), default=None)
    if not best or best['days'] != best['boards']:
        return 0, None
    return best['boards'], best['name']


def reason_tokens(text):
    tokens = []
    for part in re.split(r'[+＋]', text or ''):
        token = part.strip().strip('“”"')
        token = re.sub(r'[（(].*?[)）]', '', token).strip()
        if not 2 <= len(token) <= 16 or theme_discovery.NOISE.search(token) or token.isdecimal():
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def quote_rows(quotes, day):
    """Only a same-session quote may describe today's move."""
    result = {}
    for code, row in (quotes or {}).items():
        try:
            stamp = row['timestamp']
            price, previous = float(row['price']), float(row['previous_close'])
            if not isinstance(stamp, str) or stamp[:10] != day:
                continue
            if min(price, previous) <= 0 or not math.isfinite(price) or not math.isfinite(previous):
                continue
            result[code] = dict(pct=(price / previous - 1) * 100, price=price, previous=previous,
                                low=float(row['day_low']) if row.get('day_low') is not None else None,
                                amount=float(row['amount_yuan']) if row.get('amount_yuan') is not None else None)
        except (KeyError, TypeError, ValueError):
            continue
    return result


def sentiment(store, day, quotes, now=None):
    """涨停/跌停/封板率/连板梯队/昨日涨停今日表现/近 5 日趋势。"""
    now = now or now_cn()
    days = recent_trading_days(day, 5)
    pools, warnings = {}, []
    with ThreadPoolExecutor(4) as worker:
        jobs = {d: worker.submit(limit_up_pool, store, d, now) for d in days}
        for d, job in jobs.items():
            try:
                pools[d] = job.result()
            except Exception:
                warnings.append(f'{d} 的涨停池未取得，人气趋势缺少该日。')
    if day not in pools:
        raise ValueError('当日涨停池未取得')
    today, yesterday = pools[day], pools.get(days[-2]) if len(days) > 1 else None
    limit_up, limit_down = today['limit_up'], today['limit_down']
    ladder = _ladder(today)
    max_board, max_board_name = _max_board(today)
    total_rows = len(today['rows'])
    consecutive = sum(item['count'] for item in ladder)
    stats = quote_rows(quotes, day)
    performance = None
    if yesterday and stats:
        codes = [row['code'] for row in yesterday['rows']]
        moves = [stats[c]['pct'] for c in codes if c in stats]
        boosted = {row['code'] for row in today['rows']}
        if len(moves) >= max(3, math.ceil(.8 * len(codes))):
            performance = dict(count=len(codes), checked=len(moves),
                               advance=sum(1 for move in moves if move > 0),
                               avg_percent=round(sum(moves) / len(moves), 2),
                               promote=sum(1 for c in codes if c in boosted),
                               promote_rate=round(sum(1 for c in codes if c in boosted) / len(codes), 3))
    counts = {}
    names = {}
    for row in today['rows']:
        names[row['code']] = row['name']
        for token in reason_tokens(row['reason']):
            entry = counts.setdefault(token, {'count': 0, 'codes': []})
            entry['count'] += 1
            if row['code'] not in entry['codes']:
                entry['codes'].append(row['code'])
    hot_reasons = sorted((dict(name=name, count=item['count'],
                               stocks=[dict(code=c, name=names[c]) for c in item['codes']])
                          for name, item in counts.items()), key=lambda r: (-r['count'], r['name']))[:8]
    trend = []
    unknown_boards = 0
    for d in days:
        pool = pools.get(d)
        if not pool:
            continue
        unknown_boards += sum(1 for row in pool['rows'] if row['boards'] is None)
        board, _ = _max_board(pool)
        trend.append(dict(date=d, limit_up=pool['limit_up']['today'], limit_down=pool['limit_down']['today'],
                          sealed_rate=pool['limit_up']['sealed_rate'], max_board=board))
    if unknown_boards:
        warnings.append(f'近 {len(days)} 个交易日涨停池有 {unknown_boards} 只个股连板数据缺失（来源未提供），连板梯队只统计已知部分。')
    now_limits = limit_up['today']
    yesterday_limits = yesterday['limit_up']['today'] if yesterday else None
    if yesterday_limits is not None and now_limits >= yesterday_limits * 1.2 and (_pool_sealed(today) or 0) >= 0.65:
        temperature = '升温'
    elif yesterday_limits is not None and now_limits <= yesterday_limits * 0.7 and limit_down['today'] >= 8:
        temperature = '退潮'
    elif max_board >= 5 or now_limits >= 80:
        temperature = '高位'
    else:
        temperature = '分化'
    by_code = {row['code']: row for row in today['rows']}
    return dict(limit_up=limit_up, limit_down=limit_down, max_board=max_board, max_board_name=max_board_name,
                ladder=ladder, non_consecutive=max(0, total_rows - consecutive),
                yesterday_performance=performance, hot_reasons=hot_reasons, trend=trend,
                temperature=temperature, by_code=by_code, warnings=warnings,
                _days=pools)  # internal: dated pools reused by the speculation radar


def _parse_index_rows(payload, code):
    node = payload.get('data', {}).get(code)
    rows = node.get('day') if isinstance(node, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError('指数日线数据为空')
    output, previous = [], None
    for raw in rows:
        try:
            if not isinstance(raw, list) or len(raw) < 6:
                raise ValueError
            day = date.fromisoformat(raw[0])
            if day.isoformat() != raw[0] or (previous and day <= previous):
                raise ValueError
            previous = day
            if trading_day(day) is not True:
                raise ValueError
            values = [float(x) for x in raw[1:6]]
            if not all(math.isfinite(x) for x in values):
                raise ValueError
            op, close, high, low, volume = values
            if min(op, close, high, low) <= 0 or volume < 0 or low > min(op, close) or high < max(op, close) or low > high:
                raise ValueError
            output.append(dict(date=day.isoformat(), open=op, close=close, high=high, low=low, volume=volume * 100))
        except (TypeError, ValueError, OverflowError):
            raise ValueError('指数日线日期或价格异常') from None
    if len(output) < 25:
        raise ValueError('指数日线不足 25 个交易日')
    return output


def _tencent_daily(code, count, parser):
    errors = []
    for host in KLINE_HOSTS:
        url = f'https://{host}/appstock/app/fqkline/get?' + urlencode({'param': f'{code},day,,,{count},'})
        try:
            return parser(json.loads(get(url)), code)
        except Exception as exc:
            errors.append(type(exc).__name__)
    raise ValueError('腾讯日线未取得（' + '/'.join(errors) + '）')


def fetch_index_daily(code, count=60):
    return _tencent_daily(code, count, _parse_index_rows)


def parse_sina_daily(payload, label='日线'):
    """Same bar checks as the Tencent path, applied to {"day","open","high","low","close","volume"} rows."""
    if not isinstance(payload, list) or not payload:
        raise ValueError(f'新浪{label}数据为空')
    output, previous = [], None
    for row in payload:
        try:
            if not isinstance(row, dict) or not {'day', 'open', 'high', 'low', 'close', 'volume'} <= set(row):
                raise ValueError
            day = date.fromisoformat(row['day'])
            if day.isoformat() != row['day'] or (previous and day <= previous):
                raise ValueError
            previous = day
            if trading_day(day) is not True:
                raise ValueError
            op, close, high, low, volume = (float(row[key]) for key in ('open', 'close', 'high', 'low', 'volume'))
            if not all(math.isfinite(value) for value in (op, close, high, low, volume)):
                raise ValueError
            if min(op, close, high, low) <= 0 or volume < 0 or low > min(op, close) or high < max(op, close) or low > high:
                raise ValueError
            output.append(dict(date=day.isoformat(), open=op, close=close, high=high, low=low, volume=volume))
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError(f'新浪{label}日期或价格异常') from None
    return output


def fetch_sina_daily(code, count=60):
    url = SINA_KLINE_URL + '?' + urlencode({'symbol': code, 'scale': 240, 'ma': 'no', 'datalen': count})
    return parse_sina_daily(json.loads(get(url)), '指数' if code in dict(INDEXES) else '个股')


def index_daily(store, code, day, now):
    """Index bars only change once a session; cache per quote day to limit third-party load."""
    saved = store.getcache(code, INDEX_LEVELS_KIND, day) if store is not None else []
    if saved:
        payload = saved[0]['data']
        if payload.get('date') == day and payload.get('rows') and _cache_valid(day, now, payload.get('cached_at')):
            return payload['rows'], payload.get('source') or INDEX_KLINE_SOURCE
    try:
        rows, source = fetch_index_daily(code), INDEX_KLINE_SOURCE
    except Exception:
        rows, source = fetch_sina_daily(code), SINA_KLINE_SOURCE
    if store is not None:
        store.cache(code, INDEX_LEVELS_KIND, day, dict(date=day, rows=rows, source=source,
                                                      cached_at=now_cn().isoformat()))
    return rows, source


def index_quotes(store, day):
    result = {}
    for code, _ in INDEXES:
        rows = store.getcache(code, 'market_quote') if store is not None else []
        if not rows:
            continue
        quote = rows[-1]['data']
        try:
            stamp = quote['timestamp']
            price, previous = float(quote['price']), float(quote['previous_close'])
            if not isinstance(stamp, str) or stamp[:10] != day or min(price, previous) <= 0:
                continue
            result[code] = dict(price=price, previous=previous, stamp=stamp,
                                percent=(price / previous - 1) * 100)
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _mean(values):
    return sum(values) / len(values) if values else None


def index_trends(store, day, now, closed):
    """MA5/10/20 and 20-day low/high from completed index bars; live quote when available."""
    live = index_quotes(store, day)
    today = now.astimezone(CN).date().isoformat()
    output = []
    for code, name in INDEXES:
        rows, source = index_daily(store, code, day, now)
        complete = closed or day < today
        bars = [row for row in rows if row['date'] <= day] if complete else [row for row in rows if row['date'] < day]
        target = day if complete else previous_trading_day(day)
        if not bars:
            raise ValueError(f'{name}日线为空')
        if bars[-1]['date'] != target and not (complete and bars[-1]['date'] == previous_trading_day(day)):
            raise ValueError(f'{name}日线未更新到最近已结束交易日')
        closes = [row['close'] for row in bars]
        quote = live.get(code)
        price = quote['price'] if quote else closes[-1]
        percent = quote['percent'] if quote else ((closes[-1] / closes[-2] - 1) * 100 if len(closes) > 1 else None)
        ma5, ma10, ma20 = (_mean(closes[-n:]) if len(closes) >= n else None for n in (5, 10, 20))
        recent = bars[-20:]
        high20, low20 = max(row['high'] for row in recent), min(row['low'] for row in recent)
        # Intraday volume is incomplete; do not publish a ratio that reads as full-day activity.
        ratio = None
        volume = bars[-1]['volume']
        prior = [row['volume'] for row in bars[-6:-1]]
        if complete and len(prior) == 5 and _mean(prior):
            ratio = volume / _mean(prior)
        # Independent quote close vs the bar series (also protects the Sina fallback path).
        last_bar = bars[-1]
        if complete and quote and last_bar['date'] == day and abs(last_bar['close'] - price) > max(.02, price * .001):
            raise ValueError(f'{name}日线收盘与报价不一致：{last_bar["close"]} vs {price}')
        support = ma20 if ma20 is not None and price >= ma20 else low20
        resistance = ma5 if ma5 is not None and price < ma5 else high20
        previous_close = quote['previous'] if quote else (closes[-2] if len(closes) > 1 else closes[-1])
        output.append(dict(code=code, name=name, source=source, price=round(price, 2),
                           change=round(price - previous_close, 2),
                           percent=None if percent is None else round(percent, 2),
                           ma5=_round(ma5), ma10=_round(ma10), ma20=_round(ma20),
                           above_ma5=bool(ma5 is not None and price >= ma5),
                           above_ma20=bool(ma20 is not None and price >= ma20),
                           high20=round(high20, 2), low20=round(low20, 2), volume=volume,
                           volume_ratio=None if ratio is None else round(ratio, 2),
                           support=round(support, 2), resistance=round(resistance, 2),
                           stamp=quote['stamp'] if quote else bars[-1]['date'] + 'T15:00:00+08:00'))
    return output


def _round(value, digits=2):
    return None if value is None else round(value, digits)


def _breadth_amount(summary):
    advance, decline = summary.get('advance_amount'), summary.get('decline_amount')
    if not isinstance(advance, (int, float)) or not isinstance(decline, (int, float)):
        return None
    if not math.isfinite(advance) or not math.isfinite(decline) or min(advance, decline) < 0:
        return None
    amount = advance + decline
    return amount if amount > 0 else None


def breadth_metrics(store, day, closed):
    rows = store.getcache(BREADTH_CODE, BREADTH_KIND, day) if store is not None else []
    if not rows:
        raise ValueError('当日全市场广度未取得')
    summary = rows[0]['data']
    if summary.get('date') != day or summary.get('status') not in ('closed', 'provisional'):
        raise ValueError('当日全市场广度不完整或日期不一致')
    counts = [summary.get(key) for key in ('advance', 'decline', 'flat')]
    if not all(type(value) is int and value >= 0 for value in counts):
        raise ValueError('广度涨跌家数字段异常')
    active = sum(counts)
    if not active:
        raise ValueError('广度有成交家数为零')
    amount = _breadth_amount(summary)
    history = []
    for previous in recent_trading_days(previous_trading_day(day), 5):
        saved = store.getcache(BREADTH_CODE, BREADTH_KIND, previous)
        if not saved:
            continue
        row = saved[0]['data']
        if row.get('date') != previous or row.get('status') not in ('closed',):
            continue
        value = _breadth_amount(row)
        if value is None:
            continue
        history.append(value)
    average = _mean(history)
    # A partial session amount must never be compared with complete-day averages.
    ratio = amount / average if closed and amount and average and len(history) >= 3 else None
    return dict(date=day, status=summary['status'], advance=counts[0], decline=counts[1], flat=counts[2],
                active=active, advancing_percent=round(100 * counts[0] / active, 2),
                trin=summary.get('trin_amount') if summary.get('trin_amount') is not None else summary.get('trin'),
                trin_volume=summary.get('trin'), amount_yuan=amount,
                amount_5d_avg=None if average is None else round(average, 0),
                amount_ratio=None if ratio is None else round(ratio, 3), days_used=len(history))


def market(store, day, now, closed):
    warnings = []
    try:
        trends = index_trends(store, day, now, closed)
    except Exception as exc:
        trends = []
        warnings.append('指数日线未取得：' + _reason(exc))
    if len(trends) < len(INDEXES) and trends:
        warnings.append('部分指数日线未取得，市场温度只使用已核对指数。')
    if any(row.get('source') == SINA_KLINE_SOURCE for row in trends):
        warnings.append('腾讯指数日线暂未取得，已使用新浪日线并用同日报价收盘交叉核对。')
    try:
        breadth = breadth_metrics(store, day, closed)
    except Exception as exc:
        breadth = None
        warnings.append('全市场广度未取得：' + _reason(exc))
    if not trends and not breadth:
        raise ValueError('指数与广度都未取得，市场温度无法生成')
    signals = []
    shanghai = next((row for row in trends if row['code'] == 'sh000001'), None)
    if shanghai is not None and shanghai['ma5'] is not None:
        relation = '高于' if shanghai['above_ma5'] else '低于'
        signals.append(f"上证收 {shanghai['price']}，{relation} 5 日线 {shanghai['ma5']}。")
    if shanghai is not None and shanghai['ma20'] is not None:
        relation = '高于' if shanghai['above_ma20'] else '低于'
        signals.append(f"上证 {relation} 20 日线 {shanghai['ma20']}（区间 {shanghai['low20']}–{shanghai['high20']}）。")
    if breadth:
        signals.append(f"上涨 {breadth['advance']} 家、下跌 {breadth['decline']} 家，上涨占比 {breadth['advancing_percent']}%。")
        if breadth['amount_ratio'] is not None:
            tone = '放量' if breadth['amount_ratio'] >= 1.1 else '缩量' if breadth['amount_ratio'] < .85 else '量能持平'
            signals.append(f"两市成交额 {breadth['amount_yuan'] / 1e8:.0f} 亿元，为近 {breadth['days_used']} 个采集日均值的 {breadth['amount_ratio'] * 100:.0f}%，{tone}。")
        if breadth['trin'] is not None:
            signals.append(f"成交额口径 TRIN {breadth['trin']:.3f}。")
    return dict(indices=trends, breadth=breadth, signals=signals), warnings


def _valid_flow_snapshot(data, day, allowed_sources):
    if not isinstance(data, dict):
        return None
    if data.get('date') != day or data.get('source') not in allowed_sources:
        return None
    sectors = data.get('sectors')
    if not isinstance(sectors, list) or not sectors or not isinstance(data.get('measure'), str):
        return None
    output = []
    for row in sectors:
        try:
            code, name = row['code'], row['name']
            energy, change = float(row['net_yuan']), float(row['change_percent'])
            if not isinstance(code, str) or not isinstance(name, str) or not name:
                return None
            if not math.isfinite(energy) or not math.isfinite(change):
                return None
            output.append(dict(code=code, name=name, net_yuan=energy, change_percent=change))
        except (KeyError, TypeError, ValueError):
            return None
    return dict(date=day, source=data['source'], measure=data['measure'], sectors=output,
                quote_time=data.get('quote_time'), date_inferred=bool(data.get('date_inferred')))


def _history_sums(store, code, cutoff, allowed_sources):
    rows = store.getcache(code, FLOW_KIND) if store is not None else []
    dates = []
    for item in rows:
        data = item['data']
        try:
            stamp = data['date']
            if not isinstance(stamp, str) or stamp > cutoff or stamp in dates:
                continue
            snapshot = _valid_flow_snapshot(data, stamp, allowed_sources)
            if not snapshot:
                continue
            dates.append(stamp)
        except (KeyError, TypeError, ValueError):
            continue
    dates = sorted(dates)[-5:]
    totals = {}
    for stamp in dates:
        saved = next(item['data'] for item in rows if item['data'].get('date') == stamp)
        snapshot = _valid_flow_snapshot(saved, stamp, allowed_sources)
        for row in snapshot['sectors']:
            entry = totals.setdefault(row['code'], dict(name=row['name'], net=0.0, days=0))
            entry['net'] += row['net_yuan']
            entry['days'] += 1
    return totals, len(dates)


def capital(store, day, industry, concept, closed=False):
    warnings = []
    cutoff = day if closed else previous_trading_day(day)
    from .sector_flow import CONCEPT_SOURCE as CONCEPT_FLOW_SOURCE
    industry_allowed = {'新浪行业资金流', '东方财富行业板块资金流'}
    concept_allowed = {'新浪概念资金流', CONCEPT_FLOW_SOURCE}
    industry_snapshot = _valid_flow_snapshot(industry, day, industry_allowed)
    concept_snapshot = _valid_flow_snapshot(concept, day, concept_allowed)
    if not industry_snapshot:
        warnings.append('行业资金快照未通过日期/来源核对，资金卡暂缺行业部分。')
    if not concept_snapshot:
        warnings.append('概念资金快照未通过日期/来源核对，资金卡暂缺概念部分。')
    by_code = {}
    days_used = 0
    for code, snapshot, fallback in ((INDUSTRY_CACHE, industry_snapshot, industry_allowed),
                                     (CONCEPT_CACHE, concept_snapshot, concept_allowed)):
        # The 5-day sum only adds snapshots from the same source and measure as today's card.
        allowed = {snapshot['source']} if snapshot else fallback
        totals, used = _history_sums(store, code, cutoff, allowed)
        days_used = max(days_used, used)
        if snapshot:
            for row in snapshot['sectors']:
                if row['code'] in totals:
                    days = totals[row['code']]['days']
                    by_code[row['code']] = dict(net_5d=round(totals[row['code']]['net'], 2) if days >= 3 else None,
                                                days=days, source=snapshot['source'], measure=snapshot['measure'])
    def block(snapshot, label):
        if not snapshot:
            return None
        ranked = sorted(snapshot['sectors'], key=lambda row: row['net_yuan'], reverse=True)
        inflow = [dict(code=row['code'], name=row['name'], net_yuan=row['net_yuan'], change_percent=row['change_percent'])
                  for row in ranked if row['net_yuan'] > 0][:5]
        outflow = [dict(code=row['code'], name=row['name'], net_yuan=row['net_yuan'], change_percent=row['change_percent'])
                   for row in reversed(ranked) if row['net_yuan'] < 0][:5]
        return dict(label=label, measure=snapshot['measure'], date=day, source=snapshot['source'],
                    quote_time=snapshot.get('quote_time'), date_inferred=snapshot.get('date_inferred'),
                    inflow=inflow, outflow=outflow)
    industry_block, concept_block = block(industry_snapshot, '行业'), block(concept_snapshot, '概念')
    persistent = []
    for snapshot, kind in ((industry_snapshot, '行业'), (concept_snapshot, '概念')):
        if not snapshot:
            continue
        for row in snapshot['sectors']:
            saved = by_code.get(row['code'])
            if not saved or saved['net_5d'] is None or saved['net_5d'] <= 0 or row['net_yuan'] <= 0 or saved['days'] < 3:
                continue
            if NON_BUSINESS.search(row['name']):
                continue
            persistent.append(dict(code=row['code'], name=row['name'], sector_kind=kind,
                                   net_yuan=row['net_yuan'], net_5d=saved['net_5d'], days=saved['days'],
                                   change_percent=row['change_percent']))
    persistent.sort(key=lambda row: row['net_5d'], reverse=True)
    if days_used < 3:
        warnings.append(f'本机资金历史只有 {days_used} 个已收盘采集日，近 5 日累计不展示（需至少 3 个）。')
    if not closed:
        warnings.append('盘中不把未完成的当日资金计入近 5 日累计，只用已收盘快照。')
    if industry_snapshot and '买卖方向' not in industry_snapshot['measure']:
        warnings.append('行业资金口径为来源提供值，5 日累计只在同来源同口径下相加。')
    return dict(industry=industry_block, concept=concept_block, persistent=persistent[:8],
                history_days=days_used, by_code=by_code), warnings


def parse_stock_rows(payload, code):
    node = payload.get('data', {}).get(code)
    rows = node.get('day') if isinstance(node, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError('个股日线数据为空')
    output, previous = [], None
    for raw in rows:
        try:
            if not isinstance(raw, list) or len(raw) < 6:
                raise ValueError
            day = date.fromisoformat(raw[0])
            if day.isoformat() != raw[0] or (previous and day <= previous):
                raise ValueError
            previous = day
            values = [float(x) for x in raw[1:6]]
            if not all(math.isfinite(x) for x in values):
                raise ValueError
            op, close, high, low, volume = values
            if min(op, close, high, low) <= 0 or volume < 0 or low > min(op, close) or high < max(op, close) or low > high:
                raise ValueError
            output.append(dict(date=day.isoformat(), open=op, close=close, high=high, low=low, volume=volume))
        except (TypeError, ValueError, OverflowError):
            raise ValueError('个股日线日期或价格异常') from None
    return output


def fetch_stock_daily(code, count=40):
    return _tencent_daily(code, count, parse_stock_rows)


def _cache_valid(day, now, cached_at):
    try:
        stamp = datetime.fromisoformat(cached_at)
    except (TypeError, ValueError):
        return False
    today = now.astimezone(CN).date().isoformat()
    if day < today:
        return True
    if stamp.astimezone(CN).date().isoformat() != today:
        return False
    return not (now.strftime('%H:%M') >= '15:15' and stamp.strftime('%H:%M') < '15:15')


def stock_daily(store, codes, day, now=None):
    """Completed daily bars for candidate levels; cached per code/day, refreshed once after close."""
    now = now or now_cn()
    result, failed = {}, []
    pending = []
    for code in codes:
        saved = store.getcache(code, LEVELS_KIND, day) if store is not None else []
        if saved:
            payload = saved[0]['data']
            if payload.get('date') == day and payload.get('rows') and _cache_valid(day, now, payload.get('cached_at')):
                result[code] = payload['rows']
                continue
        pending.append(code)
    def work(code):
        for attempt in range(2):
            try:
                try:
                    rows, source = fetch_stock_daily(code), STOCK_KLINE_SOURCE
                except Exception:
                    rows, source = fetch_sina_daily(code), SINA_KLINE_SOURCE
                if store is not None:
                    store.cache(code, LEVELS_KIND, day, dict(date=day, rows=rows, source=source,
                                                             cached_at=now_cn().isoformat()))
                return code, rows
            except Exception:
                if attempt:
                    raise
                time.sleep(1.2 + 0.3 * (len(result) % 3))
    with ThreadPoolExecutor(3) as worker:
        jobs = []
        for index, code in enumerate(pending):
            jobs.append(worker.submit(work, code))
            if index % 3 == 2:
                time.sleep(.3)
        for job in jobs:
            try:
                code, rows = job.result()
                result[code] = rows
            except Exception:
                failed.append(code)
    return result, failed


def hotspots(feeds, senti):
    seen, rows = set(), []
    for item in feeds or []:
        try:
            stamp, title, url = item['time'], item['title'], item['url']
            if not isinstance(stamp, str) or not isinstance(title, str) or not isinstance(url, str):
                continue
            # The two Sina feeds can deliver the same article; one row per URL.
            if url in seen:
                continue
            seen.add(url)
            rows.append(dict(time=stamp, title=title, url=url, region=item.get('region'), match=None))
        except (KeyError, TypeError):
            continue
    rows.sort(key=lambda row: row['time'], reverse=True)
    reasons = senti['hot_reasons'] if senti else []
    return dict(news=rows[:12], reasons=reasons[:8])


def name_universe(store, day, now=None):
    """All A-share code→name once per day; name-family scans need the whole list."""
    now = now or now_cn()
    saved = store.getcache('name-universe', 'name_universe_v1', day) if store is not None else []
    if saved and saved[0]['data'].get('date') == day:
        return saved[0]['data'].get('names') or {}
    from .breadth import universe as fetch_universe
    rows = fetch_universe()
    names = {}
    for code, row in rows.items():
        name = row.get('name') if isinstance(row, dict) else None
        if isinstance(name, str) and name.strip():
            names[code] = name.strip()
    if store is not None and len(names) >= 4000:
        store.cache('name-universe', 'name_universe_v1', day,
                    dict(date=day, names=names, cached_at=now.isoformat()))
    return names


def build(store, summary, quotes, industry, concept, feeds, now):
    """Never raise: unavailable blocks stay None and count as explicit warnings."""
    if not isinstance(summary, dict) or not summary.get('date'):
        raise ValueError('市场快照缺失，无法生成研判')
    day, now = summary['date'], now or now_cn()
    closed = summary.get('status') == 'closed'
    warnings = []
    try:
        market_block, market_warnings = market(store, day, now, closed)
    except Exception as exc:
        market_block = None
        market_warnings = ['市场温度未取得：' + _reason(exc)]
    warnings.extend(market_warnings)
    try:
        capital_block, capital_warnings = capital(store, day, industry, concept, closed)
    except Exception as exc:
        capital_block = None
        capital_warnings = ['资金数据未取得：' + _reason(exc)]
    warnings.extend(capital_warnings)
    try:
        senti = sentiment(store, day, quotes, now)
        warnings.extend(senti.pop('warnings', []))
    except Exception as exc:
        senti = None
        warnings.append('人气数据未取得：' + _reason(exc))
    return dict(market=market_block, capital=capital_block, sentiment=senti,
                hotspots=hotspots(feeds, senti), warnings=warnings)


def _reason(exc):
    return str(exc) if isinstance(exc, (ValueError, KeyError)) else '数据源异常：' + type(exc).__name__
