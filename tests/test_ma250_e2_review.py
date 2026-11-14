import copy
from datetime import date, datetime, timedelta
import tempfile
import threading
import unittest
from unittest.mock import patch

from core.app import App
from core.ma250_e2 import analyze, confirmation_for
from core.ma250_pullback import prepare, analyze as formal_analyze
from core.provider import CN
from research.ma250_optimization import research_entry
from tests.test_ma250_e2 import case
from tests.test_ma250_pullback import bar, next_day


def dated_case(source_day=date(2026,11,11)):
    rows,_,_=case();i=len(rows)-5;days=[source_day]
    while len(days)<=i:
        day=days[-1]-timedelta(days=1)
        while day.weekday()>4:day-=timedelta(days=1)
        days.append(day)
    days=list(reversed(days))
    while len(days)<len(rows):days.append(next_day(days[-1].isoformat()))
    for row,day in zip(rows,days):row['date']=day.isoformat()
    return rows,i,{r['date']:True for r in rows}


class E2BoundaryReview(unittest.TestCase):
    def test_confirmation_survives_terminal_pending_entry_and_next_day_locked_entry(self):
        rows,i,market=dated_case();prefix=rows[:i+3];f=prepare(prefix)
        source=formal_analyze(prefix,market)['signals'][0]
        decision=confirmation_for(prefix,f,i,source,market)
        self.assertEqual(decision['status'],'confirmed')
        self.assertEqual(research_entry('sh600000',prefix,f,i,source,'break3',sorted(market),market)['status'],'pending_entry')
        original=analyze(prefix,market)['signals'];self.assertEqual(len(original),1)
        rows[i+3].update(open=13.16,close=13.16,high=13.16,low=13.16)
        full=prepare(rows)
        self.assertEqual(research_entry('sh600000',rows,full,i,source,'break3',sorted(market),market)['status'],'entry_unavailable')
        self.assertEqual(analyze(rows,market)['signals'],original)

    def test_missing_index_and_stock_day_cannot_extend_three_verified_sessions(self):
        rows,i,market=dated_case(date(2026,11,9));high=rows[i]['high']
        missing=rows[i+1]['date'];del market[missing];del rows[i+1]
        for j in (i+1,i+2):rows[j].update(open=high-.03,close=high-.01,high=high+.03,low=high-.04)
        value=high+.2;rows.append(bar(next_day(rows[-1]['date']),value,open_=value-.01,high=value+.04,low=value-.03));market[rows[-1]['date']]=True
        source=formal_analyze(rows,market)['signals'][0]
        self.assertEqual(rows[i+3]['date'],'2026-11-13')
        self.assertEqual(analyze(rows,market)['signals'],[])
        self.assertEqual(research_entry('sh600000',rows,prepare(rows),i,source,'break3',sorted(market),market)['status'],'confirmation_not_met')

    def test_each_prefix_ignores_later_index_values_and_price_bars(self):
        rows,i,market=dated_case();full=analyze(rows,market)['signals']
        for last in range(i,len(rows)):
            prefix=rows[:last+1];end=prefix[-1]['date'];visible={d:v for d,v in market.items() if d<=end}
            expected=[s for s in full if s['date']<=end]
            self.assertEqual(analyze(prefix,visible)['signals'],expected)
            poisoned={d:(v if d<=end else False) for d,v in market.items()}
            self.assertEqual(analyze(prefix,poisoned)['signals'],expected)


class E2ServiceReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App(self.tmp.name,False);self.code='sh600000'
        self.rows,self.i,self.market=dated_case();self.app.market_regime.above_map=lambda:self.market
        for row in self.rows:self.app.store.cache(self.code,'daily',row['date'],dict(row,volume_unit='shares'))
        self.app.store.execute('INSERT OR REPLACE INTO watch(code,name,enabled) VALUES(?,?,1)',(self.code,'研究边界样本'))

    def tearDown(self):
        self.app.stop.set();self.app.store.db.close();self.tmp.cleanup()

    def test_close_gate_and_chart_list_agree_without_future_cache_bars(self):
        before=datetime(2026,11,13,15,19,tzinfo=CN);closed=before.replace(minute=20)
        with patch('core.provider.now_cn',return_value=before):
            self.assertFalse(self.app.annual_signals.research_report(self.code)['signals'])
        with patch('core.provider.now_cn',return_value=closed),patch('core.ma250_scan.now_cn',return_value=closed):
            history=self.app.call('history',dict(code=self.code,start='2025-01-01',end='2026-11-13'))
            scan=self.app.ma250_scan.view(dict(universe='watch',recent=5,kind='e2'))
            self.assertEqual(len(history['e2']['signals']),1);self.assertEqual(len(scan['rows']),1)
            expected=history['e2']['signals'][0]
            self.assertEqual(expected['date'],'2026-11-13')
            for field,value in expected.items():self.assertEqual(scan['rows'][0][field],value)

    def test_formal_queries_do_not_wait_for_research_computation(self):
        original=self.app.annual_signals.report(self.code)
        entered,release,done=threading.Event(),threading.Event(),threading.Event();errors=[]
        def slow(*args,**kwargs):
            entered.set();release.wait(3);return dict(signals=[],error=None)
        def research():
            try:self.app.annual_signals.research_report(self.code)
            except Exception as e:errors.append(e)
        def formal():
            try:self.assertIs(self.app.annual_signals.report(self.code),original);done.set()
            except Exception as e:errors.append(e)
        with patch('core.ma250_e2.analyze',side_effect=slow):
            worker=threading.Thread(target=research);worker.start();self.assertTrue(entered.wait(1))
            reader=threading.Thread(target=formal);reader.start()
            try:self.assertTrue(done.wait(.5),'formal query blocked by research calculation')
            finally:release.set();worker.join(4);reader.join(4)
        self.assertFalse(errors)


if __name__=='__main__':unittest.main()
