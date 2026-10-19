"""Twenty observed trading dates: primary Tencent, whole-day Sina history only."""
import json,threading,time
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode
from .provider import get,symbol,now_cn,CN
from .validated_engine import MINUTES
from .sources import provider_name

class SinaHistory:
 def minutes(self,code):
  raw=get('https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData?'+urlencode(dict(symbol=symbol(code),scale=1,ma='no',datalen=1970)))
  text=raw.strip()
  if text.startswith('['):rows=json.loads(text)
  elif '=(' in text:rows=json.loads(text.split('=(',1)[1].rsplit(');',1)[0])
  else:raise ValueError('新浪历史分钟返回格式异常')
  if not isinstance(rows,list):raise ValueError('新浪历史分钟暂不可用')
  groups={};previous=''
  for r in rows:
   stamp=datetime.fromisoformat(r['day']).replace(tzinfo=CN);key=stamp.isoformat()
   if key<=previous:raise ValueError('新浪分钟重复或乱序')
   previous=key;v=Decimal(str(r['volume']));cash=Decimal(str(r['amount']));lo=Decimal(str(r['low']));hi=Decimal(str(r['high']));close=Decimal(str(r['close']))
   if not all(x.is_finite() for x in [v,cash,lo,hi,close]) or v<0 or v!=int(v) or cash<0 or not 0<lo<=close<=hi:raise ValueError('新浪分钟数值异常')
   if v and not lo*Decimal('.97')<=cash/v<=hi*Decimal('1.03'):raise ValueError('新浪量额单位无法核对，拒绝使用')
   day=stamp.date().isoformat();groups.setdefault(day,[]).append(dict(time=stamp.strftime('%H:%M'),open=r['open'],close=r['close'],high=r['high'],low=r['low'],volume=int(v),amount=str(cash),complete=(now_cn()-stamp).total_seconds()>=3,average=None))
  result=[]
  for day,bars in groups.items():
   full=bars[0]['time']=='09:31';cash=Decimal(0);volume=0;expected=MINUTES+['14:57','15:00'];index=0
   for b in bars:
    if index>=len(expected) or b['time']!=expected[index]:full=False
    index+=1
    cash+=Decimal(b['amount']);volume+=b['volume']
    if full and volume:b['average']=str(cash/volume)
   result.append(dict(date=day,bars=bars,source='sina',volume_unit='shares',adjustment='none',rule_compatible=False,
    average_basis='新浪当日累计量额，首分钟含集合竞价' if full else '缺少开盘前缀，均价不可还原',
    source_note='历史补充；新浪09:31含集合竞价且分钟边界与腾讯有差异，尚未认证规则回放。若缺少分钟，均价仅显示连续开盘前缀'))
  return result

def quality(data):
 bars={b['time']:b for b in data.get('bars',[]) if b.get('complete')}
 return len([t for t in MINUTES if t in bars])

class Archive:
 def __init__(self,app):
  self.app=app;self.provider=SinaHistory();self.lock=threading.RLock();self.last_request=0
  app.store.execute('CREATE TABLE IF NOT EXISTS archive_requests(code TEXT,source TEXT,attempt REAL,error TEXT,PRIMARY KEY(code,source))')
 def dates(self):
  end=self.app.daily_cache.completed_day().isoformat()
  return [r['day'] for r in reversed(self.app.store.query("SELECT DISTINCT day FROM cache WHERE kind='daily' AND day<=? ORDER BY day DESC LIMIT 20",(end,)))]
 def status(self,code):
  cached={r['day']:r['data'] for r in self.app.store.getcache(code,'minute')};items=[]
  for day in self.dates():
   data=cached.get(day);q=quality(data or {});bars=data.get('bars',[]) if data else []
   full=q==len(MINUTES) and any(b['time']=='15:00' and b.get('complete') for b in bars)
   source=provider_name(data.get('source')) if data else None
   items.append(dict(date=day,status='complete' if full else 'partial' if data else 'missing',source=source,
    points=q,expected=len(MINUTES),rule_ready=bool(full and data.get('limit_up') and data.get('rule_compatible',True)),
    rule_message='新浪口径待核对' if data and data.get('rule_compatible') is False else '缺少涨停参考价' if full and not data.get('limit_up') else '',
    last_time=bars[-1]['time'] if bars else None))
  return dict(code=code,target=20,basis='依据本地已下载日K的最近交易日期；不足20日会明确显示',items=items,
    complete=sum(r['status']=='complete' for r in items),partial=sum(r['status']=='partial' for r in items),missing=sum(r['status']=='missing' for r in items),
    requests=self.app.store.query('SELECT source,attempt,error FROM archive_requests WHERE code=?',(code,)))
 def fetch(self,code,source,fn):
  prior=self.app.store.query('SELECT * FROM archive_requests WHERE code=? AND source=?',(code,source))
  if prior:
   finalized=datetime.fromtimestamp(prior[0]['attempt'],CN).isoformat()>=self.app.daily_cache.completed_day().isoformat()+'T15:15'
   if time.time()-prior[0]['attempt']<(3600 if prior[0]['error'] else 43200) and (prior[0]['error'] or finalized):return []
  if self.app.stop.wait(max(0,1-(time.monotonic()-self.last_request))):return []
  self.last_request=time.monotonic()
  self.app.store.execute('INSERT OR REPLACE INTO archive_requests VALUES(?,?,?,?)',(code,source,time.time(),'正在获取'))
  try:
   rows=fn(code)
   self.app.store.execute('UPDATE archive_requests SET error=? WHERE code=? AND source=?',('',code,source));return rows
  except Exception:
   self.app.store.execute('UPDATE archive_requests SET error=? WHERE code=? AND source=?',('获取失败，已保留缓存；1小时后可重试',code,source));return []
 def update(self,code):
  with self.lock:
   if self.app.stop.is_set():return self.status(code)
   now=now_cn()
   # Never add historical IO during continuous trading; startup/after-close backfill only.
   if now.weekday()<5 and '09:15'<=now.strftime('%H:%M')<'15:15':return self.status(code)
   status=self.status(code)
   if not status['items'] or status['complete']==len(status['items']):return status
   recent=self.app.store.query('SELECT * FROM minute_requests WHERE code=?',(code,))
   final_day=status['items'][-1]
   needs_final=final_day['status']=='partial'
   if needs_final or not recent or time.time()-recent[0]['attempt']>=1800:
    for g in self.fetch(code,'tencent',self.app.provider.minutes):self.app.cache_minutes(code,g)
   missing={i['date'] for i in self.status(code)['items'] if i['status']!='complete'}
   if missing:
    for g in self.fetch(code,'sina',self.provider.minutes):
     if g['date'] not in missing:continue
     old=self.app.store.getcache(code,'minute',g['date'])
     # Never splice minutes or replace an existing Tencent day with another provider.
     if old and old[0]['data'].get('source') not in ('sina',):continue
     if old and quality(old[0]['data'])>quality(g):continue
     self.app.store.cache(code,'minute',g['date'],g)
   return self.status(code)
