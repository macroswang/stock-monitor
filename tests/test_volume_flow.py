import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from core.store import Store
from core.volume_flow import assignment,timeline,aggregate,classify_minute,TencentTicks,VolumeFlow

CODE='sh603938';DAY='2026-10-23'
ROWS=['0/09:25:01/10/0/10/10000/B','1/09:30:01/10/0/3/3000/B','2/09:30:58/10/0/2/2000/S','3/09:31:01/10/0/1/1000/M','4/14:57:00/10/0/5/5000/B']

def packet(rows):return dict(range=rows[0].split('/')[1]+'~'+rows[-1].split('/')[1],data='|'.join(rows))
def raw(pages=None):
    pages=pages or [packet(ROWS)]
    return dict(version=1,code=CODE,day=DAY,pages=pages,fetched_at='2026-10-23T16:00:00+08:00',**aggregate(pages))

class PacketTests(unittest.TestCase):
    def test_dated_json_parser_rejects_code_mismatch_and_code_execution(self):
        self.assertEqual(timeline(f'v_detail_time_{CODE}=[20261023,"09:30:01~15:00:00"];',CODE)[0],DAY)
        for text in ['v_other=[0,"a"];',f'v_detail_data_{CODE}=__import__("os").system("false");']:
            with self.assertRaises(ValueError):assignment(text,'v_detail_data_'+CODE)

    def test_end_minute_alignment_units_and_auction_exclusion(self):
        d=aggregate([packet(ROWS)])
        self.assertEqual(d['volume_multiplier'],100)
        self.assertEqual(d['buckets']['09:31'],dict(buy=300,sell=200,neutral=0,unknown=0,total=500))
        self.assertEqual(d['buckets']['09:32']['neutral'],100)
        self.assertNotIn('09:26',d['buckets']);self.assertNotIn('14:58',d['buckets'])
        shares=['0/09:30:01/10/0/300/3000/B']
        self.assertEqual(aggregate([packet(shares)])['volume_multiplier'],1)

    def test_invalid_units_duplicate_missing_id_and_unknown_direction(self):
        for rows in [ROWS[:4]+[ROWS[3]],ROWS[:2]+ROWS[3:],['0/09:30:01/10/0/3/0/B']]:
            with self.assertRaises(ValueError):aggregate([packet(rows)])
        d=aggregate([packet(['0/09:30:01/10/0/3/3000/X'])]);self.assertEqual(d['buckets']['09:31']['unknown'],300)

    def test_fetch_checks_manifest_date_and_reuses_fixed_pages(self):
        pages=[packet(ROWS[:2]),packet(ROWS[2:])];calls=[]
        def read(url):
            calls.append(url)
            if 'action=timeline' in url:return 'v_detail_time_'+CODE+'='+json.dumps([20261023,'|'.join(p['range'] for p in pages)])+';'
            i=int(url.rsplit('p=',1)[1]);return 'v_detail_data_'+CODE+'='+json.dumps([i,pages[i]['data']])+';'
        f=TencentTicks(read);first=f.fetch(CODE,DAY);calls.clear();f.fetch(CODE,DAY,first)
        self.assertEqual(sum('action=data' in c for c in calls),1)
        with self.assertRaisesRegex(ValueError,'历史日'):f.fetch(CODE,'2026-10-22')
        def swapped(url):
            if 'action=timeline' in url:return read(url)
            return 'v_detail_data_'+CODE+'='+json.dumps([99,pages[0]['data']])+';'
        with self.assertRaises(ValueError):TencentTicks(swapped).fetch(CODE,DAY)

    def test_after_hours_sparse_tail_does_not_reject_valid_continuous_packets(self):
        rows=ROWS[:3]+['3/14:56:57/10/0/1/1000/B','4/15:15:15/0/0/0/0/M']
        calls=[]
        def read(url):
            calls.append(url)
            if 'action=timeline' in url:return 'v_detail_time_'+CODE+'='+json.dumps([20261023,'09:25:01~15:18:45|15:19:15~15:22:00'])+';'
            i=int(url.rsplit('p=',1)[1])
            if i==1:raise AssertionError('after-hours-only page must not be fetched')
            return 'v_detail_data_'+CODE+'='+json.dumps([i,'|'.join(rows)])+';'
        result=TencentTicks(read).fetch(CODE,DAY)
        self.assertEqual(result['buckets']['09:31']['buy'],300)
        self.assertEqual(result['buckets']['09:31']['sell'],200)
        self.assertEqual(result['buckets']['14:57']['buy'],100)
        self.assertEqual(result['last_tick'],'14:56:57');self.assertEqual(result['pages'][1]['data'],'')
        # In-session gaps remain fatal, rather than being silently ignored.
        with self.assertRaisesRegex(ValueError,'编号重复或缺失'):
            aggregate([packet([ROWS[0],ROWS[2]])])

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'monitor.sqlite3')
        self.store.cache(CODE,'minute',DAY,dict(source='tencent',bars=[dict(time='09:31',volume=500,complete=True),dict(time='09:32',volume=100,complete=True),dict(time='09:33',volume=50,complete=False),dict(time='15:00',volume=500,complete=True)]))
        self.flow=VolumeFlow(self.store,enabled=False)
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def test_exact_packets_preserve_original_minute_cache(self):
        original=self.store.getcache(CODE,'minute',DAY);self.store.cache(CODE,'volume_flow',DAY,raw())
        d=self.flow.request(CODE,DAY);self.assertEqual(d['verified_minutes'],2)
        for m in d['minutes']:self.assertEqual(m['total'],sum(m[k] for k in ('buy','sell','neutral','unknown')))
        self.assertEqual(d['minutes'][0]['buy'],300);self.assertEqual(d['minutes'][1]['neutral'],100)
        self.assertEqual(d['minutes'][-1]['unknown'],500);self.assertEqual(self.store.getcache(CODE,'minute',DAY),original)
        bad=raw();bad['aggregation_version']=2;bad['buckets']['09:31']['total']=600;self.store.cache(CODE,'volume_flow',DAY,bad)
        self.assertEqual(self.flow.request(CODE,DAY)['minutes'][0]['unknown'],500)
    def test_no_cross_day_cross_code_or_provider_mix(self):
        bad=raw();bad['day']='2026-10-22';self.store.cache(CODE,'volume_flow',DAY,bad)
        self.assertEqual(self.flow.request(CODE,DAY)['verified_minutes'],0)
        self.assertEqual(self.flow.request(CODE,'2026-10-22')['minutes'],[])
        self.store.cache(CODE,'minute',DAY,dict(source='sina',bars=[]));self.assertIn('按原总量',self.flow.request(CODE,DAY)['message'])
    def test_async_fetch_is_nonblocking_deduplicated_and_preserves_good_cache_on_failure(self):
        release=threading.Event();started=threading.Event();calls=[]
        class Fetcher:
            def fetch(_self,*args):calls.append(args);started.set();release.wait(2);return raw()
        f=VolumeFlow(self.store,fetcher=Fetcher());start=time.perf_counter();self.assertEqual(f.request(CODE,DAY)['status'],'loading')
        self.assertLess(time.perf_counter()-start,.1);f.request(CODE,DAY);self.assertTrue(started.wait(.5));self.assertEqual(len(calls),1)
        release.set()
        deadline=time.monotonic()+2
        while f.inflight and time.monotonic()<deadline:time.sleep(.005)
        self.assertEqual(f.request(CODE,DAY)['verified_minutes'],2)
        class Failure:
            def fetch(_self,*args):raise TimeoutError()
        f.fetcher=Failure();before=self.store.getcache(CODE,'volume_flow',DAY);f._fetch((CODE,DAY),raw())
        self.assertEqual(self.store.getcache(CODE,'volume_flow',DAY),before);self.assertIn('保留已核验',f.request(CODE,DAY)['message'])

