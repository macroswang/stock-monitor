"""Test-only IPC peer. Uses the real App/SQLite with fake public data, no OS/phone sends."""
import json,sys,os
from datetime import datetime
from core.app import App,CN
app=App(os.environ['STOCK_MONITOR_DATA'],False)
class Provider:
 def quote(self,code):
  if code=='sh699999':raise ValueError('股票不存在或暂时没有行情')
  return dict(code=code,name='贵州茅台' if code=='sh600519' else code,date='2026-10-16',timestamp='2026-10-16T15:00:00+08:00',price='9.99',limit_up='10',change='-0.1')
 def minutes(self,code):
  return [dict(date='2026-10-16',bars=[dict(time='09:31',close='9.99',volume=100,complete=True)],volume_unit='shares',source='test')]
 def daily(self,*args):return [dict(date='2026-10-16',open='10',close='9.99',high='10',low='9',volume='100',volume_unit='shares',source='test')]
app.provider=Provider()
from unittest.mock import Mock,patch
paper_clock=patch("core.paper.now_cn",return_value=datetime(2026,10,23,10,0,tzinfo=CN)).start()
app.archive.provider=Mock();app.archive.provider.minutes.return_value=[]
for line in sys.stdin:
 try:
  req=json.loads(line)
  if req['method']=='__audit_cache':
   arg=req['args'];app.store.cache(arg['code'],'minute',arg['day'],arg['data']);data=True
  elif req['method']=='__audit_flow':
   arg=req['args'];app.store.cache(arg['code'],'volume_flow',arg['day'],arg['data']);data=True
  elif req['method']=='__audit_daily':
   arg=req['args'];app.store.cache(arg['code'],'daily',arg['day'],arg['data']);data=True
  elif req['method']=='__audit_quote':
   arg=req['args'];app.quotes[arg['code']]=arg['quote'];data=True
   if arg['quote'].get('name'):app.store.remember(arg['code'],arg['quote']['name'])
  elif req['method']=='__audit_market':
   for q in req['args']['quotes']:app.store.cache(q['code'],'market_quote',q['timestamp'][:10],q)
   data=True
  elif req['method']=='__audit_clock':
   paper_clock.return_value=datetime.fromisoformat(req['args']['now']);data=True
  elif req['method']=='__audit_event':
   app.store.event(req['args'],'live');data=True
  else:data=app.call(req['method'],req.get('args',{}))
  print(json.dumps(dict(ok=True,data=data),ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps(dict(ok=False,error=str(e)),ensure_ascii=False),flush=True)
app.stop.set();app.store.db.close()
