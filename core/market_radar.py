"""炒作/概念雷达：名称辈、生肖玄学、事件/产业题材。

回答“这种题材或玄学炒作能否提前识别”。只做数据统计与阶段标记（启动/发酵/加速/分歧/退潮），
纯情绪炒作只建议小仓或观察，不构成投资建议。
"""
import math
import re
from . import market_pulse, market_plan, theme_discovery

ZODIAC = ('鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊', '猴', '鸡', '狗', '猪')
HOMOPHONES = {'马': ('马', '玛'), '羊': ('羊', '阳', '洋', '扬')}
META = re.compile('字辈|生肖|玄学|谐音|跨年|属相|名字')
QUOTED = re.compile(r'[“"]([^”"]{1,6})[”"]')
FILLER = re.compile('科技|股份|电子|智能|新能|能源|电力|环保|医药|生物|材料|控股|集团|发展|国际|中国|华夏|中科|创新|产业|经济|行业|板块|概念|涨停|连板|首板|公司|机械|化工|实业|投资')
STAGE_ORDER = {'启动初期': 0, '发酵': 1, '加速/高潮': 2, '分歧': 3, '退潮': 4, '观察': 5}
VERDICT = {'启动初期': '可小仓试错（≤0.5 成）', '发酵': '回踩低吸，不追高',
           '加速/高潮': '只观察，不追高', '分歧': '只观察，等重新一致', '退潮': '回避', '观察': '先观察'}
STAGE_NOTE = {'启动初期': '近 2 日首次出现同题材 2 家以上涨停，尚未加速',
              '发酵': '涨停扩散且资金/新闻跟进',
              '加速/高潮': '连板高度或涨停家数快速抬升，接力风险高',
              '分歧': '涨停数回落或昨日涨停今日转弱',
              '退潮': '近 5 日有热度但今日已无涨停',
              '观察': '信号不足，先观察'}
NAME_RISK = '纯名称/情绪炒作，无基本面证据；历史上退潮回撤大，只宜小仓短线。'
EVENT_RISK = '事件/题材驱动需要确认持续性；新闻热度不等于订单或业绩。'
# keyword -> theme label; concept boards and news are matched through these aliases.
NEWS_NOISE = re.compile('话术|回收|新手|广告|招聘|促销|直播|视频|揭秘|测评|推荐|开户|佣金')
THEMES = (
    ('AI硬件/算力', ('算力', '光模块', '半导体', '英伟达', '数据中心', '服务器', '液冷', 'PCB', '存储芯片')),
    ('光伏/新能源', ('光伏', '硅料', '组件', '逆变器', '储能', '新能源')),
    ('冰雪经济', ('冰雪', '滑雪', '雪场', '冰雪旅游', '消费券')),
    ('人形机器人', ('人形机器人', '机器人', '减速器')),
    ('固态电池', ('固态电池', '锂电', '电池')),
    ('低空经济', ('低空', '无人机', 'eVTOL', '飞行汽车')),
    ('可控核聚变', ('核聚变', '聚变')),
    ('创新药', ('创新药', '医保', '集采', '减肥药')),
    ('稀土/资源', ('稀土', '小金属', '黄金', '铜价', '钨')),
    ('消费/跨年', ('跨年', '春节', '消费券', '旅游', '年货')),
)


def _clean(name):
    return re.sub(r'\s+', '', name or '')


def _quoted_tokens(reason):
    tokens = []
    for match in QUOTED.findall(reason or ''):
        token = _clean(match)
        if 1 <= len(token) <= 4 and token not in tokens:
            tokens.append(token)
    return tokens


def _zodiac_groups(year):
    groups = []
    for offset in (0, 1):
        cycle = ZODIAC[(year + offset - 4) % 12]
        chars = HOMOPHONES.get(cycle, (cycle,))
        if offset == 0 and len(chars) == 1:
            continue  # a single current-year character is too common to call a theme
        groups.append(dict(token=cycle, chars=chars, label=f'{year + offset} {cycle}年' + ('（跨年）' if offset else ''),
                           kind='生肖/玄学'))
    return groups


def _match(row, cluster):
    name, reason = row.get('name') or '', row.get('reason') or ''
    if cluster['kind'] == '生肖/玄学':
        chars = cluster['chars']
        return any(char in name for char in chars) or (bool(META.search(reason)) and any(char in reason for char in chars))
    token = cluster['token']
    return token in name or (bool(META.search(reason)) and token in reason)


def _cluster_rows(cluster, days, rows_by_day):
    counts, rows = [], []
    for day in days:
        found = [row for row in rows_by_day.get(day, []) if _match(row, cluster)]
        counts.append(len(found))
        rows.append(found)
    return counts, rows


