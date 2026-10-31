"""已选新浪板块的成分股报价采样，独立于资金和正式信号。"""
import math
import threading
import time
from datetime import datetime,time as clock_time,timedelta
from decimal import Decimal,InvalidOperation
from .provider import CN,get,now_cn
from .sector_flow import expected_day
from .sector_events import session


def parse_quotes(texts,members,now):
 now=now.astimezone(CN);expected=expected_day(now)
 if not expected:raise ValueError('交易日无法核对')
 codes={m['code'] for m in members};seen={}
 for text in texts:
  for part in text.split(';'):
   if '="' not in part:continue
   head,body=part.split('="',1);code=head.strip().removeprefix('v_');fields=body.split('"')[0].split('~')
   if code not in codes or code in seen or len(fields)<33:continue
   try:
    if fields[2]!=code[2:]:continue
    price=Decimal(fields[3]);prev=Decimal(fields[4]);stamp=datetime.strptime(fields[30],'%Y%m%d%H%M%S').replace(tzinfo=CN)
    if not price.is_finite() or not prev.is_finite() or price<=0 or prev<=0 or stamp.date().isoformat()!=expected or stamp>now+timedelta(seconds=5):continue
    if session(now) and (session(stamp)!=session(now) or (now-stamp).total_seconds()>180):continue
    # 收盘参照不能把停牌或早盘旧报价算作收盘。
    if not session(now) and (now.date().isoformat()!=expected or now.time()>=clock_time(15)) and stamp.time()<clock_time(15):continue
    seen[code]=(price,prev,stamp)
   except (ValueError,InvalidOperation,IndexError,OverflowError):continue
 if len(codes)<1 or len(seen)<math.ceil(len(codes)*0.9):raise ValueError('成分股报价覆盖不足或已过期')
 first=min(q[2] for q in seen.values());last=max(q[2] for q in seen.values())
 if session(now) and (last-first).total_seconds()>180:raise ValueError('成分股报价时间不一致')
 values=list(seen.values());advance=sum(p>v for p,v,_ in values);decline=sum(p<v for p,v,_ in values)
 average=sum(float((p/v-1)*100) for p,v,_ in values)/len(values)
 return dict(date=expected,first=first.isoformat(),last=last.isoformat(),collected_at=now.isoformat(),source='腾讯成分股报价',advance=advance,decline=decline,flat=len(values)-advance-decline,covered=len(values),expected=len(codes),average=average)


def fetch(members,now):
 codes=[m['code'] for m in members]
 if not codes or len(codes)>1000:raise ValueError('板块成分数量异常')
 chunks=[codes[i:i+80] for i in range(0,len(codes),80)]
 texts=[get('https://qt.gtimg.cn/q='+','.join(batch),'gb18030') for batch in chunks]
 return parse_quotes(texts,members,max(now,now_cn()))


class SectorConstituents:
 def __init__(self):self.lock=threading.Lock();self.cache={};self.series={};self.fingerprints={};self.running=set();self.errors={};self.attempt={}
 def _load(self,code,members):
  try:
   data=fetch(members,now_cn())
   with self.lock:
    signature=tuple(sorted(m['code'] for m in members))
    if self.fingerprints.get(code)!=signature:self.series.pop(code,None)
    self.fingerprints[code]=signature;self.cache[code]=data;self.errors.pop(code,None)
    points=self.series.setdefault(code,[])
    if points and points[-1]['date']!=data['date']:points.clear()
    if not points or points[-1]['last']!=data['last']:points.append(data)
    del points[:-240]
  except Exception:
   with self.lock:self.errors[code]='成分股报价不完整、过期或暂不可用'
  finally:
   with self.lock:self.running.discard(code)
 def view(self,code,members,enabled=True):
  if not members:return dict(data=None,points=[],running=False,error='板块成分尚未取得')
  with self.lock:
   if enabled and code not in self.running and time.monotonic()-self.attempt.get(code,float('-inf'))>=120:
    self.running.add(code);self.attempt[code]=time.monotonic();threading.Thread(target=self._load,args=(code,members),daemon=True).start()
   data=self.cache.get(code);now=now_cn()
   if self.fingerprints.get(code)!=tuple(sorted(m['code'] for m in members)):data=None
   if data:
    try:
     last=datetime.fromisoformat(data['last']);age=(now-last).total_seconds()
     if data['date']!=expected_day(now) or age<0 or (session(now) and (session(last)!=session(now) or age>180)):data=None
    except (ValueError,KeyError,TypeError):data=None
   return dict(data=data,points=list(self.series.get(code,[])) if data else [],running=code in self.running,error=self.errors.get(code,''))
