"""Discover recent topics from market activity and headlines; verify business ties separately."""
import hashlib
import html
import json
import re
from http.client import HTTPException
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from .provider import get, symbol, now_cn
from . import theme_sources
from .index_technical import trading_day

EVIDENCE = Path(__file__).resolve().parent.parent / 'fixtures' / 'outlook_company_evidence.json'
MARKET = 'https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool'
NOISE = re.compile('字辈|复牌|摘帽|重整|重组|实控人|国资|股权|业绩|季报|年报|半年报|增持|扭亏|资产|简称|龙虎榜|借壳|变更|回购|分红|次新|低价|超跌|拟收购|预增|减持|亏损收窄|减亏|央企$|协议转让|资产注入|高送转|更名')
ACTION = re.compile('订单|中标|签订|签署|投产|建设|投建|合同|定点|量产|生产线|项目.*进展|取得.*许可')
DENIAL = re.compile('澄清|终止|风险|异常波动|取消|减值|问询|解约|诉讼|关联交易预计|不涉及|尚未|未签|回复函|法律意见|核查意见|可行性|募集说明书|战略合作框架|意向书')
HEAD = re.compile(r'(?:^|[，、：:；！【】｜|\s])([A-Za-z0-9\u4e00-\u9fff·-]{2,12}?)(?:板块|概念)(?=股|集体|盘中|持续|走|涨|异动|拉升|活跃|爆发|领涨|反弹|崛起|回暖|[，：、\s]|$)')


def key(name):
    return re.sub(r'\s+|(?:行业|概念|板块)$','',name).casefold()


def observations(day):
    rows=[]
    for page in range(1,21):
        params=dict(date=day.replace('-',''),page=page,limit=100,filter='HS,GEM2STAR',
                    field='code,name,reason_type,high_days',order_field='199112',order_type='0')
        obj=json.loads(get(MARKET+'?'+urlencode(params)))['data']
        if obj['date']!=params['date'] or int(obj['page']['page'])!=page:
            raise ValueError('异动日期或分页未核对')
        rows.extend(obj['info'])
        if page>=int(obj['page']['count']):
            if len({r['code'] for r in rows})!=int(obj['page']['total']):
                raise ValueError('异动清单不完整')
            return rows
    raise ValueError('异动清单过长')


def notice_batch(kind, start, end):
    base='https://np-anotice-stock.eastmoney.com/api/security/ann?'
    rows={}
    total=None
    for page in range(1,101):
        params=dict(sr=-1,page_size=100,page_index=page,ann_type='A',client_source='web',
                    f_node=5,s_node=kind,begin_time=start,end_time=end)
        data=json.loads(get(base+urlencode(params)))['data']
        if int(data['page_index'])!=page or (total is not None and total!=int(data['total_hits'])):
            raise ValueError('公告目录在翻页中有变动')
        total=int(data['total_hits'])
        for row in data['list']:
            art=row['art_code']
            if not re.fullmatch(r'AN\d+',art) or not start<=row['notice_date'][:10]<=end:
                raise ValueError('公告日期或编号未核对')
            rows[art]=row
        if page*100>=total:
            if len(rows)!=total:raise ValueError('公告分页不完整')
            return list(rows.values())
    raise ValueError('公告目录超出读取范围')


def bulletin_library(day,store):
    # Closed calendar weeks are reused. Re-fetch the open week in each new screen.
    end=date.fromisoformat(day)
    spans=[]
    for kind,days in [(7,180),(8,30)]:
        last=end;floor=end-timedelta(days=days-1)
        while last>=floor:
            first=max(floor,last-timedelta(days=last.weekday()))
            spans.append((kind,first.isoformat(),last.isoformat()))
            last=first-timedelta(days=1)
    def chunk(span):
        kind,start,end=span;cache_id=f'outlook-bulletins:{kind}:{start}';cache_kind='bulk_v1'
        if store is not None:
            saved=store.getcache(cache_id,cache_kind,end)
            if saved:return saved[0]['data']['rows']
        for _ in range(2):
            try:
                data=[]
                for r in notice_batch(kind,start,end):
                    title=html.unescape(r['title'].split(':',1)[-1])
                    if not (ACTION.search(title) or DENIAL.search(title)):continue
                    for c in r['codes']:
                        if not re.fullmatch(r'(?:6|[03])\d{5}',c['stock_code']):continue
                        code=symbol(c['stock_code']);art=r['art_code']
                        url=f"https://data.eastmoney.com/notices/detail/{c['stock_code']}/{art}.html"
                        data.append((code,c['short_name'],r['notice_date'][:10],title,url))
                if store is not None and end!=day:store.cache(cache_id,cache_kind,end,{'rows':data})
                return data
            except (OSError,HTTPException,KeyError,TypeError,ValueError):pass
        raise ValueError('公告批次未完成')
    out=[];missing=0
    with ThreadPoolExecutor(4) as pool:
        jobs=[pool.submit(chunk,span) for span in spans]
        for job in jobs:
            try:out.extend(job.result())
            except ValueError:missing+=1
    return sorted(out,key=lambda x:x[2],reverse=True),missing


