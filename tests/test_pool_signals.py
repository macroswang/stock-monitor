import json,tempfile,time,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock,patch
from core.app import App
from core.provider import Tencent,CN
from core.pool_signals import bottom_point


class PoolSignalsTest(unittest.TestCase):
 def test_postclose_source_correction_does_not_discard_valid_intraday_data(self):
  day=dict(date='20261112',data=['0930 10 100 100000','1500 10 200 200000','1515 10 220 220000','1516 10 210 210000'])
  raw=json.dumps(dict(data={'sz000021':dict(data=[day])}))
  with patch('core.provider.get',return_value=raw):
   groups=Tencent().minutes('sz000021',datetime(2026,11,12,16,tzinfo=CN))
  self.assertEqual([b['time'] for b in groups[0]['bars']],['09:30','15:00'])
  day['data']=['0930 10 100 100000','1000 10 90 90000']
  with patch('core.provider.get',return_value=json.dumps(dict(data={'sz000021':dict(data=[day])}))),self.assertRaisesRegex(ValueError,'累计成交量倒退'):
   Tencent().minutes('sz000021')

 def test_unopened_pool_stocks_get_cached_summaries_without_repeated_fetch_or_computation(self):
  fixture=next(c for c in json.loads(Path('tests/ui/fixtures/turning-final-chart-cases.json').read_text()) if c['code']=='sz000981')
  data=dict(date='2026-11-12',bars=[dict(time='09:30',close=str(fixture['opening_price']),volume=0,complete=True),*fixture['bars']])
  with tempfile.TemporaryDirectory() as td:
   a=App(td,False);a.provider=Mock();a.provider.minutes.return_value=[data]
   for code in ('sz000981','sz000021'):a.store.execute("INSERT INTO pool(code,name,added_day,source,state) VALUES(?,?,'2026-11-12','手动','观察')",(code,code))
   a.store.cache('sz000981','minute','2026-11-12',data)
   a.store.execute("INSERT OR REPLACE INTO minute_requests VALUES(?,?,?)",('sz000021',time.time()-31,'网络异常'))
   service=a.pool.signals;now=datetime(2026,11,12,16,tzinfo=CN)
   def finish():
    end=time.monotonic()+3
    while service.running and time.monotonic()<end:time.sleep(.005)
    self.assertFalse(service.running)
   with patch('core.pool_signals.now_cn',return_value=now),patch('core.minute_cache.now_cn',return_value=now),patch('core.pool_signals.bottom_point',wraps=bottom_point) as compute:
    service.view();finish()
    self.assertEqual(set(service.view()['signals']),{'sz000981','sz000021'})
    calls=compute.call_count
    a.store.cache('sz000981','minute','2026-11-12',dict(data,cached_at='2026-11-12T16:10:00+08:00'))
    service.last_check=0;service.view();finish()
    self.assertEqual(compute.call_count,calls)
   a.provider.minutes.assert_called_once_with('sz000021')
   self.assertFalse(a.store.query('SELECT 1 FROM broker_requests'))
   a.stop.set();a.store.db.close()
