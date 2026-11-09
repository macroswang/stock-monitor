"""市场机会 v2 研判层：方向评分、标的角色、买入时机、剧本与仓位。

只使用已核对的数据快照；判断是本机规则（契约 §4–§7），不是作者公式，也不构成投资建议。
"""
import math
import re

from .provider import now_cn
from . import theme_discovery
from . import market_pulse

CAUTION = re.compile('下滑|下降|下调|萎缩|回撤|收紧|下跌|走弱|亏损|立案|起火|冲突|预警|抵制|暴跌|出口限制|制裁')
SUPPORT = re.compile('增长|上调|获批|投产|中标|扩产|签约|保供|订单增加|提高补贴|需求回升|增产|复产')
SHARE = 1e8
ROLES = ('低吸候选', '龙头', '中军', '弹性')
GATES = [dict(kind='market_decline_share_max', value=0.6667),
         dict(kind='sector_change_min', value=0),
         dict(kind='sector_net_min', value=0),
         dict(kind='candidate_pct_max', value=5),
         dict(kind='candidate_recover'),
         dict(kind='peers_rising_min', value=1)]
WINDOW = '下一交易日 9:45–10:30'
GATE_TEXT = dict(market_decline_share_max='市场下跌家数≤2/3', sector_change_min='板块当日上涨',
                 sector_net_min='板块资金净流入', candidate_pct_max='候选涨幅<5%',
                 candidate_recover='候选站回昨收上方', peers_rising_min='同行至少 1 只上涨')


def _reason(exc):
    return str(exc) if isinstance(exc, (ValueError, KeyError)) else '数据异常：' + type(exc).__name__


def _round(value):
    if value is None or not math.isfinite(value):
        return None
    return round(value, 2)


def quote_stats(quotes, day):
    """Same-session quotes only; a stale or malformed quote never becomes a level."""
    result = {}
    for code, row in (quotes or {}).items():
        try:
            stamp = row['timestamp']
            price, previous = float(row['price']), float(row['previous_close'])
            low = float(row['day_low'])
            amount = float(row['amount_yuan'])
            if not isinstance(stamp, str) or stamp[:10] != day:
                continue
            if not all(math.isfinite(v) for v in (price, previous, low, amount)) or min(price, previous, low) <= 0 or amount < 0:
                continue
            if low > price:
                continue
            result[code] = dict(price=price, previous=previous, low=low, amount=amount,
                                pct=(price / previous - 1) * 100)
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _member_pool(idea, stats, pool):
    members = []
    for item in idea.get('core_members') or []:
        code = item.get('code')
        if code in stats:
            members.append(dict(code=code, name=item.get('name') or code, **stats[code]))
    return members


def pick_stocks(idea, quotes, pool, levels, day, closed):
    """候选、龙头、中军、弹性；同代码只保留一个角色。"""
    stats = quote_stats(quotes, day)
    members = _member_pool(idea, stats, pool)
    pool = pool or {}
    candidate = (idea.get('stocks') or [{}])[0].get('code')
    selected = {}
    if candidate in stats:
        selected[candidate] = '低吸候选'
    members = [row for row in members if not re.search(r'ST|退', row['name'].upper())]
    def free():
        return [row for row in members if row['code'] not in selected]
    def add(code, role):
        if code and code not in selected:
            selected[code] = role
            return True
        return False
    def pool_height(row):
        entry = pool.get(row['code'])
        if not entry or entry.get('boards') is None:
            return 0
        return entry['boards'] if entry.get('days') == entry.get('boards') else 0
    pool_members = [row for row in free() if row['code'] in pool]
    pool_members.sort(key=lambda row: (pool_height(row), row['pct'], row['amount']), reverse=True)
    if pool_members:
        add(pool_members[0]['code'], '龙头')
    else:
        active = sorted((row for row in free() if row['amount'] >= 50_000_000), key=lambda row: row['pct'], reverse=True)
        if active:
            add(active[0]['code'], '龙头')
    # 中军 prefers a large, still-rising name that has not already run into the limit.
    mid = sorted((row for row in free() if row['pct'] > 0 and row['code'] not in pool),
                 key=lambda row: row['amount'], reverse=True)
    if not mid:
        mid = sorted((row for row in free() if row['pct'] > 0), key=lambda row: row['amount'], reverse=True)
    if mid:
        add(mid[0]['code'], '中军')
    elif free():
        add(sorted(free(), key=lambda row: row['amount'], reverse=True)[0]['code'], '中军')
    elastic = [row for row in free() if 30_000_000 <= row['amount'] <= 500_000_000 and row['pct'] > 0]
    if elastic:
        add(sorted(elastic, key=lambda row: row['pct'], reverse=True)[0]['code'], '弹性')
    ordered = []
    names = {row['code']: row['name'] for row in members}
    if candidate in stats and candidate not in names:
        stock = next((s for s in idea.get('stocks') or [] if s.get('code') == candidate), {})
        names[candidate] = stock.get('name') or candidate
    for role in ROLES:
        for code, current in list(selected.items()):
            if current != role:
                continue
            row = stats[code]
            entry = pool.get(code)
            roles_levels = levels.get(code)
            ordered.append(dict(code=code, name=names.get(code, code), role=role,
                                price=_round(row['price']), percent=_round(row['pct']),
                                amount_yuan=_round(row['amount']), low=_round(row['low']),
                                boards=entry.get('boards') if entry else 0,
                                limit_tag='涨停' if entry else None,
                                reason=entry.get('reason') or None if entry else None,
                                levels=roles_levels,
                                entry=stock_entry(row, roles_levels, role)))
    return ordered


