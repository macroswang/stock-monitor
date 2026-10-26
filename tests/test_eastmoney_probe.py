import unittest
from datetime import datetime
from scripts.verify_eastmoney_flow import parse_details,compare,summarize

class EastmoneyProbeTests(unittest.TestCase):
    def test_types_units_and_preauction_do_not_inflate_continuous_volume(self):
        payload=dict(data=dict(code='603938',market=1,details=['09:15:01,10,100,0,4','09:30:01,10,3,1,2','09:30:58,10,2,1,1','09:31:01,10,1,1,4']))
        d=parse_details(payload,'sh603938');self.assertEqual(d['buckets']['09:31']['total'],500);self.assertEqual(d['buckets']['09:31']['buy'],300)
        self.assertEqual(d['buckets']['09:31']['sell'],200);self.assertNotIn('09:16',d['buckets'])
        with self.assertRaises(ValueError):parse_details(payload,'sz000981')
    def test_newest_minutes_are_excluded_from_missing_volume_judgment(self):
        d=parse_details(dict(data=dict(code='603938',market=1,details=['09:30:01,10,3,1,2'])),'sh603938')
        minute=dict(date='2026-10-26',bars=[dict(time='09:31',volume=300,close='10',complete=True)])
        self.assertEqual(compare(d,minute,datetime.fromisoformat('2026-10-26T09:32:00+08:00')),[])
        self.assertTrue(compare(d,minute,datetime.fromisoformat('2026-10-26T09:33:00+08:00'))[0]['volume_match'])
    def valid_records(self):
        cs=[dict(time=f'09:{31+i}',received=100,volume_match=True,price_match=True,directions=dict(buy=60,sell=40,neutral=0,unknown=0)) for i in range(5)]
        return [dict(code='sh603938',source_status='ok',status='ok',date_anchor=True,lag_seconds=5,unknown_fraction=0,reference_date='2026-10-26',comparisons=[dict(c,directions=dict(c['directions'])) for c in cs]) for _ in range(10)]
    def test_weekend_or_undated_or_stale_samples_never_pass_live(self):
        records=self.valid_records();self.assertEqual(summarize(records,False)['result'],'NOT_VERIFIED_LIVE')
        for r in records:r['date_anchor']=False
        self.assertFalse(summarize(records,True)['stocks']['sh603938']['passed'])
        for r in records:r['date_anchor']=True;r['lag_seconds']=100
        self.assertFalse(summarize(records,True)['stocks']['sh603938']['passed'])
    def test_sufficient_fresh_consistent_data_is_only_a_bounded_candidate(self):
        self.assertEqual(summarize(self.valid_records(),True)['result'],'PASS_MINUTE_DISPLAY_CANDIDATE')
        self.assertFalse(summarize(self.valid_records()[:1],True)['stocks']['sh603938']['passed'])
    def test_changed_historical_direction_flags_and_missing_volume_fail(self):
        import copy
        records=copy.deepcopy(self.valid_records());records[-1]['comparisons'][0]['directions']['buy']=70
        self.assertGreater(summarize(records,True)['stocks']['sh603938']['settled_minute_revisions'],0)
        self.assertFalse(summarize(records,True)['stocks']['sh603938']['passed'])
        records=self.valid_records()
        for r in records:r['comparisons'][0]['volume_match']=False
        self.assertFalse(summarize(records,True)['stocks']['sh603938']['passed'])
