"""Read-only stock classifications, separate from signals and order evaluation."""
import gzip
import io
import json
import re
import threading
import time
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .provider import CN, now_cn, symbol
from .sector_flow import expected_day

KIND='stock_profile_v2'
SCHEMA=2
BASE='https://emweb.securities.eastmoney.com/PC_HSF10/'
CATALOG='https://datacenter.eastmoney.com/securities/api/data/v1/get'
LIMIT=2_000_000
STYLE=re.compile(r'^(?:20\d{2}(?:中报|年报|季报|一季报|三季报)|昨日|连续(?:亏损|盈利)|高(?:市盈率|市净率|股息)|低(?:市盈率|市净率|估值)|破净|小盘股|中盘股|大盘股|微盘股|超大盘|融资融券|沪股通|深股通|科创板做市商|MSCI|富时|上证|深证|沪深|中证|机构|基金|保险|社保|QFII|标准普尔|转融券)')
NAME_ONLY=re.compile('名称|生肖|玄学')


def _code(value):
    if not isinstance(value,str):raise ValueError('请输入有效股票代码')
    return symbol(value)


def _json(url):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':BASE})
    with urlopen(req,timeout=10) as response:raw=response.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError('个股资料过大')
    if raw[:2]==b'\x1f\x8b':raw=gzip.GzipFile(fileobj=io.BytesIO(raw)).read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError('个股资料过大')
    data=json.loads(raw)
    if not isinstance(data,dict):raise ValueError('个股资料格式异常')
    return data


def _read(section,code):
    if section!='CoreConception':return _json(BASE+section+'/PageAjax?code='+code.upper())
    # The detailed catalog identifies industry/region explicitly and supplies
    # company-specific concept reasons. BOARD_RANK is presentation order only.
    params=dict(reportName='RPT_F10_CORETHEME_BOARDTYPE',columns='ALL',
                filter=f'(SECUCODE="{code[2:]}.{code[:2].upper()}")',pageSize=200,pageNumber=1,
                sortColumns='BOARD_RANK',sortTypes=1,source='HSF10',client='PC')
    rows=[];total=None
    for page in range(1,4):
        data=_json(CATALOG+'?'+urlencode(dict(params,pageNumber=page))).get('result')
        if not isinstance(data,dict) or not isinstance(data.get('data'),list):raise ValueError('个股板块目录暂未取得')
        count,pages=data.get('count'),data.get('pages')
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=500 or pages!=(count+199)//200:
            raise ValueError('个股板块目录不完整')
        if total is not None and total!=count:raise ValueError('个股板块目录读取期间发生变化')
        total=count;rows.extend(data['data'])
        if page==pages:
            if len(rows)!=total or len({str(r.get('BOARD_CODE')) for r in rows})!=total:raise ValueError('个股板块目录不完整')
            return {'ssbk':rows}
    raise ValueError('个股板块目录过大')


def _identity(row,code):
    if not isinstance(row,dict) or row.get('SECURITY_CODE')!=code[2:] or row.get('SECUCODE')!=code[2:]+'.'+code[:2].upper():
        raise ValueError('个股资料代码不一致')


def _text(value):
    return re.sub(r'<[^>]*>','',value).strip()[:100] if isinstance(value,str) else ''


def parse(code,core,survey):
    code=_code(code)
    boards=[];concepts=[];attributes=[];industries=[];industry_rows=[];seen=set()
    def order(row):
        rank=row.get('BOARD_RANK') if isinstance(row,dict) else None
        return rank if isinstance(rank,(int,float)) and not isinstance(rank,bool) else 100000
    for row in sorted(core.get('ssbk') or [],key=order):
        _identity(row,code)
        name=_text(row.get('BOARD_NAME'))
        if not name or name in seen:continue
        seen.add(name);item=dict(name=name,code=_text(row.get('BOARD_CODE')))
        kind=_text(row.get('BOARD_TYPE'))
        if kind in ('行业','行业板块'):industry_rows.append(row)
        elif STYLE.search(name):attributes.append(item)
        elif kind in ('板块','地域板块') or name.endswith('板块'):boards.append(item)
        elif kind in ('概念','概念板块') or row.get('IS_PRECISE')=='1' or _text(row.get('SELECTED_BOARD_REASON')):
            concepts.append(item)
        else:
            # Unknown classifications remain boards; never infer a business
            # concept or industry from rank or from a stock's name.
            boards.append(item)
    for row in survey.get('jbzl') or []:
        _identity(row,code)
        industries=list(dict.fromkeys(filter(None,(_text(n) for n in _text(row.get('EM2016')).split('-')))))
    # These two official endpoints can expose different industry revisions.
    # Keep one hierarchy: company overview first, explicitly typed levels only
    # as fallback. Do not mix old industry labels into concept/region boards.
    if not industries:
        levels=[row for row in industry_rows if row.get('BOARD_LEVEL') in (1,2,3)]
        industries=list(dict.fromkeys(_text(row['BOARD_NAME']) for row in sorted(levels,key=lambda r:r['BOARD_LEVEL'])))
    if not seen and not industries:raise ValueError('暂未取得有效个股资料')
    return dict(code=code,industry=industries,boards=boards,concepts=concepts,attributes=attributes,
                collected_at=now_cn().isoformat(),source='东方财富个股资料',schema_version=SCHEMA)


def fetch(code):
    code=_code(code);parts={};failures=[]
    for name,section in [('core','CoreConception'),('survey','CompanySurvey')]:
        try:
            part=_read(section,code)
            rows=part.get('ssbk' if name=='core' else 'jbzl')
            if not isinstance(rows,list) or not rows:raise ValueError('个股资料暂未取得')
            for row in rows:_identity(row,code)
            parts[name]=part
        except Exception:parts[name]={};failures.append(name)
    result=parse(code,parts['core'],parts['survey'])
    result['partial']=bool(failures)
    return result