def _levels(rows, day, closed):
    if not rows:
        return None
    bars = [row for row in rows if row['date'] < day]
    if closed:
        today = [row for row in rows if row['date'] == day]
        bars = bars + today
    closes = [row['close'] for row in bars]
    def mean(n):
        return sum(closes[-n:]) / n if len(closes) >= n else None
    level = dict(ma5=_round(mean(5)), ma10=_round(mean(10)), ma20=_round(mean(20)),
                 high20=_round(max(row['high'] for row in bars[-20:])) if len(bars) >= 20 else None,
                 low20=_round(min(row['low'] for row in bars[-20:])) if len(bars) >= 20 else None)
    return level if any(value is not None for value in level.values()) else None


def stock_entry(stats, levels, role):
    prev, price, low = stats['previous'], stats['price'], stats['low']
    chase = prev * (1.07 if role == '龙头' else 1.05 if role == '中军' else 1.03)
    cap = prev * (1.05 if role == '龙头' else 1.03 if role == '中军' else 1.02)
    buy_high = min(price, cap)
    ma5 = (levels or {}).get('ma5')
    buy_low = max(low, ma5 if ma5 is not None and ma5 <= price else low * 0.98)
    # A gap-up name can have a day low above the reference cap; a buy zone must stay below the
    # no-chase cap and its stop below the zone, otherwise the printed plan is not executable.
    buy_low = min(buy_low, buy_high)
    chase = max(chase, buy_high + 0.01)
    ma10 = (levels or {}).get('ma10')
    stop = max(ma10 if ma10 is not None and ma10 < low else low, low * 0.93) * 0.98
    stop = min(stop, buy_low * 0.98)
    stop = _round(stop)
    high20 = (levels or {}).get('high20')
    # A 1-3 day plan uses a nearby resistance; a far 20-day high is not a realistic swing target.
    target1 = high20 if high20 is not None and price * 1.02 < high20 <= price * 1.15 else price * 1.08
    target1 = _round(target1)
    target2 = _round(max(target1 * 1.06, price * 1.15))
    trail = ma5 if ma5 is not None and ma5 > stop else (ma10 if ma10 is not None and ma10 > stop else None)
    # Quote the same rounded target the table shows, so one plan never displays two percentages.
    target_text = f"接近 {target1}（{(target1 / price - 1) * 100:+.1f}%）分批减半"
    if trail is not None:
        target_text += f"；收盘跌破 {_round(trail)}（均线）或 {stop}（防守位）离场"
    else:
        target_text += f"；跌破 {stop}（防守位）离场"
    return dict(buy_low=_round(buy_low), buy_high=_round(buy_high), stop=stop, chase=_round(chase),
                target1=_round(target1), target2=_round(target2),
                trail=None if trail is None else _round(trail),
                sell_note=target_text + '；持有 1–3 个交易日。',
                note=f"回踩 {_round(buy_low)}–{_round(buy_high)} 可分批；高开超过 {_round(chase)} 不追；跌破 {stop} 离场。")


def _news_weight(title):
    if not title:
        return 0
    return -0.5 if CAUTION.search(title) else 0.7 if SUPPORT.search(title) else 0.1


