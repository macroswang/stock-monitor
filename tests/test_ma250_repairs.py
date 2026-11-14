"""Regression cases from the review, independent of profitable sample selection."""
import json,tempfile,threading,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from core.app import App
from core.provider import CN
from core.ma250_pullback import analyze,rule_spec,prepare
from core.ma250_sessions import eligible_sessions
from tests.test_ma250_pullback import bar,calendar,next_day,strong_case
from research.ma250_execution import entry_for,close_exit,path_exit,net_pct
from research.ma250_portfolio import simulate
from research.ma250_pullback_lab import candidates
from scripts.report_ma250_journal import evaluate,summary,load as load_journal
from scripts.study_ma250_large import metrics


def crossing(volume=1500):
    days=calendar(340);prices=[10+i*.001 for i in range(338)]+[9.9,10.8]
    bars=[bar(d,p,open_=p-.01,high=p+.04,low=p-.04) for d,p in zip(days,prices)]
    for b in bars:b['volume']=1000
    bars[-1]['volume']=volume
    return bars


class DetectorRepairs(unittest.TestCase):
    def test_real_volume_is_preserved_and_missing_volume_cannot_confirm(self):
        bs=crossing();r=analyze(bs)['breakouts'][-1]
        self.assertAlmostEqual(r['volume_ratio'],1.5);self.assertTrue(r['quality'])
        self.assertFalse(analyze(crossing(100))['breakouts'][-1]['quality'])
        del bs[-1]['volume'];r=analyze(bs)['breakouts'][-1]
        self.assertIsNone(r['volume_ratio']);self.assertFalse(r['quality'])

    def test_anomalous_jump_and_bad_history_do_not_produce_breakouts(self):
        bs=crossing();bs[-1].update(open=15,close=16,high=16.1,low=14.9)
        self.assertFalse(any(r['date']==bs[-1]['date'] for r in analyze(bs)['breakouts']))
        bs=crossing();bs[290]['high']=float('nan');self.assertIsNotNone(analyze(bs)['error'])
        bs=crossing();bs[290]['provisional']=True;self.assertIsNotNone(analyze(bs)['error'])

    def test_full_retracement_low_and_stop_are_retained(self):
        bs,day=strong_case(touch_above=False);ma=sum(b['close'] for b in bs[-251:-1])/250
        bs[-2]['low']=round(ma*.90,4);bs[-1]['low']=round(ma*1.01,4)
        s=analyze(bs,market={day:True})['signals'][-1]
        self.assertFalse(s['strong']);self.assertEqual(s['touch_low'],bs[-2]['low'])
        self.assertLess(s['stop'],bs[-2]['low']);self.assertEqual(s['setup_type'],'undercut_reclaim')

    def test_ordinary_signal_can_upgrade_once_inside_cooldown(self):
        bs,day=strong_case();next_=next_day(day).isoformat();value=bs[-1]['close']*1.01
        bs.append(bar(next_,value,open_=value-.05,low=value-.06,high=value+.05))
        market={day:False,next_:True};rows=analyze(bs,market=market)['signals']
        self.assertEqual([(r['strong'],r['upgrade']) for r in rows],[(False,False),(True,True)])
        self.assertEqual(rows[0]['episode_id'],rows[1]['episode_id'])
        previous=rows[0].copy()
        for _ in range(2):
            d=next_day(bs[-1]['date']).isoformat();v=bs[-1]['close']*1.001
            bs.append(bar(d,v,open_=v-.01));market[d]=True
        result=analyze(bs,market=market)['signals'];self.assertEqual(result[0],previous)
        self.assertEqual(sum(r['strong'] for r in result),1)

    def test_a_higher_low_can_still_break_a_rising_line(self):
        bs,day=strong_case();f=prepare(bs)
        bs[-2]['low']=f['ma250'][-2]+.0001
        bs[-1]['low']=f['ma250'][-1]-.0001
        self.assertGreater(bs[-1]['low'],bs[-2]['low'])
        s=analyze(bs,market={day:True})['signals'][-1]
        self.assertEqual(s['touch_date'],bs[-2]['date'])
        self.assertFalse(s['strong']);self.assertIn('broke-line',s['strong_reasons'])
        self.assertEqual(s['setup_type'],'undercut_reclaim')

    def test_research_uses_every_exact_client_event_including_pending(self):
        bs,day=strong_case();market={b['date']:True for b in bs}
        index={b['date']:dict(above_ma250=True,above_ma20=True,close=3000+i,ret20=1.) for i,b in enumerate(bs)}
        live=analyze(bs,market=market)['signals'];study=candidates('sh600000',bs,index)
        fields=lambda r:(r['date'],r['episode_id'],r['strong'],r['upgrade'],r['rule_id'])
        self.assertEqual(list(map(fields,live)),list(map(fields,study)))
        self.assertEqual(study[-1]['execution_status'],'pending_entry')
        self.assertIsNone(study[-1]['forward']['20'])

    def test_close_gate_calendar_has_no_1630_delay(self):
        self.assertEqual(eligible_sessions(datetime(2026,11,13,15,19,tzinfo=CN)),['2026-11-12'])
        self.assertEqual(eligible_sessions(datetime(2026,11,13,15,20,tzinfo=CN)),['2026-11-13'])
        self.assertEqual(eligible_sessions(datetime(2026,11,14,16,tzinfo=CN)),['2026-11-13'])
        self.assertEqual(eligible_sessions(datetime(2026,10,1,16,tzinfo=CN)),['2026-09-30'])


