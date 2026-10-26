"""Read-only buy/sell display from dated public Tencent trade packets.
Never supplies prices or volumes to formal signals or simulated executions.
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as clock_time
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .provider import now_cn, symbol
from .eastmoney_flow import EastmoneyTicks


def assignment(text, name):
    match=re.fullmatch(re.escape(name)+r'\s*=\s*(\[.*\])\s*;?\s*',text.strip(),re.S)
    if not match:raise ValueError('分笔返回标识不一致')
    value=json.loads(match[1])
    if not isinstance(value,list) or len(value)!=2:raise ValueError('分笔结构无效')
    return value


def timeline(text, code):
    stamp,ranges=assignment(text,'v_detail_time_'+code)
    day=date.fromisoformat(str(stamp)[:4]+'-'+str(stamp)[4:6]+'-'+str(stamp)[6:]).isoformat()
    if len(str(stamp))!=8 or not isinstance(ranges,str):raise ValueError('分笔交易日期无效')
    pages=ranges.split('|') if ranges else []
    if not pages or len(pages)>256:raise ValueError('分笔分页数量无效')
    for r in pages:
        if not re.fullmatch(r'\d{2}:\d{2}:\d{2}~\d{2}:\d{2}:\d{2}',r):raise ValueError('分笔分页时间无效')
        first,last=map(clock_time.fromisoformat,r.split('~'))
        if first>last:raise ValueError('分笔分页时间倒退')
    return day,pages


def aggregate(pages):
    records=[];last_id=-1;last_time=''
    for page in pages:
        for row in page['data'].split('|'):
            if not row:continue
            fields=row.split('/')
            if len(fields)!=7:raise ValueError('分笔字段不足')
            index,stamp,price,_,volume,amount,side=fields
            if not re.fullmatch(r'\d{2}:\d{2}:\d{2}',stamp):raise ValueError('分笔时间无效')
            clock_time.fromisoformat(stamp)
            # Post-continuous/after-hours packets are not rendered. Their sparse
            # IDs and stale catalogue tails must not invalidate earlier trades.
            if stamp>='14:57:00':continue
            if not index.isdigit() or int(index)!=last_id+1:raise ValueError('分笔编号重复或缺失')
            if stamp<last_time:raise ValueError('分笔时间倒退')
            p,v,a=map(Decimal,(price,volume,amount))
            if not all(x.is_finite() for x in (p,v,a)) or p<=0 or v<0 or v!=int(v) or a<0:raise ValueError('分笔数值无效')
            if v>0 and a<=0:raise ValueError('无法核验分笔数量单位')
            last_id,last_time=int(index),stamp
            records.append((stamp,p,int(v),a,side))
    positive=[r for r in records if r[2]>0]
    factors=[factor for factor in (1,100) if positive and all(Decimal('.5')<=a/(p*v*factor)<=2 for _,p,v,a,_ in positive)]
    if len(factors)!=1:raise ValueError('无法核验分笔数量单位')
    factor=factors[0];buckets={}
    for stamp,p,v,a,side in records:
        # Auction indicative quantities are not summed into continuous trades.
        if not ('09:30:00'<=stamp<='11:30:00' or '13:00:00'<=stamp<'14:57:00'):continue
        h,m,_=map(int,stamp.split(':'));end=690 if stamp=='11:30:00' else h*60+m+1;label=f'{end//60:02}:{end%60:02}'
        b=buckets.setdefault(label,dict(buy=0,sell=0,neutral=0,unknown=0,total=0))
        field={'B':'buy','S':'sell','M':'neutral'}.get(side,'unknown')
        b[field]+=v*factor;b['total']+=v*factor
    return dict(buckets=buckets,volume_multiplier=factor,record_count=len(records),last_tick=last_time)


def classify_minute(bar,packet,allow_split=True):
    total=bar['volume'];keys=('buy','sell','neutral','unknown')
    valid=bool(packet and all(type(packet.get(k)) is int and packet[k]>=0 for k in (*keys,'total')) and sum(packet[k] for k in keys)==packet['total'])
    source_total=packet['total'] if valid else None
    difference=source_total-total if valid else None
    approximate=bool(valid and total>0 and source_total>0 and difference!=0 and abs(difference)<=100 and abs(difference)/total<=.01)
    good=bool(allow_split and bar.get('complete') and valid and (difference==0 or approximate))
    return dict(time=bar['time'],total=total,source_total=source_total,difference=difference,approximate=good and approximate,
                **{k:packet[k] if good else total if k=='unknown' else 0 for k in keys},verified=good)


class TencentTicks:
    def __init__(self,reader=None):
        self.reader=reader;self.lock=threading.Lock();self.last_request=0

    def get(self,code,action,page=None):
        params=dict(appn='detail',action=action,c=code)
        if page is not None:params['p']=page
        url='https://stock.gtimg.cn/data/index.php?'+urlencode(params)
        if self.reader:return self.reader(url)
        # One shared limiter, including rapid stock switches; incremental pages only.
        with self.lock:
            time.sleep(max(0,.15-(time.monotonic()-self.last_request)));self.last_request=time.monotonic()
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'}),timeout=6) as r:
            data=r.read(2*1024*1024+1)
            if len(data)>2*1024*1024:raise ValueError('分笔响应过大')
            return data.decode('utf-8')

    def fetch(self,code,day,previous=None):
        code=symbol(code);actual,ranges=timeline(self.get(code,'timeline'),code)
        if actual!=day:raise ValueError('公开分笔仅提供最近交易日，该历史日暂无已保存分笔')
        prior=(previous or {}) if (previous or {}).get('day')==day else {}
        old=prior.get('pages',[]);pages=[None]*len(ranges);missing=[]
        for i,bound in enumerate(ranges):
            if bound.split('~')[0]>='14:57:00':
                pages[i]=dict(range=bound,data='');continue
            if i<len(old) and old[i].get('range')==bound and i<len(ranges)-1:pages[i]=old[i]
            else:missing.append(i)
        def load(i):
            index,data=assignment(self.get(code,'data',i),'v_detail_data_'+code)
            if index!=i or not isinstance(data,str):raise ValueError('分笔分页返回不一致')
            rows=[r for r in data.split('|') if r]
            if not rows or rows[0].split('/')[1]!=ranges[i].split('~')[0]:raise ValueError('分笔分页起点与目录不一致')
            # The newest page can grow during collection, older pages must be fixed.
            if i<len(ranges)-1 and rows[-1].split('/')[1]!=ranges[i].split('~')[1] and min(rows[-1].split('/')[1],ranges[i].split('~')[1])<'14:57:00':raise ValueError('分笔分页终点与目录不一致')
            return i,dict(range=ranges[i],data=data)
        pool=ThreadPoolExecutor(max_workers=2)
        futures=[pool.submit(load,i) for i in missing]
        try:
            for future in as_completed(futures):i,value=future.result();pages[i]=value
        finally:pool.shutdown(wait=True,cancel_futures=True)
        after,_=timeline(self.get(code,'timeline'),code)
        if after!=day:raise ValueError('采集期间分笔交易日发生变化')
        result=aggregate(pages)
        return dict(version=1,aggregation_version=2,code=code,day=day,source='tencent_tick',fetched_at=now_cn().isoformat(),pages=pages,**result)


class VolumeFlow:
    def __init__(self,store,enabled=True,fetcher=None,secondary=None):
        self.store=store;self.enabled=enabled;self.fetcher=fetcher or TencentTicks();self.lock=threading.Lock()
        self.secondary=secondary if secondary is not None else EastmoneyTicks() if fetcher is None else None
        self.inflight=set();self.retry={};self.errors={};self.secondary_retry={};self.secondary_errors={}

    def request(self,code,day):
        code=symbol(code);date.fromisoformat(day);key=(code,day)
        rows=self.store.getcache(code,'minute',day)
        if not rows:return dict(code=code,day=day,status='unavailable',minutes=[],message='暂无该日分钟量，按原总量显示')
        if rows[0]['data'].get('source')!='tencent':return dict(code=code,day=day,status='unavailable',minutes=[],message='分钟量非腾讯口径，按原总量显示')
        raw=self.store.getcache(code,'volume_flow',day);cached=raw[0]['data'] if raw else None
        if cached and (cached.get('code')!=code or cached.get('day')!=day or cached.get('version')!=1):cached=None
        if cached and cached.get('pages') and cached.get('aggregation_version',0)<2:
            try:
                migrated=dict(cached,**aggregate(cached['pages']),aggregation_version=2)
                # A fresh background result must never be overwritten by an old-cache migration.
                self.store.execute("UPDATE cache SET payload=? WHERE code=? AND kind='volume_flow' AND day=? AND COALESCE(json_extract(payload,'$.aggregation_version'),0)<2",(json.dumps(migrated,ensure_ascii=False),code,day))
                cached=self.store.getcache(code,'volume_flow',day)[0]['data']
            except (ValueError,TypeError,KeyError):cached=None
        now=now_cn()
        try:age=(now-datetime.fromisoformat(cached['fetched_at'])).total_seconds() if cached else None
        except (ValueError,TypeError,KeyError):cached=None;age=None
        stale=not cached or (day==now.date().isoformat() and now.strftime('%H:%M')<'15:05' and (age<0 or age>=30))
        supplement=self.store.getcache(code,'volume_flow_em',day)
        extra=supplement[0]['data'] if supplement else None
        if extra and (extra.get('code')!=code or extra.get('day')!=day or extra.get('version')!=1 or extra.get('source')!='eastmoney_tick' or not extra.get('date_verified')):extra=None
        def wants_extra(bar):
            if not bar.get('complete') or bar['volume']<=0 or not ('09:31'<=bar['time']<='11:30' or '13:01'<=bar['time']<='14:57'):return False
            cell=classify_minute(bar,(cached or {}).get('buckets',{}).get(bar['time']))
            if cell['verified'] and not cell['approximate']:return False
            packet=(extra or {}).get('buckets',{}).get(bar['time'])
            try:
                if packet and packet['total']==bar['volume'] and Decimal(packet['last_price'])==Decimal(str(bar['close'])) and classify_minute(bar,packet)['verified']:return False
            except (KeyError,ValueError,TypeError,ArithmeticError):pass
            return True
        needs_extra=self.secondary and any(wants_extra(bar) for bar in rows[0]['data'].get('bars',[]))
        with self.lock:
            refresh_primary=stale and time.monotonic()>=self.retry.get(key,0)
            refresh_extra=needs_extra and time.monotonic()>=self.secondary_retry.get(key,0)
            if self.enabled and (refresh_primary or refresh_extra) and key not in self.inflight and len(self.inflight)<2:
                self.inflight.add(key)
                if refresh_primary:self.retry[key]=time.monotonic()+30
                threading.Thread(target=self._fetch,args=(key,cached,refresh_primary),daemon=True).start()
            loading=key in self.inflight
            error=self.errors.get(key,'')
        live_window=day==now.date().isoformat() and ('09:30:00'<=now.strftime('%H:%M:%S')<='11:30:00' or '13:00:00'<=now.strftime('%H:%M:%S')<'14:57:00')
        def fresh(data):
            try:
                tick=datetime.fromisoformat(day+'T'+data['last_tick']).replace(tzinfo=now.tzinfo)
                fetched=datetime.fromisoformat(data['fetched_at'])
                return 0<=(now-fetched).total_seconds()<=90 and 0<=(now-tick).total_seconds()<=90
            except (ValueError,TypeError,KeyError):return False
        primary_fresh=fresh(cached);extra_fresh=fresh(extra)
        def usable(data,bar,is_fresh):
            if not live_window or is_fresh:return True
            # A late update must not blank already settled history. A stale
            # snapshot can only cover minutes ended >=90s before it was fetched.
            try:
                end=datetime.fromisoformat(day+'T'+bar['time']+':00').replace(tzinfo=now.tzinfo)
                tick=datetime.fromisoformat(day+'T'+data['last_tick']).replace(tzinfo=now.tzinfo)
                fetched=datetime.fromisoformat(data['fetched_at'])
                return end<=tick<=fetched<=now and (fetched-end).total_seconds()>=90
            except (ValueError,TypeError,KeyError):return False
        minutes=[];sources=set()
        for bar in rows[0]['data'].get('bars',[]):
            chosen=classify_minute(bar,(cached or {}).get('buckets',{}).get(bar['time']),usable(cached,bar,primary_fresh))
            chosen['source']='tencent_tick' if chosen['verified'] else None
            packet=(extra or {}).get('buckets',{}).get(bar['time'])
            # Check persisted supplements again against the currently displayed minute.
            try:price_match=bool(packet and bar.get('close') is not None and Decimal(str(packet.get('last_price','NaN')))==Decimal(str(bar['close'])))
            except Exception:price_match=False
            if price_match and packet.get('total')==bar['volume']:
                other=classify_minute(bar,packet,usable(extra,bar,extra_fresh))
                if other['verified'] and (not chosen['verified'] or chosen['approximate']):chosen=dict(other,source='eastmoney_tick')
            if chosen['verified']:sources.add(chosen['source'])
            minutes.append(chosen)
        verified=sum(m['verified'] for m in minutes);approximate=sum(m['approximate'] for m in minutes)
        secondary_count=sum(m.get('source')=='eastmoney_tick' for m in minutes)
        status='ready' if verified else 'loading' if loading else 'unavailable'
        label='腾讯分笔 + 东财补充' if secondary_count else '腾讯分笔'
        message=f'{label} · 可拆分{verified}根（含{approximate}根约值），其余按总量显示' if verified else '正在补查买卖量，当前按原总量显示' if loading else error or '买卖量暂无可用数据，按原总量显示'
        total_only=bool(live_window and not verified)
        if total_only:message='当日分笔未确认及时更新，正在补查备用来源，暂按原总量显示'
        elif live_window and not(primary_fresh or extra_fresh):message+=' · 保留已核验历史分钟，新分钟补查中'
        if error and verified:message+=' · 主来源更新失败，保留已核验分笔'
        return dict(code=code,day=day,status=status,source='+'.join(sorted(sources)) or 'tencent_tick',minutes=minutes,verified_minutes=verified,approximate_minutes=approximate,secondary_minutes=secondary_count,total_only=total_only,live_fresh=(primary_fresh or extra_fresh) if live_window else None,updated_at=(cached or extra or {}).get('fetched_at'),message=message)

    def _fetch(self,key,previous,refresh_primary=True):
        primary=previous
        try:
            try:
                if refresh_primary:
                    primary=self.fetcher.fetch(*key,previous)
                    self.store.cache(key[0],'volume_flow',key[1],primary)
                    with self.lock:self.errors.pop(key,None)
            except Exception as error:
                message=str(error) if isinstance(error,ValueError) else '主分笔暂不可用（'+type(error).__name__+'）'
                with self.lock:self.errors[key]=message;self.retry[key]=time.monotonic()+600
            reference=self.store.getcache(key[0],'minute',key[1])
            if not reference or not self.secondary:return
            reference=reference[0]['data']
            # Auctions have no meaningful B/S classification. Do not fetch extra
            # providers just to color auction bars or genuinely zero-volume minutes.
            def needs_supplement(bar):
                if not bar.get('complete') or bar['volume']<=0 or not ('09:31'<=bar['time']<='11:30' or '13:01'<=bar['time']<='14:57'):return False
                cell=classify_minute(bar,(primary or {}).get('buckets',{}).get(bar['time']))
                return not cell['verified'] or cell['approximate']
            missing=any(needs_supplement(bar) for bar in reference.get('bars',[]))
            now=now_cn()
            stale_live=key[1]==now.date().isoformat() and ('09:30'<=now.strftime('%H:%M')<='11:30' or '13:00'<=now.strftime('%H:%M')<'14:57')
            if stale_live and primary:
                try:
                    tick=datetime.fromisoformat(key[1]+'T'+primary['last_tick']).replace(tzinfo=now.tzinfo)
                    stale_live=not (0<=(now-tick).total_seconds()<=90 and 0<=(now-datetime.fromisoformat(primary['fetched_at'])).total_seconds()<=90)
                except (ValueError,TypeError,KeyError):pass
            if (missing or stale_live) and time.monotonic()>=self.secondary_retry.get(key,0):
                self.secondary_retry[key]=time.monotonic()+30
                try:
                    supplement=self.secondary.fetch(*key,reference)
                    self.store.cache(key[0],'volume_flow_em',key[1],supplement)
                    with self.lock:self.secondary_errors.pop(key,None)
                except Exception as error:
                    with self.lock:
                        self.secondary_errors[key]=type(error).__name__+': '+str(error)[:120]
                        self.secondary_retry[key]=time.monotonic()+600
        finally:
            with self.lock:self.inflight.discard(key)