def score_direction(idea, stats, pool, capital_by_code):
    pct, net = idea.get('change'), idea.get('net')
    if pct is None or not math.isfinite(pct) or net is None or not math.isfinite(net):
        return None
    saved = capital_by_code.get(idea.get('sector_code')) or {}
    days = saved.get('days') or 0
    net_5d = saved.get('net_5d') if days >= 3 and saved.get('net_5d') is not None else None
    boards = 0
    promoted = False
    for item in idea.get('core_members') or []:
        entry = pool.get(item.get('code'))
        if not entry:
            continue
        boards += 1
        if entry.get('days') == entry.get('boards') and entry['boards'] >= 2:
            promoted = True
    members = [stats[item['code']] for item in idea.get('core_members') or [] if item.get('code') in stats]
    checked = len(members)
    rising = sum(1 for row in members if row['pct'] > 0)
    parts = dict(
        capital=round((2 if net > 0 else 0) + (0.5 if net_5d and net_5d > 0 else 0), 2),
        trend=round(min(max(pct, 0), 3) + (0.5 if checked >= 3 and rising / checked >= .6 else 0), 2),
        sentiment=round(min(boards, 3) * 0.5 + (0.5 if promoted else 0), 2),
        hotspot=_news_weight(idea.get('news_title')),
        evidence=0.5 if idea.get('sector_kind') == '题材' and len(idea.get('core_members') or []) >= 3 else 0,
    )
    return dict(score=round(sum(parts.values()), 2), parts=parts, boards=boards, rising=rising,
                checked=checked, net_5d=net_5d, days=days)


def assess(direction, quotes, day, breadth):
    """The live gate check shared by the backend state and the frontend display."""
    stats = quote_stats(quotes, day)
    candidate = stats.get(direction['candidate']['code'])
    peers = [stats.get(item['code']) for item in direction.get('peers') or []]
    if not candidate or not peers or any(row is None for row in peers):
        return dict(status='missing', why='本期行情正在核对。')
    if candidate['price'] < direction['entry_stop']:
        return dict(status='weak', why=f"候选股已跌破防守位 {direction['entry_stop']}。")
    if all(row['price'] < direction['peer_stops'][item['code']] for item, row in zip(direction.get('peers') or [], peers)):
        return dict(status='weak', why='两只同行都已跌破各自防守位。')
    if breadth and breadth.get('active'):
        if breadth['decline'] * 3 >= breadth['active'] * 2:
            return dict(status='watch', why='市场中至少三分之二的股票在跌，暂缓建仓。')
    if direction['change'] <= 0 or direction['net'] <= 0:
        return dict(status='watch', why='板块上涨和资金净流入尚未同时出现。')
    if candidate['pct'] >= 5:
        return dict(status='watch', why='候选股当日已涨至少 5%，继续等回落机会。')
    recovered = candidate['low'] <= candidate['previous'] < candidate['price']
    if not recovered or not any(row['pct'] > 0 for row in peers):
        return dict(status='watch', why='候选股回落后重新超过昨收、同行同步上涨的条件尚未齐备。')
    if direction.get('closed'):
        return dict(status='watch', why='收盘时已走强，下一交易日开盘后再确认。')
    return dict(status='ready', why='候选回落后已重回昨收上方，有同行上涨，板块上涨且资金净流入。')


def state_of(result, direction, net_5d):
    if result['status'] == 'ready':
        return '可考虑建仓', result['why']
    if result['status'] == 'weak':
        return '观察', result['why']
    if CAUTION.search(direction.get('news_title') or ''):
        return '回避', '消息面出现不利或不确定表述，先等确认。'
    if direction['net'] < 0 and net_5d is not None and net_5d < 0:
        return '回避', '当日与近 5 个采集日资金都在净流出。'
    if direction['change'] <= 0 or direction['net'] <= 0:
        return '观察', result['why']
    return '继续等', result['why']


def direction_rule(name):
    clean = theme_discovery.key(name)
    return clean.casefold()


def _opportunity(idea, scored, pool, stats):
    pieces = []
    if idea['net'] > 0:
        pieces.append(f"当日净流入 {idea['net'] / SHARE:.2f} 亿元")
    if scored['net_5d'] and scored['net_5d'] > 0:
        pieces.append(f"近 {scored['days']} 个采集日累计 {scored['net_5d'] / SHARE:.1f} 亿元")
    if scored['boards']:
        pieces.append(f"板块内 {scored['boards']} 只涨停")
    if idea.get('news_title'):
        pieces.append('消息面「' + idea['news_title'][:16] + '」')
    if scored['checked'] >= 3 and scored['rising'] / scored['checked'] >= .6:
        pieces.append(f"{scored['rising']}/{scored['checked']} 只成分股上涨")
    if not pieces:
        return '资金与热度尚未同时出现，先观察。'
    return '、'.join(pieces[:3]) + '。'


