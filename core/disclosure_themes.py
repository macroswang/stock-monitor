"""Snapshot-scoped, disclosure-backed A-share baskets and their market data."""
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlencode

from .provider import CN, get

CNINFO = 'https://static.cninfo.com.cn/finalpage/'
FLOW_PATH = '/api/qt/stock/fflow/'
def money_flow(code, name, quote, day, closed):
    price, previous = float(quote['price']),float(quote['previous_close'])
    move = price/previous-1
    if quote['timestamp'][:10]!=day or min(price, previous)<=0 or not math.isfinite(move):
        raise ValueError('个股报价日期或价格异常')
    market = 1 if code.startswith('sh') else 0
    fields = 'f51,f52,f53,f54,f55,f56'
    if closed:
        endpoint = 'https://push2his.eastmoney.com'+FLOW_PATH+'daykline/get'
        fields += ',f57,f58,f59,f60,f61,f62,f63'
    else:
        endpoint = 'https://push2delay.eastmoney.com'+FLOW_PATH+'kline/get'
    params = dict(klt=101 if closed else 1, lmt=1 if closed else 0, secid=f'{market}.{code[2:]}',
                  fields1='f1,f2,f3', fields2=fields)
    data = json.loads(get(endpoint+'?'+urlencode(params)))['data']
    if data['code']!=code[2:] or data['market']!=market:
        raise ValueError('资金数据与证券代码不一致')
    stamp = quote['timestamp']
    if closed:
        point = data['klines'][-1].split(',')
        if (point[0]!=day or stamp[11:16]<'15:00' or not math.isclose(float(point[11]),price,abs_tol=.005)
                or not math.isclose(float(point[12]),100*move,abs_tol=.015)):
            raise ValueError('资金日期或收盘价未核对')
    else:
        quote_time = datetime.fromisoformat(stamp)
        # Minute series is cumulative. Use the last point at or before the quote.
        eligible = [line for line in data['klines'] if line.startswith(day+' ') and line[:16]<=stamp[:16].replace('T',' ')]
        point = eligible[-1].split(',')
        flow_time = datetime.strptime(point[0],'%Y-%m-%d %H:%M').replace(tzinfo=CN)
        if not 0<=(quote_time-flow_time).total_seconds()<=120:
            raise ValueError('盘中资金流未同步')
        stamp = flow_time.isoformat()
    net = float(point[1])
    if not math.isfinite(net):
        raise ValueError('资金数值无效')
    return net,stamp


def quoted_funds(codes,quotes,day,closed):
    ids=','.join(('1.' if c.startswith('sh') else '0.')+c[2:] for c in codes)
    params=dict(secids=ids,fltt=2,fields='f2,f12,f13,f18,f62,f66,f72,f124')
    data=json.loads(get('https://push2delay.eastmoney.com/api/qt/ulist.np/get?'+urlencode(params)))['data']
    validated={}
    for row in data['diff']:
        code=('sh' if row['f13']==1 else 'sz')+row['f12']
        if code not in codes:continue
        try:
            q=quotes[code]
            stamp=datetime.fromtimestamp(row['f124'],CN)
            when=datetime.fromisoformat(q['timestamp'])
            if stamp.date().isoformat()!=day or when.date()!=stamp.date():continue
            if closed:
                if min(stamp.hour,when.hour)<15:continue
            elif not 0<=(when-stamp).total_seconds()<=120:continue
            net=float(row['f62'])
            if not math.isclose(float(q['price']),float(row['f2']),abs_tol=.005):continue
            if not math.isclose(float(q['previous_close']),float(row['f18']),abs_tol=.005):continue
            if not math.isfinite(net) or abs(net-row['f66']-row['f72'])>max(100,abs(net)*.00001):continue
            validated[code]=(net,stamp.isoformat())
        except (KeyError,TypeError,ValueError):continue
    return validated


def collect(quotes, day, closed, pools, allow_partial=True):
    funds = {}
    codes=sorted({m[0] for _,members in pools.values() for m in members if m[0] in quotes})
    if len(codes)>=25:
        with ThreadPoolExecutor(4) as worker:
            batches=[worker.submit(quoted_funds,codes[i:i+60],quotes,day,closed) for i in range(0,len(codes),60)]
            for job in batches:
                try:funds.update(job.result())
                except (OSError,TypeError,ValueError,KeyError):pass
    with ThreadPoolExecutor(5) as worker:
        jobs = {c:worker.submit(money_flow,c,n,quotes[c],day,closed) for c,n in
                {(m[0],m[1]) for _,members in pools.values() for m in members} if c in quotes and c not in funds}
        for code,job in jobs.items():
            try:
                funds[code] = job.result()
            except (OSError, TypeError, ValueError, IndexError, KeyError, ArithmeticError):
                pass
    themes, sectors = [], []
    for key,(name,members) in pools.items():
        companies = [dict(code=c,name=n,basis=b,source=url if url.startswith('https://') else CNINFO+url)
                     for c,n,b,url in members]
        record = dict(code=key,name=name,members=companies)
        themes.append(record)
        missing = [n for c,n,_,_ in members if c not in funds]
        if len(members)<3:
            record['error']=f'已核实 {len(members)} 家相关公司，需要至少三家才能比较候选和两只同行；继续等。'
            continue
        if missing and allow_partial and len(members)-len(missing)>=max(3,math.ceil(.8*len(members))):
            record['unquoted']=len(missing)
            members=[m for m in members if m[0] in funds]
            record['members']=[m for m in companies if m['code'] in funds]
        elif missing:
            record['error']='、'.join(missing)+'的同日价格或资金流未核对，本期继续等。'
            continue
        codes = [m[0] for m in members]
        moves = [(float(quotes[c]['price'])/float(quotes[c]['previous_close'])-1)*100 for c in codes]
        change = sum(moves)/len(moves)
        net = sum(funds[c][0] for c in codes)
        record.update(change=change,net=net,advance=sum(p>0 for p in moves))
        sectors.append(dict(code=key,name=name,change_percent=change,net_yuan=net,
                            time=min(funds[c][1] for c in codes)))
    return themes,sectors


class LiveThemeFlow:
    """Keep network I/O off the RPC thread and never reuse flows from an older batch."""
    def __init__(self):
        self.lock=threading.Lock()
        self.running=False
        self.key=None
        self.results={}
        self.retry=0

    def view(self, pools, day, batch, quotes):
        key=(day,batch,tuple(sorted((code,tuple(m[0] for m in members)) for code,(_,members) in pools.items())))
        with self.lock:
            if not self.running and (self.key!=key or time.monotonic()>=self.retry):
                self.running=True
                threading.Thread(target=self._refresh,args=(key,quotes,pools),daemon=True).start()
            return self.results if self.key==key else {}

    def _refresh(self,key,quotes,pools):
        result={}
        try:
            day=key[0]
            # Use dated closing flows for a batch in which all relevant quotes are after close.
            closed=all(q['timestamp'][11:16]>='15:00' for q in quotes.values())
            _,rows=collect(quotes,day,closed,pools,allow_partial=False)
            result={r['code']:dict(change=r['change_percent'],net=r['net_yuan'],time=r['time'],inferred=not closed) for r in rows}
        finally:
            with self.lock:
                self.key=key
                self.results=result
                self.retry=float('inf') if len(result)==len(key[2]) else time.monotonic()+20
                self.running=False
