"""Test-only IPC peer. Uses the real App/SQLite with fake public data, no OS/phone sends."""
import json,sys,os,time
from datetime import datetime
from core.app import App,CN
app=App(os.environ['STOCK_MONITOR_DATA'],False)
daily_feeds={};daily_delays={}
class Provider:
 def quote(self,code):
  if code=='sh699999':raise ValueError('股票不存在或暂时没有行情')
  return dict(code=code,name='贵州茅台' if code=='sh600519' else code,date='2026-10-16',timestamp='2026-10-16T15:00:00+08:00',price='9.99',limit_up='10',change='-0.1')
 def minutes(self,code):
  return [dict(date='2026-10-16',bars=[dict(time='09:31',close='9.99',volume=100,complete=True)],volume_unit='shares',source='test')]
 def daily(self,code,start,end):
  if code in daily_feeds:
   time.sleep(daily_delays.get(code,0));return [r for r in daily_feeds[code] if start<=r['date']<=end]
  rows=[r['data'] for r in app.store.getcache(code,'daily') if start<=r['day']<=end]
  return rows or ([dict(date='2026-10-16',open='10',close='9.99',high='10',low='9',volume='100',volume_unit='shares',source='test')] if start<='2026-10-16'<=end else [])
app.provider=Provider()
from unittest.mock import Mock,patch
paper_clock=patch("core.paper.now_cn",return_value=datetime(2026,10,23,10,0,tzinfo=CN)).start()
app.archive.provider=Mock();app.archive.provider.minutes.return_value=[]
for line in sys.stdin:
 try:
  req=json.loads(line)
  if req['method']=='__audit_cache':
   arg=req['args'];app.store.cache(arg['code'],'minute',arg['day'],arg['data']);data=True
  elif req['method']=='__audit_auto_runs':
   arg=req['args']
   for ident,number in [('chart-a','1111111001'),('chart-b','2222222002')]:
    app.store.execute('INSERT OR REPLACE INTO broker_accounts(id,broker,account) VALUES(?,?,?)',(ident,'zhangle',number))
    app.store.execute('INSERT OR REPLACE INTO trading_rules VALUES(?,?,?,?,?)',(ident,arg['code'],json.dumps(dict(buy_enabled=True,sell_enabled=True)),1,arg['day']+'T09:00:00+08:00'))
   for row in arg['rows']:
    account=row.get('account','chart-a');ident=row['id'];stamp=arg['day']+'T'+row['time']+':35+08:00'
    payload=dict(mode=row.get('mode','live'),signal=dict(key=row['signal_key'],time=row['time'],price=row['reference']),reference_price=row['reference'],message=row.get('message','测试委托'),plan=dict(account_id=account,code=arg['code'],side=row.get('side','buy'),price=row['limit'],quantity=200),price_checks=dict(before_submit=dict(checked_at=stamp)))
    if row.get('verification'):payload['verification']=row['verification']
    app.store.execute('INSERT OR REPLACE INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,account,arg['code'],row.get('side','buy'),arg['day']+'|'+ident,arg['day'],row['status'],json.dumps(payload),stamp,stamp))
    if row['status'] not in ('skipped','trial'):
     ack=dict(status=row['status'],order_id='contract-'+ident)
     if row.get('legacy_receipt'):
      ack=dict(status='unknown',submitted=False,confirm=dict(title='委托买入',code=arg['code'][2:],price=row['limit'],quantity='200'),result=dict(kind='unknown',title='系统提示',message='委托提交成功,合同号:142783'))
     request=dict(account_id=account,code=arg['code'][2:],side=row.get('side','buy'),price=row['limit'],quantity=200,dry_run=False)
     app.store.execute('INSERT OR REPLACE INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+ident,account,json.dumps(request),row['status'],json.dumps(ack),stamp,stamp))
   data=True
  elif req['method']=='__audit_flow':
   arg=req['args'];app.store.cache(arg['code'],'volume_flow',arg['day'],arg['data']);data=True
  elif req['method']=='__audit_daily':
   arg=req['args'];app.store.cache(arg['code'],'daily',arg['day'],arg['data']);data=True
  elif req['method']=='__audit_daily_feed':
   daily_feeds[req['args']['code']]=req['args']['rows'];daily_delays[req['args']['code']]=req['args'].get('delay',0);app.store.execute('DELETE FROM daily_requests WHERE code=?',(req['args']['code'],));data=True
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
  elif req['method']=='__audit_market_decision_reference':
   # Use recorded public responses and an isolated store, never the user's account.
   from pathlib import Path
   from core.index_technical import parse_daily
   now=datetime.fromisoformat('2026-10-31T04:00:00+08:00')
   for module in ('core.breadth','core.index_technical','core.csi300'):
    patch(module+'.now_cn',return_value=now).start()
   source=Path(__file__).resolve().parents[2]/'docs/author-trading-system-20261028/vwmacd-tencent-20261031.json'
   rows=parse_daily(json.loads(source.read_text(encoding='utf-8')),'2026-01-01','2026-10-30')
   with patch('core.index_technical.fetch_daily',return_value=rows):app.index_technical.refresh(now)
   if app.index_technical.error:raise ValueError(app.index_technical.error)
   data=True
  elif req['method']=='__audit_breadth_error':
   app.breadth.error=req['args']['error'];data=True
  elif req['method']=='__audit_index_error':
   app.index_technical.error=req['args']['error'];data=True
  elif req['method']=='__audit_etf_option_clock':
   patch('core.etf_option_pcr.now_cn',return_value=datetime.fromisoformat(req['args']['now'])).start();data=True
  else:data=app.call(req['method'],req.get('args',{}))
  print(json.dumps(dict(ok=True,data=data),ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps(dict(ok=False,error=str(e)),ensure_ascii=False),flush=True)
app.stop.set();app.store.db.close()
