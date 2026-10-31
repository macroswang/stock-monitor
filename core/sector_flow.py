"""东方财富行业大单统计：只读观察，不参与交易或市场信号。"""
import json
import math
import re
import threading
import time
from datetime import datetime, time as clock_time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .index_technical import trading_day
from .provider import CN, now_cn

CODE, KIND = 'eastmoney-industry', 'sector_flow_v1'
# 刷新频率应快于盘中 180 秒的过期阈值，避免正常采集时出现空档。
REFRESH_SECONDS = 120
SOURCE = '东方财富行业板块资金流'
URL = 'https://push2.eastmoney.com/api/qt/clist/get'
SOURCE_PAGE = 'https://data.eastmoney.com/bkzj/hy.html'
SINA_SOURCE = '新浪行业资金流'
SINA_CONCEPT_SOURCE = '新浪概念资金流'
SINA_PAGE = 'https://finance.sina.com.cn/realstock/company/plate.shtml'
SINA_URL = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk'


def expected_day(now):
    now=now.astimezone(CN)
    day=now.date()
    flag=trading_day(day)
    if flag is None:return None
    if flag and now.time()>=clock_time(9,30):return day.isoformat()
    for _ in range(10):
        day-=timedelta(days=1)
        flag=trading_day(day)
        if flag is None:return None
        if flag:return day.isoformat()
    return None


def parse(payload,now):
    """完整单页、同日时间及主力额分项核对后，才允许作为板块观察。"""
    now=now.astimezone(CN)
    expected=expected_day(now)
    if not expected:raise ValueError('交易日历不足，无法核对板块日期')
    data=payload.get('data') if isinstance(payload,dict) else None
    if not isinstance(data,dict):raise ValueError('板块数据为空')
    rows=data.get('diff');total=data.get('total')
    if not isinstance(total,int) or not 70<=total<=1000 or not isinstance(rows,list) or len(rows)!=total:
        raise ValueError('板块数据不完整，暂不展示排行')
    out=[];stamps=[];seen=set()
    for row in rows:
        try:
            code=row['f12'];name=row['f14'];net=row['f62'];large=row['f72'];extra=row['f66'];change=row['f3'];stamp=row['f124']
            nums=(net,large,extra,change,stamp)
            if not isinstance(code,str) or not re.fullmatch(r'BK\d{4}',code) or code in seen or not isinstance(name,str) or not name or len(name)>40:raise ValueError()
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in nums):raise ValueError()
            # 东财将主力额定义为大单和超大单净额之和，单位为元。
            if abs(net-large-extra)>max(100,abs(net)*0.00001):raise ValueError()
            ts=datetime.fromtimestamp(stamp,CN)
            if ts.date().isoformat()!=expected or ts>now+timedelta(seconds=5):raise ValueError()
            seen.add(code);stamps.append(ts)
            out.append(dict(code=code,name=name,net_yuan=net,change_percent=change,source_time=ts.isoformat()))
        except (KeyError,TypeError,ValueError,OverflowError,OSError):
            raise ValueError('板块字段、日期或资金分项无法核对') from None
    if (max(stamps)-min(stamps)).total_seconds()>180:raise ValueError('板块数据时间不一致')
    is_session=(trading_day(now.date()) is True and (clock_time(9,30)<=now.time()<=clock_time(11,30) or clock_time(13)<=now.time()<clock_time(15)))
    if is_session and (now-max(stamps)).total_seconds()>180:raise ValueError('盘中板块数据已过期')
    ranked=sorted(out,key=lambda x:x['net_yuan'],reverse=True)
    return dict(date=expected,source=SOURCE,source_url=SOURCE_PAGE,quote_time=max(stamps).isoformat(),
                collected_at=now.isoformat(),total=total,measure='大单及超大单净额',observations=out,sectors=out,
                inflow=[r for r in ranked if r['net_yuan']>0][:3],
                outflow=[r for r in reversed(ranked) if r['net_yuan']<0][:3])


