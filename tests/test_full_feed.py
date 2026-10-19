"""Complete simulated market-day ingestion, not an execution-time backtest."""
import json,tempfile,unittest
from datetime import datetime
from core.app import App,ROOT,CN
from core.validated_engine import MINUTES

class FullFeedTest(unittest.TestCase):
 def test_twelve_stocks_full_day_live_ingestion_and_dedup(self):
  total=0
  with tempfile.TemporaryDirectory() as directory:
   app=App(directory,False)
   for path in sorted((ROOT/'fixtures').glob('[s][hz]*-2026-10-16-tencent.json')):
    d=json.loads(path.read_text());expected=json.loads(path.with_name('expected-'+path.name).read_text())['matches'];code=path.name.split('-')[0]
    selected=[b for b in d['bars'] if b['time'] in MINUTES];available=[]
    def poll(clock):
     at=datetime.fromisoformat(d['trading_date']+'T'+clock).replace(tzinfo=CN)
     price=available[-1]['close'] if available else selected[0]['close']
     quote=dict(date=d['trading_date'],timestamp=at.isoformat(),price=price,limit_up=d['limit_up'])
     app.ingest(code,quote,[dict(date=d['trading_date'],bars=available[:],source='simulated-saved-tencent',volume_unit='shares')],at)
    poll('09:30:50')
    for b in selected:
     if b['time']=='13:01':poll('13:00:05');poll('13:00:35')
     available.append(b);poll(b['time']+':05');poll(b['time']+':35')
    rows=app.store.query('SELECT payload,mode FROM events WHERE key LIKE ?',(d['trading_date']+'|'+code[2:]+'|%',))
    actual=[json.loads(r['payload']) for r in rows]
    self.assertEqual(sorted(e['key'] for e in actual),sorted(e['key'] for e in expected),code)
    self.assertTrue(all(r['mode']=='live' for r in rows),code)
    self.assertEqual(len(app.store.query('SELECT key FROM local_delivery WHERE key LIKE ?',(d['trading_date']+'|'+code[2:]+'|%',))),len(expected))
    total+=len(actual)
   app.store.db.close()
  self.assertEqual(total,19)
