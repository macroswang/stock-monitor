import unittest
from datetime import datetime
from unittest.mock import patch
from core.eastmoney_flow import EastmoneyTicks
from core.volume_flow import VolumeFlow
from tests import test_volume_flow as fixtures
CODE,DAY,raw=fixtures.CODE,fixtures.DAY,fixtures.raw

class SecondaryTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    tearDown=fixtures.FlowTests.tearDown

    def source(self,quote_day=DAY):
        calls=[]
        def read(url):
            calls.append(url)
            if '/stock/get?' in url:
                return {'data':{'f57':CODE[2:],'f86':int(datetime.fromisoformat(quote_day+'T16:00:00+08:00').timestamp())}}
            return {'data':{'code':CODE[2:],'market':1,'details':['09:30:01,10,3,0,2','09:30:58,10,2,0,1','09:31:01,11,1,0,2']}}
        return EastmoneyTicks(read),calls

    def test_supplement_uses_explicit_provider_date_and_exact_minute_price_and_volume(self):
        fetcher,calls=self.source()
        ref={'bars':[{'time':'09:31','volume':500,'close':'10.00','complete':True},{'time':'09:32','volume':100,'close':'10','complete':True}]}
        result=fetcher.fetch(CODE,DAY,ref)
        self.assertEqual(len(calls),3);self.assertTrue(result['date_verified']);self.assertEqual(result['buckets']['09:31']['buy'],300)
        self.assertNotIn('09:32',result['buckets']) # Same volume, wrong closing price.
        fetcher,calls=self.source('2026-10-22')
        with self.assertRaisesRegex(ValueError,'交易日'):fetcher.fetch(CODE,DAY,ref)
        self.assertEqual(len(calls),1) # Wrong day: never fetch/label today's packets as history.

    def test_primary_failure_uses_verified_secondary_minute_without_combining_sources(self):
        fetcher,_=self.source()
        class Failure:
            def fetch(self,*args):raise TimeoutError('primary')
        self.store.cache(CODE,'minute',DAY,{'source':'tencent','bars':[{'time':'09:31','close':'10','volume':500,'complete':True}]})
        f=VolumeFlow(self.store,enabled=False,fetcher=Failure(),secondary=fetcher);f._fetch((CODE,DAY),None)
        result=f.request(CODE,DAY)
        self.assertEqual(result['secondary_minutes'],1);self.assertEqual(result['minutes'][0]['source'],'eastmoney_tick');self.assertEqual(result['minutes'][0]['sell'],200)
        # Changing reference prices invalidates old alternate data on read too.
        self.store.cache(CODE,'minute',DAY,{'source':'tencent','bars':[{'time':'09:31','close':'10.01','volume':500,'complete':True}]})
        self.assertFalse(f.request(CODE,DAY)['minutes'][0]['verified'])

    def test_secondary_failure_does_not_erase_good_primary_and_has_own_backoff(self):
        class Primary:
            def fetch(self,*args):return raw()
        class Failure:
            calls=0
            def fetch(self,*args):self.calls+=1;raise TimeoutError('secondary')
        secondary=Failure();f=VolumeFlow(self.store,enabled=False,fetcher=Primary(),secondary=secondary)
        # Force one nonzero continuous-minute hole.
        row=self.store.getcache(CODE,'minute',DAY)[0]['data'];row['bars'].append({'time':'10:01','close':'10','volume':500,'complete':True});self.store.cache(CODE,'minute',DAY,row)
        f._fetch((CODE,DAY),None);f._fetch((CODE,DAY),None)
        self.assertEqual(secondary.calls,1);self.assertEqual(f.request(CODE,DAY)['verified_minutes'],2)
        self.assertTrue(f.secondary_errors)

    def test_live_secondary_is_rejected_when_stale(self):
        fetcher,_=self.source()
        ref={'bars':[{'time':'09:31','volume':500,'close':'10','complete':True}]}
        data=fetcher.fetch(CODE,DAY,ref);data['buckets']['10:00']=data['buckets'].pop('09:31');ref['bars'][0]['time']='10:00';data.update(fetched_at=DAY+'T10:00:00+08:00',last_tick='09:59:57')
        self.store.cache(CODE,'minute',DAY,dict(source='tencent',**ref));self.store.cache(CODE,'volume_flow_em',DAY,data)
        with patch('core.volume_flow.now_cn',return_value=datetime.fromisoformat(DAY+'T10:03:00+08:00')):
            result=self.flow.request(CODE,DAY);self.assertTrue(result['total_only']);self.assertEqual(result['verified_minutes'],0)
        with patch('core.volume_flow.now_cn',return_value=datetime.fromisoformat(DAY+'T10:00:01+08:00')):
            self.assertEqual(self.flow.request(CODE,DAY)['secondary_minutes'],1)

    def test_approximate_primary_also_requests_exact_secondary_before_accepting_approximation(self):
        class Primary:
            def fetch(self,*args):
                result=raw();result.update(aggregation_version=2,buckets={'09:31':dict(buy=9900,sell=0,neutral=0,unknown=0,total=9900)});return result
        calls=[]
        def read(url):
            calls.append(url)
            if '/stock/get?' in url:return {'data':{'f57':CODE[2:],'f86':int(datetime.fromisoformat(DAY+'T16:00:00+08:00').timestamp())}}
            return {'data':{'code':CODE[2:],'market':1,'details':['09:30:01,10,60,0,2','09:30:58,10,40,0,1']}}
        ref={'source':'tencent','bars':[dict(time='09:31',volume=10000,close='10',complete=True)]};self.store.cache(CODE,'minute',DAY,ref)
        f=VolumeFlow(self.store,enabled=False,fetcher=Primary(),secondary=EastmoneyTicks(read));f._fetch((CODE,DAY),None)
        result=f.request(CODE,DAY);self.assertEqual(len(calls),3);self.assertEqual(result['secondary_minutes'],1);self.assertFalse(result['minutes'][0]['approximate']);self.assertEqual(result['minutes'][0]['buy'],6000)

    def test_existing_historical_approximate_cache_still_starts_alternate_lookup(self):
        import time
        class Primary:
            calls=0
            def fetch(self,*args):self.calls+=1;raise AssertionError('Historical cache must not refetch primary')
        class Alternate:
            calls=0
            def fetch(self,*args):
                self.calls+=1
                return dict(version=1,source='eastmoney_tick',code=CODE,day=DAY,date_verified=True,fetched_at=DAY+'T16:00:00+08:00',last_tick='14:56:57',buckets={'09:31':dict(buy=6000,sell=4000,neutral=0,unknown=0,total=10000,last_price='10')})
        stored=raw();stored.update(aggregation_version=2,buckets={'09:31':dict(buy=9900,sell=0,neutral=0,unknown=0,total=9900)})
        self.store.cache(CODE,'volume_flow',DAY,stored);self.store.cache(CODE,'minute',DAY,dict(source='tencent',bars=[dict(time='09:31',volume=10000,close='10',complete=True)]))
        primary=Primary();other=Alternate();f=VolumeFlow(self.store,fetcher=primary,secondary=other);f.request(CODE,DAY)
        deadline=time.monotonic()+2
        while f.inflight and time.monotonic()<deadline:time.sleep(.005)
        self.assertEqual(primary.calls,0);self.assertEqual(other.calls,1);self.assertEqual(f.request(CODE,DAY)['secondary_minutes'],1)
        self.assertEqual(other.calls,1)