def _logic(idea, scored, pool, capital, days):
    output = []
    saved = (capital or {}).get('by_code', {}).get(idea.get('sector_code')) if capital else None
    block = (capital or {}).get('industry' if idea.get('sector_kind') == '行业' else 'concept') if capital else None
    measure = saved.get('measure') if saved else (block or {}).get('measure')
    base = f"资金：当日净额 {idea['net'] / SHARE:+.2f} 亿元（{measure or '来源未取得'}）"
    if saved and saved.get('net_5d') is not None:
        output.append(base + f"，近 {saved['days']} 个采集日累计 {saved['net_5d'] / SHARE:+.2f} 亿元。")
    else:
        output.append(base + f"，近 5 个采集日累计不展示（已核对 {saved['days'] if saved else 0} 天，需要至少 3 天）。")
    if scored['boards']:
        best = max((pool.get(item['code']) for item in idea.get('core_members') or []
                    if pool.get(item['code']) and pool[item['code']].get('boards') is not None),
                   key=lambda row: row['boards'], default=None)
        output.append(f"人气：板块内 {scored['boards']} 只涨停，最高 {best['boards']} 板（{best['name']}）。" if best and best.get('days') == best.get('boards')
                      else f"人气：板块内 {scored['boards']} 只涨停。")
    else:
        output.append(f"人气：板块内今日没有涨停股（成分股 {scored['checked']} 只，{scored['rising']} 只上涨）。")
    output.append(f"趋势：{scored['rising']}/{scored['checked']} 只成分股上涨。")
    if idea.get('news_title'):
        output.append('热点：「' + idea['news_title'][:28] + '」' + ('（含不利表述）' if CAUTION.search(idea['news_title']) else ''))
    if idea.get('sector_kind') == '题材':
        output.append(f"题材：{len(idea.get('core_members') or [])} 家成分来自公告/年报/互动易证据。")
    return output


def _evidence(idea, capital, scored, pool):
    saved = (capital or {}).get('by_code', {}).get(idea.get('sector_code')) if capital else None
    block = (capital or {}).get('industry' if idea.get('sector_kind') == '行业' else 'concept') if capital else None
    output = [dict(label='资金', value=f"当日 {idea['net'] / SHARE:+.2f} 亿" + (f"，近 {saved['days']} 日 {saved['net_5d'] / SHARE:+.2f} 亿" if saved and saved.get('net_5d') is not None else ''),
                   source=(saved or {}).get('source') or (block or {}).get('source') or '成分股资金合计（本机）'),
              dict(label='人气', value=f"板块内 {scored['boards']} 只涨停，成分股 {scored['rising']}/{scored['checked']} 只上涨",
                   source='同花顺涨停池 + 本批全市场报价')]
    if idea.get('news_title'):
        output.append(dict(label='热点', value=idea['news_title'][:40], source='新浪滚动新闻'))
    if idea.get('sector_kind') == '题材':
        output.append(dict(label='题材', value='公告/年报/互动易证据', source='巨潮公告 + 东方财富经营评述 + 互动易'))
    return output


def _timing(idea, stocks, scored, regime, breadth, closed, day):
    candidate = next((row for row in stocks if row['role'] == '低吸候选'), stocks[0])
    entry = candidate['entry']
    stop = entry['stop']
    triggers = [
        f"板块当日涨幅 > 0 且资金净额 > 0（当前 {idea['change']:+.2f}%、{idea['net'] / SHARE:+.2f} 亿元）。",
        f"{candidate['name']} 涨幅 < 5%（当前 {candidate['percent']:+.2f}%），回踩 {entry['buy_low']}–{entry['buy_high']} 可分批买入。",
        f"两只同行至少一只上涨，{candidate['name']} 不跌破 {stop}。",
    ]
    if breadth:
        triggers.append(f"市场上涨占比 ≥ 50%（当前 {breadth['advancing_percent']}%），下跌家数不超过有成交家数的三分之二。")
    invalidation = [f"{candidate['name']} 跌破 {stop}（防守位）。",
                    f"板块资金净额转为负值（当前 {idea['net'] / SHARE:+.2f} 亿元）。",
                    f"板块涨幅跌破 -1%（当前 {idea['change']:+.2f}%）。",
                    '板块内出现 2 只以上跌停。']
    index = next((row for row in (regime.get('indices') or []) if row['code'] == 'sh000001'), None)
    if index:
        invalidation.append(f"上证跌破参考支撑 {index['support']}。")
    window = WINDOW if closed or not day else '今日剩余时段 + ' + WINDOW
    return dict(window=window, triggers=triggers, invalidation=invalidation, gates=[dict(gate) for gate in GATES])


