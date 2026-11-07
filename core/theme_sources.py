"""Membership evidence from annual operating reviews, issuer answers and quoted concept boards."""
import base64
import gzip
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from http.client import HTTPException
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .provider import CN, symbol

FAILURES = (OSError, HTTPException, ValueError, KeyError, TypeError, IndexError)
ANNUAL = 'https://datacenter.eastmoney.com/securities/api/data/v1/get'
QUESTIONS = 'https://irm.cninfo.com.cn/newircs/index/search'
QUOTES = 'https://push2delay.eastmoney.com/api/qt/clist/get'
A_SHARE = re.compile(r'(?:6|[03])\d{5}$')
BUSINESS = re.compile('主营|研发|开发|生产|制造|批量|应用于|供应|供货|销售|订单|运营|推出|量产|提供|投产|产品包括|产品涵盖')
ISSUER = re.compile('公司|本集团|我们|本企业|主营业务|主要产品')
NEGATIVE = re.compile('政策环境|发展前景|行业前景|产业趋势|政策机遇|行业机遇|投资机会|战略规划|不涉及|未涉及|尚未|暂未|未开展|暂无|没有|不生产|未生产|不从事|无相关|未形成|不具备|无直接|计划|拟开展|拟进入|力争|有望|预计|敬请关注|行业趋势|据统计|市场规模')


def read_json(url, params, post=False):
    encoded=urlencode(params)
    req=Request(url if post else url+'?'+encoded,
                data=encoded.encode() if post else None,
                headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'gzip','Referer':url})
    with urlopen(req,timeout=12) as response:
        raw=response.read()
        if response.headers.get('Content-Encoding')=='gzip':
            raw=gzip.decompress(raw)
    return json.loads(raw)


def topic_pattern(names):
    def literal(k):
        # Avoid matching IP inside CHIP or 算力服务 inside 算力服务器.
        escaped=re.escape(k)
        if k=='高速':return r'高速(?=公路|收费|路网|通行)'
        if k.isascii(): return r'(?<![a-z0-9])'+escaped+r'(?![a-z0-9])'
        return escaped+(r'(?!器)' if k.endswith('服务') else '')
    return re.compile('|'.join(literal(k) for k in sorted(names,key=lambda k:(-len(k),k))),re.I)


def positive_links(text, pattern):
    text=html.unescape(re.sub(r'<[^>]*>','',text or ''))
    for sentence in re.split(r'[。！？；;\n]',text):
        if not ISSUER.search(sentence) or NEGATIVE.search(sentence):
            continue
        for match in pattern.finditer(sentence):
            excerpt=sentence[max(0,match.start()-52):match.end()+52].strip()
            context=sentence[max(0,match.start()-110):match.end()+52]
            if BUSINESS.search(excerpt) and ISSUER.search(context):
                yield match.group().casefold(),excerpt


def annual_evidence(names,day,store):
    today=date.fromisoformat(day)
    # Use the latest completed annual reporting season.
    year=today.year-(1 if today.month>=5 else 2)
    period=f'{year}-12-31'
    def page(num):
        ident=f'outlook-annual:{num}'
        if store:
            saved=store.getcache(ident,'operating_reviews_v1',period)
            if saved:
                cached=saved[0]['data']
                if datetime.fromisoformat(cached['cached_at']).date() >= today-timedelta(days=7):
                    return cached['pages'],json.loads(gzip.decompress(base64.b64decode(cached['payload'])))
        data=read_json(ANNUAL,dict(reportName='RPT_F10_OP_BUSINESSANALYSIS',
                       columns='SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,REPORT_NAME,BUSINESS_REVIEW',
                       filter=f"(REPORT_DATE='{period}')",pageSize=100,pageNumber=num,sortColumns='SECURITY_CODE',
                       sortTypes=1,source='HSF10',client='PC'))['result']
        pages=int(data['pages'])
        if not 1<=num<=pages<=200 or not data['data']:
            raise ValueError('年报目录未核对')
        rows=[(r['SECURITY_CODE'],r['SECURITY_NAME_ABBR'],r['BUSINESS_REVIEW']) for r in data['data']
              if A_SHARE.fullmatch(r['SECURITY_CODE']) and r['REPORT_DATE'][:10]==period and r['REPORT_NAME']==f'{year}年报']
        if store:
            payload=base64.b64encode(gzip.compress(json.dumps(rows,ensure_ascii=False).encode(),compresslevel=2)).decode()
            store.cache(ident,'operating_reviews_v1',period,dict(pages=pages,payload=payload))
        return pages,rows
    pattern=topic_pattern(names)
    found={}
    def consume(rows):
        for code,company,review in rows:
            ticker=symbol(code)
            for k,excerpt in positive_links(review,pattern):
                basket=found.setdefault(k,{})
                if ticker not in basket:
                    url='https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/Index?type=web&code='+ticker.upper()
                    basket[ticker]=(ticker,company,f'{year} 年报经营评述：{excerpt}',url)
    pages,rows=page(1)
    consume(rows)
    failed=0
    with ThreadPoolExecutor(4) as worker:
        jobs=[worker.submit(page,num) for num in range(2,pages+1)]
        for job in jobs:
            try:
                count,rows=job.result()
                if count!=pages:raise ValueError('年报目录变化')
                consume(rows)
            except FAILURES:failed+=1
    return found,failed