def filing_matches(name, rows):
    found={};denied=set()
    literal=theme_sources.topic_pattern([key(name)])
    for code,company,stamp,title,url in rows:
        title=html.unescape(re.sub('<[^>]+>','',title))
        if not literal.search(title):continue
        if re.search('终止|解约|取消|不涉及',title):
            denied.add(code);continue
        if (code in denied or not ACTION.search(title) or DENIAL.search(title)
                or ('采购' in title and not re.search('获得|中标|定点|订单|销售',title))):
            continue
        found.setdefault(code,(code,company,f'{stamp} 公司公告：{title}',url))
    return list(found.values()),denied


def current_evidence(member, day):
    match=re.search(r'(20\d\d)-?(\d\d)-?(\d\d)',member[3])
    end=date.fromisoformat(day)
    return match and end-timedelta(days=365)<=date.fromisoformat('-'.join(match.groups()))<=end


def discover(day, feeds, boards, store=None, now=None):
    # Historic filing evidence is an input, not the list of permitted themes.
    history=json.loads(EVIDENCE.read_text(encoding='utf-8'))
    history={ident:(name,[m for m in members if current_evidence(m,day)]) for ident,(name,members) in history.items()}
    history={ident:value for ident,value in history.items() if value[1]}
    names={key(n):n for n,_ in history.values()}
    official={key(b['name']) for b in boards}
    hints={}
    dates=[date.fromisoformat(day)-timedelta(days=i) for i in range(10)]
    days=[d.isoformat() for d in dates if trading_day(d) is True][:5]
    failed=0
    def clean(name):
        return (2<=len(name)<=16 and not NOISE.search(name) and re.fullmatch(r'[\w·-]+',name)
                and not name.isdecimal())
    with ThreadPoolExecutor(5) as pool:
        jobs={d:pool.submit(observations,d) for d in days}
        for d,job in jobs.items():
            try: rows=job.result()
            except (OSError,HTTPException,ValueError,KeyError,TypeError): failed+=1;continue
            for row in rows:
                for name in (row.get('reason_type') or '').split('+'):
                    name=name.strip()
                    if clean(name):
                        k=key(name);names.setdefault(k,name)
                        hints.setdefault(k,set()).add(row['code'])
    headlines=set()
    for item in feeds:
        for name in HEAD.findall(item['title']):
            if clean(name):
                k=key(name);names.setdefault(k,name);headlines.add(k)
    # Distinct issuers, not repeat mentions of one stock. Also admit a named news theme
    # before any stock has hit limit-up. Existing quoted boards already enter the ordinary screen.
    topics={k for k in hints if len(hints[k])>=2 or any(k in item['title'].casefold() for item in feeds)} | headlines
    prior={key(n):ident for ident,(n,_) in history.items()}
    eligible=(topics-official)|set(prior)
    pools={}
    errors={}
    library,missing=bulletin_library(day,store)
    extra,vetoes,unavailable=theme_sources.expand({k:names[k] for k in eligible},day,now or now_cn(),store,key)
    for k in sorted(eligible):
        ident=prior.get(k) or 'topic_'+hashlib.sha256(k.encode()).hexdigest()[:20]
        historical=history.get(ident,(None,[]))[1]
        matches,denied=filing_matches(names[k],library)
        denied.update(vetoes.get(k,set()))
        members={}
        for source in extra.values():
            members.update(source.get(k,{}))
        members.update((m[0],m) for m in historical)
        members.update((m[0],m) for m in matches)
        for code in denied:
            members.pop(code,None)
        if missing and len(members)<3:
            errors[ident]='部分公告未取得，其他来源也未补足三家公司'
        pools[ident]=(names[k],list(members.values()))
    return pools,dict(days=len(days),failed_days=failed,filing_errors=errors,
                      source_failures=unavailable,source_links={label:sum(len(v) for v in data.values()) for label,data in extra.items()},
                      bulletins=len({m[4] for m in library}),missing_batches=missing,observed=len(topics),outside=len(topics-official))
