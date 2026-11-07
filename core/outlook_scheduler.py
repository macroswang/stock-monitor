"""App-owned half-hourly research. No Codex process, API key or order interface."""
import json
import math
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from . import breadth, disclosure_themes, sector_flow, sector_members, theme_discovery
from .provider import CN, get, now_cn

INTERVAL_MINUTES = 30
SCREEN_VERSION = 7
NON_BUSINESS = re.compile('重仓|参股|解禁|ST|央企50|融资融券|整体上市|改革|持股|沪深300|次新|上证|深证|三板|举牌|增持|破净|送转|预盈|预增|低价股|高价股|资产注入|外资背景|地域|地区|股权|本月|B股|综合行业')
CAUTION = re.compile('下滑|下降|下调|萎缩|回撤|收紧|下跌|走弱|亏损|立案|起火|冲突|预警|抵制|暴跌|出口限制|制裁')
SUPPORT = re.compile('增长|上调|获批|投产|中标|扩产|签约|保供|订单增加|提高补贴|需求回升|增产|复产')


def due_slot(now):
    local = now.astimezone(CN)
    start = local.replace(minute=local.minute // INTERVAL_MINUTES * INTERVAL_MINUTES, second=0, microsecond=0)
    return start.strftime('%Y-%m-%d %H:%M')



def news(region, lid, now):
    payload = json.loads(get(f'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid={lid}&num=50&page=1'))
    rows = []
    for item in payload['result']['data']:
        stamp = datetime.fromtimestamp(int(item['ctime']), CN)
        title, url = (item.get('title') or '').strip(), item.get('url') or ''
        if now-timedelta(hours=72) <= stamp <= now and title and url.startswith(('https://','http://')):
            rows.append(dict(region=region, time=stamp.isoformat(), title=title, url=url))
    if not rows:
        raise ValueError('近期新闻不足')
    return rows


def market(store, now):
    day = sector_flow.expected_day(now)
    if not day:
        raise ValueError('交易日历未就绪')
    def cached(kind):
        values = store.getcache(breadth.CODE, kind, day)
        return values[0]['data'] if values else {}
    summary, raw = cached(breadth.KIND), cached('breadth_raw_v1')
    if not (breadth.valid_closed_breadth(summary, day, now) and raw.get('collected_at') == summary.get('collected_at')):
        summary, raw = breadth.collect()
    if (summary['date'] != day or raw['date'] != day or summary['missing'] or
            summary['expected'] != summary['covered'] or raw['collected_at'] != summary['collected_at'] or
            summary['status'] not in ('closed','provisional')):
        raise ValueError('完整沪深行情未就绪')
    return summary, {q['code']: q for q in raw['quotes']}


def members(code):
    """Turnover leaders, not a claim to compare every constituent."""
    if re.fullmatch(r'(new_|gn_)[A-Za-z0-9]+', code):
        params = dict(node=code, page=1, num=40, sort='amount', asc=0)
        rows = json.loads(get(sector_members.BASE + 'getHQNodeData?' + urlencode(params)))
        return [(r['symbol'], r['name']) for r in rows]
    if re.fullmatch(r'BK\d+', code):
        params = dict(fs='b:'+code,pn=1,pz=40,po=1,np=1,fltt=2,fid='f6',fields='f12,f13,f14')
        rows = json.loads(get(sector_flow.URL+'?'+urlencode(params)))['data']['diff']
        return [(('sh' if r['f13']==1 else 'sz')+r['f12'], r['f14']) for r in rows if r['f13'] in (0,1)]
    raise ValueError('板块成分代码无效')


def ranked_sectors(sectors, feeds, exclusions):
    ranked = []
    for row in sectors:
        name = re.sub(r'行业$|概念$', '', row['name'])
        if len(name)<2 or NON_BUSINESS.search(row['name']):
            exclusions[row['code']] = '本轮筛选只比较有明确业务方向的行业或概念。'
            continue
        hits = [n for n in feeds if theme_discovery.key(name) in re.sub(r'\s+', '', n['title']).casefold()]
        head = max(hits, key=lambda n:n['time'], default=None)
        # Require relative interest in the form of a rising sector. A news mention
        # alone never establishes a buying opportunity.
        pct, net = row['change_percent'], row['net_yuan']
        if pct <= 0:
            exclusions[row['code']] = f"筛选时板块涨跌幅为 {pct:+.2f}%，未高于零。"
            continue
        if net <= 0 and not hits:
            exclusions[row['code']] = '筛选时板块没有资金净流入，本轮新闻中也没有匹配到板块消息。'
            continue
        news_weight = (-0.5 if CAUTION.search(head['title']) else 0.7 if SUPPORT.search(head['title']) else 0.1) if head else 0
        score = (2 if net>0 else 0) + min(pct,3) + news_weight
        ranked.append((score, row, head))
    return sorted(ranked, key=lambda v:(-v[0],v[1]['code']))


def select_stocks(rows, quotes, used):
    eligible = {}
    for code,name in rows:
        q = quotes.get(code)
        if not q or not re.fullmatch(r'(sh6|sz[03])\d{5}',code) or re.search(r'ST|退|^[NC]',name.upper()):
            continue
        low, prev, price, amount = (float(q[k] or 0) for k in ('day_low','previous_close','price','amount_yuan'))
        if not all(math.isfinite(x) and x>0 for x in (low,prev,price,amount)) or low>price:
            continue
        eligible[code] = (code, name, low, (price/prev-1)*100, amount, low<=prev<price)
    active = sorted(eligible.values(),key=lambda x:-x[4])
    choices = [r for r in active if r[0] not in used and 0<r[3]<5 and r[4]>=50_000_000]
    if len(active)<3:
        return None, f'本轮只有 {len(active)} 只有效报价，凑不齐候选和两只同行。'
    if not choices:
        return None, '活跃成分股里没有同时满足当日上涨不足 5%、成交至少 5000 万元且未被其他方向选中的新候选。'
    lead = max(choices,key=lambda r:(r[5],r[4]))
    peers = [r for r in active if r[0]!=lead[0]][:2]
    if not any(r[3]>0 for r in peers):
        peer_moves = '、'.join(f'{r[1]} {r[3]:+.2f}%' for r in peers)
        return None, f'{lead[1]}涨 {lead[3]:.2f}%，但成交额排在前面的两只对照股（{peer_moves}）都没有上涨。'
    return [lead,*peers], None


def produce(store, now):
    with ThreadPoolExecutor(5) as pool:
        m = pool.submit(market,store,now)
        sf = [pool.submit(sector_flow.fetch,now,k) for k in ('industry','concept')]
        nf = [pool.submit(news,r,lid,now) for r,lid in [('domestic',2517),('international',2518)]]
        summary, quotes = m.result()
        industry,concept = (f.result() for f in sf)
        domestic,international = (f.result() for f in nf)
    if any(s['date']!=summary['date'] for s in (industry,concept)):
        raise ValueError('板块与沪深行情日期未对齐')
    feeds = domestic+international
    boards=industry['sectors']+concept['sectors']
    pools,discovery=theme_discovery.discover(summary['date'],feeds,boards,store,now)
    # Compare up to 40 active stocks per theme, the same turnover limit used for quoted sectors.
    sizes={code:len(members) for code,(_,members) in pools.items()}
    pools={code:(name,sorted(members,key=lambda m: (-float(quotes.get(m[0],{}).get('amount_yuan') or 0),m[0]))[:40])
           for code,(name,members) in pools.items()}
    themes, custom = disclosure_themes.collect(quotes,summary['date'],summary.get('status')=='closed',pools)
    for t in themes:
        t['matched_count']=sizes[t['code']]
        if t['code'] in discovery['filing_errors']:
            t['error']='本次公告查询失败，无法核对该方向的最新公司名单；继续等。'
    custom=[r for r in custom if r['code'] not in discovery['filing_errors']]
    exclusions = {t['code']:t['error'] for t in themes if 'error' in t}
    universe = industry['sectors'] + concept['sectors'] + custom
    ranked = ranked_sectors(universe, feeds, exclusions)
    kinds = {row['code']: kind for kind, rows in [('行业', industry['sectors']), ('概念', concept['sectors']), ('补充题材', custom)] for row in rows}
    ideas, used, groups, missed = [], set(), [], 0
    baskets={t['code']:[(m['code'],m['name']) for m in t['members']] for t in themes}
    def constituents_for(code):
        return baskets[code] if code in baskets else members(code)
    with ThreadPoolExecutor(4) as pool:
        jobs = [(row,head,pool.submit(constituents_for,row['code'])) for _,row,head in ranked]
        for row,head,future in jobs:
            try:
                constituents = future.result()
                if not constituents: raise ValueError('成分为空')
            except Exception:
                exclusions[row['code']] = '本轮未取得板块成分，无法比较个股。'
                missed += 1
                continue
            basket = {c for c,_ in constituents}
            overlap = next((name for name,g in groups if len(basket&g) >= 0.65*min(len(basket),len(g))), None)
            if overlap:
                exclusions[row['code']] = f'与排序在前的「{overlap}」活跃成分股高度重合，本轮合并展示。'
                continue
            stocks, reason = select_stocks(constituents, quotes, used)
            if not stocks:
                exclusions[row['code']] = reason
                continue
            positive = row['net_yuan']>0
            supportive = bool(head and SUPPORT.search(head['title']) and not CAUTION.search(head['title']))
            firm = all(r[3]>0 for r in stocks)
            allow = positive and (not head or not CAUTION.search(head['title'])) and (firm or supportive)
            reason = f"板块涨 {row['change_percent']:.2f}%，资金净{'流入' if positive else '流出'} {abs(row['net_yuan'])/1e8:.2f} 亿元；{stocks[0][1]}涨 {stocks[0][3]:.2f}%，两只活跃同行中有 {sum(r[3]>0 for r in stocks[1:])} 只上涨。"
            risk = ('板块仍在净流出，等资金回流。' if not positive else
                    '消息含有不利或不确定因素，先等后续确认。' if head and CAUTION.search(head['title']) else
                    '同行走势还不够一致，继续等。' if not allow else '若板块资金转为流出或候选跌破参考低点，继续等。')
            ideas.append(dict(sector=row['name'],sector_code=row['code'],sector_kind=kinds[row['code']],reason=reason,risk=risk,
                              news_title=head['title'] if head else None,news_region=head['region'] if head else None,
                              sources=[head] if head else [],allow_entry=allow,
                              stocks=[dict(code=c,name=n,low=l) for c,n,l,*_ in stocks]))
            used.add(stocks[0][0]); groups.append((row['name'],basket))
    if ranked and missed==len(ranked):
        raise ValueError('所有候选板块成分均未取得')
    return dict(exclusions=exclusions, directory={r['code']:r['name'] for r in boards}, discovery=discovery, themes=themes, quote_date=summary['date'],covered=summary['covered'],
                coverage=dict(industry=len(industry['sectors']),concept=len(concept['sectors']),disclosed=len(themes),unavailable=missed),
                news_counts=dict(domestic=len(domestic),international=len(international)),ideas=ideas)


def write_issue(folder, issue, stamp):
    folder.mkdir(parents=True,exist_ok=True)
    target = folder/(stamp.strftime('%Y-%m-%d_%H%M%S_%f')+'.json')
    with tempfile.NamedTemporaryFile(dir=folder,mode='w',encoding='utf-8',delete=False) as tmp:
        try:
            json.dump(issue,tmp,ensure_ascii=False,allow_nan=False)
            tmp.flush();os.fsync(tmp.fileno())
        except BaseException:
            os.unlink(tmp.name);raise
    os.replace(tmp.name,target)
    return target


class OutlookScheduler:
    def __init__(self, app):
        self.app = app
        self.done = None
        self.state = '等待定时更新'

    def tick(self, clock=now_cn, generator=produce):
        now = clock()
        slot = due_slot(now)
        if slot==self.done: return
        folder = Path(self.app.dir)/'daily-outlook'
        for path in sorted(folder.glob(slot[:10]+'_*.json'), reverse=True):
            try:
                issue = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(issue.get('native_slot'), str) and issue['native_slot'] < slot:
                    break
                if issue.get('native_slot')==slot and issue.get('screen_version')==SCREEN_VERSION:
                    self.done=slot;self.state='本期已更新';return
            except (ValueError,OSError,AttributeError): pass
        self.state='正在筛选'
        try:
            issue = generator(self.app.store,now)
            stamp = clock()
            if due_slot(stamp)!=slot: return
            issue.update(native_slot=slot,published_at=stamp.isoformat(),screen_version=SCREEN_VERSION)
            write_issue(folder,issue,stamp)
            self.done=slot;self.state='本期已更新'
        except Exception:
            self.state='更新未完成，5 分钟后重试'

    def run(self):
        while not self.app.stop.is_set():
            self.tick()
            now = now_cn()
            next_slot = now.replace(second=0, microsecond=0) + timedelta(minutes=INTERVAL_MINUTES - now.minute % INTERVAL_MINUTES)
            remaining = (next_slot - now).total_seconds()
            interval = 300 if self.state.startswith('更新未完成') else 10
            self.app.stop.wait(min(interval, remaining))