def _leader(rows):
    def height(row):
        boards = row.get('boards') or 0
        return boards if row.get('days') == row.get('boards') else 0
    return max(rows, key=lambda row: (row.get('boards') or 0, height(row), row.get('order_amount') or 0), default=None)


def _stage(counts, max_board, performance):
    today, previous = counts[-1], counts[-2] if len(counts) > 1 else 0
    if today >= 2 and max(counts[:-1] or [0]) == 0:
        return '启动初期'
    if max_board >= 4 or today >= 6 or (today >= 3 and today >= previous * 1.5):
        return '加速/高潮'
    if today >= 2 and today >= previous and previous >= 1:
        return '发酵'
    if today >= 1 and (today < previous or (performance and performance.get('checked')
                                            and performance['advance'] * 2 < performance['checked'])):
        return '分歧'
    if today == 0 and sum(counts[:-1]) >= 3:
        return '退潮'
    return '观察'


def _stage_risk(stage, base):
    extra = {'启动初期': ' 首板阶段辨识度低，次日不接力则放弃。',
             '发酵': ' 扩散到跟风股时追高风险上升。',
             '加速/高潮': ' 已在高位，断板易连续回落。',
             '分歧': ' 分歧期只做低吸，不做打板。',
             '退潮': ' 退潮期原则上不参与。'}.get(stage, '')
    return base + extra


def _watch(stage):
    return {'启动初期': ['次日同题材首板 ≥2 家且龙头不炸板', '板块资金连续 2 日净流入', '出现新的新闻/政策跟进'],
            '发酵': ['龙头封板率不下降', '跟风股不出现批量跌停', '分歧回踩不破防守位'],
            '加速/高潮': ['只剩观察价值；断板或炸板增加即离场', '不接高位加速'],
            '分歧': ['缩量回踩后重新转强再看', '板块资金重新净流入']}.get(stage, ['等新一轮异动或首个同题材涨停再现'])


def _news_hits(news, keywords):
    keys = [item.casefold() for item in keywords]
    return [item for item in news if not NEWS_NOISE.search(item.get('title') or '')
            and any(key in (item.get('title') or '').casefold() for key in keys)]


def _limit_stocks(rows, stats, limit=2):
    output = []
    def height(row):
        boards = row.get('boards') or 0
        return boards if row.get('days') == row.get('boards') else 0
    ranked = sorted(rows, key=lambda row: (row.get('boards') or 0, height(row), row.get('order_amount') or 0),
                    reverse=True)
    for row in ranked[:limit]:
        stat = stats.get(row['code'])
        if not stat:
            continue
        role = '龙头' if not output else '跟风'
        output.append(dict(code=row['code'], name=row['name'], role=role,
                           price=round(stat['price'], 2), percent=round(stat['pct'], 2),
                           boards=row.get('boards'), limit_tag='涨停', reason=row.get('reason') or None,
                           levels=None, entry=market_plan.stock_entry(stat, None, role)))
    return output


def _candidate(names, stats, cluster, used, limit=1):
    token, chars = cluster.get('token'), cluster.get('chars') or ()
    output = []
    for code, name in names.items():
        if code in used or not isinstance(name, str) or re.search('ST|退', name.upper()):
            continue
        hit = any(char in name for char in chars) if cluster['kind'] == '生肖/玄学' else token in name
        if not hit:
            continue
        stat = stats.get(code)
        if not stat or not (0 < stat['pct'] < 5) or stat['amount'] < 50_000_000:
            continue
        output.append(dict(code=code, name=name, role='低吸候选', price=round(stat['price'], 2),
                           percent=round(stat['pct'], 2), boards=0, limit_tag=None, reason=None,
                           levels=None, entry=market_plan.stock_entry(stat, None, '低吸候选'),
                           amount=stat['amount']))
    output.sort(key=lambda row: row['amount'], reverse=True)
    return output[:limit]