def regime(pulse, summary):
    """契约 §4 的本机规则；数据不足按防守处理并说明。"""
    market = (pulse or {}).get('market')
    senti = (pulse or {}).get('sentiment')
    if not market:
        return dict(score=None, bias='防守', verdict='数据不足 · 以观察为主',
                    position='总仓 ≤2 成或空仓，只观察不追高。', indices=[], notes=['市场温度数据未取得。'])
    indices = market.get('indices') or []
    shanghai = next((row for row in indices if row['code'] == 'sh000001'), None)
    breadth = market.get('breadth')
    score, notes = 0, []
    if shanghai and shanghai.get('ma5') is not None:
        score += 1 if shanghai['above_ma5'] else 0
        notes.append(('上证站上 5 日线' if shanghai['above_ma5'] else '上证低于 5 日线') + f" {shanghai['ma5']}：{' +1' if shanghai['above_ma5'] else ' 0'}。")
    if shanghai and shanghai.get('ma20') is not None:
        score += 1 if shanghai['above_ma20'] else 0
    if breadth:
        share = breadth['advancing_percent']
        if share >= 65:
            score += 2
        elif share >= 55:
            score += 1
        elif share < 30:
            score -= 2
        elif share < 40:
            score -= 1
        notes.append(f"上涨占比 {share}%。")
        if breadth['amount_ratio'] is not None:
            score += 1 if breadth['amount_ratio'] >= 1.1 else -1 if breadth['amount_ratio'] < .85 else 0
            notes.append(f"成交额为近 {breadth['days_used']} 日均值的 {breadth['amount_ratio'] * 100:.0f}%。")
    elif (market.get('breadth') is None):
        score -= 1
        notes.append('全市场广度缺失，按偏保守处理。')
    if senti:
        limits = senti['limit_up']
        if limits.get('yesterday'):
            if limits['today'] > limits['yesterday']:
                score += 1
            elif limits['today'] < limits['yesterday'] * .7:
                score -= 1
        if limits.get('sealed_rate') is not None:
            score += 1 if limits['sealed_rate'] >= .7 else -1 if limits['sealed_rate'] < .6 else 0
        if senti['limit_down']['today'] >= 20:
            score -= 2
        elif senti['limit_down']['today'] >= 10:
            score -= 1
        if senti['max_board'] >= 5:
            score -= 1
        notes.append(f"涨停 {limits['today']} 家、跌停 {senti['limit_down']['today']} 家、最高 {senti['max_board']} 板。")
    bias = '进攻' if score >= 4 else '试错' if score >= 1 else '防守'
    share = breadth['advancing_percent'] if breadth else None
    ratio = breadth['amount_ratio'] if breadth else None
    limits = senti['limit_up'] if senti else {}
    if score <= 0 and senti and senti['limit_down']['today'] >= 10:
        verdict = '情绪退潮 · 防守为主'
    elif score <= 0:
        verdict = '弱势震荡 · 等待修复'
    elif share is not None and share >= 60 and (ratio is None or ratio >= .9):
        verdict = '普涨修复 · 可跟随强势'
    elif share is not None and share >= 50 and ratio is not None and ratio < .85:
        verdict = '缩量修复 · 只做强势方向'
    elif share is not None and share < 40:
        verdict = '缩量回踩 · 修复未确认'
    else:
        verdict = '分化震荡 · 精选方向'
    position = ('总仓 5–6 成，单方向 ≤2 成。' if bias == '进攻'
                else '总仓 3–4 成，单方向 ≤1.5 成。' if bias == '试错'
                else '总仓 ≤2 成或空仓，只观察不追高。')
    return dict(score=score, bias=bias, verdict=verdict, position=position, indices=indices,
                notes=notes, limits=limits)


