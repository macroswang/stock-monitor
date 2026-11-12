"""Lazy historical minute loading with persistent cooldown; live sampling is separate."""
import threading,time
from .provider import now_cn
from .paper_session import calendar

class MinuteCache:
 def __init__(self,app):
  self.app=app;self.lock=threading.RLock()
  app.store.execute('CREATE TABLE IF NOT EXISTS minute_requests(code TEXT PRIMARY KEY,attempt REAL,error TEXT)')
 def note(self,code,error=''):
  self.app.store.execute('INSERT OR REPLACE INTO minute_requests VALUES(?,?,?)',(code,time.time(),error))
 def ensure(self,code,day,refresh=False):
  with self.lock:
   if refresh:
    now=now_cn();closed=calendar(now.year);clock=now.strftime('%H:%M:%S')
    if day!=now.date().isoformat():raise ValueError('实时分时只能刷新今天')
    if now.weekday()>=5 or closed is None or any(first<=day<=last for first,last in closed) or not ('09:20:00'<=clock<'11:30:00' or '13:00:00'<=clock<'15:00:00'):
     return dict(status='paused')
   if not refresh and self.app.store.getcache(code,'minute',day):return dict(status='cached')
   old=self.app.store.query('SELECT * FROM minute_requests WHERE code=?',(code,))
   rows=self.app.store.getcache(code,'minute')
   if refresh and old and time.time()-old[0]['attempt']<(30 if old[0]['error'] else 5):
    if old[0]['error']:raise ValueError('分时更新暂不可用，已保留缓存，稍后自动重试')
    return dict(status='cached')
   if not refresh and old and time.time()-old[0]['attempt']<1800:
    outside=not old[0]['error'] and rows and day<rows[0]['day']
    return dict(status='retry_later' if old[0]['error'] else 'outside_coverage' if outside else 'unavailable',message='上次请求失败，稍后重试' if old[0]['error'] else '该日不在来源本轮返回的分时范围；可查看日K，不能据此认定无触发')
   self.note(code,'正在获取')
   try:
    groups=self.app.provider.minutes(code)
    for group in groups:
     if not refresh or group.get('date')==day:self.app.cache_minutes(code,group)
    if refresh and not any(group.get('date')==day and group.get('bars') for group in groups):
     raise ValueError('来源未返回今天的分时')
    self.note(code)
   except Exception:
    self.note(code,'网络或来源暂时异常')
    raise ValueError('分时更新失败，已保留缓存，稍后自动重试' if refresh else '分时获取失败，已保留本地缓存；30分钟内不会重复请求')
   return dict(status='downloaded' if self.app.store.getcache(code,'minute',day) else 'unavailable',message='仅缓存来源实际返回的日期，未返回不代表无成交或无触发')
