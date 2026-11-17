import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from core.app import App
from core.history import _view, analyze
from core.provider import CN
from core.read_cache import ReadCache
from core.sector_events import build_observations
from core.sector_observations import (COMPRESSED, LEGACY, ObservationAccumulator,
    SectorObservationCache, decode_snapshot, encode_snapshot)


class HistoryReadCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App(self.tmp.name,False)
        self.args=dict(code='sh603002',start='2026-10-16',end='2026-10-16')

    def tearDown(self):
        if hasattr(self.app,'paper'):self.app.paper.db.close()
        self.app.store.db.close();self.tmp.cleanup()

    def read(self):return self.app.call('history',self.args)

    def assert_reference(self,result):
        self.assertEqual(result,dict(_view(self.app,**self.args),source=self.app.source_info(self.args['code'])))

    def test_unchanged_reads_do_not_replay_minutes(self):
        with patch('core.history.analyze',wraps=analyze) as check:
            first=self.read();second=self.read()
            self.assertEqual(check.call_count,1)
        self.assertEqual(first,second);self.assert_reference(second)

    def test_raw_minute_update_delete_and_restore_invalidate(self):
        first=self.read();code=self.args['code'];day=self.args['start']
        payload=self.app.store.query('SELECT payload FROM cache WHERE code=? AND kind=? AND day=?',(code,'minute',day))[0]['payload']
        bad=json.loads(payload);bad['rule_compatible']=False
        self.app.store.execute('UPDATE cache SET payload=? WHERE code=? AND kind=? AND day=?',(json.dumps(bad),code,'minute',day))
        changed=self.read();self.assertNotEqual(first['days'],changed['days']);self.assert_reference(changed)
        self.app.store.execute('DELETE FROM cache WHERE code=? AND kind=? AND day=?',(code,'minute',day))
        deleted=self.read();self.assertEqual(deleted['days'][0]['status'],'missing_minutes');self.assert_reference(deleted)
        self.app.store.execute('INSERT INTO cache VALUES(?,?,?,?)',(code,'minute',day,payload))
        self.assertEqual(first,self.read())

    def test_daily_live_and_history_backfill_invalidate_chart_and_history(self):
        code=self.args['code'];self.read();before=self.app.call('chart',dict(code=code,kind='daily'))
        data=dict(date='2026-10-17',open='9',close='10',high='11',low='8',volume='100',source='tencent',cached_at='2026-10-17T10:00:00+08:00')
        self.app.store.cache(code,'daily_live',data['date'],data)
        self.assertNotEqual(before,self.app.call('chart',dict(code=code,kind='daily')))
        self.args['end']='2026-10-17';self.assert_reference(self.read())
        self.app.store.cache(code,'daily',data['date'],dict(data,close='10.5',cached_at='2026-10-17T15:20:00+08:00'))
        result=self.read();self.assertEqual(float(result['daily'][-1]['close']),10.5);self.assert_reference(result)

    def test_instrument_and_provider_changes_are_not_hidden_by_cache(self):
        self.read();code=self.args['code']
        self.app.store.execute('UPDATE instruments SET name=? WHERE code=?',('新名称',code))
        self.app.store.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('provider','"sina"'))
        result=self.read();self.assertEqual(result['source']['selected'],'sina');self.assert_reference(result)

    def test_scopes_and_cache_budget(self):
        first=self.read();other=self.app.call('history',dict(self.args,code='sh603938'))
        self.assertEqual(first['code'],'sh603002');self.assertEqual(other['code'],'sh603938')
        cache=ReadCache(entries=3,byte_limit=100)
        for i in range(20):cache.get(i,lambda:{'data':'x'*20})
        self.assertLessEqual(len(cache.values),3);self.assertLessEqual(cache.bytes,100)

    def test_light_paper_revision_is_read_only_and_does_not_create_account(self):
        self.assertIsNone(self.app.call('paper_account_state',{}))
        paper=self.app.paper_service()
        account=paper.call('paper_create',dict(cash='10000',name='测试账户'))
        before=paper.db.total_changes
        self.assertEqual(self.app.call('paper_account_state',dict(account=account['id'])),dict(id=account['id'],revision=0))
        self.assertEqual(before,paper.db.total_changes)


class SectorIncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App(self.tmp.name,False)
        self.store=self.app.store;self.code='eastmoney-industry';self.day='2026-10-30'
        self.now=datetime(2026,10,30,10,10,tzinfo=CN)

    def tearDown(self):self.store.db.close();self.tmp.cleanup()

    def snapshot(self,offset,change=.5,net=200):
        stamp=self.now+timedelta(minutes=offset)
        return dict(date=self.day,source='东方财富行业板块资金流',quote_time=stamp.isoformat(),
            observations=[dict(code='BK1',name='板块',source_time=stamp.isoformat(),change_percent=change,net_yuan=net)])

    def save(self,snapshot,kind=LEGACY):
        payload=encode_snapshot(snapshot) if kind==COMPRESSED else json.dumps(snapshot)
        self.store.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',(self.code,kind,snapshot['quote_time'],payload))

    def reference(self,cache,rows,now=None):
        actual=cache.read(self.day,now or self.now);actual.pop('series_revision')
        self.assertEqual(actual,build_observations(rows,now or self.now,self.day))
        return actual

    def test_append_warm_read_out_of_order_update_and_delete_match_reference(self):
        rows=[self.snapshot(-6,0,100),self.snapshot(-1)]
        for row in rows:self.save(row)
        cache=SectorObservationCache(self.store,self.code)
        self.reference(cache,rows);loaded=cache.loaded_snapshots
        self.reference(cache,rows);self.assertEqual(cache.loaded_snapshots,loaded)
        rows.append(self.snapshot(0,.8,250));self.save(rows[-1],COMPRESSED)
        self.reference(cache,rows);self.assertEqual(cache.loaded_snapshots,loaded+1)
        early=self.snapshot(-8,-.1,90);rows.insert(0,early);self.save(early)
        self.reference(cache,rows)
        rows[0]['observations'][0]['net_yuan']=80;self.save(rows[0])
        self.reference(cache,rows)
        self.store.execute('DELETE FROM cache WHERE code=? AND kind=? AND day=?',(self.code,LEGACY,rows[0]['quote_time']))
        self.reference(cache,rows[1:])

    def test_future_cutoff_expiry_clock_rollback_lunch_and_next_day(self):
        rows=[self.snapshot(-8,0,100),self.snapshot(-6,.1,110),self.snapshot(-2,.4,150),self.snapshot(0,.7,200),self.snapshot(2,1.2,300)]
        for row in rows:self.save(row)
        cache=SectorObservationCache(self.store,self.code)
        for now in (self.now,self.now+timedelta(minutes=2),self.now-timedelta(minutes=3),self.now.replace(hour=12),self.now+timedelta(days=1)):
            self.reference(cache,rows,now)

    def test_duplicate_first_name_wrong_source_and_invalid_rows_match(self):
        first=self.snapshot(-6,0,100);late=self.snapshot(-1)
        bad=copy.deepcopy(late);bad['observations'][0]['change_percent']=float('nan')
        conflict=copy.deepcopy(late);conflict['observations'][0].update(name='后名',net_yuan=999)
        rows=[bad,first,late,conflict,dict(late,source='错误来源')]
        accumulator=ObservationAccumulator(self.day)
        for row in rows:accumulator.add(row)
        self.assertEqual(accumulator.report(self.now),build_observations(rows,self.now,self.day))

    def test_cached_events_recheck_future_seconds_and_exact_expiry(self):
        future=self.snapshot(0);stamp=self.now+timedelta(seconds=4)
        future['observations'][0]['source_time']=stamp.isoformat()
        rows=[self.snapshot(-6,0,100),future]
        accumulator=ObservationAccumulator(self.day)
        for row in rows:accumulator.add(row)
        for now in (self.now,stamp,stamp+timedelta(seconds=180),stamp+timedelta(seconds=180,microseconds=1),self.now):
            self.assertEqual(accumulator.report(now),build_observations(rows,now,self.day))

    def test_mixed_timezone_order_and_future_first_names_match_reference(self):
        first=self.snapshot(2);first['observations'][0]['name']='未来名称'
        second=self.snapshot(-1);utc=copy.deepcopy(second)
        utc['observations'][0].update(source_time='2026-10-30T02:09:30+00:00',name='UTC名称')
        rows=[first,self.snapshot(-6,0,100),second,utc]
        accumulator=ObservationAccumulator(self.day)
        for row in rows:accumulator.add(row)
        for now in (self.now,self.now+timedelta(minutes=3),self.now-timedelta(minutes=2)):
            self.assertEqual(accumulator.report(now),build_observations(rows,now,self.day))

    def test_streaming_large_history_keeps_identical_events_and_points(self):
        rows=[];start=self.now.replace(hour=9,minute=30)
        for second in range(0,2400,5):
            stamp=start+timedelta(seconds=second)
            row=dict(date=self.day,source='东方财富行业板块资金流',quote_time=stamp.isoformat(),observations=[dict(code='BK1',name='板块',source_time=stamp.isoformat(),change_percent=second/1000,net_yuan=second*100)])
            rows.append(row);self.save(row,COMPRESSED if second%2 else LEGACY)
        self.reference(SectorObservationCache(self.store,self.code),rows)

    def test_idle_release_reloads_from_unchanged_persistent_records(self):
        rows=[self.snapshot(-6,0,100),self.snapshot(-1)]
        for row in rows:self.save(row)
        cache=SectorObservationCache(self.store,self.code)
        with patch('core.sector_observations.monotonic',return_value=100):self.reference(cache,rows)
        with patch('core.sector_observations.monotonic',return_value=401):cache.expire_if_idle()
        self.assertIsNone(cache.accumulator)
        self.assertEqual(len(self.store.getcache(self.code,LEGACY)),2)
        with patch('core.sector_observations.monotonic',return_value=402):self.reference(cache,rows)

    def test_lossless_compression_and_conditional_series_keep_expiry_gate(self):
        rows=[self.snapshot(-6,0,100),self.snapshot(-1)]
        for row in rows:self.save(row,COMPRESSED)
        self.assertEqual(decode_snapshot(encode_snapshot(rows[0]),COMPRESSED),rows[0])
        flow=self.app.sector_flow
        with patch.object(flow,'view',return_value={'snapshot':rows[-1]}),patch('core.sector_flow.now_cn',return_value=self.now):
            first=flow.intraday();second=flow.intraday(first['series_revision'])
        self.assertEqual(len(first['events']),1);self.assertTrue(second['series_unchanged']);self.assertNotIn('series',second)
        with patch.object(flow,'view',return_value={'snapshot':rows[-1]}),patch('core.sector_flow.now_cn',return_value=self.now+timedelta(minutes=4)):
            expired=flow.intraday(first['series_revision'])
        self.assertEqual(expired['events'],[])

    def test_new_snapshot_storage_preserves_all_legacy_records(self):
        old=self.snapshot(-6,0,100);new=self.snapshot(-1);self.save(old)
        payload=self.store.query('SELECT payload FROM cache WHERE code=? AND kind=?',(self.code,LEGACY))[0]['payload']
        with patch('core.sector_flow.fetch',return_value=new):self.app.sector_flow.refresh(force=True)
        saved=self.store.query('SELECT payload FROM cache WHERE code=? AND kind=?',(self.code,COMPRESSED))
        self.assertEqual(decode_snapshot(saved[0]['payload'],COMPRESSED),new)
        self.assertEqual(self.store.query('SELECT payload FROM cache WHERE code=? AND kind=?',(self.code,LEGACY))[0]['payload'],payload)


if __name__=='__main__':unittest.main()
