import json
import math
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.option_pcr import CODE, KIND, NOT_PUBLISHED, OptionPCR, add_bands, eligible_sessions, parse_day
from core.provider import CN
from core.store import Store


def raw(day='2026-10-28'):
    return {'result':[dict(SECURITY_CODE='510050',SECURITY_ABBR='上证50ETF华夏',TRADE_DATE=day,
                           CALL_VOLUME='499,320',PUT_VOLUME='343,583',TOTAL_VOLUME='842,903',CP_RATE='68.81')]}


class OptionPCRTests(unittest.TestCase):
    def test_official_counts_are_checked_and_ratio_is_not_rounded_percent(self):
        result=parse_day(raw(),'2026-10-28','2026-10-28T17:00:00+08:00')
        self.assertEqual(result['call_volume'],499320)
        self.assertEqual(result['put_volume'],343583)
        self.assertAlmostEqual(result['pcr'],343583/499320)
        self.assertEqual(result['official_percent'],68.81)

    def test_reject_wrong_date_duplicate_missing_inconsistent_and_invalid_values(self):
        cases=[]
        cases.append(raw('2026-10-27'))
        d=raw();d['result'].append(dict(d['result'][0]));cases.append(d)
        cases.append({'result':[]})
        for field,value in [('TOTAL_VOLUME','1'),('CALL_VOLUME','0'),('PUT_VOLUME','NaN'),('CP_RATE','50.00')]:
            d=raw();d['result'][0][field]=value;cases.append(d)
        for d in cases:
            with self.subTest(d=d),self.assertRaises(ValueError):parse_day(d,'2026-10-28','2026-10-28T17:00:00+08:00')

    def test_empty_result_is_pending_but_nonempty_missing_product_is_an_error(self):
        with self.assertRaisesRegex(ValueError, NOT_PUBLISHED):
            parse_day({'result':[]}, '2026-10-30', '2026-10-30T16:30:00+08:00')
        with self.assertRaisesRegex(ValueError, '缺失或重复'):
            parse_day(raw(), '2026-10-28', '2026-10-28T17:00:00+08:00', '510300')

    def test_today_is_not_eligible_before_close_cutoff(self):
        before=datetime(2026,10,28,16,29,tzinfo=CN)
        after=datetime(2026,10,28,16,30,tzinfo=CN)
        self.assertEqual(eligible_sessions(before,1),['2026-10-27'])
        self.assertEqual(eligible_sessions(after,1),['2026-10-28'])
        self.assertEqual(eligible_sessions(datetime(2026,10,4,18,tzinfo=CN),1),['2026-09-30'])

    def test_bands_use_20_actual_consecutive_dates_and_population_stddev(self):
        days=eligible_sessions(datetime(2026,10,28,17,tzinfo=CN),21)
        rows=[{'date':d,'pcr':i/10} for i,d in enumerate(days)]
        out=add_bands(rows)
        self.assertIsNone(out[18]['band_mid'])
        mean=sum(i/10 for i in range(20))/20
        sd=math.sqrt(sum((i/10-mean)**2 for i in range(20))/20)
        self.assertAlmostEqual(out[19]['band_mid'],mean)
        self.assertAlmostEqual(out[19]['band_upper'],mean+2*sd)
        holiday=next(i for i in range(1,len(days)) if days[i-1]=='2026-09-30')
        self.assertFalse(out[holiday]['gap_before'])
        missing=add_bands(rows[:8]+rows[9:])
        self.assertTrue(missing[8]['gap_before'])
        self.assertIsNone(missing[-1]['band_mid'])

    def test_failed_refresh_keeps_previous_cache_and_reports_error(self):
        with tempfile.TemporaryDirectory() as root,patch('core.option_pcr.HISTORY',Path('/nonexistent-option-pcr.json')):
            store=Store(Path(root)/'monitor.sqlite3')
            old=parse_day(raw(),'2026-10-28','2026-10-28T17:00:00+08:00')
            store.cache(CODE,KIND,old['date'],old)
            service=OptionPCR(store)
            with patch('core.option_pcr.fetch_day',side_effect=OSError('offline')),patch('core.option_pcr.eligible_sessions',return_value=['2026-10-28']):
                service.refresh(datetime(2026,10,28,18,tzinfo=CN))
                view=service.view(datetime(2026,10,28,18,tzinfo=CN))
            self.assertEqual(view['days'][0]['pcr'],old['pcr'])
            self.assertIn('获取失败',view['error'])
            self.assertFalse(view['running'])

    def test_unpublished_then_published_recovers_and_updates_valid_cache(self):
        with tempfile.TemporaryDirectory() as root, patch('core.option_pcr.HISTORY', Path('/nonexistent-option-pcr.json')):
            store=Store(Path(root)/'monitor.sqlite3')
            service=OptionPCR(store)
            now=datetime(2026,10,28,18,tzinfo=CN)
            published=parse_day(raw(), '2026-10-28', now.isoformat())
            with patch('core.option_pcr.eligible_sessions',return_value=['2026-10-28']), patch('core.option_pcr.fetch_day',side_effect=[ValueError(NOT_PUBLISHED),(published,raw())]), patch('core.option_pcr.time.sleep'):
                service.refresh(now)
                self.assertEqual(service.view(now)['error'], NOT_PUBLISHED)
                self.assertEqual(service.view(now)['days'], [])
                service.refresh(now)
                result=service.view(now)
            self.assertEqual(result['error'], '')
            self.assertEqual(result['days'][0]['date'], '2026-10-28')
            self.assertAlmostEqual(result['days'][0]['pcr'], 343583/499320)

    def test_data_collected_after_current_time_is_not_visible(self):
        with tempfile.TemporaryDirectory() as root,patch('core.option_pcr.HISTORY',Path('/nonexistent-option-pcr.json')):
            store=Store(Path(root)/'monitor.sqlite3')
            row=parse_day(raw(),'2026-10-28','2026-10-28T18:00:00+08:00')
            store.cache(CODE,KIND,row['date'],row)
            service=OptionPCR(store)
            self.assertEqual(service.view(datetime(2026,10,28,17,tzinfo=CN))['days'],[])
            self.assertEqual(len(service.view(datetime(2026,10,28,19,tzinfo=CN))['days']),1)

    def test_a_preclose_capture_cannot_become_a_daily_close_later(self):
        with tempfile.TemporaryDirectory() as root,patch('core.option_pcr.HISTORY',Path('/nonexistent-option-pcr.json')):
            store=Store(Path(root)/'monitor.sqlite3')
            service=OptionPCR(store)
            row=parse_day(raw(),'2026-10-28','2026-10-28T14:59:59+08:00')
            store.cache(CODE,KIND,row['date'],row)
            self.assertEqual(service.view(datetime(2026,10,29,19,tzinfo=CN))['days'],[])
            row['collected_at']='2026-10-28T15:00:00+08:00'
            store.cache(CODE,KIND,row['date'],row)
            self.assertEqual(len(service.view(datetime(2026,10,29,19,tzinfo=CN))['days']),1)

    def test_corrupt_cache_cannot_override_verified_record(self):
        with tempfile.TemporaryDirectory() as root, patch('core.option_pcr.HISTORY', Path('/nonexistent-option-pcr.json')):
            store=Store(Path(root)/'monitor.sqlite3')
            service=OptionPCR(store)
            valid=parse_day(raw(),'2026-10-28','2026-10-28T17:00:00+08:00')
            for field,value in [('security_code','510300'),('total_volume',1),('pcr',float('nan')),('call_volume',True)]:
                row=dict(valid, **{field:value})
                store.cache(CODE,KIND,row['date'],row)
                with self.subTest(field=field):
                    self.assertEqual(service.view(datetime(2026,10,28,19,tzinfo=CN))['days'],[])

    def test_separate_products_and_missing_rows(self):
        payload=raw()
        payload['result'].append(dict(payload['result'][0], SECURITY_CODE='510300', SECURITY_ABBR='沪深300ETF华泰柏瑞', CALL_VOLUME='100', PUT_VOLUME='80', TOTAL_VOLUME='180', CP_RATE='80.00'))
        first=parse_day(payload,'2026-10-28','2026-10-28T17:00:00+08:00')
        second=parse_day(payload,'2026-10-28','2026-10-28T17:00:00+08:00','510300')
        self.assertEqual(second['pcr'],.8)
        with tempfile.TemporaryDirectory() as root, patch('core.option_pcr.HISTORY',Path('/nonexistent-option-pcr.json')):
            store=Store(Path(root)/'monitor.sqlite3')
            store.cache('sse-510050',KIND,first['date'],first)
            store.cache('sse-510300',KIND,second['date'],second)
            time=datetime(2026,10,28,19,tzinfo=CN)
            self.assertEqual(OptionPCR(store).view(time)['days'][0]['security_code'],'510050')
            self.assertEqual(OptionPCR(store,'510300').view(time)['days'][0]['security_code'],'510300')
        with self.assertRaises(ValueError):parse_day(raw(),'2026-10-28','2026-10-28T17:00:00+08:00','510300')

    def test_research_fixture_has_contiguous_context_for_september_comparison(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'monitor.sqlite3')
            now=datetime(2026,10,29,23,tzinfo=CN)
            for code,expected,lower in [('510050',.6897,.4645),('510300',.6191,.6015)]:
                days=OptionPCR(store,code).view(now)['days']
                self.assertGreaterEqual(len(days),50)
                row=next(r for r in days if r['date']=='2026-09-30')
                self.assertAlmostEqual(row['pcr'],expected,places=4)
                self.assertAlmostEqual(row['band_lower'],lower,places=4)

    def test_late_october_rows_reproduce_official_responses_and_respect_capture_time(self):
        root=Path(__file__).resolve().parents[1]
        archive=root/'docs/author-trading-system-20261028/exchange-pcr-history-20261031'
        report=json.loads((archive/'report.json').read_text(encoding='utf-8'))
        observed={r['date']:r['captured_at'] for r in report['rows']}
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'monitor.sqlite3')
            for code in ('510050','510300'):
                service=OptionPCR(store,code)
                early=service.view(datetime(2026,10,31,4,10,tzinfo=CN))['days']
                self.assertNotIn('2026-10-29',[r['date'] for r in early])
                rows=service.view(datetime(2026,10,31,4,30,tzinfo=CN))['days']
                for day in ('2026-10-29','2026-10-30'):
                    source=json.loads((archive/f'sse-{day}.json').read_text(encoding='utf-8'))
                    expected=parse_day(source,day,observed[day],code)
                    actual=next(r for r in rows if r['date']==day)
                    for field,value in expected.items():
                        self.assertEqual(actual[field],value)
                    self.assertIsNotNone(actual['band_mid'])


if __name__ == '__main__':
    unittest.main()
