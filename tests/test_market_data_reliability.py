"""Data-quality gates and sharing; never exercises a broker or trading action."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import daily_outlook, outlook_scheduler as out, sector_flow as flow
from core.provider import CN
from core.store import Store


class MarketDataReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,16,10,30,tzinfo=CN)
        self.rows=[dict(cate_type='0',category=f'new_{i}',name=f'行业{i}',ts_symbol=f'sz{i:06d}',
                       netamount=str(i*100),inamount=str(10000+i*100),outamount='10000',
                       avg_changeratio='0.01',ts_trade='10.00',ts_changeratio='0') for i in range(40)]
        self.quotes={r['ts_symbol']:dict(price='10.02',previous='10',stamp=self.now-timedelta(seconds=10)) for r in self.rows}

    def parse(self):return flow.parse_sina(self.rows,[],self.quotes,self.now)

    def test_small_cross_provider_tick_drift_preserves_original_sector_values(self):
        result=self.parse()
        self.assertEqual(result['verified_count'],40)
        self.assertEqual(result['excluded_count'],0)
        self.assertEqual(result['sectors'][0]['net_yuan'],3900)
        self.assertEqual(result['sectors'][0]['change_percent'],1)
        self.assertTrue(result['date_inferred'])
        self.assertIsNone(result['quote_time'])

    def test_same_previous_close_is_required_even_if_last_prices_match(self):
        self.quotes['sz000000'].update(price='10.00',previous='9.70')
        result=self.parse()
        self.assertEqual(result['verified_count'],39)
        self.assertNotIn('new_0',{r['code'] for r in result['sectors']})

    def test_excessive_drift_is_not_silently_accepted(self):
        self.quotes['sz000000']['price']='10.10'
        self.assertEqual(self.parse()['verified_count'],39)
        for i in range(9):self.quotes[f'sz{i:06d}']['price']='10.10'
        with self.assertRaisesRegex(ValueError,'31/40.*不足 80%'):self.parse()

    def test_prior_day_future_and_expired_quotes_never_become_verified_sectors(self):
        stamps=[self.now-timedelta(days=1),self.now+timedelta(seconds=6),self.now-timedelta(seconds=181)]
        for i,stamp in enumerate(stamps):self.quotes[f'sz{i:06d}']['stamp']=stamp
        result=self.parse()
        self.assertEqual(result['verified_count'],37)
        self.assertTrue({r['code'] for r in result['sectors']}.isdisjoint({'new_0','new_1','new_2'}))
        self.assertEqual(result['validation_rejections']['日期或时效不符'],3)

    def test_abnormal_quotes_and_amounts_still_fail(self):
        for value in ['NaN','Infinity','0','-1']:
            with self.subTest(value=value):
                self.quotes['sz000000']['price']=value
                self.assertEqual(self.parse()['verified_count'],39)
        self.rows[0]['inamount']='999999'
        with self.assertRaises(ValueError):self.parse()

    def test_lagging_representative_requires_actual_recent_flow_updates_and_day_range(self):
        import copy
        for q in self.quotes.values():q.update(price='10.20',low='9.90',high='10.30')
        prior=copy.deepcopy(self.rows)
        for r in self.rows:
            r['netamount']=str(int(r['netamount'])+10)
            r['inamount']=str(int(r['inamount'])+10)
        with self.assertRaises(ValueError):self.parse()
        result=flow.parse_sina(self.rows,[],self.quotes,self.now,prior=(prior,self.now-timedelta(seconds=30)))
        self.assertEqual(result['verified_count'],40)
        self.assertEqual(result['update_verified_count'],40)
        for stamp in [self.now-timedelta(seconds=181),self.now+timedelta(seconds=1),self.now-timedelta(days=1)]:
            with self.subTest(stamp=stamp),self.assertRaises(ValueError):
                flow.parse_sina(self.rows,[],self.quotes,self.now,prior=(prior,stamp))
        with self.assertRaises(ValueError):
            flow.parse_sina(self.rows,[],self.quotes,self.now,prior=(self.rows,self.now-timedelta(seconds=30)))
        for q in self.quotes.values():q['low']='10.10'
        with self.assertRaises(ValueError):
            flow.parse_sina(self.rows,[],self.quotes,self.now,prior=(prior,self.now-timedelta(seconds=30)))

    def test_sina_requests_bypass_cached_url_and_keep_timeout(self):
        response=Mock();response.read.return_value=b'[]'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.object(flow,'urlopen',return_value=response) as get,patch.object(flow.time,'time',side_effect=[100,101]):
            flow._sina_page(1);flow._sina_page(1)
        first,second=[call.args[0] for call in get.call_args_list]
        self.assertNotEqual(first.full_url,second.full_url)
        self.assertEqual(first.get_header('Cache-control'),'no-cache')
        self.assertEqual(get.call_args.kwargs['timeout'],8)

    def test_stale_and_future_http_responses_are_rejected(self):
        from email.utils import format_datetime
        for seconds in [-181,6]:
            response=Mock();response.read.return_value=b'[]'
            response.headers={'Date':format_datetime(self.now+timedelta(seconds=seconds))}
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            with patch.object(flow,'urlopen',return_value=response),patch.object(flow,'now_cn',return_value=self.now):
                with self.assertRaisesRegex(ValueError,'过期或在未来'):flow._sina_page(1)

    def test_cached_research_is_rechecked_after_clock_moves_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'daily-outlook').mkdir()
            issue=dict(published_at=(self.now-timedelta(seconds=30)).isoformat(),quote_date='2026-11-16',ideas=[])
            (root/'daily-outlook/2026-11-16_102930.json').write_text(json.dumps(issue))
            app=SimpleNamespace(dir=root,store=Mock())
            app.store.getcache.return_value=[]
            with patch.object(daily_outlook,'now_cn',return_value=self.now):
                self.assertIsNotNone(daily_outlook._view(app,'2026-11-16','batch')['issue'])
            with patch.object(daily_outlook,'now_cn',return_value=self.now-timedelta(seconds=60)):
                self.assertIsNone(daily_outlook._view(app,'2026-11-16','batch')['issue'])

    def test_concurrent_research_consumers_share_one_fetch_and_persistent_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'monitor.sqlite3')
            try:
                service=flow.SectorFlow(store,enabled=False)
                data=self.parse();entered=threading.Event();release=threading.Event()
                def fetch(*args):entered.set();release.wait(2);return data
                with patch.object(flow,'fetch',side_effect=fetch) as pull,patch.object(flow,'now_cn',return_value=self.now):
                    with ThreadPoolExecutor(2) as pool:
                        first=pool.submit(service.snapshot,self.now)
                        self.assertTrue(entered.wait(1))
                        second=pool.submit(service.snapshot,self.now)
                        release.set()
                        self.assertEqual(first.result(2)['date'],'2026-11-16')
                        self.assertEqual(second.result(2)['verified_count'],40)
                    self.assertEqual(pull.call_count,1)
                    self.assertEqual(service.view()['snapshot']['source'],'新浪行业资金流')
                    self.assertEqual(store.getcache(flow.CODE,flow.KIND,'2026-11-16')[0]['data']['verified_count'],40)
                with patch.object(flow,'now_cn',return_value=self.now+timedelta(seconds=181)):
                    self.assertIsNone(service.view()['snapshot'])
                with patch.object(flow,'now_cn',return_value=self.now-timedelta(minutes=1)):
                    self.assertIsNone(service.view()['snapshot'])
            finally:store.db.close()

    def test_scheduler_reports_specific_stage_failure_and_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            worker=out.OutlookScheduler(SimpleNamespace(dir=Path(folder),store=None))
            def fail(*args):return out._stage('行业资金',Mock(side_effect=ValueError('代表股通过 20/48，不足 80%')))
            worker.tick(lambda:self.now,fail)
            self.assertEqual(worker.status['stage'],'行业资金')
            self.assertIn('20/48',worker.status['last_error'])
            self.assertEqual(worker.status['next_retry'],(self.now+timedelta(seconds=60)).isoformat())
            worker.tick(lambda:self.now,lambda *a:dict(quote_date='2026-11-16',ideas=[]))
            self.assertEqual(worker.status['last_error'],'')
            self.assertEqual(worker.status['last_success'],self.now.isoformat())
            self.assertIsNone(worker.status['next_retry'])

    def test_crossing_half_hour_does_not_discard_valid_report(self):
        with tempfile.TemporaryDirectory() as folder:
            worker=out.OutlookScheduler(SimpleNamespace(dir=Path(folder),store=None))
            clock=Mock(side_effect=[self.now-timedelta(seconds=30),self.now+timedelta(seconds=30)])
            worker.tick(clock,lambda *a:dict(quote_date='2026-11-16',ideas=[]))
            files=list(Path(folder).rglob('*.json'))
            self.assertEqual(len(files),1)
            self.assertEqual(json.loads(files[0].read_text())['native_slot'],'2026-11-16 10:00')
            self.assertEqual(worker.done,'2026-11-16 10:00')

    def test_old_report_has_current_independent_funding_and_historical_label(self):
        sector=self.parse()
        report=dict(issue=dict(quote_date='2026-11-13'),quotes=[],day='2026-11-16')
        service=Mock();service.view.return_value=dict(snapshot=sector,running=False,error='')
        app=SimpleNamespace(sector_flow=service,concept_flow=service)
        with patch.object(daily_outlook,'_view',return_value=report),patch.object(daily_outlook,'now_cn',return_value=self.now):
            result=daily_outlook.view(app,None,None)
        self.assertEqual(result['reference_status'],'historical')
        self.assertEqual(result['live_data']['industry']['snapshot']['date'],'2026-11-16')
        self.assertEqual(result['quotes'],[])
        self.assertNotIn('live_data',report) # No mutation of the cached research report.
        sector['date']='2026-11-13'
        with patch.object(daily_outlook,'_view',return_value=report),patch.object(daily_outlook,'now_cn',return_value=self.now):
            self.assertIsNone(daily_outlook.view(app,None,None)['live_data']['industry']['snapshot'])


if __name__=='__main__':unittest.main()