def _snapshot(value,code,now):
    if not isinstance(value,dict) or value.get('schema_version')!=SCHEMA or value.get('code')!=code:return None
    try:
        stamp=datetime.fromisoformat(value['collected_at'])
        if stamp.tzinfo is None or not 0<=(now-stamp).total_seconds()<=86400:return None
        if not isinstance(value.get('industry'),list) or any(not isinstance(v,str) for v in value['industry']):return None
        for key in ('boards','concepts','attributes'):
            rows=value.get(key)
            if not isinstance(rows,list) or len(rows)>500 or any(not isinstance(v,dict) or not isinstance(v.get('name'),str) for v in rows):return None
        return value
    except (KeyError,TypeError,ValueError):return None


class StockProfile:
    def __init__(self,store,directory,enabled=True):
        self.store=store;self.directory=Path(directory);self.enabled=enabled
        self.lock=threading.Lock();self.running=set();self.attempts={};self.errors={}
        self.theme_cache=None

    def _load(self,code):
        try:
            data=fetch(code)
            self.store.cache(code,KIND,data['collected_at'][:10],data)
            with self.lock:self.errors.pop(code,None)
        except Exception as exc:
            with self.lock:self.errors[code]=str(exc) if isinstance(exc,ValueError) else '个股资料暂未取得'
        finally:
            with self.lock:self.running.discard(code)

    def _themes(self,code,now,selected_day=None):
        cutoff=now
        if selected_day:
            try:
                selected=date.fromisoformat(selected_day)
                if selected>now.date():return [],[],'unavailable',None
                if selected<now.date():cutoff=datetime.combine(selected,clock_time(15),CN)
            except (ValueError,TypeError):return [],[],'unavailable',None
        wanted=expected_day(cutoff)
        for offset in range(4):
            label=(cutoff.date()-timedelta(days=offset)).isoformat()
            for path in sorted((self.directory/'daily-outlook').glob(label+'_*.json'),reverse=True):
                try:
                    if path.stat().st_size>8_000_000:continue
                    key=(str(path),path.stat().st_mtime_ns,wanted)
                    cached=self.theme_cache
                    if cached and key==cached[0] and cached[1]<=cutoff:
                        themes=cached[2].get(code,[]);observations=cached[3].get(code,[])
                        return themes,observations,'available' if themes or observations else 'unmatched',cached[1]
                    issue=json.loads(path.read_text())
                    stamp=datetime.fromisoformat(issue['published_at'])
                    if stamp.tzinfo is None or stamp>cutoff or issue.get('quote_date')!=wanted:continue
                    index={};observations={}
                    def add(stock,name,kind):
                        if not isinstance(stock,str) or not re.fullmatch(r'(sh6|sz[03])\d{5}',stock) or not _text(name):return
                        item=dict(name=_text(name),kind=_text(kind));target=observations if NAME_ONLY.search(item['kind']) else index
                        if item not in target.setdefault(stock,[]):target[stock].append(item)
                    filing_errors=(issue.get('discovery') or {}).get('filing_errors') or {}
                    for theme in issue.get('themes') or []:
                        # Price/flow coverage and the three-peer entry gate do not
                        # invalidate a company-specific business-membership source.
                        if theme.get('code') in filing_errors:continue
                        for member in theme.get('members') or []:
                            if not member.get('basis') or not str(member.get('source','')).startswith(('https://','http://')):continue
                            add(member.get('code'),theme.get('name'),'研究题材')
                    for theme in issue.get('radar') or []:
                        for member in theme.get('stocks') or []:add(member.get('code'),theme.get('theme'),theme.get('kind') or '研究题材')
                    self.theme_cache=(key,stamp,index,observations)
                    themes=index.get(code,[]);notes=observations.get(code,[])
                    return themes,notes,'available' if themes or notes else 'unmatched',stamp
                except (OSError,ValueError,TypeError,KeyError,AttributeError):continue
        return [],[],'unavailable',None

    def view(self,code,day=None):
        code=_code(code);now=now_cn();data=None
        # Indexed LIMIT query: old profile history must not be decoded on every UI poll.
        for row in self.store.query('SELECT payload FROM cache WHERE code=? AND kind=? ORDER BY day DESC LIMIT 2',(code,KIND)):
            try:data=_snapshot(json.loads(row['payload']),code,now)
            except (ValueError,TypeError):data=None
            if data:break
        with self.lock:
            wait=60 if code in self.errors or data and data.get('partial') else 21600
            wanted=data is None or (now-datetime.fromisoformat(data['collected_at'])).total_seconds()>=wait
            pending=self.enabled and wanted and time.monotonic()-self.attempts.get(code,float('-inf'))>=wait
            if pending and code not in self.running and len(self.running)<2:
                self.running.add(code);self.attempts[code]=time.monotonic()
                if len(self.attempts)>256:
                    for old in sorted(self.attempts,key=self.attempts.get)[:len(self.attempts)-256]:
                        if old not in self.running:self.attempts.pop(old,None);self.errors.pop(old,None)
                threading.Thread(target=self._load,args=(code,),daemon=True).start()
            running=code in self.running or pending and len(self.running)>=2
            error=self.errors.get(code,'')
        themes,observations,status,theme_stamp=self._themes(code,now,day)
        return dict(code=code,data=data,themes=themes,observations=observations,theme_status=status,
                    theme_published_at=theme_stamp.isoformat() if theme_stamp else None,
                    running=bool(running),error=error)