def playbooks(pulse, state, directions):
    market = (pulse or {}).get('market') or {}
    senti = (pulse or {}).get('sentiment') or {}
    breadth = market.get('breadth') or {}
    shanghai = next((row for row in market.get('indices') or [] if row['code'] == 'sh000001'), None)
    ready = [row['sector'] for row in directions if row['state'] == '可考虑建仓'][:2]
    focus = '、'.join(ready) if ready else '等待确认后再说'
    ma5 = shanghai['ma5'] if shanghai and shanghai.get('ma5') is not None else None
    ma10 = shanghai['ma10'] if shanghai and shanghai.get('ma10') is not None else None
    ma5_text = f'5 日线 {ma5}' if ma5 is not None else '5 日线（待取得）'
    ma10_text = f'10 日线 {ma10}' if ma10 is not None else '10 日线（待取得）'
    limit_up = (senti.get('limit_up') or {}).get('today')
    limit_down = (senti.get('limit_down') or {}).get('today')
    sealed = (senti.get('limit_up') or {}).get('sealed_rate')
    ratio = breadth.get('amount_ratio')
    rows = [
        dict(name='修复延续', active=state['bias'] == '进攻',
             conditions=[f'上证站上 {ma5_text}',
                         '成交额 ≥ 近 5 日均额 0.9 倍' + ('' if ratio is None else f'（当前 {ratio:.2f}）'),
                         '涨停数不低于昨日'],
             action=f'主做可考虑建仓方向（{focus}），开盘 30 分钟确认资金与同行同步后再分批。',
             position='5–6 成'),
        dict(name='高低切/分化', active=state['bias'] == '试错',
             conditions=[f'上证在 {ma5_text} 附近 ±1%',
                         '封板率 0.6–0.7' + ('' if sealed is None else f'（当前 {sealed:.2f}）'),
                         '涨停与跌停同时出现'],
             action='只低吸不追高：候选回到昨收上方、同行上涨才分批；高位连板只观察。',
             position='3–4 成'),
        dict(name='补跌防守', active=state['bias'] == '防守',
             conditions=[f'上证跌破 {ma10_text}',
                         '跌停 ≥20 家' + ('' if limit_down is None else f'（当前 {limit_down} 家）'),
                         '涨停数 < 昨日 70%'],
             action='空仓或只保留低位观察仓，不做反抽，等涨停家数回升再重新评估。',
             position='≤2 成'),
    ]
    return rows


def timetable(pulse, state, directions):
    market = (pulse or {}).get('market') or {}
    senti = (pulse or {}).get('sentiment') or {}
    breadth = market.get('breadth') or {}
    shanghai = next((row for row in market.get('indices') or [] if row['code'] == 'sh000001'), None)
    ma5 = shanghai['ma5'] if shanghai and shanghai.get('ma5') is not None else '—'
    focus = [row for row in directions if row['state'] in ('可考虑建仓', '继续等')][:2]
    names = '、'.join(row['sector'] for row in focus) if focus else '暂无'
    stocks = '、'.join(dict.fromkeys(stock['name'] for row in focus for stock in row['stocks'][:2])) or '—'
    ratio = breadth.get('amount_ratio')
    sealed = (senti.get('limit_up') or {}).get('sealed_rate')
    open_num = (senti.get('limit_up') or {}).get('open_num')
    ratio_text = '待取得（盘中不提前用未完成成交额）' if ratio is None else f'{ratio:.2f}'
    sealed_text = '待取得' if sealed is None else f'{sealed:.2f}'
    open_text = '待取得' if open_num is None else str(open_num)
    return [
        dict(time='9:15–9:25', focus='竞价', rule=f"看 {stocks} 高开幅度：0–3% 正常，超过 3% 不追；龙头竞价放量且板块资金转正才算强。"),
        dict(time='9:30–10:00', focus='确认方向', rule=f"两市成交额与上涨占比先看；上证站上 {ma5} 且 {names} 同向上涨才考虑分批。"),
        dict(time='10:30', focus='资金与涨停', rule='板块资金仍净流入、板块内至少 2 只上涨；候选涨幅 <5% 且不破防守位。'),
        dict(time='14:30', focus='尾盘兑现',
             rule=f"尾盘两市成交额达到近 5 日均值的 0.90 倍（当前比 {ratio_text}）、封板率不低于 0.60（当前 {sealed_text}）可持有；"
                  f"封板率跌破 0.60、当日炸板数 ≥15 家（当前 {open_text}）或板块资金净额转负时减仓，不隔夜重仓。"),
        dict(time='收盘后', focus='更新研判', rule='等本机研判每 30 分钟更新一次后核对：方向、资金、涨停池是否仍支持原计划。'),
    ]


def sizing_for(state, role):
    if state['bias'] == '防守':
        return '≤0.5 成'
    if state['bias'] == '进攻':
        return '1–1.5 成' if role == '低吸候选' else '1 成'
    return '≤1 成' if role == '低吸候选' else '0.5–1 成'


