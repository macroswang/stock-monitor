"""股票池：按入选基准价持续跟踪研判候选，并做分组与胜率复盘。

只在本机记录与展示，不自动下单、不写自选、不参与交易。三类来源：
- 建仓清单：本期 top_picks（含已涨停/高于追高上限，作为可复盘样本）；
- 方向候选：每个方向的候选股（含“条件未达”的方向，用于扩大样本）；
- 炒作雷达：事件/题材、名称辈、生肖玄学的代表股。

每条记录保留首次入选日的基准价（added_price），之后用最新可用行情计算自入选涨跌幅，
并按来源/板块类型/雷达类型分组，支持按入选时间段筛选与胜率统计。所有统计都注明样本数。
"""
import json
import re
import statistics
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from .provider import CN, get, now_cn, symbol
from .breadth import parse_quotes
from .paper_session import calendar

QUOTE_URL = 'https://qt.gtimg.cn/q='
POLL_SECONDS = 8
ARCHIVE_DAYS = 30
WINDOWS = (1, 3, 5)
HOLDING_BUCKETS = (('0', '今日'), ('1', '1日'), ('2', '2日'), ('3-5', '3–5日'), ('6-10', '6–10日'), ('10+', '10日以上'))
BENCHMARK_CODE = 'sh000001'
BENCHMARK_NAME = '上证指数'
EPISODE_LIMIT = 100
BACKTEST_LIMIT = 200
TAG_LIMIT = 4
THEME_CATEGORIES = ('题材', '名称辈', '生肖玄学')
TAG_BUCKETS = ('concept', 'theme', 'event', 'other')
FUND_FLOW_URL = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
FUND_FLOW_FIELDS = 'f12,f13,f14,f62,f184'
FUND_FLOW_BATCH = 80
FUND_FLOW_SECONDS = 30
DRIVER_SHORT_MESSAGE_LIMIT = 26
DRIVER_SHORT_RADAR_LIMIT = 24
DRIVER_SHORT_FALLBACK_LIMIT = 20
_MESSAGE_DRIVER_RE = re.compile(r'消息面[：:]?\s*[「『“"]([^」』”"]+)[」』”"]')
_SHORT_DRIVER_RULES = (
    ('板块上涨且资金净流入', '板块上涨、资金净流入'),
    ('只观察，不追高', '只观察不追高'),
    ('回踩低吸', '回踩低吸'),
    ('涨停待回踩', '涨停待回踩'),
    ('加速/高潮', '加速期'),
    ('发酵', '题材发酵'),
)

ALERT_KINDS = {'已进入买区': ('buy_zone', '进入买区'), '已跌破防守位': ('stop_break', '跌破防守位')}


def _is_archived(value):
    try:
        return int(value or 0) == 1
    except (TypeError, ValueError):
        return False


def _bucket(days):
    if days <= 0:
        return '0'
    if days == 1:
        return '1'
    if days == 2:
        return '2'
    if days <= 5:
        return '3-5'
    if days <= 10:
        return '6-10'
    return '10+'


def _weekday_dates(start, end):
    rows = []
    cursor = start + timedelta(days=1)
    while cursor <= end:
        if cursor.weekday() < 5:
            rows.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return rows
MARKED = ('已买入', '已退出', '忽略')
AUTO_STATES = ('可建仓', '涨停待回踩', '高于追高上限', '条件未达', '题材观察', '观察')
STATES = AUTO_STATES + MARKED
CATEGORY_ORDER = ('行业', '概念', '题材', '事件', '名称辈', '生肖玄学', '手动', '其他')
STATE_ORDER = {state: index for index, state in enumerate(AUTO_STATES + MARKED)}

_GROUP_MAP = {
    '行业': '行业',
    '概念': '概念',
    '补充题材': '题材',
    '题材': '题材',
    '事件/题材': '事件',
    '事件': '事件',
    '名称类': '名称辈',
    '生肖/玄学': '生肖玄学',
    '生肖玄学': '生肖玄学',
}


def trading(now):
    clock = now.strftime('%H:%M:%S')
    return now.weekday() < 5 and ('09:30:00' <= clock <= '11:31:00' or '13:00:00' <= clock <= '15:00:00')


def _float(value):
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def _now():
    return now_cn().isoformat()


def _trading_day(now):
    """Most recent exchange session at/before now; holiday/weekend aware when a calendar exists."""
    day = now.date()
    for _ in range(15):
        if day.weekday() < 5:
            closed = calendar(day.year)
            if closed is None or not any(first <= day.isoformat() <= last for first, last in closed):
                return day.isoformat()
        day -= timedelta(days=1)
    return day.isoformat()


def _tag_bucket(category):
    """Map a pool category to the terminal-table tag column it should surface in."""
    if category == '概念':
        return 'concept'
    if category in THEME_CATEGORIES:
        return 'theme'
    if category == '事件':
        return 'event'
    return 'other'


def _secid(code):
    """Eastmoney secid: Shanghai -> 1.xxxxxx, Shenzhen -> 0.xxxxxx."""
    code = str(code or '')
    if code.startswith('sh'):
        return '1.' + code[2:]
    if code.startswith('sz'):
        return '0.' + code[2:]
    return None


def _fund_flow_url(secids):
    return (FUND_FLOW_URL + '?fltt=2&secids=' + ','.join(secids)
            + '&fields=' + FUND_FLOW_FIELDS)


def _parse_fund_flow_payload(payload, captured_at):
    """Parse one ulist.np fund-flow response into {code: {net, net_yi, rate, time}}.

    f62 主力净流入(元), f184 主力净流入率(%). Rows without a finite net inflow are skipped.
    """
    flows = {}
    data = payload.get('data') if isinstance(payload, dict) else None
    items = data.get('diff') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return flows
    for item in items:
        if not isinstance(item, dict):
            continue
        market, raw_code = item.get('f13'), str(item.get('f12') or '')
        net = _float(item.get('f62'))
        if net is None or not raw_code:
            continue
        if market == 1:
            code = 'sh' + raw_code
        elif market == 0:
            code = 'sz' + raw_code
        elif raw_code.startswith(('sh', 'sz')):
            code = raw_code
        else:
            continue
        flows[code] = dict(net=net, net_yi=round(net / 1e8, 4), rate=_float(item.get('f184')),
                           time=captured_at)
    return flows


def _short_driver(text, limit=DRIVER_SHORT_FALLBACK_LIMIT):
    """Compress a research reason into one short, concrete driver phrase (契约 §12.1)."""
    value = str(text or '').strip()
    for prefix in ('方向：', '方向:'):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    for keyword, short in _SHORT_DRIVER_RULES:
        if keyword in value:
            return short
    segments = [segment.strip(' 。') for segment in value.split('；') if segment.strip(' 。')]
    if not segments:
        return ''
    return segments[-1][:limit]


def _message_driver(opportunity):
    """Extract 消息面「标题」 from a direction opportunity text (quotes/whitespace removed)."""
    match = _MESSAGE_DRIVER_RE.search(str(opportunity or ''))
    if not match:
        return ''
    title = re.sub(r'\s+', '', match.group(1)).strip()
    return title[:DRIVER_SHORT_MESSAGE_LIMIT]


def _radar_driver(reason):
    """Radar driver keeps the stage/verdict tail of the theme·stage·verdict reason."""
    parts = [part.strip() for part in str(reason or '').split('·')
             if part.strip() and part.strip() != 'None']
    tail = '·'.join(parts[1:]) if len(parts) > 1 else ''
    if not tail:
        return _short_driver(reason)
    return tail[:DRIVER_SHORT_RADAR_LIMIT]


def _category(kind):
    return _GROUP_MAP.get(kind, '其他')


def _radar_category(item):
    kind = item.get('kind')
    if kind == '事件/题材':
        return '事件' if (item.get('news_count') or 0) > 0 else '题材'
    return _category(kind)


def _limit_percent(code, name):
    board = 20 if isinstance(code, str) and code.startswith(('sz30', 'sh68')) else 10
    if isinstance(name, str) and name.upper().replace(' ', '').startswith(('ST', '*ST')):
        board = 5
    return board


def _tag(price, percent, chase, state, code='', name=''):
    if percent is not None and price is not None and percent >= _limit_percent(code, name) - 0.2:
        return '涨停待回踩'
    if chase is not None and price is not None and price > chase:
        return '高于追高上限'
    if state and state != '可考虑建仓':
        return '条件未达'
    return '可建仓'


def _stamp(value):
    try:
        moment = datetime.fromisoformat(value)
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=CN)
    except (TypeError, ValueError):
        return None


def _name_tokens(issue):
    tokens = []
    for item in issue.get('radar') or []:
        kind, theme = item.get('kind'), item.get('theme') or ''
        if kind == '名称类' and theme:
            tokens.append((theme, '名称辈', theme))
        elif kind == '生肖/玄学':
            zodiac = [char for char in ('羊', '洋', '阳', '扬') if char in theme]
            if zodiac:
                tokens.extend((char, '生肖玄学', theme) for char in zodiac)
            elif theme:
                tokens.append((theme, '生肖玄学', theme))
    return tokens