def fetch_eastmoney(now):
    params={'pn':1,'pz':1000,'po':1,'np':1,'fltt':2,'fid':'f62','fs':'m:90+t:2',
            'fields':'f3,f12,f14,f62,f66,f72,f124'}
    req=Request(URL+'?'+urlencode(params),headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'})
    with urlopen(req,timeout=8) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('板块数据过大')
    return parse(json.loads(raw),now)


def _sina_page(page,kind='industry'):
    params={'page':page,'num':1000,'sort':'netamount','asc':0,'fenlei':0 if kind=='industry' else 1}
    req=Request(SINA_URL+'?'+urlencode(params),headers={'User-Agent':'Mozilla/5.0','Referer':'https://finance.sina.com.cn/'})
    with urlopen(req,timeout=8) as response:raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('板块数据过大')
    return json.loads(raw)


def parse_sina(rows,extra,quotes,now,kind='industry'):
    """新浪无板块时间：用两端代表股的同日价格匹配，日期仅作推定。"""
    if kind not in ('industry','concept'):raise ValueError('不支持的板块类型')
    now=now.astimezone(CN);day=expected_day(now)
    if day is None or not isinstance(rows,list) or not 35<=len(rows)<=500 or extra!=[]:
        raise ValueError('新浪行业数据不完整')
    output=[];seen=set()
    try:
        for row in rows:
            name=row['name'];code=row['category'];stock=row['ts_symbol']
            if (row['cate_type']!=('0' if kind=='industry' else '1') or not isinstance(name,str) or not name or len(name)>40 or
                not isinstance(code,str) or not re.fullmatch(r'(?:new_|gn_)[A-Za-z0-9]+',code) or not code.startswith('new_' if kind=='industry' else 'gn_') or code in seen or
                not isinstance(stock,str) or not re.fullmatch(r'(sh[69]|sz[03])\d{5}',stock)):
                raise ValueError()
            values=[Decimal(str(row[k])) for k in ('netamount','inamount','outamount','avg_changeratio','ts_trade','ts_changeratio')]
            if not all(x.is_finite() for x in values) or values[1]<0 or values[2]<0 or abs(values[0]-values[1]+values[2])>Decimal('0.1') or values[4]<0:
                raise ValueError()
            seen.add(code)
            output.append(dict(code=code,name=name,net_yuan=float(values[0]),change_percent=float(values[3]*100),
                               stock=stock,stock_price=values[4],stock_change=values[5]))
        output.sort(key=lambda x:x['net_yuan'],reverse=True)
        picked=output[:3]+output[-3:]
        if len({x['stock'] for x in picked})<3:raise ValueError()
        anchor=[];anchor_details=[]
        for row in picked:
            q=quotes[row['stock']];ts=q['stamp'];price=Decimal(q['price']);previous=Decimal(q['previous'])
            if (ts.tzinfo is None or ts.astimezone(CN).date().isoformat()!=day or ts>now+timedelta(seconds=5) or
                previous<=0 or abs(price-row['stock_price'])>Decimal('0.0051') or
                abs(price/previous-1-row['stock_change'])>Decimal('0.0001')):raise ValueError()
            anchor.append(ts)
            anchor_details.append(dict(code=row['stock'],sector_price=str(row['stock_price']),reference_price=str(price),reference_time=ts.isoformat()))
        session=trading_day(now.date()) is True and (clock_time(9,30)<=now.time()<=clock_time(11,30) or clock_time(13)<=now.time()<clock_time(15))
        if session and any((now-ts).total_seconds()>180 for ts in anchor):raise ValueError()
    except (KeyError,TypeError,ValueError,InvalidOperation,ZeroDivisionError,OverflowError):
        raise ValueError('新浪数据日期、金额或代表股价格未通过核对') from None
    def simple(row):return {k:row[k] for k in ('code','name','net_yuan','change_percent')}
    return dict(date=day,source=SINA_SOURCE if kind=='industry' else SINA_CONCEPT_SOURCE,source_url='https://finance.sina.com.cn/temp/guest4377.shtml',
                quote_time=None,anchor_time=max(anchor).isoformat(),collected_at=now.isoformat(),total=len(output),
                measure='买卖方向净额',date_inferred=True,anchor_details=anchor_details,sectors=[simple(r) for r in output],
                inflow=[simple(r) for r in output if r['net_yuan']>0][:3],
                outflow=[simple(r) for r in reversed(output) if r['net_yuan']<0][:3])


def fetch_sina(now,kind='industry'):
    if kind not in ('industry','concept'):raise ValueError('不支持的板块类型')
    rows=_sina_page(1,kind);extra=_sina_page(2,kind)
    if not isinstance(rows,list) or len(rows)<35:raise ValueError('新浪行业数据不完整')
    sorted_rows=sorted(rows,key=lambda r:Decimal(str(r['netamount'])),reverse=True)
    codes=list(dict.fromkeys(r['ts_symbol'] for r in sorted_rows[:3]+sorted_rows[-3:]))
    if any(not isinstance(c,str) or not re.fullmatch(r'(sh[69]|sz[03])\d{5}',c) for c in codes):raise ValueError('股票代码异常')
    req=Request('https://qt.gtimg.cn/q='+','.join(codes),headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
    with urlopen(req,timeout=8) as response:text=response.read(100000).decode('gb18030')
    quotes={}
    for line in text.splitlines():
        if '="' not in line:continue
        code=line.split('=',1)[0].split('_')[-1];fields=line.split('="',1)[1].split('~')
        if code in codes and len(fields)>30:
            quotes[code]=dict(price=fields[3],previous=fields[4],stamp=datetime.strptime(fields[30],'%Y%m%d%H%M%S').replace(tzinfo=CN))
    return parse_sina(rows,extra,quotes,now,kind)


def fetch(now,kind='industry'):
    if kind=='concept':return fetch_sina(now,'concept')
    if kind!='industry':raise ValueError('不支持的板块类型')
    try:return fetch_eastmoney(now)
    except Exception:return fetch_sina(now)


class SectorFlow:
    def __init__(self,store,enabled=True,kind='industry'):
        if kind not in ('industry','concept'):raise ValueError('不支持的板块类型')
        self.store=store;self.enabled=enabled;self.kind=kind;self.code=CODE if kind=='industry' else 'sina-concept';self.lock=threading.Lock();self.running=False;self.last_attempt=float('-inf');self.error=''

    def refresh(self,force=False):
        with self.lock:
            if self.running:return
            if not force and time.monotonic()-self.last_attempt<REFRESH_SECONDS:return
            self.running=True;self.last_attempt=time.monotonic()
        try:
            now=now_cn();result=fetch(now,self.kind)
            self.store.cache(self.code,KIND,result['date'],result)
            if result.get('source')==SOURCE and result.get('quote_time') and result.get('observations'):
                # 仅保存来源提供时间的完整快照，重复时间不覆盖既有样本。
                with self.store.lock,self.store.db:
                    self.store.db.execute('INSERT OR IGNORE INTO cache VALUES(?,?,?,?)',(self.code,'sector_intraday_v1',result['quote_time'],json.dumps(result,ensure_ascii=False)))
            self.error=''
        except Exception:
            self.error='板块资金暂未取得或未通过核对'
        finally:
            with self.lock:self.running=False

    def view(self):
        if self.enabled and not self.running and time.monotonic()-self.last_attempt>=REFRESH_SECONDS:
            threading.Thread(target=self.refresh,daemon=True).start()
        rows=self.store.getcache(self.code,KIND)
        now=now_cn();wanted=expected_day(now)
        latest=rows[-1]['data'] if rows else None
        allowed=(SOURCE,SINA_SOURCE) if self.kind=='industry' else (SINA_CONCEPT_SOURCE,)
        usable=bool(latest and latest.get('source') in allowed and latest.get('date')==wanted)
        if usable:
            try:
                ts=datetime.fromisoformat(latest.get('quote_time') or latest['anchor_time'])
                collected=datetime.fromisoformat(latest['collected_at'])
                age=(now-ts).total_seconds()
                session=trading_day(now.date()) is True and (clock_time(9,30)<=now.time()<=clock_time(11,30) or clock_time(13)<=now.time()<clock_time(15))
                usable=ts.tzinfo is not None and collected.tzinfo is not None and collected<=now+timedelta(seconds=5) and -5<=age and (not session or age<=180)
            except (ValueError,TypeError,KeyError):usable=False
        return dict(snapshot=latest if usable else None,running=self.running,error=self.error,expected_date=wanted,source_url=SOURCE_PAGE)

    def intraday(self):
        from .sector_events import build_observations
        view=self.view();snapshot=view.get('snapshot');now=now_cn()
        if not snapshot or snapshot.get('source')!=SOURCE or not snapshot.get('quote_time'):
            return dict(events=[],series={},date=view.get('expected_date'),status='来源未提供可靠的板块时间，无法计算盘中异动')
        day=snapshot['date']
        rows=self.store.query('SELECT payload FROM cache WHERE code=? AND kind=? AND day>=? AND day<? ORDER BY day',(self.code,'sector_intraday_v1',day+'T00',day+'T24'))
        return build_observations([json.loads(r['payload']) for r in rows],now,day)