def _name_radar(days, rows_by_day, names, news, concept, stats):
    today_rows = rows_by_day.get(days[-1], [])
    clusters, zodiac = {}, {group['token']: group for group in _zodiac_groups(int(days[-1][:4]))}
    for row in today_rows:
        reason = row.get('reason') or ''
        for token in _quoted_tokens(reason):
            if token in zodiac:
                group = zodiac[token]
                clusters['zodiac:' + token] = dict(key='zodiac:' + token, kind='生肖/玄学', token=token,
                                                   chars=group['chars'], label=group['label'])
            else:
                clusters.setdefault('name:' + token, dict(key='name:' + token, kind='名称类', token=token, label=token))
        if META.search(reason):
            for group in zodiac.values():
                if any(char in reason for char in group['chars']):
                    clusters['zodiac:' + group['token']] = dict(key='zodiac:' + group['token'], kind='生肖/玄学',
                                                                token=group['token'], chars=group['chars'],
                                                                label=group['label'])
    for row in today_rows:
        name = row.get('name') or ''
        for index in range(len(name) - 1):
            token = name[index:index + 2]
            if len(token) != 2 or FILLER.search(token) or any(char.isdigit() for char in token):
                continue
            if ('name:' + token) in clusters:
                continue
            if sum(1 for other in today_rows if token in (other.get('name') or '')) >= 3:
                clusters['name:' + token] = dict(key='name:' + token, kind='名称类', token=token, label=token)
    items = []
    for cluster in clusters.values():
        counts, rows = _cluster_rows(cluster, days, rows_by_day)
        if counts[-1] == 0 and sum(counts) < 3:
            continue
        leader = _leader(rows[-1])
        max_board = max((row.get('boards') or 0) for row in rows[-1]) if rows[-1] else 0
        previous_rows = rows[-2] if len(rows) > 1 else []
        moves = [stats[row['code']]['pct'] for row in previous_rows if row['code'] in stats]
        performance = None
        if previous_rows and len(moves) >= max(3, math.ceil(.8 * len(previous_rows))):
            performance = dict(checked=len(moves), advance=sum(1 for move in moves if move > 0),
                               avg=round(sum(moves) / len(moves), 2))
        stage = _stage(counts, max_board, performance)
        if stage == '观察' and counts[-1] < 2:
            continue
        stocks = _limit_stocks(rows[-1], stats)
        stocks += _candidate(names, stats, cluster, {row['code'] for row in stocks})
        hits = _news_hits(news, [cluster['token']]) if cluster.get('token') else []
        net = change = None
        for sector in (concept or {}).get('sectors') or []:
            if cluster.get('token') and cluster['token'] in sector['name']:
                net, change = sector['net_yuan'], sector['change_percent']
                break
        signals = [f"今日涨停 {counts[-1]} 家（昨日 {counts[-2] if len(counts) > 1 else 0} 家、近 5 日 {sum(counts)} 家）"]
        if leader:
            signals.append(f"最高 {max_board} 板（{leader['name']}）")
        if performance:
            signals.append(f"昨日涨停今日 {performance['advance']}/{performance['checked']} 上涨，平均 {performance['avg']:+.2f}%")
        if hits:
            signals.append(f'近 72 小时新闻提及 {len(hits)} 条')
        if net is not None:
            signals.append(f'关联概念资金 {net / 1e8:+.2f} 亿元，涨幅 {change:+.2f}%')
        evidence = [dict(label='涨停池', value=' / '.join(f'{row["name"]}({row.get("reason") or "原因未标注"})'
                                                       for row in rows[-1][:3]) or '今日无涨停',
                       source='同花顺涨停池（当日+近 5 交易日）')]
        if hits:
            evidence.append(dict(label='新闻', value=hits[0]['title'][:48], source='新浪滚动新闻'))
        items.append(dict(theme=cluster['label'], kind=cluster['kind'], stage=stage,
                          stage_note=STAGE_NOTE[stage], signals=signals,
                          limit_up_today=counts[-1], limit_up_prev=counts[-2] if len(counts) > 1 else 0,
                          limit_up_5d=sum(counts), max_board=max_board, news_count=len(hits),
                          net_yuan=net, change=change, verdict=VERDICT[stage],
                          risk=_stage_risk(stage, NAME_RISK + ' 候选股均线未取，只按当日报价价位。'),
                          watch=_watch(stage), stocks=stocks, evidence=evidence,
                          _heat=counts[-1] * 2 + max_board))
    items.sort(key=lambda item: (STAGE_ORDER[item['stage']], -item['_heat']))
    return items


