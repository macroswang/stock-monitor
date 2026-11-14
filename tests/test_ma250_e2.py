import copy
from datetime import datetime
import tempfile
import unittest
from unittest.mock import patch

from core.app import App
from core.ma250_e2 import analyze, confirmation_window
from core.ma250_pullback import analyze as formal_analyze
from core.provider import CN
from tests.test_ma250_pullback import bar, next_day, strong_case


def case():
    rows,source=strong_case()
    high=rows[-1]['high']
    for value in [high-.02,high+.1,high+.2,high+.3]:
        rows.append(bar(next_day(rows[-1]['date']),value,open_=value-.02,high=value+.1,low=value-.03))
    for b in rows:b['volume']=1000
    market={b['date']:True for b in rows}
    return rows,source,market


class E2DetectorTests(unittest.TestCase):
    def test_confirm_on_close_and_keep_original_source_date(self):
        rows,source,market=case();before=copy.deepcopy(rows)
        result=analyze(rows,market)['signals']
        self.assertEqual(len(result),1)
        signal=result[0]
        self.assertEqual(signal['source_date'],source)
        self.assertEqual(signal['date'],rows[-3]['date'])
        self.assertEqual(signal['confirmation_day'],2)
        self.assertTrue(signal['research_only'])
        self.assertGreater(signal['close'],signal['source_high'])
        self.assertEqual(rows,before)

    def test_intraday_high_and_equal_close_do_not_confirm(self):
        rows,source,market=case();i=next(i for i,b in enumerate(rows) if b['date']==source)
        high=rows[i]['high'];rows[i+1].update(close=high,open=high-.01,high=high+.5)
        self.assertFalse(analyze(rows[:i+2],market)['signals'])
        self.assertEqual(analyze(rows,market)['signals'][0]['date'],rows[i+2]['date'])

    def test_expired_window_cannot_buy_a_day_four_breakout(self):
        rows,source,market=case();i=next(i for i,b in enumerate(rows) if b['date']==source)
        high=rows[i]['high']
        for j in range(i+1,i+4):rows[j].update(open=high-.03,close=high-.01,low=high-.04,high=high+.3)
        self.assertFalse(analyze(rows,market)['signals'])

    def test_structure_break_cancels_the_entire_candidate(self):
        rows,source,market=case();formal=formal_analyze(rows,market);stop=formal['signals'][0]['stop']
        rows[-4]['low']=stop-.01
        self.assertFalse(analyze(rows,market)['signals'])

    def test_market_is_required_and_unknown_is_not_true(self):
        rows,source,market=case();i=next(i for i,b in enumerate(rows) if b['date']==source)
        for b in rows[i+1:]:market[b['date']]=False
        self.assertFalse(analyze(rows,market)['signals'])
        self.assertFalse(analyze(rows,{})['signals'])

    def test_close_above_source_high_still_needs_to_clear_ma5(self):
        from core.ma250_pullback import prepare
        rows,source,market=case();i=next(i for i,b in enumerate(rows) if b['date']==source)
        rows[i+1].update(open=13.4,close=13.5,high=13.6,low=13.3);market[rows[i+1]['date']]=False
        value=rows[i]['high']+.01
        for j in (i+2,i+3):rows[j].update(open=value-.02,close=value,high=value+.05,low=value-.03)
        f=prepare(rows)
        self.assertGreater(value,rows[i]['high']);self.assertLess(value,f['ma5'][i+2])
        self.assertFalse(analyze(rows,market)['signals'])

    def test_provisional_candle_is_not_confirmation(self):
        rows,source,market=case();rows=rows[:-2];rows[-1]['provisional']=True
        self.assertFalse(analyze(rows,market)['signals'])
        rows[-1]['provisional']=False
        self.assertEqual(len(analyze(rows,market)['signals']),1)

    def test_future_prices_do_not_revoke_an_earlier_confirmation(self):
        rows,source,market=case();confirmed=analyze(rows[:-2],market)['signals']
        rows[-1].update(open=10.,close=10.,high=10.1,low=9.)
        self.assertEqual(analyze(rows,market)['signals'],confirmed)

    def test_verified_window_counts_weekends_and_never_bridges_unknown_year(self):
        confirmation_window.cache_clear();self.addCleanup(confirmation_window.cache_clear)
        self.assertEqual(confirmation_window('2026-11-13','2026-11-20')[0],('2026-11-16','2026-11-17','2026-11-18'))
        days,known=confirmation_window('2026-12-30','2027-01-08')
        self.assertEqual(days,('2026-12-31',));self.assertFalse(known)

    def test_bad_or_mismatched_data_does_not_create_markers(self):
        rows,source,market=case();bad=copy.deepcopy(rows);bad[20]['high']=float('nan')
        self.assertIsNotNone(analyze(bad,market)['error'])
        formal=formal_analyze(rows,market);formal['signals'][0]['date']='2029-01-01'
        result=analyze(rows,market,formal=formal)
        self.assertFalse(result['signals']);self.assertIsNotNone(result['error'])


class E2IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=App(self.temp.name,False)
        self.rows,self.source,self.market=case();self.code='sh600000'
        self.app.market_regime.above_map=lambda:self.market
        for b in self.rows:self.app.store.cache(self.code,'daily',b['date'],dict(b,volume_unit='shares'))
        self.app.store.execute('INSERT OR REPLACE INTO watch(code,name,enabled) VALUES(?,?,1)',(self.code,'E2样本'))

    def tearDown(self):
        self.app.stop.set();self.app.store.db.close();self.temp.cleanup()

    def test_history_scan_and_cache_share_one_read_only_research_report(self):
        formal=copy.deepcopy(self.app.annual_signals.report(self.code))
        tables=['events','delivery','local_delivery','ma250_journal','trading_runs','broker_requests']
        before={t:self.app.store.query('SELECT * FROM '+t) for t in tables}
        history=self.app.call('history',dict(code=self.code,start='2023-01-01',end='2026-11-13'))
        scan=self.app.call('ma250_scan',dict(universe='watch',recent=1000,kind='e2'))
        self.assertEqual(len(scan['rows']),1)
        self.assertEqual(history['e2']['signals'][0]['date'],scan['rows'][0]['date'])
        self.assertFalse(scan['rows'][0]['strong']);self.assertTrue(scan['rows'][0]['research_only'])
        self.assertEqual(self.app.annual_signals.report(self.code),formal)
        self.assertEqual({t:self.app.store.query('SELECT * FROM '+t) for t in tables},before)
        misses=self.app.annual_signals.research_misses
        self.app.annual_signals.research_report(self.code)
        self.assertEqual(self.app.annual_signals.research_misses,misses)

    def test_mid_history_edit_invalidates_e2_cache(self):
        original=self.app.annual_signals.research_report(self.code)['signals'][0]
        row=dict(self.rows[-4]);value=self.rows[-5]['high']+.01
        row.update(open=value-.01,close=value,high=value+.05,low=value-.03)
        self.app.store.cache(self.code,'daily',row['date'],row)
        changed=self.app.annual_signals.research_report(self.code)['signals'][0]
        self.assertNotEqual(original['date'],changed['date'])
        self.assertEqual(changed['date'],row['date'])

    def test_formal_close_checks_do_not_compute_research_signals(self):
        with patch.object(self.app.annual_signals,'research_report',side_effect=AssertionError('E2 reached alert path')):
            self.app.check_ma250(self.code,datetime(2026,11,13,15,25,tzinfo=CN))


if __name__=='__main__':unittest.main()
