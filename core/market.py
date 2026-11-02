"""Shared index feed; isolated from stock rules and fetched once per 30 seconds."""
import json,threading,concurrent.futures
from decimal import Decimal
from datetime import datetime
from .provider import get,now_cn,CN

CODES=('sh000001','sz399001','sz399006')
NAMES={'sh000001':'上证指数','sz399001':'深证成指','sz399006':'创业板指'}

def quotes():
 result=[]
 for part in get('https://qt.gtimg.cn/q='+','.join(CODES),'gb18030').split(';'):
  if '=\"' not in part:continue
  head,body=part.split('=\"',1);code=head.strip().removeprefix('v_');f=body.split('"')[0].split('~')
  if code not in CODES or len(f)<35:continue
  values=[Decimal(f[i]) for i in (3,4,31,32)]
  if not all(x.is_finite() for x in values) or min(values[:2])<=0:continue
  stamp=datetime.strptime(f[30],'%Y%m%d%H%M%S').replace(tzinfo=CN)
  result.append(dict(code=code,name=f[1],price=f[3],previous_close=f[4],change=f[31],percent=f[32],timestamp=stamp.isoformat(),source='tencent'))
 return result

def minutes(code='sh000001'):
 if code not in CODES:raise ValueError('不支持的指数')
 raw=json.loads(get('https://web.ifzq.gtimg.cn/appstock/app/day/query?code='+code))['data'][code];result=[]
 for item in raw['data']:
  date=datetime.strptime(item['date'],'%Y%m%d').date().isoformat();base=Decimal(str(item.get('prec',0)))
  if not base.is_finite() or base<=0:continue
  bars=[]
  for line in item['data']:
   t,p,*_=line.split();v=Decimal(p)
   if len(t)!=4 or not t.isdigit() or not v.is_finite() or v<=0:raise ValueError('指数分钟数据异常')
   bars.append(dict(time=t[:2]+':'+t[2:],close=p))
  if [b['time'] for b in bars]!=sorted(set(b['time'] for b in bars)):raise ValueError('指数分钟顺序异常')
  result.append(dict(code=code,name=NAMES[code],date=date,previous_close=str(base),bars=bars,source='tencent'))
 return result

class Market:
 def __init__(self,app):self.app=app;self.error='';self.index_errors={};self.lock=threading.Lock()
 def poll(self):
  with self.lock:
   errors=[];self.index_errors={}
   # Shared feed: fetch each index once, off the UI/stock-monitoring threads.
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    pending={pool.submit(quotes):None,**{pool.submit(minutes,code):code for code in CODES}}
    for future in concurrent.futures.as_completed(pending):
     code=pending[future]
     try:
      for item in future.result():
       if code:self.app.store.cache(code,'market_minute',item['date'],dict(item,code=code,name=NAMES[code]))
       else:self.app.store.cache(item['code'],'market_quote',item['timestamp'][:10],item)
     except Exception:
      if code:self.index_errors[code]=NAMES[code]+'分时暂时不可用'
      else:errors.append('指数报价暂时不可用')
   if 'sh000001' in self.index_errors:errors.append(self.index_errors['sh000001'])
   self.error='；'.join(errors)
 def index_view(self,code,day=None):
  if code not in CODES:raise ValueError('不支持的指数')
  if day is not None:day=datetime.fromisoformat(day).date().isoformat()
  quotes=self.app.store.getcache(code,'market_quote',day) if day else self.app.store.getcache(code,'market_quote')
  quote=quotes[-1]['data'] if quotes else None
  if day is None:day=quote['timestamp'][:10] if quote else None
  rows=self.app.store.getcache(code,'market_minute',day) if day else []
  minute=dict(rows[0]['data'],code=code,name=NAMES[code]) if rows else None
  return dict(quotes=[quote] if quote else [],minute=minute,error=self.index_errors.get(code,''))
 def view(self,day):
  items=[]
  for code in CODES:
   rows=self.app.store.getcache(code,'market_quote')
   if rows:items.append(rows[-1]['data'])
  rows=self.app.store.getcache('sh000001','market_minute',day) if day else []
  return dict(quotes=items,minute=rows[0]['data'] if rows else None,error=self.error)
