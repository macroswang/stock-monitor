import math
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from core.index_technical import CODE,KIND,IndexTechnical,indicators,parse_daily,weekly
from core.option_pcr import eligible_sessions
from core.provider import CN
from core.store import Store


class IndexTechnicalTests(unittest.TestCase):
    def setUp(self):
        self.days=eligible_sessions(datetime(2026,10,28,17,tzinfo=CN),30)
        self.raw=[[day,i,i,i,i,1] for i,day in enumerate(self.days,1)]

    def test_boll_and_cci_known_analytic_values(self):
        rows=parse_daily({'data':{CODE:{'day':self.raw}}},self.days[0],self.days[-1])
        result=indicators(rows)
        self.assertIsNone(result[18]['boll_mid'])
        self.assertAlmostEqual(result[19]['boll_mid'],10.5)
        self.assertAlmostEqual(result[19]['boll_upper'],10.5+2*math.sqrt(33.25))
        self.assertAlmostEqual(result[19]['cci'],6.5/(.015*3.5))
        constant=[dict(r,open=10,high=10,low=10,close=10) for r in rows]
        self.assertIsNone(indicators(constant)[-1]['cci'])

    def test_gap_resets_indicator_windows(self):
        rows=parse_daily({'data':{CODE:{'day':self.raw}}},self.days[0],self.days[-1])
        out=indicators(rows[:12]+rows[13:])
        self.assertTrue(out[12]['gap_before'])
        self.assertIsNone(out[-1]['boll_mid'])
        self.assertIsNotNone(out[-1]['cci'])

    def test_current_week_excluded_and_missing_daily_bar_excludes_its_week(self):
        rows=parse_daily({'data':{CODE:{'day':self.raw}}},self.days[0],self.days[-1])
        out=weekly(rows,'2026-10-28')
        self.assertEqual(out[-1]['date'],'2026-10-23')
        self.assertEqual(out[-1]['first_date'],'2026-10-19')
        missed=weekly([r for r in rows if r['date']!='2026-10-21'],'2026-10-28')
        self.assertNotIn('2026-10-23',[r['date'] for r in missed])

    def test_volume_weighted_reference_and_gap_reset(self):
        rows=parse_daily({'data':{CODE:{'day':self.raw}}},self.days[0],self.days[-1])
        self.assertEqual(rows[0]['volume'],100)
        out=indicators(rows)
        self.assertIsNone(out[24]['vw_dif'])
        self.assertAlmostEqual(out[25]['vw_dif'],7)
        self.assertAlmostEqual(out[-1]['vw_dea'],7)
        self.assertAlmostEqual(out[-1]['vw_macd'],0)
        without_volume=[dict(row) for row in rows]
        without_volume[15].pop('volume')
        self.assertIsNone(indicators(without_volume)[-1]['vw_dif'])
        weeks=weekly(rows,'2026-10-28')
        self.assertEqual(weeks[-1]['volume'],500)
        weeks_missing=weekly(without_volume,'2026-10-28')
        self.assertTrue(any(row['volume'] is None for row in weeks_missing))

    def test_legacy_price_only_snapshot_remains_available(self):
        with tempfile.TemporaryDirectory() as root,patch('core.index_technical.HISTORY',Path('/nonexistent-index-reference.json')):
            store=Store(Path(root)/'db.sqlite');svc=IndexTechnical(store)
            rows=parse_daily({'data':{CODE:{'day':self.raw}}},self.days[0],self.days[-1])
            for row in rows:row.pop('volume')
            store.cache(CODE,KIND,self.days[-1],{'rows':rows,'collected_at':'2026-10-28T18:00:00+08:00','source':'腾讯公开上证指数日线'})
            with patch('core.index_technical.eligible_sessions',return_value=['2026-10-28']):
                view=svc.view(datetime(2026,10,28,19,tzinfo=CN))
            self.assertIsNotNone(view['daily'][-1]['boll_mid'])
            self.assertIsNone(view['daily'][-1]['vw_dif'])

    def test_reject_duplicated_wrong_date_invalid_high_low_or_missing_latest(self):
        for rows in (self.raw+self.raw[-1:],self.raw[:-1],self.raw[:-1]+[[self.days[-1],10,12,11,9,1]],self.raw[:-1]+[[self.days[-1],10,12,float('nan'),9,1]]):
            with self.subTest(rows=rows[-1]),self.assertRaises(ValueError):parse_daily({'data':{CODE:{'day':rows}}},self.days[0],self.days[-1])

    def test_cache_excludes_future_and_retains_previous_after_failure(self):
        with tempfile.TemporaryDirectory() as root,patch('core.index_technical.HISTORY',Path('/nonexistent-index-reference.json')):
            store=Store(Path(root)/'db.sqlite');svc=IndexTechnical(store)
            rows=parse_daily({'data':{CODE:{'day':self.raw}}},self.days[0],self.days[-1])
            snap={'rows':rows,'collected_at':'2026-10-28T18:00:00+08:00','source':'腾讯公开上证指数日线'}
            store.cache(CODE,KIND,self.days[-1],snap)
            with patch('core.index_technical.eligible_sessions',return_value=['2026-10-28']),patch('core.index_technical.fetch_daily',side_effect=OSError('offline')):
                self.assertFalse(svc.view(datetime(2026,10,28,17,tzinfo=CN))['daily'])
                svc.refresh(datetime(2026,10,28,19,tzinfo=CN))
                view=svc.view(datetime(2026,10,28,19,tzinfo=CN))
            self.assertEqual(len(view['daily']),30)
            self.assertIn('获取失败',view['error'])

    def test_current_day_snapshot_collected_before_close_is_rejected(self):
        with tempfile.TemporaryDirectory() as root,patch('core.index_technical.HISTORY',Path('/nonexistent-index-reference.json')):
            store=Store(Path(root)/'db.sqlite');svc=IndexTechnical(store)
            rows=parse_daily({'data':{CODE:{'day':self.raw}}},self.days[0],self.days[-1])
            snap={'rows':rows,'collected_at':'2026-10-28T10:00:00+08:00','source':'腾讯公开上证指数日线'}
            store.cache(CODE,KIND,self.days[-1],snap)
            self.assertEqual(svc.view(datetime(2026,10,28,19,tzinfo=CN))['daily'],[])

    def test_refresh_preserves_prior_year_warmup_only_with_known_calendar(self):
        # Synthetic calendars and prices test the year boundary; this is not
        # a claim about 2027 exchange holidays or future market data.
        end = '2027-01-04'
        now = datetime(2027,1,4,17,tzinfo=CN)
        day = datetime(2026,6,1,tzinfo=CN)
        source = []
        while day <= now:
            if day.weekday() < 5:
                n = len(source) + 100
                source.append(dict(date=day.date().isoformat(),first_date=day.date().isoformat(),
                                   open=n,close=n,high=n,low=n,volume=10000))
            day += timedelta(days=1)
        with tempfile.TemporaryDirectory() as root, patch('core.index_technical.HISTORY',Path('/nonexistent-index-reference.json')):
            store=Store(Path(root)/'db.sqlite');svc=IndexTechnical(store)
            try:
                known=lambda year: [] if year in (2026,2027) else None
                with patch('core.index_technical.calendar',side_effect=known), \
                     patch('core.breadth.calendar',side_effect=known), \
                     patch('core.index_technical.eligible_sessions',return_value=[end]), \
                     patch('core.index_technical.fetch_daily',return_value=source) as fetch:
                    svc.refresh(now)
                    fetch.assert_called_once_with('2026-01-01',end)
                    view=svc.view(now)
                    self.assertIsNotNone(view['daily'][-1]['boll_mid'])
                    self.assertIsNotNone(view['weekly'][-1]['vw_dif'])
                with patch('core.index_technical.calendar',side_effect=lambda year: [] if year==2027 else None), \
                     patch('core.index_technical.eligible_sessions',return_value=[end]), \
                     patch('core.index_technical.fetch_daily',return_value=source) as fetch:
                    svc.refresh(now)
                    fetch.assert_called_once_with('2027-01-01',end)
            finally:
                store.db.close()


if __name__=='__main__':unittest.main()