def top_picks(state, directions, limit=6):
    """The trader's short list: one buy plan per leading direction, plus the top leader."""
    picks, used = [], set()
    for direction in directions:
        stocks = direction.get('stocks') or []
        candidate = next((row for row in stocks if row['role'] == '低吸候选'), None)
        leader = next((row for row in stocks if row['role'] == '龙头'), None)
        wanted = [candidate]
        if direction['rank'] <= 2 and leader is not None and leader is not candidate:
            wanted.append(leader)
        for stock in wanted:
            if stock is None or len(picks) >= limit or stock['code'] in used:
                continue
            used.add(stock['code'])
            entry = stock.get('entry') or {}
            picks.append(dict(code=stock['code'], name=stock['name'], role=stock['role'],
                              sector=direction['sector'], sector_code=direction['sector_code'],
                              sector_kind=direction['sector_kind'], rank=direction['rank'],
                              state=direction['state'], why=direction['why'],
                              price=stock['price'], percent=stock['percent'],
                              boards=stock['boards'], limit_tag=stock['limit_tag'],
                              buy_low=entry.get('buy_low'), buy_high=entry.get('buy_high'),
                              chase=entry.get('chase'), stop=entry.get('stop'),
                              target1=entry.get('target1'), target2=entry.get('target2'),
                              trail=entry.get('trail'), note=entry.get('note'),
                              sell_note=entry.get('sell_note'),
                              window=direction['timing']['window'],
                              trigger='；'.join(GATE_TEXT.get(gate['kind'], gate['kind'])
                                               for gate in direction['timing'].get('gates') or []),
                              sizing=sizing_for(state, stock['role'])))
        if len(picks) >= limit:
            break
    return picks


def focus_of(directions):
    if not directions:
        return None
    first = directions[0]
    candidate = first.get('candidate') or {}
    return dict(sector=first['sector'], sector_code=first['sector_code'], state=first['state'],
                why=first['why'], candidate=candidate, window=first['timing']['window'],
                summary=(f"首选 {first['sector']} · {candidate.get('name') or '待取得'}：{first['why']}"
                         if candidate.get('name') else f"首选 {first['sector']}：{first['why']}"))


def risk_items(pulse, state, directions, warnings):
    items = []
    senti = (pulse or {}).get('sentiment') or {}
    if senti.get('max_board', 0) >= 5:
        items.append(f"最高连板 {senti['max_board']} 板（{senti.get('max_board_name')}），高位股断板风险大，不追高。")
    sealed = (senti.get('limit_up') or {}).get('sealed_rate')
    if sealed is not None and sealed < .65:
        items.append(f"封板率 {sealed:.2f}，炸板偏多，追高容易被套。")
    temperature = senti.get('temperature')
    if temperature == '退潮':
        items.append('人气温度为退潮：涨停减少、跌停增加，短线只做低吸不做接力。')
    elif temperature == '高位':
        items.append('人气温度为高位：连板高度已高，接力风险大于低吸。')
    if warnings:
        items.append('数据缺口见“数据覆盖”：缺失项不参与评分，结论可能滞后。')
    items.append('所有数值来自公开行情与公告统计，只是研究记录，不构成任何投资建议。')
    return items[:6]