class ReconciliationTests(unittest.TestCase):
    def test_morning_endpoint_and_afternoon_open_belong_to_correct_minutes(self):
        rows=['0/11:29:57/2.26/0/67/15142/B','1/11:30:00/2.25/0/1144/257411/S','2/13:00:00/2.25/0/4065/915565/S']
        d=aggregate([packet(rows)])['buckets']
        self.assertEqual(d['11:30']['total'],121100);self.assertEqual(d['11:30']['sell'],114400)
        self.assertEqual(d['13:01']['sell'],406500);self.assertNotIn('11:31',d)

    def test_one_hand_small_error_is_explicitly_approximate_and_raw_counts_preserved(self):
        b=dict(time='10:36',volume=6212500,complete=True);p=dict(buy=6134600,sell=78000,neutral=0,unknown=0,total=6212600)
        d=classify_minute(b,p);self.assertTrue(d['verified']);self.assertTrue(d['approximate']);self.assertEqual(d['difference'],100)
        self.assertEqual(d['buy'],6134600);self.assertEqual(d['total'],6212500);self.assertEqual(d['source_total'],6212600)
        d=classify_minute(dict(time='13:01',volume=4920200,complete=True),dict(buy=4000000,sell=920100,neutral=0,unknown=0,total=4920100))
        self.assertTrue(d['approximate']);self.assertEqual(d['difference'],-100)

    def test_big_relative_error_missing_and_unfinished_are_total_only(self):
        p=dict(buy=300,sell=200,neutral=0,unknown=0,total=500)
        for b in [dict(time='09:31',volume=1000,complete=True),dict(time='09:31',volume=500,complete=False),dict(time='09:31',volume=400,complete=True)]:
            d=classify_minute(b,p);self.assertFalse(d['verified']);self.assertEqual(d['unknown'],b['volume'])
        self.assertFalse(classify_minute(dict(time='09:31',volume=500,complete=True),None)['verified'])