def _apply_name_groups(issue, items):
    """Name-family/zodiac grouping overrides industry/concept for matching stock names."""
    tokens = _name_tokens(issue)
    if not tokens:
        return
    for item in items.values() if isinstance(items, dict) else items:
        name = item.get('name') or ''
        for token, category, group in tokens:
            if token and token in name:
                item['category'] = category
                item['group_name'] = group
                break


class Pool:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.lock = threading.RLock()
        self.quotes = {}
        self.day_track = {}
        self.last_write = {}
        self.last_poll = 0.0
        self.error = ''
        self.running = False
        self.last_zones = {}
        self.prefetch_started = False
        self.fund_flows = None
        self.fund_at = 0.0

    # ---------- 报价 ----------
    def codes(self):
        return [row['code'] for row in self.store.query('SELECT code FROM pool')]

    def _batch(self, codes):
        if not codes:
            return {}
        text = get(QUOTE_URL + ','.join(codes), 'gb18030')
        return parse_quotes(text, set(codes))

    def refresh_fund_flows(self, codes=None):
        """Refresh Eastmoney main-force net inflow for pool codes.

        Bounded to pool codes, <=80 secids per request; a failed batch is skipped silently so the
        previous values stay visible. Callers (poll/preview) own the >=30s throttling.
        """
        allowed = self.codes()
        if not allowed:
            return {}
        allowed_set = set(allowed)
        selected = [code for code in dict.fromkeys(codes or allowed) if code in allowed_set]
        captured_at = _now()
        self.fund_at = time.monotonic()
        flows = dict(self.fund_flows or {})
        for start in range(0, len(selected), FUND_FLOW_BATCH):
            flows.update(self._fetch_fund_flows(selected[start:start + FUND_FLOW_BATCH], captured_at))
        self.fund_flows = {code: value for code, value in flows.items() if code in allowed_set}
        return dict(self.fund_flows)

    def _fetch_fund_flows(self, codes, captured_at=None):
        """Fetch one <=80 batch from Eastmoney; any network/parse failure returns {}."""
        secids = [value for value in (_secid(code) for code in codes) if value]
        if not secids:
            return {}
        request = urllib.request.Request(_fund_flow_url(secids), headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Referer': 'https://quote.eastmoney.com/'})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except (OSError, ValueError, TypeError):
            return {}
        return _parse_fund_flow_payload(payload, captured_at or _now())

    def poll(self, force=False):
        live = trading(now_cn())
        with self.lock:
            if self.running:
                return
            interval = POLL_SECONDS if live else 1800
            if not force and time.monotonic() - self.last_poll < interval:
                return
            self.last_poll = time.monotonic()
        codes = self.codes()
        if not codes:
            return
        with self.lock:
            self.running = True
        try:
            quotes = {}
            with ThreadPoolExecutor(2) as worker:
                jobs = [worker.submit(self._batch, codes[start:start + 50]) for start in range(0, len(codes), 50)]
                for job in jobs:
                    quotes.update(job.result())
            stamp = now_cn()
            with self.lock:
                self.quotes.update(quotes)
                self.error = ''
            self._record(quotes, stamp)
            self._check_alerts(quotes, stamp)
            if time.monotonic() - self.fund_at >= FUND_FLOW_SECONDS:
                try:
                    self.refresh_fund_flows(codes)
                except Exception:
                    pass
        except Exception as exc:
            with self.lock:
                self.error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        finally:
            with self.lock:
                self.running = False

    def _record(self, quotes, now):
        day = now.astimezone(CN).date().isoformat()
        with self.lock:
            tracked = dict(self.day_track)
        for code, quote in quotes.items():
            price = _float(quote.get('price'))
            if price is None:
                continue
            key = (code, day)
            state = tracked.get(key) or dict(high=price, low=price)
            state['high'] = max(state['high'], price)
            state['low'] = min(state['low'], price)
            tracked[key] = state
        with self.lock:
            self.day_track = tracked
        for code, quote in quotes.items():
            key = (code, day)
            last = self.last_write.get(key, 0)
            if time.monotonic() - last < 60 and now.strftime('%H:%M') < '15:00':
                continue
            self._write_day(code, day, quote, tracked.get(key), now)
            with self.lock:
                self.last_write[key] = time.monotonic()

    def _write_day(self, code, day, quote, track, now):
        price = _float(quote.get('price'))
        previous = _float(quote.get('previous_close'))
        if price is None:
            return
        percent = (price / previous - 1) * 100 if previous else None
        plan = self._plan(code)
        high = (track or {}).get('high', price)
        low = (track or {}).get('low', price)
        hit_buy = bool(plan and plan.get('buy_low') is not None and low <= plan['buy_low'] <= high)
        hit_stop = bool(plan and plan.get('stop') is not None and low <= plan['stop'])
        hit_target = bool(plan and plan.get('target1') is not None and high >= plan['target1'])
        turnover_rate = _float(quote.get('turnover_rate'))
        volume_ratio = _float(quote.get('volume_ratio'))
        with self.store.lock:
            self.store.db.execute(
                'INSERT INTO pool_day(code,day,price,percent,high,low,state,hit_buy,hit_stop,hit_target,collected_at,'
                'turnover_rate,volume_ratio) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(code,day) DO UPDATE SET '
                'price=excluded.price,percent=excluded.percent,high=excluded.high,low=excluded.low,'
                'hit_buy=excluded.hit_buy,hit_stop=excluded.hit_stop,hit_target=excluded.hit_target,'
                'collected_at=excluded.collected_at,turnover_rate=excluded.turnover_rate,'
                'volume_ratio=excluded.volume_ratio',
                (code, day, price, percent, high, low, None, int(hit_buy), int(hit_stop), int(hit_target),
                 now.isoformat(), turnover_rate, volume_ratio))
            self.store.db.commit()

    def _plan(self, code):
        row = self.store.query('SELECT plan FROM pool WHERE code=?', (code,))
        if not row:
            return {}
        try:
            return json.loads(row[0]['plan'] or '{}')
        except (TypeError, ValueError):
            return {}

    # ---------- 同步与维护 ----------
    def _remember_all(self):
        for row in self.store.query('SELECT code,name FROM pool WHERE name IS NOT NULL AND name<>""'):
            self.store.remember(row['code'], row['name'])

    def _upsert(self, code, name, source, state, added_day, added_price, category=None, group_name=None,
                entry_tag=None, groups=None, sector=None, role=None, reason=None, plan=None, seen_day=None, added_at=None):
        now = _now()
        marker = seen_day or added_day
        with self.store.lock:
            existing = self.store.db.execute(
                'SELECT code,source,state,added_day,added_price FROM pool WHERE code=?', (code,)).fetchone()
            if existing:
                keep_state = existing['state'] if existing['state'] in MARKED else state
                self.store.db.execute(
                    'UPDATE pool SET name=?,category=?,group_name=?,entry_tag=?,groups_json=?,sector=?,role=?,reason=?,state=?,'
                    'plan=?,added_at=COALESCE(added_at,?),archived=0,updated_at=? WHERE code=?',
                    (name, category, group_name, entry_tag, json.dumps(groups or [category], ensure_ascii=False),
                     sector, role, reason, keep_state, json.dumps(plan or {}, ensure_ascii=False),
                     added_at, now, code))
                if source != '手动' and existing['source'] != '手动':
                    self.store.db.execute('UPDATE pool SET source=? WHERE code=?', (source, code))
            else:
                self.store.db.execute(
                    'INSERT INTO pool(code,name,added_day,added_price,source,category,group_name,entry_tag,'
                    'groups_json,sector,role,reason,state,plan,added_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (code, name, marker, added_price, source, category, group_name, entry_tag,
                     json.dumps(groups or [category], ensure_ascii=False), sector, role, reason, state,
                     json.dumps(plan or {}, ensure_ascii=False), added_at, now))
            self.store.db.commit()
        if isinstance(name, str) and name:
            self.store.remember(code, name)
        self.quotes.setdefault(code, {})

    def _metadata(self, issue):
        """Lightweight code->group metadata used to backfill earlier entries."""
        meta = {}

        def put(code, category, group_name, tag, source):
            if code and code not in meta:
                meta[code] = dict(category=category, group_name=group_name, entry_tag=tag, source=source)

        for pick in issue.get('top_picks') or []:
            code = pick.get('code')
            put(code, _category(pick.get('sector_kind')), pick.get('sector'),
                _tag(_float(pick.get('price')), _float(pick.get('percent')), _float(pick.get('chase')),
                     pick.get('state'), code, pick.get('name')), '建仓清单')
        for direction in issue.get('directions') or []:
            stocks = list(direction.get('stocks') or [])
            candidate = direction.get('candidate') or {}
            if candidate and not any(s.get('code') == candidate.get('code') for s in stocks):
                stocks.append(candidate)
            for stock in stocks:
                code = stock.get('code')
                if not code:
                    continue
                entry = stock.get('entry') or {}
                tag = _tag(_float(stock.get('price')), _float(stock.get('percent')), _float(entry.get('chase')),
                           direction.get('state'), code, stock.get('name'))
                if direction.get('state') != '可考虑建仓' and tag == '可建仓':
                    tag = '条件未达'
                put(code, _category(direction.get('sector_kind')), direction.get('sector'), tag, '方向候选')
        for item in issue.get('radar') or []:
            for stock in item.get('stocks') or []:
                put(stock.get('code'), _radar_category(item), item.get('theme'), '题材观察', '炒作雷达')
        _apply_name_groups(issue, meta)
        return meta

    def _backfill_metadata(self):
        missing = self.store.query("SELECT code FROM pool WHERE category IS NULL OR category='' OR entry_tag IS NULL")
        if not missing:
            return
        wanted = {row['code'] for row in missing}
        folder = self.app.dir / 'daily-outlook'
        if not folder.exists():
            return
        for path in sorted(folder.glob('*_*.json'), reverse=True)[:24]:
            try:
                issue = json.loads(path.read_text(encoding='utf-8'))
                if issue.get('screen_version', 0) < 9:
                    continue
                meta = self._metadata(issue)
            except (OSError, ValueError, TypeError):
                continue
            for code in list(wanted):
                item = meta.get(code)
                if not item:
                    continue
                with self.store.lock:
                    self.store.db.execute(
                        "UPDATE pool SET category=?,group_name=?,entry_tag=?,groups_json=COALESCE(groups_json,?),"
                        "state=CASE WHEN state IN ('已买入','已退出','忽略') THEN state ELSE ? END WHERE code=?",
                        (item['category'], item['group_name'], item['entry_tag'],
                         json.dumps([item['category']], ensure_ascii=False), item['entry_tag'], code))
                    self.store.db.commit()
                wanted.discard(code)
            if not wanted:
                break

    def _collect(self, issue):
        """Build the candidate map for one issue, keeping every source membership for multi-label groups."""
        candidates = {}
        priority = {'建仓清单': 0, '方向候选': 1, '炒作雷达': 2}

        def consider(code, name, source, category, group_name, role, sector, reason, plan,
                     price, percent, chase, tag, sector_kind=None, driver_short=None):
            if not code:
                return
            membership = (category, group_name)
            current = candidates.get(code)
            if current is None:
                candidates[code] = dict(code=code, name=name or code, source=source, category=category,
                                        group_name=group_name, role=role, sector=sector, reason=reason,
                                        plan=plan or {}, price=price, percent=percent, tag=tag,
                                        sector_kind=sector_kind, driver_short=driver_short or None,
                                        memberships=[membership])
                return
            if membership not in current['memberships']:
                current['memberships'].append(membership)
            if priority.get(current['source'], 9) <= priority.get(source, 9):
                return
            current.update(name=name or code, source=source, role=role, sector=sector, reason=reason,
                           plan=plan or {}, price=price, percent=percent, tag=tag, sector_kind=sector_kind,
                           driver_short=driver_short or None)

        for pick in issue.get('top_picks') or []:
            code = pick.get('code')
            if not code:
                continue
            price = _float(pick.get('price'))
            percent = _float(pick.get('percent'))
            chase = _float(pick.get('chase'))
            tag = _tag(price, percent, chase, pick.get('state'), code, pick.get('name'))
            reason = (pick.get('sector') or '') + '·' + (pick.get('role') or '')
            if pick.get('why'):
                reason += '；' + str(pick['why'])[:60]
            plan = {key: pick.get(key) for key in ('buy_low', 'buy_high', 'chase', 'stop', 'target1',
                                                   'target2', 'trail', 'note', 'sell_note')}
            consider(code, pick.get('name'), '建仓清单', _category(pick.get('sector_kind')), pick.get('sector'),
                     pick.get('role'), pick.get('sector'), reason, plan, price, percent, chase, tag,
                     pick.get('sector_kind'), _short_driver(pick.get('why') or pick.get('note')))

        tokens = _name_tokens(issue)
        for direction in issue.get('directions') or []:
            stocks = direction.get('stocks') or []
            candidate = direction.get('candidate') or {}
            candidate_code = candidate.get('code') or (stocks[0].get('code') if stocks else None)
            # Topic/news headline first (消息面「…」), then compressed direction reason.
            message_driver = _message_driver(direction.get('opportunity'))
            pool = list(stocks)
            if candidate and not any(s.get('code') == candidate.get('code') for s in pool):
                pool.append(candidate)
            for stock in pool:
                code = stock.get('code')
                if not code:
                    continue
                name = stock.get('name') or ''
                name_hit = any(token and token in name for token, _, _ in tokens)
                if code != candidate_code and not name_hit:
                    continue
                price = _float(stock.get('price'))
                percent = _float(stock.get('percent'))
                entry = stock.get('entry') or {}
                chase = _float(entry.get('chase'))
                tag = _tag(price, percent, chase, direction.get('state'), code, stock.get('name'))
                if direction.get('state') != '可考虑建仓' and tag == '可建仓':
                    tag = '条件未达'
                reason = f"方向：{direction.get('sector')}（{direction.get('state')}）；{(direction.get('why') or '')[:60]}"
                driver_short = (message_driver or
                                _short_driver(direction.get('why') or stock.get('reason')))
                consider(code, stock.get('name'), '方向候选', _category(direction.get('sector_kind')),
                         direction.get('sector'), stock.get('role'), direction.get('sector'), reason, entry,
                         price, percent, chase, tag, direction.get('sector_kind'), driver_short)

        for item in issue.get('radar') or []:
            category = _radar_category(item)
            for stock in item.get('stocks') or []:
                code = stock.get('code')
                if not code:
                    continue
                price = _float(stock.get('price'))
                entry = stock.get('entry') or {}
                reason = f"{item.get('theme')}·{item.get('stage')}·{item.get('verdict')}"
                consider(code, stock.get('name'), '炒作雷达', category, item.get('theme'), stock.get('role'),
                         item.get('theme'), reason, entry, price, _float(stock.get('percent')),
                         _float(entry.get('chase')), '题材观察', item.get('kind'), _radar_driver(reason))

        for item in candidates.values():
            memberships = item.pop('memberships')
            primary_category, primary_group = memberships[0]
            for token, category, group in tokens:
                if token and token in item['name']:
                    primary_category, primary_group = category, group
                    break
            item['category'], item['group_name'] = primary_category, primary_group
            groups = [primary_category]
            for category, _ in memberships:
                if category not in groups:
                    groups.append(category)
            item['groups'] = groups
        return candidates

    def record_episodes(self, issue, candidates=None):
        """Persist one episode row per research candidate for the issue (idempotent by code+issue).

        Repeated syncs keep the first record; missing metadata on legacy rows is filled in place so
        tags/percent work for databases written by earlier builds without duplicating counts.
        """
        if not isinstance(issue, dict):
            return dict(recorded=0, issue_id=None)
        issue_id = issue.get('published_at')
        if not issue_id:
            return dict(recorded=0, issue_id=None)
        candidates = candidates if candidates is not None else self._collect(issue)
        quote_date = issue.get('quote_date')
        created = _now()
        rows = []
        for item in candidates.values():
            groups = item.get('groups') or [item.get('category')]
            rows.append((item['code'], issue_id, issue_id, quote_date, item.get('source'), item.get('tag'),
                         item.get('price'), item.get('percent'), item.get('category'), item.get('group_name'),
                         json.dumps(groups, ensure_ascii=False), item.get('sector'), item.get('sector_kind'),
                         item.get('reason'), item.get('driver_short') or None,
                         json.dumps(item.get('plan') or {}, ensure_ascii=False), created))
        if not rows:
            return dict(recorded=0, issue_id=issue_id)
        with self.store.lock:
            self.store.db.executemany(
                'INSERT INTO pool_episode(code,issue_id,published_at,quote_date,source,entry_tag,price,percent,'
                'category,group_name,groups_json,sector,sector_kind,reason,driver_short,plan,created_at) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(code,issue_id) DO UPDATE SET '
                'percent=COALESCE(pool_episode.percent,excluded.percent),'
                'category=COALESCE(pool_episode.category,excluded.category),'
                'group_name=COALESCE(pool_episode.group_name,excluded.group_name),'
                'groups_json=COALESCE(pool_episode.groups_json,excluded.groups_json),'
                'sector_kind=COALESCE(pool_episode.sector_kind,excluded.sector_kind),'
                'driver_short=COALESCE(pool_episode.driver_short,excluded.driver_short)',
                rows)
            self.store.db.commit()
        return dict(recorded=len(rows), issue_id=issue_id)

    def _backfill_episodes(self, limit=EPISODE_LIMIT):
        """Record every archived issue as episodes (recent <=limit files, oldest first)."""
        folder = self.app.dir / 'daily-outlook'
        if not folder.exists():
            return dict(issues=0, recorded=0)
        try:
            paths = sorted(folder.glob('*_*.json'))
        except OSError:
            return dict(issues=0, recorded=0)
        if limit:
            paths = paths[-int(limit):]
        parsed = []
        for path in paths:
            try:
                issue = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError, TypeError):
                continue
            if isinstance(issue, dict) and issue.get('published_at'):
                parsed.append(issue)
        parsed.sort(key=lambda issue: issue.get('published_at') or '')
        recorded = 0
        for issue in parsed:
            recorded += self.record_episodes(issue)['recorded']
        return dict(issues=len(parsed), recorded=recorded)

    def sync_issue(self, issue, fetch=True):
        """Add every research candidate with entry timestamp and multi-label grouping.

        All build-list picks, each direction's candidate plus name-family hits, and all radar
        representatives are recorded. fetch=False is used while replaying older issues so only one
        quote batch is pulled afterwards.
        """
        if not isinstance(issue, dict):
            return dict(added=0, updated=0, skipped='无研判', candidates=0)
        quote_day = issue.get('quote_date') or now_cn().date().isoformat()
        added_at = issue.get('published_at') or _now()
        candidates = self._collect(issue)
        added = updated = 0
        for item in candidates.values():
            exists = self.store.query('SELECT code FROM pool WHERE code=?', (item['code'],))
            self._upsert(item['code'], item['name'], item['source'], item['tag'], quote_day,
                         item['price'], category=item['category'], group_name=item['group_name'],
                         entry_tag=item['tag'], groups=item['groups'], sector=item['sector'],
                         role=item['role'], reason=item['reason'], plan=item['plan'],
                         seen_day=quote_day, added_at=added_at)
            if exists:
                updated += 1
            else:
                added += 1
        self.record_episodes(issue, candidates)
        self._backfill_metadata()
        self.archive_old()
        self._remember_all()
        if fetch and (added or updated):
            try:
                self.poll(force=True)
            except Exception:
                pass
        return dict(added=added, updated=updated, skipped='', candidates=len(candidates))


    def bootstrap(self):
        folder = self.app.dir / 'daily-outlook'
        if not folder.exists():
            return
        # Replay the most recent issue day in chronological order: first-seen date/price become
        # the baseline, newer issues refresh tags, and entries receive their issue publish time.
        files = sorted(folder.glob('*_*.json'))
        if not files:
            return
        latest_day = files[-1].name[:10]
        by_day = {}
        for path in files:
            by_day.setdefault(path.name[:10], []).append(path)
        dates = sorted(by_day)
        replay = list(by_day[latest_day])
        for date in dates[:-1][-2:]:
            replay.append(by_day[date][-1])
        files = sorted(set(replay))
        for path in files:
            try:
                issue = json.loads(path.read_text(encoding='utf-8'))
                if issue.get('screen_version', 0) < 9:
                    continue
                self.sync_issue(issue, fetch=False)
            except (OSError, ValueError, TypeError):
                continue
        self._backfill_episodes()
        self._backfill_metadata()
        self._backfill_added_at()
        self.archive_old()
        self._remember_all()
        try:
            self.poll(force=True)
        except Exception:
            pass
        if not self.prefetch_started:
            self.prefetch_started = True
            threading.Thread(target=self.daily_loop, daemon=True).start()

    def _backfill_added_at(self):
        missing = self.store.query('SELECT code FROM pool WHERE added_at IS NULL')
        if not missing:
            return
        wanted = {row['code'] for row in missing}
        folder = self.app.dir / 'daily-outlook'
        if not folder.exists():
            return
        for path in sorted(folder.glob('*_*.json')):
            try:
                issue = json.loads(path.read_text(encoding='utf-8'))
                if issue.get('screen_version', 0) < 9:
                    continue
                meta = self._metadata(issue)
                stamp = issue.get('published_at')
                if not stamp:
                    continue
            except (OSError, ValueError, TypeError):
                continue
            hit = [code for code in wanted if code in meta]
            if hit:
                with self.store.lock:
                    for code in hit:
                        self.store.db.execute('UPDATE pool SET added_at=? WHERE code=? AND added_at IS NULL', (stamp, code))
                    self.store.db.commit()
                wanted.difference_update(hit)
            if not wanted:
                break

    def add_manual(self, code):
        code = symbol(code)
        quote = self._batch([code]).get(code)
        if not quote:
            raise ValueError('该股票行情未取得，无法加入股票池')
        fields = get('https://qt.gtimg.cn/q=' + code, 'gb18030').split('="', 1)[-1].split('~')
        name = fields[1] if len(fields) > 2 and fields[2] == code[2:] else code
        self._upsert(code, name or code, '手动', '观察', now_cn().date().isoformat(),
                     _float(quote.get('price')), category='手动', group_name='手动', entry_tag='观察',
                     groups=['手动'], reason='手动加入，等待条件确认', plan=None)
        return dict(ok=True, message=f'已加入 {name or code}')

    def remove(self, code):
        code = symbol(code)
        with self.store.lock:
            self.store.db.execute('DELETE FROM pool WHERE code=?', (code,))
            self.store.db.commit()
        with self.lock:
            self.quotes.pop(code, None)
        return dict(ok=True)

    def mark(self, code, state):
        code = symbol(code)
        if state not in STATES:
            raise ValueError('不支持的股票池状态')
        with self.store.lock:
            changed = self.store.db.execute('UPDATE pool SET state=?,updated_at=? WHERE code=?',
                                            (state, _now(), code)).rowcount
            self.store.db.commit()
        if not changed:
            raise ValueError('股票池中没有该股票')
        return dict(ok=True)

    # ---------- 展示 ----------
    def _zone(self, entry, quote):
        plan = entry.get('plan') or {}
        price = _float((quote or {}).get('price'))
        if price is None:
            return '行情待取得', ''
        stop, buy_low, buy_high, chase = plan.get('stop'), plan.get('buy_low'), plan.get('buy_high'), plan.get('chase')
        if stop is not None and price <= stop:
            return '已跌破防守位', '跌破止损，停止买入计划，按纪律处理'
        if buy_low is not None and price < buy_low:
            return '低于买区', '低于参考买区，等企稳或回到买区'
        if buy_low is not None and buy_high is not None and buy_low <= price <= buy_high:
            return '已进入买区', '价格进入买区，可按计划分批；跌破止损离场'
        if chase is not None and price > chase:
            return '高于追高上限', '高于追高上限，不追，等回踩'
        return '等待回踩', '价格未进入买区，等回踩或盘中条件满足'

    def _entry(self, row, now, day_rows=None):
        try:
            plan = json.loads(row['plan'] or '{}')
        except (TypeError, ValueError):
            plan = {}
        with self.lock:
            quote = dict(self.quotes.get(row['code']) or {})
        price = _float(quote.get('price'))
        basis = 'live' if price is not None else None
        if price is None:
            latest = self.store.query('SELECT * FROM pool_day WHERE code=? ORDER BY day DESC LIMIT 1', (row['code'],))
            if latest:
                stored = latest[0]
                price = _float(stored['price'])
                quote = dict(timestamp=stored['collected_at'], day_low=stored['low'], day_high=stored['high'],
                             turnover_rate=_float(stored.get('turnover_rate')),
                             volume_ratio=_float(stored.get('volume_ratio')))
                basis = 'last'
        if price is None and row['added_price']:
            price = _float(row['added_price'])
            quote = dict(timestamp=row['added_day'])
            basis = 'added'
        previous = _float(quote.get('previous_close'))
        percent = (price / previous - 1) * 100 if price is not None and previous else None
        if percent is None and basis == 'last':
            stored = self.store.query('SELECT percent FROM pool_day WHERE code=? ORDER BY day DESC LIMIT 1', (row['code'],))
            if stored:
                percent = _float(stored[0]['percent'])
        fresh = False
        if basis == 'live' and price is not None:
            stamp = _stamp(quote.get('timestamp'))
            fresh = bool(stamp and (now - stamp).total_seconds() <= 180)
        zone, hint = self._zone(dict(plan=plan), {'price': price} if price is not None else {})
        if basis == 'added':
            hint = '行情未取得，暂显示入选价；等待下一次行情刷新'
        elif basis == 'last':
            hint += '（显示最近一次行情）'
        added = row['added_price']
        sample_ready = basis in ('live', 'last')
        since = (price / added - 1) * 100 if sample_ready and price is not None and added else None
        distance = round((price - plan['buy_high']) / plan['buy_high'] * 100, 2) if price and plan.get('buy_high') else None
        if day_rows is None:
            ordered = list(reversed(self.store.query(
                'SELECT * FROM pool_day WHERE code=? ORDER BY day DESC LIMIT 30', (row['code'],))))
        else:
            ordered = list(day_rows)[-30:]
        history = [dict(day=item['day'], price=item['price'], percent=item['percent'], high=item['high'],
                        low=item['low'], hit_buy=bool(item['hit_buy']), hit_stop=bool(item['hit_stop']),
                        hit_target=bool(item['hit_target']),
                        turnover_rate=_float(item.get('turnover_rate')),
                        volume_ratio=_float(item.get('volume_ratio'))) for item in ordered]
        highs = [h['high'] for h in history if h['high'] is not None]
        lows = [h['low'] for h in history if h['low'] is not None]
        if sample_ready and price is not None:
            highs.append(price)
            lows.append(price)
        day_high, day_low = _float(quote.get('day_high')), _float(quote.get('day_low'))
        if sample_ready and day_high is not None:
            highs.append(day_high)
        if sample_ready and day_low is not None:
            lows.append(day_low)
        max_gain = (max(highs) / added - 1) * 100 if sample_ready and highs and added else None
        # Drawdown is measured from the entry baseline and cannot be positive; when the
        # tracked low is still above it, the stock has not drawn down yet (0%, not a gain).
        max_drawdown = min(0.0, (min(lows) / added - 1) * 100) if sample_ready and lows and added else None
        hold_days = len({h['day'] for h in history}) if history else 0
        category = row['category'] or '其他'
        try:
            groups = json.loads(row['groups_json'] or '[]') or [category]
        except (TypeError, ValueError):
            groups = [category]
        if category not in groups:
            groups.insert(0, category)
        return dict(code=row['code'], name=row['name'], added_day=row['added_day'], added_at=row['added_at'] or row['added_day'], added_price=added,
                    source=row['source'], sector=row['sector'], role=row['role'], reason=row['reason'],
                    state=row['state'], entry_tag=row['entry_tag'] or row['state'], category=category,
                    groups=groups, group_name=row['group_name'] or row['sector'] or '其他', updated_at=row['updated_at'],
                    quote=dict(price=price, percent=percent, time=quote.get('timestamp'),
                               low=_float(quote.get('day_low')), high=_float(quote.get('day_high')),
                               turnover_rate=_float(quote.get('turnover_rate')),
                               volume_ratio=_float(quote.get('volume_ratio')),
                               amplitude=_float(quote.get('amplitude')),
                               float_mcap_yi=_float(quote.get('float_mcap_yi')),
                               basis=basis, fresh=fresh) if price is not None else None,
                    plan=plan, since_add_percent=since, today_percent=percent,
                    distance_to_buy_percent=distance, zone=zone, hint=hint, history=history,
                    max_gain_percent=max_gain, max_drawdown_percent=max_drawdown, hold_days=hold_days,
                    fund=(self.fund_flows or {}).get(row['code']))

    def _benchmark(self):
        rows = self.store.getcache(BENCHMARK_CODE, 'index_daily_v1')
        if not rows:
            return {}, []
        try:
            items = rows[-1]['data'].get('rows') or []
        except (KeyError, TypeError, AttributeError):
            return {}, []
        bench = {}
        for row in items:
            try:
                bench[str(row['date'])] = float(row['close'])
            except (KeyError, TypeError, ValueError):
                continue
        return bench, sorted(bench)

    def _daily_map(self, codes, start_day=None):
        unique = [code for code in dict.fromkeys(codes) if code]
        if not unique:
            return {}
        marks = ','.join('?' * len(unique))
        if start_day:
            records = self.store.query(
                f"SELECT code,kind,day,payload FROM cache WHERE code IN ({marks}) AND kind IN ('daily','daily_live') AND day>=?",
                tuple(unique) + (start_day,))
        else:
            records = self.store.query(
                f"SELECT code,kind,day,payload FROM cache WHERE code IN ({marks}) AND kind IN ('daily','daily_live')",
                tuple(unique))
        data = {}
        for row in records:
            try:
                close = float(json.loads(row['payload']).get('close'))
            except (TypeError, ValueError, KeyError):
                continue
            key = (row['code'], row['day'])
            # Final daily rows win over intraday provisional candles.
            if row['kind'] == 'daily' or key not in data:
                data[key] = close
        return data

    def _entry_calendar_days(self, entry, benchmark_calendar, today=None):
        """Trading sessions after the entry day, used for T+N windows and pending/missing split."""
        try:
            start = date.fromisoformat(entry['added_day'])
        except (TypeError, ValueError):
            return []
        today = today or now_cn().date()
        calendar = [day for day in benchmark_calendar if start.isoformat() < day <= today.isoformat()]
        if not calendar or (today.weekday() < 5 and calendar and calendar[-1] != today.isoformat()):
            calendar = _weekday_dates(start, today)
        return calendar

    def _attach_performance(self, entry, daily, bench, benchmark_calendar):
        try:
            start = date.fromisoformat(entry['added_day'])
        except (TypeError, ValueError):
            entry['holding_days'] = 0
            entry['holding_bucket'] = '0'
            entry['windows'] = {}
            return
        today = now_cn().date()
        calendar = self._entry_calendar_days(entry, benchmark_calendar, today)
        entry['holding_days'] = len(calendar)
        entry['holding_bucket'] = _bucket(len(calendar))
        base = entry['added_price']
        entry_day = start.isoformat()
        windows = {}
        if not base:
            entry['windows'] = windows
            return
        for n in WINDOWS:
            if len(calendar) < n:
                continue
            target = calendar[n - 1]
            close = daily.get((entry['code'], target))
            if close is None:
                continue
            ret = (close / base - 1) * 100
            bench_entry, bench_target = bench.get(entry_day), bench.get(target)
            bench_ret = (bench_target / bench_entry - 1) * 100 if bench_entry and bench_target else None
            windows[f'T+{n}'] = dict(n=n, date=target, close=round(close, 2),
                                      return_percent=round(ret, 2),
                                      benchmark_return=round(bench_ret, 2) if bench_ret is not None else None,
                                      excess_percent=round(ret - bench_ret, 2) if bench_ret is not None else None)
        entry['windows'] = windows

    def _window_stats(self, entries):
        stats = []
        for n in WINDOWS:
            key = f'T+{n}'
            rows = [entry['windows'][key] for entry in entries if key in (entry.get('windows') or {})]
            values = [row['return_percent'] for row in rows]
            excess = [row['excess_percent'] for row in rows if row['excess_percent'] is not None]
            stats.append(dict(window=key, sample=len(rows),
                              win_rate=round(100 * sum(1 for value in values if value > 0) / len(values), 1) if values else None,
                              avg_return_percent=round(sum(values) / len(values), 2) if values else None,
                              beat_rate=round(100 * sum(1 for value in excess if value > 0) / len(excess), 1) if excess else None,
                              avg_excess_percent=round(sum(excess) / len(excess), 2) if excess else None))
        return stats

    def _holding_stats(self, entries):
        stats = []
        for key, label in HOLDING_BUCKETS:
            rows = [entry for entry in entries if entry.get('holding_bucket') == key]
            values = [entry['since_add_percent'] for entry in rows if entry['since_add_percent'] is not None]
            stats.append(dict(bucket=key, label=label, count=len(rows), sample=len(values),
                              win_rate=round(100 * sum(1 for value in values if value > 0) / len(values), 1) if values else None,
                              avg_since_percent=round(sum(values) / len(values), 2) if values else None))
        return stats

    # ---------- 入选事件 / 标签 / 回测 ----------
    def _episode_counts(self, codes, trading_today):
        """One query for episode-day counts (never one query per entry).

        total counts distinct natural selection days (substr(published_at,1,10)) so several issues
        of the same code on one day count once; today is 1 when the current session is one of
        those days, else 0; first_at/last_at stay the min/max published_at.
        """
        unique = [code for code in dict.fromkeys(codes) if code]
        if not unique:
            return {}
        marks = ','.join('?' * len(unique))
        rows = self.store.query(
            'SELECT code,substr(published_at,1,10) AS day,MIN(published_at) AS first_at,'
            'MAX(published_at) AS last_at '
            f'FROM pool_episode WHERE code IN ({marks}) GROUP BY code,day',
            tuple(unique))
        counts = {}
        for row in rows:
            code, day = row['code'], row['day']
            item = counts.get(code)
            if item is None:
                counts[code] = dict(total=1, today=1 if day == trading_today else 0,
                                    first_at=row['first_at'], last_at=row['last_at'])
                continue
            item['total'] += 1
            if day == trading_today:
                item['today'] = 1
            if item['first_at'] is None or (row['first_at'] or '') < item['first_at']:
                item['first_at'] = row['first_at']
            if item['last_at'] is None or (row['last_at'] or '') > item['last_at']:
                item['last_at'] = row['last_at']
        return counts

    def _episode_meta(self, codes):
        unique = [code for code in dict.fromkeys(codes) if code]
        if not unique:
            return {}
        marks = ','.join('?' * len(unique))
        rows = self.store.query(
            f'SELECT code,category,group_name,groups_json,sector,sector_kind,published_at,reason,driver_short '
            f'FROM pool_episode WHERE code IN ({marks}) ORDER BY code,published_at', tuple(unique))
        meta = {}
        for row in rows:
            meta.setdefault(row['code'], []).append(row)
        return meta

    def _episode_first_percent(self, codes):
        unique = [code for code in dict.fromkeys(codes) if code]
        if not unique:
            return {}
        marks = ','.join('?' * len(unique))
        rows = self.store.query(
            f'SELECT code,percent FROM pool_episode WHERE code IN ({marks}) ORDER BY code,published_at',
            tuple(unique))
        first = {}
        for row in rows:
            first.setdefault(row['code'], row['percent'])
        return first

    def _episode_coverage(self):
        rows = self.store.query(
            'SELECT COUNT(DISTINCT issue_id) AS issues,MIN(published_at) AS first_at,'
            'MAX(published_at) AS last_at FROM pool_episode')
        item = rows[0] if rows else {}
        first, last = item.get('first_at'), item.get('last_at')
        if not first or not last:
            return 0, None
        return int(item.get('issues') or 0), f"{str(first)[:10]}~{str(last)[:10]}"

    @staticmethod
    def _tag_labels(category, group_name, groups_json, sector):
        labels = []
        primary = group_name or sector
        if primary:
            labels.append(str(primary))
        try:
            groups = json.loads(groups_json or '[]')
        except (TypeError, ValueError):
            groups = []
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, str):
                    # groups_json keeps category memberships (概念/题材/…), not label text.
                    if group and group not in CATEGORY_ORDER:
                        labels.append(group)
                elif isinstance(group, (list, tuple)) and len(group) >= 2 and group[1]:
                    labels.append(str(group[1]))
        return labels

    def _entry_tags(self, entry, episode_rows=None):
        """Derive concept/theme/event/other labels from episode metadata, falling back to the pool row."""
        tags = {bucket: [] for bucket in TAG_BUCKETS}

        def add(bucket, label):
            label = str(label or '').strip()
            if label and label not in tags[bucket] and len(tags[bucket]) < TAG_LIMIT:
                tags[bucket].append(label)

        for row in episode_rows or []:
            category = row.get('category') or _category(row.get('sector_kind') or '')
            bucket = _tag_bucket(category)
            for label in self._tag_labels(category, row.get('group_name'), row.get('groups_json'),
                                          row.get('sector')):
                add(bucket, label)
        if not any(tags.values()):
            category = entry.get('category') or ''
            bucket = _tag_bucket(category)
            for label in self._tag_labels(category, entry.get('group_name'), None, entry.get('sector')):
                add(bucket, label)
        return tags

    @staticmethod
    def _entry_driver(episode_rows):
        """Latest-episode reason for the group “驱动” line; None when the code has no episode."""
        if not episode_rows:
            return None
        latest = episode_rows[-1]  # _episode_meta is ordered by published_at
        text = str(latest.get('reason') or '').strip()
        if not text:
            return None
        return dict(at=latest.get('published_at'), text=text[:80])

    @staticmethod
    def _entry_driver_short(episode_rows):
        """Most recent specific driver_short (fallback: latest non-empty); returns (text, published_at) or None."""
        generic = frozenset({
            '板块上涨、资金净流入', '只观察不追高', '回踩低吸', '涨停待回踩', '加速期', '题材发酵',
            '收盘时已走强，下一交易日开盘后再确认', '市场中至少三分之二的股票在跌，暂缓建仓',
            '候选股回落后重新超过昨收、同行同步上涨的',
        })
        latest = None
        for row in reversed(episode_rows or []):
            text = str(row.get('driver_short') or '').strip()
            if not text:
                continue
            at = row.get('published_at')
            if latest is None:
                latest = (text, at)
            if text not in generic and len(text) >= 10:
                return text, at
        return latest

    def _attach_episode_view(self, entries, trading_today):
        """Attach episodes/quant/tags/driver/driver_short to view entries with one episode query."""
        codes = [entry['code'] for entry in entries]
        counts = self._episode_counts(codes, trading_today)
        meta = self._episode_meta(codes)
        for entry in entries:
            entry['episodes'] = counts.get(entry['code'], dict(total=0, today=0, first_at=None, last_at=None))
            quote = entry.get('quote') or {}
            entry['quant'] = dict(turnover_rate=quote.get('turnover_rate'),
                                  volume_ratio=quote.get('volume_ratio'),
                                  amplitude=quote.get('amplitude'),
                                  float_mcap_yi=quote.get('float_mcap_yi'))
            rows = meta.get(entry['code'])
            entry['tags'] = self._entry_tags(entry, rows)
            entry['driver'] = self._entry_driver(rows)
            short = self._entry_driver_short(rows)
            entry['driver_short'] = short[0] if short else None
            entry['driver_short_at'] = short[1] if short else None

    def pool_backtest(self):
        """Read-only backtest of every non-archived pool row using the existing T+1/3/5 windows."""
        now = now_cn()
        bench, benchmark_calendar = self._benchmark()
        rows = [row for row in self.store.query('SELECT * FROM pool')
                if not _is_archived(row.get('archived'))][:BACKTEST_LIMIT]
        day_rows = {}
        for item in self.store.query('SELECT * FROM pool_day ORDER BY code,day'):
            day_rows.setdefault(item['code'], []).append(item)
        entries = [self._entry(row, now, day_rows.get(row['code'], [])) for row in rows]
        earliest = min((entry['added_day'] for entry in entries if entry.get('added_day')), default=None)
        daily = self._daily_map([entry['code'] for entry in entries], earliest)
        for entry in entries:
            self._attach_performance(entry, daily, bench, benchmark_calendar)
        codes = [entry['code'] for entry in entries]
        counts = self._episode_counts(codes, _trading_day(now))
        meta = self._episode_meta(codes)
        first_percent = self._episode_first_percent(codes)
        results = []
        with_returns = 0
        for entry in entries:
            windows = entry.get('windows') or {}
            episode = counts.get(entry['code'], dict(total=0, today=0, first_at=None, last_at=None))
            calendar = self._entry_calendar_days(entry, benchmark_calendar, now.date())
            returns = {}
            pending, missing = [], []
            today = now.date()
            market_closed = now.hour * 60 + now.minute >= 15 * 60
            for n in WINDOWS:
                key = f'T+{n}'
                window = windows.get(key)
                if window and str(window.get('date') or '') == today.isoformat() and not market_closed:
                    # 目标日就是今天且尚未收盘：行情是盘中暂态，不能当 T+N 收益。
                    returns[key] = None
                    pending.append(key)
                    continue
                if window:
                    # Alias ret/bench keys for the earlier timed-pool contract shape.
                    returns[key] = dict(n=n, date=window.get('date'), close=window.get('close'),
                                        ret_percent=window.get('return_percent'),
                                        return_percent=window.get('return_percent'),
                                        bench_percent=window.get('benchmark_return'),
                                        benchmark_return=window.get('benchmark_return'),
                                        excess_percent=window.get('excess_percent'))
                    continue
                returns[key] = None
                if len(calendar) < n:
                    # 目标交易日还没到（含今天但未收盘）：未到期，不是缺数据。
                    pending.append(key)
                    continue
                target = str(calendar[n - 1])
                target_day = date.fromisoformat(target) if target else None
                if target_day is not None and target_day == today and not market_closed:
                    pending.append(key)
                else:
                    missing.append(key)
            if any(value is not None for value in returns.values()):
                with_returns += 1
            quote = entry.get('quote') or {}
            history = entry.get('history') or []
            latest_day = (str(quote.get('time'))[:10] if quote.get('time') else None) or (
                history[-1]['day'] if history else entry['added_day'])
            latest_price = quote.get('price') if quote.get('price') is not None else (
                history[-1]['price'] if history else entry['added_price'])
            latest_percent = entry.get('today_percent')
            if latest_percent is None and history:
                latest_percent = history[-1]['percent']
            results.append(dict(
                code=entry['code'], name=entry['name'], source=entry['source'], category=entry['category'],
                first_day=entry['added_day'], first_price=entry['added_price'],
                first_percent=first_percent.get(entry['code']),
                episodes=episode['total'],  # 入选天数（同一天多期研判只计 1 天）
                first_episode_at=episode['first_at'], last_episode_at=episode['last_at'],
                latest_day=latest_day, latest_price=latest_price, latest_percent=latest_percent,
                latest=dict(day=latest_day, price=latest_price, percent=latest_percent),
                since_percent=entry['since_add_percent'], since=entry['since_add_percent'],
                returns=returns, pending=pending, missing=missing,
                tags=self._entry_tags(entry, meta.get(entry['code'])),
                entry_tag=entry.get('entry_tag'), state=entry.get('state'), zone=entry.get('zone'),
            ))
        episode_issues, episode_range = self._episode_coverage()
        return dict(updated_at=_now(), bench=BENCHMARK_NAME, rows=results,
                    coverage=dict(rows=len(results), with_returns=with_returns, bench=BENCHMARK_NAME,
                                  daily_codes=len({code for code, _ in daily}),
                                  episode_issues=episode_issues, episode_range=episode_range,
                                  note='T+N=首次入选日后第 N 个交易日收盘/入选价格−1，基准上证；'
                                       '未到期/缺数据不按 0 计；历史样本仅供研究，不构成投资建议。'))

    def _check_alerts(self, quotes, now):
        """Once-per-day local/phone alert when a pool stock enters its buy zone or breaks the stop."""
        if not quotes or now.weekday() > 4 or not trading(now):
            return
        day = now.date().isoformat()
        for row in self.store.query('SELECT * FROM pool WHERE archived=0'):
            if row['state'] in MARKED:
                continue
            code = row['code']
            plan = self._plan(code)
            if not plan.get('buy_low') and not plan.get('stop'):
                continue
            quote = quotes.get(code)
            if not quote:
                continue
            stamp = _stamp(quote.get('timestamp'))
            if not stamp or stamp.date().isoformat() != day or (now - stamp).total_seconds() > 180:
                continue
            zone, _ = self._zone(dict(plan=plan), quote)
            previous = self.last_zones.get(code)
            self.last_zones[code] = zone
            if previous is None or previous == zone:
                continue
            alert = ALERT_KINDS.get(zone)
            if not alert:
                continue
            kind, label = alert
            inserted = self.store.execute(
                'INSERT OR IGNORE INTO pool_alerts(code,day,kind,created_at) VALUES(?,?,?,?)',
                (code, day, kind, now.isoformat()))
            if not inserted:
                continue
            price = _float(quote.get('price'))
            title = f'观量 · 股票池提醒 · {row["name"]}'
            body = f'{row["name"]}（{code}）{label}，现价 {price:.2f}；仅提醒，手动交易。'
            event = dict(key=f'pool|{day}|{code}|{kind}', code=code, symbol=code[2:], trading_date=day,
                         candidate_time='—', confirmation_label='股票池', event_label=now.strftime('%H:%M:%S'),
                         volumes=[], kind='POOL_ALERT', observed_at=now.isoformat(), reference_price=price,
                         manual_sell_only=True, notification_title=title, notification_body=body)
            try:
                self.store.event(event, 'live')
            except Exception:
                continue

    def archive_old(self):
        cutoff = (now_cn().date() - timedelta(days=ARCHIVE_DAYS)).isoformat()
        self.store.execute(
            'UPDATE pool SET archived=1 WHERE COALESCE(CAST(archived AS INTEGER),0)=0 AND added_day<?', (cutoff,))

    def prefetch_daily(self):
        cache = getattr(self.app, 'daily_cache', None)
        if cache is None:
            return
        stop = getattr(self.app, 'stop', None)
        today = now_cn().date()
        start = today - timedelta(days=30)
        # Only entries whose entry day is already over need T+N closes; today's entries have no
        # completed window yet. This keeps the background fetch small and avoids racing the
        # watchlist daily loop for dozens of unnecessary stocks.
        for row in self.store.query(
                "SELECT code FROM pool WHERE COALESCE(CAST(archived AS INTEGER),0)=0 AND added_day<?",
                (today.isoformat(),)):
            if stop is not None and stop.is_set():
                return
            try:
                # DailyCache.fetch expects date objects, not ISO strings.
                cache.fetch(row['code'], start, today)
            except Exception:
                continue

    def daily_loop(self):
        stop = getattr(self.app, 'stop', None)
        while stop is None or not stop.is_set():
            self.prefetch_daily()
            if stop is None:
                return
            stop.wait(1800)

    def export(self, days=None, start=None, end=None, group=None, status=None, holding=None):
        collected = []
        offset = 0
        page = None
        while True:
            page = self.view(days, start, end, group, status, holding, 200, offset)
            collected.extend(page['entries'])
            offset += len(page['entries'])
            if not page['has_more'] or not page['entries']:
                break
        folder = self.app.dir / 'exports'
        folder.mkdir(parents=True, exist_ok=True)
        stamp = now_cn().strftime('%Y%m%d_%H%M%S')
        csv_path = folder / f'股票池复盘_{stamp}.csv'
        md_path = folder / f'股票池复盘_{stamp}.md'
        headers = ['代码', '名称', '来源', '主分组', '全部分组', '入选时间', '入选价格', '现价', '今日%', '自入选%',
                   'T+1%', 'T+1超额%', 'T+3%', 'T+3超额%', 'T+5%', 'T+5超额%', '期间最高%', '期间回撤%',
                   '已跟踪交易日', '入选状态', '当前区间', '组内排名', '买点下限', '买点上限', '追高上限', '止损',
                   '目标1', '目标2']
        import csv
        with csv_path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for entry in collected:
                windows = entry.get('windows') or {}
                plan = entry.get('plan') or {}
                def win(key, field):
                    return windows.get(key, {}).get(field)
                writer.writerow([
                    entry['code'], entry['name'], entry['source'], entry['category'],
                    '/'.join(entry.get('groups') or [entry['category']]), entry.get('added_at') or entry['added_day'],
                    entry['added_price'], (entry.get('quote') or {}).get('price'), entry.get('today_percent'),
                    entry.get('since_add_percent'), win('T+1', 'return_percent'), win('T+1', 'excess_percent'),
                    win('T+3', 'return_percent'), win('T+3', 'excess_percent'),
                    win('T+5', 'return_percent'), win('T+5', 'excess_percent'),
                    entry.get('max_gain_percent'), entry.get('max_drawdown_percent'), entry.get('holding_days'),
                    entry.get('entry_tag'), entry.get('zone'),
                    f"{entry.get('group_rank')}/{entry.get('group_size')}",
                    plan.get('buy_low'), plan.get('buy_high'), plan.get('chase'), plan.get('stop'),
                    plan.get('target1'), plan.get('target2')])
        summary = page['summary'] if page else {}
        lines = [f'# 股票池复盘报告（{now_cn().strftime("%Y-%m-%d %H:%M")}）', '',
                 f'- 筛选：时间段={page["filters"].get("days") or "全部"}，分组={group or "全部"}，状态={status or "全部"}',
                 f'- 样本：{summary.get("total")} 条，胜率 {summary.get("win_rate")}%，平均自入选 {summary.get("avg_since_percent")}%，'
                 f'中位 {summary.get("median_since_percent")}%，平均最大回撤 {summary.get("avg_max_drawdown_percent")}%',
                 f'- 基准：{BENCHMARK_NAME}（超额=个股区间收益-同期指数收益）', '', '## 按窗口收益', '',
                 '| 窗口 | 样本 | 上涨占比 | 平均收益 | 跑赢基准占比 | 平均超额 |',
                 '|---|---|---|---|---|---|']
        for row in page.get('window_stats') or []:
            lines.append(f"| {row['window']} | {row['sample']} | {row['win_rate']}% | {row['avg_return_percent']}% | {row['beat_rate']}% | {row['avg_excess_percent']}% |")
        lines += ['', '## 按持有交易日', '', '| 持有 | 样本 | 胜率 | 平均自入选 |', '|---|---|---|---|']
        for row in page.get('holding') or []:
            lines.append(f"| {row['label']} | {row['sample']} | {row['win_rate']}% | {row['avg_since_percent']}% |")
        lines += ['', '## 按入选状态', '', '| 状态 | 样本 | 胜率 | 平均自入选 |', '|---|---|---|---|']
        for row in page.get('tag_stats') or []:
            lines.append(f"| {row['entry_tag']} | {row['sample']} | {row['win_rate']}% | {row['avg_since_percent']}% |")
        lines += ['', '## 按分组', '', '| 分组 | 样本 | 胜率 | 平均自入选 |', '|---|---|---|---|']
        for row in page.get('groups') or []:
            lines.append(f"| {row['category']} | {row['sample']} | {row['win_rate']}% | {row['avg_since_percent']}% |")
        lines += ['', '## 明细（前 20 条）', '', '| 名称 | 入选时间 | 基准 | 现价 | 自入选 | 状态 |', '|---|---|---|---|---|---|']
        for entry in collected[:20]:
            lines.append(f"| {entry['name']} | {entry.get('added_at') or entry['added_day']} | {entry['added_price']} | "
                         f"{(entry.get('quote') or {}).get('price')} | {entry.get('since_add_percent')}% | {entry.get('entry_tag')} |")
        lines += ['', '> 说明：胜率=最新价高于入选基准价的样本占比；T+N 使用本机已缓存日K；无数据的样本不参与统计；'
                  '分组计数可重复（多标签）；结论仅为历史样本复盘，不构成投资建议。']
        md_path.write_text('\n'.join(lines), encoding='utf-8')
        return dict(csv=str(csv_path), report=str(md_path), count=len(collected))

    def view(self, days=None, start=None, end=None, group=None, status=None, limit=60, offset=0,
             holding=None, include_archived=False):
        now = now_cn()
        try:
            days = int(days) if days not in (None, '', 0, '0') else 0
        except (TypeError, ValueError):
            days = 0
        try:
            limit = max(1, min(200, int(limit)))
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            limit, offset = 60, 0
        bench, benchmark_calendar = self._benchmark()
        if days > 0:
            trading_days = [day for day in benchmark_calendar if day <= now.date().isoformat()]
            cutoff = trading_days[-days] if len(trading_days) >= days else (
                now.date() - timedelta(days=days - 1)).isoformat()
        else:
            cutoff = None
        rows = []
        archived_count = 0
        for row in self.store.query('SELECT * FROM pool'):
            if _is_archived(row.get('archived')) and not include_archived:
                archived_count += 1
                continue
            added = row['added_day'] or ''
            if cutoff and added < cutoff:
                continue
            if start and added < str(start):
                continue
            if end and added > str(end):
                continue
            rows.append(row)
        # One batched read of daily snapshots avoids N queries while polling every 6 seconds.
        day_rows = {}
        for item in self.store.query('SELECT * FROM pool_day ORDER BY code,day'):
            day_rows.setdefault(item['code'], []).append(item)
        entries = [self._entry(row, now, day_rows.get(row['code'], [])) for row in rows]
        earliest = min((entry['added_day'] for entry in entries if entry.get('added_day')), default=None)
        daily = self._daily_map([entry['code'] for entry in entries], earliest)
        for entry in entries:
            self._attach_performance(entry, daily, bench, benchmark_calendar)
        self._attach_episode_view(entries, _trading_day(now))
        # Primary-group ranking for “组内 #n/m”.
        rank_groups = {}
        for entry in entries:
            rank_groups.setdefault(entry['category'], []).append(entry)
        for items in rank_groups.values():
            items.sort(key=lambda item: (item['since_add_percent'] if item['since_add_percent'] is not None else -999), reverse=True)
            size = len(items)
            for index, entry in enumerate(items, 1):
                entry['group_rank'] = index
                entry['group_size'] = size
        cat_index = {category: index for index, category in enumerate(CATEGORY_ORDER)}
        entries.sort(key=lambda item: (cat_index.get(item['category'], len(CATEGORY_ORDER)),
                                       STATE_ORDER.get(item['state'], 9),
                                       -(item['since_add_percent'] if item['since_add_percent'] is not None else -999),
                                       item['code']))
        base_entries = list(entries)
        def count_by(predicate):
            return sum(1 for entry in base_entries if predicate(entry))
        counts = dict(total=len(base_entries),
                      ready=count_by(lambda entry: entry['entry_tag'] == '可建仓'),
                      limit_up=count_by(lambda entry: entry['entry_tag'] == '涨停待回踩'),
                      above_chase=count_by(lambda entry: entry['entry_tag'] == '高于追高上限'),
                      waiting=count_by(lambda entry: entry['entry_tag'] == '条件未达'),
                      speculative=count_by(lambda entry: entry['entry_tag'] == '题材观察'),
                      manual=count_by(lambda entry: entry['source'] == '手动'),
                      bought=count_by(lambda entry: entry['state'] == '已买入'),
                      exited=count_by(lambda entry: entry['state'] == '已退出'),
                      ignored=count_by(lambda entry: entry['state'] == '忽略'))
        tag_stats = []
        for tag in ('可建仓', '涨停待回踩', '高于追高上限', '条件未达', '题材观察', '观察', '已买入', '已退出', '忽略'):
            subset = [entry for entry in base_entries if entry['entry_tag'] == tag]
            if not subset:
                continue
            values = [entry['since_add_percent'] for entry in subset if entry['since_add_percent'] is not None]
            wins = sum(1 for value in values if value > 0)
            tag_stats.append(dict(entry_tag=tag, count=len(subset), sample=len(values),
                                  win_rate=round(100 * wins / len(values), 1) if values else None,
                                  avg_since_percent=round(sum(values) / len(values), 2) if values else None))
        groups = {}
        for entry in base_entries:
            for category in entry.get('groups') or [entry['category']]:
                bucket = groups.setdefault(category, dict(category=category, count=0, sample=0,
                                                          wins=0, since_sum=0.0))
                bucket['count'] += 1
                if entry['since_add_percent'] is not None:
                    bucket['sample'] += 1
                    if entry['since_add_percent'] > 0:
                        bucket['wins'] += 1
                    bucket['since_sum'] += entry['since_add_percent']
        group_rows = []
        for category in list(CATEGORY_ORDER) + [c for c in groups if c not in CATEGORY_ORDER]:
            bucket = groups.get(category)
            if not bucket:
                continue
            group_rows.append(dict(category=category, count=bucket['count'], sample=bucket['sample'],
                                   win_rate=round(100 * bucket['wins'] / bucket['sample'], 1) if bucket['sample'] else None,
                                   avg_since_percent=round(bucket['since_sum'] / bucket['sample'], 2) if bucket['sample'] else None))
        if group:
            entries = [entry for entry in entries if entry['category'] == group or group in (entry.get('groups') or [])]
        if status:
            entries = [entry for entry in entries if entry['state'] == status or entry['entry_tag'] == status]
        if holding:
            entries = [entry for entry in entries if entry.get('holding_bucket') == holding]
        filtered_total = len(entries)
        samples = [entry for entry in entries if entry['since_add_percent'] is not None]
        values = [entry['since_add_percent'] for entry in samples]
        wins = sum(1 for value in values if value > 0)
        losses = sum(1 for value in values if value < 0)
        drawdowns = [entry['max_drawdown_percent'] for entry in entries if entry['max_drawdown_percent'] is not None]
        def avg(field):
            picked = [entry[field] for entry in entries if entry[field] is not None]
            return round(sum(picked) / len(picked), 2) if picked else None
        summary = dict(
            total=len(entries), sample=len(samples), wins=wins, losses=losses,
            flat=max(0, len(samples) - wins - losses),
            win_rate=round(100 * wins / len(samples), 1) if samples else None,
            avg_since_percent=round(sum(values) / len(values), 2) if values else None,
            median_since_percent=round(statistics.median(values), 2) if values else None,
            max_since_percent=round(max(values), 2) if values else None,
            min_since_percent=round(min(values), 2) if values else None,
            avg_today_percent=avg('today_percent'),
            avg_max_gain_percent=avg('max_gain_percent'),
            avg_max_drawdown_percent=round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else None,
            target_hits=sum(1 for entry in entries if any(row['hit_target'] for row in entry['history'])),
            stop_hits=sum(1 for entry in entries if any(row['hit_stop'] for row in entry['history'])),
            buy_zone_hits=sum(1 for entry in entries if any(row['hit_buy'] for row in entry['history'])),
            ready=sum(1 for entry in entries if entry['entry_tag'] == '可建仓'),
            limit_up=sum(1 for entry in entries if entry['entry_tag'] == '涨停待回踩'),
            above_chase=sum(1 for entry in entries if entry['entry_tag'] == '高于追高上限'),
            waiting=sum(1 for entry in entries if entry['entry_tag'] == '条件未达'),
            speculative=sum(1 for entry in entries if entry['entry_tag'] == '题材观察'),
            manual=sum(1 for entry in entries if entry['source'] == '手动'),
            bought=sum(1 for entry in entries if entry['state'] == '已买入'),
            exited=sum(1 for entry in entries if entry['state'] == '已退出'),
            in_zone=sum(1 for entry in entries if entry['zone'] == '已进入买区'),
        )
        page = entries[offset:offset + limit]
        stamps = [entry['quote']['time'] for entry in base_entries if entry['quote'] and entry['quote'].get('time')]
        # Window / holding reference tables describe the selected time range as a whole.
        # They must not go blank just because the user narrowed the list by status/group/holding
        # (e.g. holding="0" previously hid every T+1 sample).
        window_stats = self._window_stats(base_entries)
        windows = {item['window']: item for item in window_stats}
        holding_stats = self._holding_stats(base_entries)
        return dict(updated_at=_now(), quotes_time=max(stamps) if stamps else None, error=self.error,
                    trading=trading(now), summary=summary, counts=counts, tag_stats=tag_stats,
                    groups=group_rows, entries=page, filtered_total=filtered_total,
                    offset=offset, limit=limit, has_more=offset + len(page) < filtered_total,
                    windows=windows, window_stats=window_stats, holding=holding_stats, benchmark=BENCHMARK_NAME,
                    daily_ready=sum(1 for entry in entries if entry.get('windows')),
                    archived_count=archived_count,
                    filters=dict(days=days or None, start=start or None, end=end or None, group=group or None,
                                 status=status or None, holding=holding or None, limit=limit, offset=offset,
                                 include_archived=bool(include_archived)))


    def count(self):
        rows = self.store.query('SELECT state,COUNT(*) AS n FROM pool WHERE COALESCE(CAST(archived AS INTEGER),0)=0 GROUP BY state')
        return {row['state']: row['n'] for row in rows}