def build(store, ideas, pulse, quotes, summary, now=None):
    now = now or now_cn()
    day = summary['date']
    closed = summary.get('status') == 'closed'
    warnings = []
    capital = (pulse or {}).get('capital')
    capital_by_code = (capital or {}).get('by_code') or {}
    senti = (pulse or {}).get('sentiment')
    pool = (senti or {}).get('by_code') or {}
    stats = quote_stats(quotes, day)
    scored = []
    for idea in ideas:
        value = score_direction(idea, stats, pool, capital_by_code)
        if value:
            scored.append((value['score'], idea, value))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[:8]
    # Roles need quotes only; levels are fetched once for the selected names.
    prelim = []
    codes = []
    for score, idea, value in selected:
        stocks = pick_stocks(idea, quotes, pool, {}, day, closed)
        if not stocks:
            warnings.append(f"{idea['sector']} 的候选股行情未取得，本期不列入方向。")
            continue
        prelim.append((score, idea, value, stocks))
        for stock in stocks:
            if stock['code'] not in codes and len(codes) < 32:
                codes.append(stock['code'])
    if len(codes) >= 32 and any(stock['code'] not in codes for _, _, _, stocks in prelim for stock in stocks):
        warnings.append('本期只为排名靠前方向的重点股票取日线均线，其余用当日报价价位。')
    levels_map, failed = ({}, [])
    if codes:
        try:
            levels_map, failed = market_pulse.stock_daily(store, codes, day, now)
        except Exception as exc:
            failed = codes
            warnings.append('候选股日线未取得：' + _reason(exc))
    if failed:
        warnings.append(f'{len(failed)} 只候选股日线未取得，买入时机只用当日报价价位。')
    state = regime(pulse, summary)
    directions = []
    if closed:
        rejected = 0
        for code in list(levels_map):
            rows, row = levels_map[code], stats.get(code)
            if rows and row and rows[-1]['date'] == day and abs(rows[-1]['close'] - row['price']) > max(.02, row['price'] * .001):
                # A different close means the daily series and the quote batch disagree;
                # never draw levels from a misaligned source.
                levels_map.pop(code)
                rejected += 1
        if rejected:
            warnings.append(f'{rejected} 只候选股的日线收盘与当日报价不一致，均线不展示。')
    levels_by_code = {code: _levels(rows, day, closed) for code, rows in levels_map.items()}
    for score, idea, value, preliminary in prelim:
        stocks = pick_stocks(idea, quotes, pool, levels_by_code, day, closed)
        candidate = (idea.get('stocks') or [{}])[0]
        peers = []
        for item in (idea.get('stocks') or [])[1:3]:
            stats_row = stats.get(item['code'])
            peers.append(dict(code=item['code'], name=item['name'],
                              stop=_round(stats_row['low'] * 0.98) if stats_row else None))
        candidate_stocks = [stock for stock in stocks if stock['role'] == '低吸候选']
        entry_stop = candidate_stocks[0]['entry']['stop'] if candidate_stocks else None
        peer_stops = {item['code']: item['stop'] for item in peers if item.get('stop') is not None}
        direction = dict(sector=idea['sector'], sector_code=idea['sector_code'], sector_kind=idea.get('sector_kind') or '行业',
                         change=idea.get('change'), net=idea.get('net'),
                         net_5d=value['net_5d'], net_5d_days=value['days'] if value['net_5d'] is not None else None,
                         score=score, score_parts=value['parts'], candidate=dict(code=candidate.get('code'), name=candidate.get('name')),
                         peers=peers, stocks=stocks, entry_stop=entry_stop, peer_stops=peer_stops,
                         closed=closed, news_title=idea.get('news_title'),
                         opportunity=_opportunity(idea, value, pool, stats),
                         logic=_logic(idea, value, pool, capital, value['days']),
                         risk=(idea.get('risk') or '') + (' 最高 5 板以上，注意断板风险。' if senti and senti.get('max_board', 0) >= 5 else ''),
                         evidence=_evidence(idea, capital, value, pool),
                         timing=_timing(idea, stocks, value, state, (pulse.get('market') or {}).get('breadth'), closed, day))
        if entry_stop is not None:
            result = assess(direction, quotes, day, (pulse.get('market') or {}).get('breadth'))
        else:
            result = dict(status='missing', why='候选股数据不完整。')
        direction['state'], direction['why'] = state_of(result, direction, value['net_5d'])
        direction['_assess'] = result['status']
        directions.append(direction)
    if not directions:
        warnings.append('本轮没有同时满足资金/趋势/人气的方向，等待下一期研判。')
    for rank, direction in enumerate(directions, 1):
        direction['rank'] = rank
    hotspots = (pulse or {}).get('hotspots') or {}
    for item in hotspots.get('news') or []:
        item['match'] = None
        for direction in directions:
            if theme_discovery.key(direction['sector']).casefold() in item['title'].casefold():
                item['match'] = direction['sector']
                break
    ordered_keys = ['rank', 'sector', 'sector_code', 'sector_kind', 'change', 'net', 'net_5d', 'net_5d_days',
                    'score', 'score_parts', 'state', 'why', 'opportunity', 'logic', 'risk', 'candidate', 'peers',
                    'stocks', 'timing', 'evidence']
    clean = [{key: direction[key] for key in ordered_keys if key in direction and key != 'stocks'}
             for direction in directions]
    for row, direction in zip(clean, directions):
        row['stocks'] = direction['stocks']
        row['news_title'] = direction.get('news_title')
    if capital is None:
        warnings.append('资金数据缺失，方向评分中的资金项按 0 计算。')
    if not capital_by_code:
        warnings.append('板块资金历史不足 3 个采集日，方向不展示近 5 日累计。')
    return dict(verdict=state['verdict'], bias=state['bias'], position=state['position'], horizon='未来 1–3 个交易日',
                focus=focus_of(clean), top_picks=top_picks(state, clean),
                directions=clean, playbooks=playbooks(pulse, state, clean),
                timetable=timetable(pulse, state, clean), risk=risk_items(pulse, state, clean, warnings),
                warnings=warnings)