class CacheAndFreshnessTests(unittest.TestCase):
    setUp=FlowTests.setUp
    tearDown=FlowTests.tearDown
    def test_existing_raw_cache_is_reaggregated_locally_at_morning_boundary(self):
        from unittest.mock import patch
        stored=raw([packet(['0/11:29:57/10/0/3/3000/B','1/11:30:00/10/0/2/2000/S'])]);stored['buckets']['11:30']['sell']=0;stored['buckets']['11:30']['total']=300
        self.store.cache(CODE,'minute',DAY,dict(source='tencent',bars=[dict(time='11:30',volume=500,complete=True)]));self.store.cache(CODE,'volume_flow',DAY,stored)
        result=self.flow.request(CODE,DAY)
        self.assertEqual(result['minutes'][0]['sell'],200);self.assertTrue(result['minutes'][0]['verified'])
        self.assertEqual(self.store.getcache(CODE,'volume_flow',DAY)[0]['data']['aggregation_version'],2)

    def test_today_stale_packets_keep_settled_minutes_but_not_new_or_uncovered_minutes(self):
        from datetime import datetime
        from unittest.mock import patch
        stored=raw();stored['aggregation_version']=2;stored['last_tick']='09:59:57';stored['fetched_at']='2026-10-23T09:59:58+08:00';self.store.cache(CODE,'volume_flow',DAY,stored)
        with patch('core.volume_flow.now_cn',return_value=datetime.fromisoformat('2026-10-23T10:00:00+08:00')):
            current=self.flow.request(CODE,DAY);self.assertFalse(current['total_only']);self.assertTrue(current['minutes'][0]['verified'])
        with patch('core.volume_flow.now_cn',return_value=datetime.fromisoformat('2026-10-23T10:03:00+08:00')):
            stale=self.flow.request(CODE,DAY);self.assertFalse(stale['total_only']);self.assertEqual(stale['verified_minutes'],2);self.assertFalse(stale['minutes'][2]['verified']);self.assertIn('新分钟补查',stale['message'])
