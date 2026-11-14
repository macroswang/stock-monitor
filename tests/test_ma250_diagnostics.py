import copy
import tempfile
import unittest
from datetime import date, timedelta

from core.app import App
from core.ma250_diagnostics import describe
from core.ma250_pullback import analyze
from tests.test_ma250_pullback import bar, calendar


def history():
    return [bar(day, 10) for day in calendar(500)]


class AnnualDataDiagnostics(unittest.TestCase):
    def test_short_history_explains_310_bar_warmup_without_changing_input(self):
        bars=history()[-136:];saved=copy.deepcopy(bars);report=analyze(bars);original=copy.deepcopy(report)
        issue=describe('sh600000','测试',bars,report)
        self.assertEqual(issue['bars'],136);self.assertEqual(issue['minimum_bars'],310)
        self.assertIn('仅136根',issue['reasons'][0])
        self.assertEqual(issue['repair_ranges'][0]['end'],(date.fromisoformat(bars[0]['date'])-timedelta(days=1)).isoformat())
        self.assertEqual(bars,saved);self.assertEqual(report,original)

    def test_long_gap_proposes_only_missing_dates_and_deduplicates_windows(self):
        bars=history();previous,following=bars[299]['date'],bars[380]['date'];del bars[300:380]
        report=analyze(bars);self.assertEqual(report['latest']['readiness'],'quality_blocked')
        issue=describe('sh600000','测试',bars,report)
        self.assertEqual(len(issue['repair_ranges']),1)
        repair=issue['repair_ranges'][0]
        self.assertEqual(repair['start'],(date.fromisoformat(previous)+timedelta(days=1)).isoformat())
        self.assertEqual(repair['end'],(date.fromisoformat(following)-timedelta(days=1)).isoformat())
        self.assertFalse(any(repair['start']<=b['date']<=repair['end'] for b in bars))
        self.assertTrue(any('间隔' in reason for reason in issue['reasons']))

    def test_price_jump_is_explained_without_a_repair_or_adjustment_switch(self):
        bars=history()
        for b in bars[400:]:
            for key in ['open','close','high','low']:b[key]*=1.5
        issue=describe('sh600000','测试',bars,analyze(bars))
        self.assertEqual(issue['state'],'quality_blocked');self.assertEqual(issue['repair_ranges'],[])
        self.assertTrue(any('22%' in reason for reason in issue['reasons']))
        self.assertIn('不自动切换复权',issue['suggestion'])

    def test_changed_or_invalid_data_never_breaks_the_scan_explanation(self):
        issue=describe('sh600000','测试',[{'date':'broken'}],dict(latest={'readiness':'quality_blocked'},error=None))
        self.assertIn('日线正在更新',issue['reasons'][0])
        self.assertEqual(describe('sh600000','测试',[],dict(latest=None,error='日线无效'))['state'],'invalid')

    def test_scan_diagnostics_are_memoized_and_do_not_write_business_state(self):
        with tempfile.TemporaryDirectory() as folder:
            app=App(folder,False)
            try:
                app.store.execute('DELETE FROM watch')
                bars=history();del bars[300:380]
                for b in bars:app.store.cache('sh600000','daily',b['date'],b)
                app.store.execute("INSERT OR REPLACE INTO watch(code,name,enabled) VALUES('sh600000','测试',1)")
                tables=['events','delivery','local_delivery','ma250_journal','trading_runs','broker_requests']
                before={t:app.store.query('SELECT * FROM '+t) for t in tables}
                formal=copy.deepcopy(app.annual_signals.report('sh600000'))
                first=app.ma250_scan.view(dict(universe='watch'));second=app.ma250_scan.view(dict(universe='watch'))
                self.assertEqual(len(first['data_issues']),1)
                self.assertIs(first['data_issues'],second['data_issues'])
                self.assertEqual(formal,app.annual_signals.report('sh600000'))
                self.assertEqual({t:app.store.query('SELECT * FROM '+t) for t in tables},before)
            finally:app.stop.set();app.store.db.close()


if __name__=='__main__':unittest.main()
