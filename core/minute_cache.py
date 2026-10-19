"""Lazy historical minute loading with persistent cooldown; live sampling is separate."""
import threading,time

class MinuteCache:
 def __init__(self,app):
  self.app=app;self.lock=threading.RLock()
  app.store.execute('CREATE TABLE IF NOT EXISTS minute_requests(code TEXT PRIMARY KEY,attempt REAL,error TEXT)')
 def note(self,code,error=''):
  self.app.store.execute('INSERT OR REPLACE INTO minute_requests VALUES(?,?,?)',(code,time.time(),error))
 def ensure(self,code,day):
  with self.lock:
   if self.app.store.getcache(code,'minute',day):return dict(status='cached')
   old=self.app.store.query('SELECT * FROM minute_requests WHERE code=?',(code,))
   rows=self.app.store.getcache(code,'minute')
   if old and time.time()-old[0]['attempt']<1800:
    outside=not old[0]['error'] and rows and day<rows[0]['day']
    return dict(status='retry_later' if old[0]['error'] else 'outside_coverage' if outside else 'unavailable',message='上次请求失败，稍后重试' if old[0]['error'] else '该日不在来源本轮返回的分时范围；可查看日K，不能据此认定无触发')
   self.note(code,'正在获取')
   try:
    groups=self.app.provider.minutes(code)
    for group in groups:self.app.cache_minutes(code,group)
    self.note(code)
   except Exception:
    self.note(code,'网络或来源暂时异常');raise ValueError('分时获取失败，已保留本地缓存；30分钟内不会重复请求')
   return dict(status='downloaded' if self.app.store.getcache(code,'minute',day) else 'unavailable',message='仅缓存来源实际返回的日期，未返回不代表无成交或无触发')