class ExecutionRepairs(unittest.TestCase):
    def series(self,n=30):
        days=calendar(n);bs=[bar(d,10,open_=10,high=10.2,low=9.8) for d in days]
        for b in bs:b['volume']=1000
        return bs

    def test_twenty_sessions_includes_entry_and_pending_is_not_a_forced_exit(self):
        bs=self.series();e=entry_for(bs,0,'sh600000');x=close_exit(bs,e['index'],20)
        self.assertEqual(x['index'],20)
        self.assertEqual(close_exit(bs[:20],1,20)['status'],'pending_exit')

    def test_t_plus_one_cannot_book_a_first_day_target(self):
        bs=self.series(4);bs[1].update(open=10,close=10.5,high=11.2,low=9.9)
        r=path_exit(bs,1,9,11,max_hold=2)
        self.assertEqual(r['outcome'],'timeout');self.assertEqual(r['index'],2)
        bs[1]['low']=8.8;bs[2].update(open=9.5,close=9.4,high=9.6,low=9.3)
        r=path_exit(bs,1,9,11,max_hold=2)
        self.assertEqual(r['index'],2);self.assertEqual(r['price'],9.5)

    def test_locked_entry_and_locked_exit_are_not_assumed_fills(self):
        bs=self.series();bs[1].update(open=11,close=11,high=11,low=11)
        self.assertEqual(entry_for(bs,0,'sh600000')['status'],'entry_unavailable')
        bs=self.series();bs[20].update(open=9,close=9,high=9,low=9)
        self.assertEqual(close_exit(bs,1,20)['index'],21)

    def test_future_evening_cash_cannot_fund_morning_entry(self):
        bs=self.series(4);series={'A':bs,'B':bs}
        es=[dict(code='A',entry_date=bs[0]['date'],entry=10,exit_date=bs[1]['date'],strong=True),
            dict(code='B',entry_date=bs[1]['date'],entry=10,exit_date=bs[2]['date'],strong=True)]
        curve,trades=simulate(series,es,bs[0]['date'],bs[-1]['date'],slots=1)
        self.assertEqual([t['code'] for t in trades],['A'])
        self.assertGreater(curve[0][1],0)

    def test_unfilled_old_event_cannot_close_a_new_position(self):
        bs=self.series(8);series={'A':bs}
        es=[dict(code='A',entry_date=bs[0]['date'],entry=10,exit_date=bs[2]['date'],strong=True),
            dict(code='A',entry_date=bs[1]['date'],entry=10,exit_date=bs[4]['date'],strong=True),
            dict(code='A',entry_date=bs[3]['date'],entry=10,exit_date=bs[6]['date'],strong=True)]
        _,trades=simulate(series,es,bs[0]['date'],bs[-1]['date'],slots=1)
        self.assertEqual([t['exit_date'] for t in trades],[bs[2]['date'],bs[6]['date']])
        self.assertTrue(all(t['exit_date']==t['planned_exit'] for t in trades))

    def test_journal_retains_pending_and_separates_rule_ids(self):
        bs=self.series(1);journal=[dict(code='A',day=bs[0]['date'],rule_id=r,data=dict(signal=dict(strong=True))) for r in ('old','new')]
        rows=evaluate(journal,{'A':bs});self.assertEqual(len(rows),2)
        self.assertEqual({r['rule_id'] for r in rows},{'old','new'});self.assertEqual(summary(rows)['pending'],2)

    def test_each_horizon_and_path_label_respects_the_research_boundary(self):
        row=dict(date='2023-12-01',execution_status='entered',forward={str(h):1. for h in (5,10,20,60)},
                 exits={str(h):dict(date='2023-12-20' if h<=20 else '2024-02-01') for h in (5,10,20,60)},
                 path_outcome='target',path_label_end='2024-01-05',
                 path_wins={k:True for k in ('5_3','8_4','10_5','15_8')},
                 path_policy_label_end={k:'2024-01-05' for k in ('5_3','8_4','10_5','15_8')},excess20=0.)
        m=metrics([row],label_cutoff='2024-01-01')
        self.assertEqual(m['n20'],1);self.assertEqual(m['n60'],0)
        self.assertEqual(m['n_path'],0);self.assertTrue(all(v is None for v in m['policies'].values()))