def _event_radar(day, now, rows_today, news, concept, directions, stats):
    output = []
    sectors = (concept or {}).get('sectors') or []
    direction_by_key = {theme_discovery.key(row['sector']): row for row in directions}
    for label, keywords in THEMES:
        hits = _news_hits(news, keywords)
        members = [row for row in rows_today
                   if any(key.casefold() in (row.get('reason') or '').casefold() for key in keywords)]
        board = None
        for sector in sectors:
            if any(key in sector['name'] or theme_discovery.key(sector['name']) in key for key in keywords):
                board = sector
                break
        if not hits and not members:
            continue
        change = board['change_percent'] if board else None
        net = board['net_yuan'] if board else None
        if board and change <= 0 and net <= 0:
            continue
        # One stock's tag alone is not a theme; require news or a matched concept board.
        if not (hits or (board and members)):
            continue
        latest = max((item['time'] for item in hits), default='')
        stage = '观察'
        if len(hits) >= 2 and len(members) <= 1 and (change is None or change < 3):
            stage = '启动初期'
        elif len(members) >= 3 or (change is not None and change >= 4):
            stage = '加速/高潮'
        elif members and (change is None or change > 0) and (net is None or net > 0):
            stage = '发酵'
        elif members and ((change is not None and change < 0) or (net is not None and net < 0)):
            stage = '分歧'
        if stage == '观察':
            continue
        direction = None
        for key in keywords:
            direction = direction_by_key.get(theme_discovery.key(key))
            if direction:
                break
        stocks = []
        if direction:
            stocks = [{k: stock[k] for k in ('code', 'name', 'role', 'price', 'percent', 'boards', 'limit_tag',
                                            'reason', 'levels', 'entry') if k in stock}
                      for stock in (direction.get('stocks') or [])[:3]]
        if not stocks:
            stocks = _limit_stocks(members, stats, limit=2)
        signals = []
        if hits:
            signals.append(f'近 72 小时新闻 {len(hits)} 条（最新 {latest[5:16].replace("T", " ") }）')
        if board:
            signals.append(f'概念「{board["name"]}」当日 {change:+.2f}%，资金 {net / 1e8:+.2f} 亿元')
        if members:
            signals.append(f'概念内涨停 {len(members)} 家')
        evidence = []
        if hits:
            evidence.append(dict(label='新闻', value=hits[0]['title'][:48], source='新浪滚动新闻（72 小时）'))
        if board:
            evidence.append(dict(label='概念资金', value=f'{board["name"]} {change:+.2f}% / {net / 1e8:+.2f} 亿',
                                 source='行业/概念资金快照'))
        verdict = VERDICT[stage]
        if not stocks:
            verdict = '先观察，等首批涨停或资金确认'
        output.append(dict(theme=label, kind='事件/题材', stage=stage, stage_note=STAGE_NOTE[stage], signals=signals,
                           limit_up_today=len(members), limit_up_prev=None, limit_up_5d=None,
                           max_board=max((row.get('boards') or 0) for row in members) if members else 0,
                           news_count=len(hits), net_yuan=net, change=change, verdict=verdict,
                           risk=_stage_risk(stage, EVENT_RISK), watch=_watch(stage),
                           stocks=stocks, evidence=evidence, _heat=len(hits) + len(members)))
    output.sort(key=lambda item: (STAGE_ORDER[item['stage']], -item['_heat']))
    return output


def build(store, summary, quotes, concept, feeds, sentiment, directions, now=None):
    day = summary['date']
    now = now or market_pulse.now_cn()
    warnings = []
    pools = (sentiment or {}).get('_days')
    if not pools:
        return dict(items=[], summary='', warnings=['涨停池多日明细未取得，炒作雷达暂不可用。'])
    days = sorted(pools)[-5:]
    rows_by_day = {stamp: pools[stamp].get('rows') or [] for stamp in days}
    stats = market_plan.quote_stats(quotes, day)
    try:
        names = market_pulse.name_universe(store, day, now)
    except Exception:
        names = {}
        warnings.append('全市场名称表未取得，名称类炒作的“低吸候选”暂缺。')
    try:
        name_items = _name_radar(days, rows_by_day, names, feeds or [], concept, stats)
    except Exception as exc:
        name_items = []
        warnings.append('名称类炒作雷达未完成：' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
    try:
        event_items = _event_radar(day, now, rows_by_day.get(day, []), feeds or [], concept, directions or [], stats)
    except Exception as exc:
        event_items = []
        warnings.append('事件/题材雷达未完成：' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
    combined, seen = [], set()
    for item in sorted(name_items[:3] + event_items[:2], key=lambda item: (STAGE_ORDER[item['stage']], -item['_heat'])):
        key = (item['kind'], item['theme'])
        if key in seen:
            continue
        seen.add(key)
        combined.append(item)
    combined = [{key: value for key, value in item.items() if key != '_heat'} for item in combined][:5]
    starts = sum(1 for item in combined if item['stage'] == '启动初期')
    summary_text = ''
    if combined:
        summary_text = (f"识别 {len(combined)} 个 · 启动初期 {starts} 个 · "
                        f"名称/玄学 {sum(1 for item in combined if item['kind'] != '事件/题材')} 个")
    return dict(items=combined, summary=summary_text, warnings=warnings)
