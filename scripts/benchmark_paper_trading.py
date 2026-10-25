import sys,tempfile,json,time,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.store import Store
from core.paper import Paper
from unittest.mock import patch
from datetime import datetime
from core.provider import CN
with patch('core.paper.now_cn',return_value=datetime(2026,10,23,10,0,tzinfo=CN)),tempfile.TemporaryDirectory() as tmp:
 st=Store(Path(tmp)/'monitor.sqlite3');p=Paper(Path(tmp)/'paper.sqlite3',st)
 account=p.call('paper_create',{'cash':1000000})['id']
 bars=[dict(time=f'{m//60:02}:{m%60:02}',close='10',volume=10000000,complete=True) for m in [*range(571,691),*range(781,901)]]
 for n in range(5):
  code=f'sh60000{n}'
  for day in range(1,29):st.cache(code,'minute',f'2026-09-{day:02}',dict(bars=bars,volume_unit='shares',source='test'))
  st.cache(code,'minute','2026-10-19',dict(bars=bars,volume_unit='shares',source='test'))
 s=p.load(account);s['clock']='2026-10-19 09:31';s['lots']=[dict(code=f'sh60000{n}',name='bench',shares=100,cost=100000,day='',seed=True) for n in range(5)]
 with p.db:
  p.save(s)
  for n in range(10000):
   o=dict(id=str(n),account=account,code='sh600000',name='bench',stamp='2026-09-28 09:31',side='buy' if n%2 else 'sell',shares=100,price=1000,amount=100000,fees=500,commission=500,transfer=0,stamp_tax=0,realized=0,status='filled',parent_id='bench',reason='',source='test',origin='bench')
   p.db.execute('INSERT INTO orders(account,id,payload,request) VALUES(?,?,?,?)',(account,str(n),json.dumps(o),'{}'))
  if hasattr(p,'index_fill'):
   for row in p.db.execute('SELECT payload FROM orders'):p.index_fill(json.loads(row[0]))
 chart_times=[]
 for _ in range(8):
  t=time.perf_counter();chart=p.call('paper_chart',dict(account=account,code='sh600000',start='2026-09-01',end='2026-10-19'));chart_times.append((time.perf_counter()-t)*1000)
 times=[]
 for _ in range(8):
  t=time.perf_counter();out=p.call('paper_snapshot',{'account':account});times.append((time.perf_counter()-t)*1000)
 print(json.dumps(dict(rows=10000,positions=5,cache_days_each=29,snapshot_median_ms=round(statistics.median(times),2),snapshot_max_ms=round(max(times),2),payload_bytes=len(json.dumps(out)),chart_median_ms=round(statistics.median(chart_times),2),chart_points=len(chart['points'])),ensure_ascii=False))
 p.db.close();st.db.close()