def answers(name,now):
    payload=read_json(QUESTIONS,dict(keyWord=name,pageNum=1,pageSize=50),post=True)
    pattern=topic_pattern([name.casefold()])
    found={};denied=set()
    rows=payload['results']
    for r in sorted(rows,key=lambda r:int(r.get('attachedPubDate') or 0),reverse=True):
        code=r.get('stockCode') or ''
        if not A_SHARE.fullmatch(code) or r.get('contentType')!=11:continue
        stamp=datetime.fromtimestamp(int(r.get('attachedPubDate') or 0)/1000,CN)
        if not now-timedelta(days=365)<=stamp<=now:continue
        answer=html.unescape(re.sub('<[^>]*>','',r.get('attachedContent') or ''))
        ticker=symbol(code)
        if ticker in found or ticker in denied:continue
        for sentence in re.split('[。！？；]',answer):
            if pattern.search(sentence) and re.search('不涉及|未涉及|无相关业务|未开展|不从事|没有相关|暂无相关',sentence):
                denied.add(ticker);break
        if ticker in denied:continue
        hit=next(positive_links(answer,pattern),None)
        if hit:
            url='https://irm.cninfo.com.cn/ircs/question/questionDetail?questionId='+str(r['indexId'])
            found[ticker]=(ticker,r['companyShortName'],f'{stamp.date()} 互动易公司回复：{hit[1]}',url)
    return found,denied


def board_evidence(names,day,normalize):
    def read_page(fs,page,size,fields,sort):
        data=read_json(QUOTES,dict(fs=fs,pn=page,pz=size,np=1,po=1,fltt=2,fid=sort,fields=fields))['data']
        return int(data['total']),data['diff']
    def dated(row):
        return datetime.fromtimestamp(row['f124'],CN).date().isoformat()==day
    boards={};total=None;page=1;seen=set()
    while total is None or len(seen)<total:
        total,rows=read_page('m:90+t:3',page,100,'f12,f14,f124','f12')
        if not rows or page>20:raise ValueError('概念目录未核对')
        for r in rows:
            if r['f12'] in seen:raise ValueError('概念分页重复')
            seen.add(r['f12'])
            k=normalize(r['f14'])
            if k in names and dated(r):boards[k]=r
        page+=1
    def members(board):
        _,rows=read_page('b:'+board['f12'],1,40,'f12,f13,f14,f6,f124','f6')
        result={}
        for r in rows:
            code=r['f12']
            if A_SHARE.fullmatch(code) and dated(r) and isinstance(r['f6'],(int,float)) and r['f6']>0:
                ticker=symbol(code)
                result[ticker]=(ticker,r['f14'],f"{day} 东方财富「{board['f14']}」活跃成分股",
                                'https://quote.eastmoney.com/bk/90.'+board['f12']+'.html')
        return result
    found={};failed=0
    with ThreadPoolExecutor(4) as worker:
        jobs={k:worker.submit(members,b) for k,b in boards.items()}
        for k,job in jobs.items():
            try:found[k]=job.result()
            except FAILURES:failed+=1
    return found,failed


def expand(names,day,now,store,normalize):
    by_source={};failures={};denied={}
    if not names:return {},{},{}
    with ThreadPoolExecutor(5) as worker:
        annual=worker.submit(annual_evidence,names,day,store)
        boards=worker.submit(board_evidence,names,day,normalize)
        jobs={k:worker.submit(answers,n,now) for k,n in names.items()}
        for label,job in [('行情成分',boards),('年报',annual)]:
            try:by_source[label],failures[label]=job.result()
            except FAILURES:by_source[label]={};failures[label]=1
        qa={};failures['互动易']=0
        for k,job in jobs.items():
            try:qa[k],denied[k]=job.result()
            except FAILURES:failures['互动易']+=1
        by_source['互动易']=qa
    return by_source,denied,failures
