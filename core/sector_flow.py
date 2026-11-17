"""东方财富行业大单统计：只读观察，不参与交易或市场信号。"""
import concurrent.futures
import json
import math
import re
import threading
import time
from datetime import datetime, time as clock_time, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .index_technical import trading_day
from .provider import CN, now_cn

CODE, KIND = 'eastmoney-industry', 'sector_flow_v1'
# 刷新频率应快于盘中 180 秒的过期阈值，避免正常采集时出现空档。
REFRESH_SECONDS = 30
RETRY_SECONDS = 10
# Cross-provider last trades need not be the same tick. Keep the independent
# date/freshness gate, then bound drift and reconcile the implied previous close.
PRICE_DRIFT = Decimal('0.005')
SOURCE = '东方财富行业板块资金流'
URL = 'https://push2.eastmoney.com/api/qt/clist/get'
SOURCE_PAGE = 'https://data.eastmoney.com/bkzj/hy.html'
SINA_SOURCE = '新浪行业资金流'
SINA_CONCEPT_SOURCE = '新浪概念资金流'
SINA_PAGE = 'https://finance.sina.com.cn/realstock/company/plate.shtml'
SINA_URL = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk'
_SINA_OBSERVED = {}
_SINA_LOCK = threading.Lock()


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
            sector=dict(code=code,name=name,net_yuan=net,change_percent=change,source_time=ts.isoformat())
            symbol,label,pct=row.get('f140'),row.get('f128'),row.get('f136')
            if (isinstance(symbol,str) and re.fullmatch(r'\d{6}',symbol) and row.get('f141') in (0,1)
                    and isinstance(label,str) and label.strip() and isinstance(pct,(int,float)) and math.isfinite(pct)):
                sector['representative']=dict(code=('sh' if row['f141']==1 else 'sz')+symbol,name=label,
                                              change_percent=pct,time=ts.isoformat())
            out.append(sector)
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
    started=time.monotonic()
    params={'pn':1,'pz':1000,'po':1,'np':1,'fltt':2,'fid':'f62','fs':'m:90+t:2',
            'fields':'f3,f12,f14,f62,f66,f72,f124,f128,f136,f140,f141'}
    req=Request(URL+'?'+urlencode(params),headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'})
    with urlopen(req,timeout=8) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('板块数据过大')
    return parse(json.loads(raw),now+timedelta(seconds=time.monotonic()-started))


def _sina_page(page,kind='industry'):
    params={'page':page,'num':1000,'sort':'netamount','asc':0,'fenlei':0 if kind=='industry' else 1,
            '_':int(time.time()*1000)}
    req=Request(SINA_URL+'?'+urlencode(params),headers={'User-Agent':'Mozilla/5.0','Referer':'https://finance.sina.com.cn/',
                                                    'Cache-Control':'no-cache'})
    with urlopen(req,timeout=8) as response:
        raw=response.read(2_000_001)
        stamp=response.headers.get('Date')
        if isinstance(stamp,str):
            age=(now_cn()-parsedate_to_datetime(stamp)).total_seconds()
            if not -5<=age<=180:raise ValueError('新浪响应时间已过期或在未来')
    if len(raw)>2_000_000:raise ValueError('板块数据过大')
    return json.loads(raw)


def parse_sina(rows,extra,quotes,now,kind='industry',prior=None):
    """新浪未提供板块时间：逐板块核对代表股，日期仅作推定。"""
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
        source_rows={r['category']:r for r in rows}
        verified=[];details={};stamps=[];rejected={};update_verified=0
        older={}
        if prior:
            earlier,observed=prior
            if (observed.tzinfo is not None and observed.astimezone(CN).date()==now.date() and
                    0<(now-observed).total_seconds()<=180):
                older={r['category']:r for r in earlier if isinstance(r,dict) and 'category' in r}
        session=trading_day(now.date()) is True and (clock_time(9,30)<=now.time()<=clock_time(11,30) or clock_time(13)<=now.time()<clock_time(15))
        # Check each displayed sector's representative, instead of letting one
        # moving price erase the whole screen or endorsing unchecked sectors.
        for row in output:
            try:
                q=quotes[row['stock']];ts=q['stamp'];price=Decimal(q['price']);previous=Decimal(q['previous'])
                if (ts.tzinfo is None or ts.astimezone(CN).date().isoformat()!=day or ts>now+timedelta(seconds=5) or
                    (session and (now-ts).total_seconds()>180)):
                    rejected['日期或时效不符']=rejected.get('日期或时效不符',0)+1;continue
                sector_price,sector_change=row['stock_price'],row['stock_change']
                if (not price.is_finite() or not previous.is_finite() or previous<=0 or price<=0 or
                        sector_price<=0 or sector_change<=-1):
                    raise ValueError()
                implied_previous=sector_price/(1+sector_change)
                # Sina ratios are rounded; allow one price tick plus ratio rounding.
                previous_tolerance=Decimal('0.01')+previous*Decimal('0.0001')
                drift_tolerance=max(Decimal('0.02'),min(price,sector_price)*PRICE_DRIFT)
                if abs(implied_previous-previous)>previous_tolerance:
                    rejected['价格或昨收不符']=rejected.get('价格或昨收不符',0)+1;continue
                if abs(price-sector_price)>drift_tolerance:
                    # The funding endpoint's representative last trade can lag even
                    # while its money-flow fields are updating. Verify actual changes
                    # in two uncached source observations within 180s, not a wider
                    # arbitrary price tolerance. The lagged price must also have
                    # traded inside today's independently timestamped price range.
                    old=older.get(row['code'])
                    low,high=Decimal(q.get('low','NaN')),Decimal(q.get('high','NaN'))
                    before=[Decimal(str(old[k])) for k in ('netamount','inamount','outamount')] if old else []
                    changed=bool(old and old.get('ts_symbol')==row['stock'] and old.get('cate_type')==('0' if kind=='industry' else '1') and
                                 all(x.is_finite() for x in before) and before[1]>=0 and before[2]>=0 and
                                 abs(before[0]-before[1]+before[2])<=Decimal('0.1') and
                                 any(Decimal(str(old[k]))!=Decimal(str(source_rows[row['code']][k]))
                                     for k in ('netamount','inamount','outamount')))
                    if not (changed and low.is_finite() and high.is_finite() and 0<low<=high and
                            low-Decimal('0.0051')<=sector_price<=high+Decimal('0.0051')):
                        rejected['价格或昨收不符']=rejected.get('价格或昨收不符',0)+1;continue
                    update_verified+=1
            except (KeyError,TypeError,ValueError,InvalidOperation,ZeroDivisionError):
                rejected['代表股报价缺失或异常']=rejected.get('代表股报价缺失或异常',0)+1;continue
            verified.append(row);stamps.append(ts)
            if isinstance(q.get('name'),str) and q['name'].strip():
                row['representative']=dict(code=row['stock'],name=q['name'],time=ts.isoformat(),
                                           change_percent=float((price/previous-1)*100))
            details[row['code']]=dict(code=row['stock'],sector_price=str(row['stock_price']),reference_price=str(price),reference_time=ts.isoformat())
        if len(verified)<math.ceil(len(output)*.8):
            detail='、'.join(f'{key} {value}' for key,value in rejected.items())
            raise ValueError(f'代表股通过 {len(verified)}/{len(output)}，不足 80%；{detail}')
        picked=verified[:3]+verified[-3:]
        if len({r['stock'] for r in picked})<3:raise ValueError()
    except (KeyError,TypeError,ValueError,InvalidOperation,ZeroDivisionError,OverflowError) as exc:
        detail=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('代表股通过') else ''
        raise ValueError('新浪数据日期、金额或代表股价格未通过核对'+('：'+detail if detail else '')) from None
    def simple(row):return {k:row[k] for k in ('code','name','net_yuan','change_percent','representative') if k in row}
    return dict(date=day,source=SINA_SOURCE if kind=='industry' else SINA_CONCEPT_SOURCE,source_url='https://finance.sina.com.cn/temp/guest4377.shtml',
                quote_time=None,anchor_time=min(stamps).isoformat(),collected_at=now.isoformat(),total=len(output),
                verified_count=len(verified),excluded_count=len(output)-len(verified),validation_rejections=rejected,update_verified_count=update_verified,
                validation='同日新鲜报价与昨收核对；小幅价差或 180 秒内资金实际更新及当日成交区间验证；日期为推定',
                measure='买卖方向净额',date_inferred=True,anchor_details=[details[r['code']] for r in picked],sectors=[simple(r) for r in verified],
                inflow=[simple(r) for r in verified if r['net_yuan']>0][:3],
                outflow=[simple(r) for r in reversed(verified) if r['net_yuan']<0][:3])


def _reference_quotes(codes):
    def batch(group):
        req=Request('https://qt.gtimg.cn/q='+','.join(group)+'&_='+str(int(time.time()*1000)),
                    headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/','Cache-Control':'no-cache'})
        with urlopen(req,timeout=8) as response:text=response.read(100000).decode('gb18030')
        found={}
        for line in text.splitlines():
            if '="' not in line:continue
            code=line.split('=',1)[0].split('_')[-1];fields=line.split('="',1)[1].split('~')
            if code in group and len(fields)>30 and fields[2]==code[2:]:
                found[code]=dict(name=fields[1],price=fields[3],previous=fields[4],high=fields[33] if len(fields)>34 else '',
                                 low=fields[34] if len(fields)>34 else '',stamp=datetime.strptime(fields[30],'%Y%m%d%H%M%S').replace(tzinfo=CN))
        return found
    groups=[codes[i:i+50] for i in range(0,len(codes),50)]
    result={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for rows in pool.map(batch,groups):result.update(rows)
    return result


def fetch_sina(now,kind='industry'):
    if kind not in ('industry','concept'):raise ValueError('不支持的板块类型')
    started=time.monotonic()
    rows=_sina_page(1,kind);extra=_sina_page(2,kind)
    if not isinstance(rows,list) or len(rows)<35:raise ValueError('新浪行业数据不完整')
    observed=now
    with _SINA_LOCK:
        prior=_SINA_OBSERVED.get(kind)
        if len(rows)<=500 and extra==[]:_SINA_OBSERVED[kind]=(rows,observed)
    codes=list(dict.fromkeys(r['ts_symbol'] for r in rows))
    if any(not isinstance(c,str) or not re.fullmatch(r'(sh[69]|sz[03])\d{5}',c) for c in codes):raise ValueError('股票代码异常')
    quotes=_reference_quotes(codes)
    return parse_sina(rows,extra,quotes,now+timedelta(seconds=time.monotonic()-started),kind,prior=prior)





URL_DELAY = 'https://push2delay.eastmoney.com/api/qt/clist/get'
CONCEPT_SOURCE = '东方财富概念板块资金流'
CONCEPT_PAGE = 'https://data.eastmoney.com/bkzj/gn.html'
CONCEPT_CODE = 'eastmoney-concept'


def _page_payload(host, fs, page, size=100):
    # Order by board code: ranking by a changing flow value makes page boundaries unstable.
    params = {'pn': page, 'pz': size, 'po': 0, 'np': 1, 'fltt': 2, 'fid': 'f12', 'fs': fs,
              'fields': 'f3,f12,f14,f62,f66,f72,f124,f128,f136,f140,f141'}
    req = Request(host + '?' + urlencode(params), headers={'User-Agent': 'Mozilla/5.0',
                                                           'Referer': 'https://data.eastmoney.com/'})
    with urlopen(req, timeout=10) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('板块数据过大')
    data = json.loads(raw).get('data')
    if not isinstance(data, dict) or not isinstance(data.get('diff'), list):
        raise ValueError('板块数据为空')
    return data


def _parse_paged(rows, expected, now, total):
    """The single-page parser needs the full board list; page mode rebuilds the same snapshot."""
    if not isinstance(total, int) or not 70 <= total <= 1200 or len(rows) != total:
        raise ValueError('板块数据不完整，暂不展示排行')
    now = now.astimezone(CN)
    out, stamps, seen = [], [], set()
    for row in rows:
        try:
            code, name = row['f12'], row['f14']
            net, large, extra, change, stamp = row['f62'], row['f72'], row['f66'], row['f3'], row['f124']
            nums = (net, large, extra, change, stamp)
            if not isinstance(code, str) or not re.fullmatch(r'BK\d{4}', code) or code in seen \
                    or not isinstance(name, str) or not name or len(name) > 40:
                raise ValueError()
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                   for value in nums):
                raise ValueError()
            if abs(net - large - extra) > max(100, abs(net) * 0.00001):
                raise ValueError()
            ts = datetime.fromtimestamp(stamp, CN)
            if ts.date().isoformat() != expected or ts > now + timedelta(seconds=5):
                raise ValueError()
            seen.add(code)
            stamps.append(ts)
            sector = dict(code=code, name=name, net_yuan=net, change_percent=change, source_time=ts.isoformat())
            symbol, label, pct = row.get('f140'), row.get('f128'), row.get('f136')
            if (isinstance(symbol, str) and re.fullmatch(r'\d{6}', symbol) and row.get('f141') in (0, 1)
                    and isinstance(label, str) and label.strip() and isinstance(pct, (int, float))
                    and math.isfinite(pct)):
                sector['representative'] = dict(code=('sh' if row['f141'] == 1 else 'sz') + symbol,
                                                name=label, change_percent=pct, time=ts.isoformat())
            out.append(sector)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            raise ValueError('板块字段、日期或资金分项无法核对') from None
    if (max(stamps) - min(stamps)).total_seconds() > 180:
        raise ValueError('板块数据时间不一致')
    is_session = (trading_day(now.date()) is True and
                  (clock_time(9, 30) <= now.time() <= clock_time(11, 30)
                   or clock_time(13) <= now.time() < clock_time(15)))
    if is_session and (now - max(stamps)).total_seconds() > 180:
        raise ValueError('盘中板块数据已过期')
    ranked = sorted(out, key=lambda row: row['net_yuan'], reverse=True)
    return ranked, max(stamps)


def fetch_eastmoney_paged(now, kind='industry'):
    """Both Eastmoney hosts may cap a page at 100 rows; walk pages so the full board list is complete."""
    if kind not in ('industry', 'concept'):
        raise ValueError('不支持的板块类型')
    started = time.monotonic()
    expected = expected_day(now)
    if not expected:
        raise ValueError('交易日历不足，无法核对板块日期')
    fs = 'm:90+t:2' if kind == 'industry' else 'm:90+t:3'
    hosts = (URL_DELAY, URL)
    first = None
    error = None
    for host in hosts:
        try:
            first = _page_payload(host, fs, 1)
            break
        except Exception as exc:
            error = exc
    if first is None:
        raise ValueError('板块数据为空') from error
    total = int(first['total'])
    pages = (total + 99) // 100
    if total < 70 or total > 1200 or pages > 20:
        raise ValueError('板块总数异常')
    rows = list(first['diff'])
    if len(rows) != min(100, total):
        raise ValueError('板块分页长度异常')
    for page in range(2, pages + 1):
        data = None
        for host in hosts:
            try:
                data = _page_payload(host, fs, page)
                break
            except Exception as exc:
                error = exc
        if data is None:
            raise ValueError('板块后续分页未取得') from error
        if int(data['total']) != total or len(data['diff']) != min(100, total - (page - 1) * 100):
            raise ValueError('板块分页在读取中变动')
        rows.extend(data['diff'])
    parsed, stamp = _parse_paged(rows, expected, now + timedelta(seconds=time.monotonic() - started), total)
    source = SOURCE if kind == 'industry' else CONCEPT_SOURCE
    page_url = SOURCE_PAGE if kind == 'industry' else CONCEPT_PAGE
    return dict(date=expected, source=source, source_url=page_url, quote_time=stamp.isoformat(),
                collected_at=now_cn().isoformat(), total=total, measure='大单及超大单净额',
                observations=parsed, sectors=parsed,
                inflow=[row for row in parsed if row['net_yuan'] > 0][:3],
                outflow=[row for row in reversed(parsed) if row['net_yuan'] < 0][:3])


def fetch(now,kind='industry'):
    if kind not in ('industry','concept'):raise ValueError('不支持的板块类型')
    started=time.monotonic()
    # push2 is frequently WAF-blocked; both live hosts cap pages at 100 rows,
    # so the complete-list fallback walks pages before trying Sina.
    failures=[]
    if kind=='industry':
        try:return fetch_eastmoney(now)
        except Exception as exc:failures.append('东财单页：'+type(exc).__name__)
    try:return fetch_eastmoney_paged(now+timedelta(seconds=time.monotonic()-started),kind)
    except Exception as exc:failures.append('东财分页：'+str(exc))
    try:return fetch_sina(now+timedelta(seconds=time.monotonic()-started),kind)
    except Exception as exc:
        raise ValueError('；'.join(failures+['新浪：'+str(exc)])) from exc


class SectorFlow:
    def __init__(self,store,enabled=True,kind='industry'):
        if kind not in ('industry','concept'):raise ValueError('不支持的板块类型')
        from .sector_observations import SectorObservationCache
        self.observation_lock=threading.RLock();self.observation_cache=SectorObservationCache(store,CODE if kind=='industry' else 'sina-concept')
        self.store=store;self.enabled=enabled;self.kind=kind;self.code=CODE if kind=='industry' else 'sina-concept';self.lock=threading.Lock();self.running=False;self.last_attempt=float('-inf');self.error=''
        self.ready=threading.Event();self.ready.set()

    def refresh(self,force=False):
        # The existing collector also releases unused display memory; no new
        # timer, data deletion or changes to collection/trading schedules.
        with self.observation_lock:self.observation_cache.expire_if_idle()
        with self.lock:
            if self.running:return
            if not force and time.monotonic()-self.last_attempt<(RETRY_SECONDS if self.error else REFRESH_SECONDS):return
            self.running=True;self.ready.clear();self.last_attempt=time.monotonic()
        try:
            now=now_cn();result=fetch(now,self.kind)
            self.store.cache(self.code,KIND,result['date'],result)
            if result.get('source')==SOURCE and result.get('quote_time') and result.get('observations'):
                # 仅保存来源提供时间的完整快照，重复时间不覆盖既有样本。
                with self.store.lock,self.store.db:
                    from .sector_observations import COMPRESSED,encode_snapshot
                    self.store.db.execute('INSERT OR IGNORE INTO cache SELECT ?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM cache WHERE code=? AND kind=? AND day=?)',
                        (self.code,COMPRESSED,result['quote_time'],encode_snapshot(result),self.code,'sector_intraday_v1',result['quote_time']))
            self.error=''
        except Exception as exc:
            self.error=('板块资金暂未取得或未通过核对：'+type(exc).__name__+' '+str(exc))[:500]
        finally:
            with self.lock:self.running=False;self.ready.set()

    def snapshot(self, now):
        """Research and all UI consumers share one refresh, cache and validation gate."""
        self.refresh()
        if not self.ready.wait(60):raise ValueError('板块采集仍未完成（等待超过 60 秒）')
        report=self.view(refresh=False)
        if not report['snapshot']:raise ValueError(report['error'] or '板块快照日期或时效未通过核对')
        if report['snapshot']['date']!=expected_day(now):raise ValueError('板块与研判交易日不一致')
        return report['snapshot']

    def view(self, refresh=True):
        if refresh and self.enabled and not self.running and time.monotonic()-self.last_attempt>=(RETRY_SECONDS if self.error else REFRESH_SECONDS):
            threading.Thread(target=self.refresh,daemon=True).start()
        rows=self.store.getcache(self.code,KIND)
        now=now_cn();wanted=expected_day(now)
        latest=rows[-1]['data'] if rows else None
        allowed=(SOURCE,SINA_SOURCE) if self.kind=='industry' else (CONCEPT_SOURCE,SINA_CONCEPT_SOURCE)
        usable=bool(latest and latest.get('source') in allowed and latest.get('date')==wanted)
        checked=usable
        if usable:
            try:
                ts=datetime.fromisoformat(latest.get('quote_time') or latest['anchor_time'])
                collected=datetime.fromisoformat(latest['collected_at'])
                age=(now-ts).total_seconds()
                session=trading_day(now.date()) is True and (clock_time(9,30)<=now.time()<=clock_time(11,30) or clock_time(13)<=now.time()<clock_time(15))
                checked=ts.tzinfo is not None and collected.tzinfo is not None and collected<=now+timedelta(seconds=5) and -5<=age
                usable=checked and (not session or (age<=180 and (now-collected).total_seconds()<=180))
            except (ValueError,TypeError,KeyError):usable=False;checked=False
        return dict(snapshot=latest if usable else None,cached_snapshot=latest if checked and not usable else None,stale=bool(checked and not usable),running=self.running,error=self.error,expected_date=wanted,source_url=SOURCE_PAGE,refresh_seconds=REFRESH_SECONDS)

    def intraday(self,since=None):
        view=self.view();snapshot=view.get('snapshot');now=now_cn()
        if not snapshot or snapshot.get('source')!=SOURCE or not snapshot.get('quote_time'):
            return dict(events=[],series={},date=view.get('expected_date'),status='来源未提供可靠的板块时间，无法计算盘中异动')
        day=snapshot['date']
        # Separate from refresh's lock: no network IO or live rules use this cache.
        with self.observation_lock:
            result=self.observation_cache.read(day,now)
            if since and since==result['series_revision']:
                result=dict(result,series_unchanged=True);result.pop('series')
            return result