class ClientRepairs(unittest.TestCase):
    def setUp(self):
        self.calendar_patch=patch('core.app.annual_sessions',side_effect=lambda now,n:[now.date().isoformat()]);self.calendar_patch.start()
        self.tmp=tempfile.TemporaryDirectory();self.app=App(self.tmp.name,False)
        self.app.store.execute('DELETE FROM watch');self.app.store.execute('DELETE FROM pool')
        self.bs,self.day=strong_case();self.code='sh600000'
        for b in self.bs:self.app.store.cache(self.code,'daily',b['date'],b)
        self.app.store.execute('INSERT INTO watch(code,name) VALUES(?,?)',(self.code,'测试'))
        self.app.market_regime.above_map=lambda:{self.day:True}
    def tearDown(self):self.calendar_patch.stop();self.app.store.db.close();self.tmp.cleanup()

    def test_cache_hit_and_mid_history_or_index_edit_invalidation(self):
        first=self.app.annual_signals.report(self.code);second=self.app.annual_signals.report(self.code)
        self.assertIs(first,second)
        changed=dict(self.bs[280],high=self.bs[280]['high']+.01)
        self.app.store.cache(self.code,'daily',changed['date'],changed)
        third=self.app.annual_signals.report(self.code);self.assertIsNot(second,third)
        self.app.store.cache('sh000300','index_regime_v1','latest',dict(rows=[]))
        self.assertIsNot(third,self.app.annual_signals.report(self.code))
        self.assertEqual(len(self.app.annual_signals.memo),1)

    def test_log_is_immutable_and_independent_of_alert_switch(self):
        self.app.store.setconfig('ma250_alert',False);now=datetime.fromisoformat(self.day+'T15:25').replace(tzinfo=CN)
        self.app.check_ma250(self.code,now)
        saved=self.app.store.query('SELECT * FROM ma250_journal');self.assertEqual(len(saved),2)
        self.app.ma250_checked.clear();self.app.check_ma250(self.code,now)
        self.assertEqual(saved,self.app.store.query('SELECT * FROM ma250_journal'))
        self.assertEqual(self.app.store.query('SELECT * FROM events'),[])
        self.app.store.setconfig('ma250_alert',True);self.app.check_ma250(self.code,now)
        self.assertEqual(len(self.app.store.query('SELECT * FROM events')),1)

    def test_transient_notification_write_failure_is_retried(self):
        now=datetime.fromisoformat(self.day+'T15:25').replace(tzinfo=CN)
        with patch.object(self.app.store,'event',side_effect=OSError('temporary disk error')):
            with self.assertRaises(OSError):self.app.check_ma250(self.code,now)
        self.app.check_ma250(self.code,now)
        self.assertEqual(len(self.app.store.query('SELECT * FROM events')),1)
        self.app.check_ma250(self.code,now)
        self.assertEqual(len(self.app.store.query('SELECT * FROM events')),1)

    def test_journal_report_rejects_bad_history_instead_of_splicing(self):
        broken=dict(self.bs[280],high=None)
        self.app.store.cache(self.code,'daily',broken['date'],broken)
        _,bars,_=load_journal(Path(self.tmp.name)/'monitor.sqlite3')
        self.assertEqual(bars[self.code],[])

    def test_filters_apply_before_paging_and_membership_identity_invalidates(self):
        base=analyze(self.bs,market={self.day:True})['signals'][0]
        codes=[f'S{i:04}' for i in range(501)]
        with self.app.store.lock,self.app.store.db:
            self.app.store.db.execute('DELETE FROM watch')
            self.app.store.db.executemany('INSERT INTO watch(code,name) VALUES(?,?)',[(c,c) for c in codes])
        def report(code):
            s=dict(base,date='2026-11-13',strong=code==codes[-1])
            return dict(signals=[s],breakouts=[],latest=dict(date=s['date'],ready=True),error=None)
        with patch.object(self.app.annual_signals,'report',side_effect=report):
            r=self.app.ma250_scan.view(dict(universe='watch',strong_only=True,page_size=100))
            self.assertEqual(r['total'],501);self.assertEqual(r['filtered_total'],1)
            self.assertEqual(r['rows'][0]['code'],codes[-1])
            r=self.app.ma250_scan.view(dict(universe='watch',query=codes[-2]))
            self.assertEqual(r['rows'][0]['code'],codes[-2])
            self.app.store.execute('UPDATE watch SET code=?,name=? WHERE code=?',('NEW','NEW',codes[-2]))
            r=self.app.ma250_scan.view(dict(universe='watch',query='NEW'))
            self.assertEqual(r['filtered_total'],1)

    def test_scan_job_does_not_block_the_ipc_request_thread(self):
        entered,release=threading.Event(),threading.Event()
        def slow(_):entered.set();release.wait(3);return dict(rows=[])
        with patch.object(self.app.ma250_scan,'view',side_effect=slow):
            job=self.app.call('ma250_scan_start',{})
            self.assertTrue(entered.wait(1));self.assertEqual(self.app.call('job',job)['status'],'running')
            release.set()

    def test_ready_stock_close_checks_precede_multi_year_warmups(self):
        self.app.store.execute('INSERT INTO watch(code,name) VALUES(?,?)',('sh600001','第二只'))
        calls=[]
        def end_loop(_):self.app.stop.set();return True
        with patch.object(self.app.market_regime,'ensure'), \
             patch.object(self.app.daily_cache,'update',side_effect=lambda code:calls.append(('update',code))), \
             patch.object(self.app.daily_cache,'ensure_history',side_effect=lambda code:calls.append(('warm',code))), \
             patch.object(self.app,'check_ma250',side_effect=lambda code,now:calls.append(('check',code))), \
             patch.object(self.app.stop,'wait',side_effect=end_loop):
            self.app.daily_loop()
        self.assertLess(calls.index(('check','sh600001')),calls.index(('warm',self.code)))

if __name__=='__main__':unittest.main()
