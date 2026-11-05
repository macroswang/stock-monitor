"""Optional caps removed; identity, funds, latest intent and idempotency remain.

All state is temporary and every native brokerage operation is replaced.
"""
import json
from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch
from core.live_trading import LiveTrading
from tests import test_trading_quantity_modes as fixtures


class RequiredChecksTests(TestCase):
    setUp = fixtures.QuantityServiceTests.setUp
    arm = fixtures.QuantityServiceTests.arm
    observe = fixtures.QuantityServiceTests.observe

    def run_row(self):
        return self.store.query('SELECT * FROM trading_runs ORDER BY rowid DESC')[0]

    def live(self):
        self.service.configure(dict(mode='live',confirm_live=True));self.arm()

    def snapshot_now(self,**changes):
        return {**self.snapshot,'observed_at':self.now.isoformat(),**changes}

    def test_cash_equal_to_order_value_has_no_extra_reserve(self):
        self.live()
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot_now(funds=dict(available='3000'))),patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
            self.observe('exact-cash');self.service.drain(reports=False)
        self.assertEqual(self.run_row()['status'],'accepted');submit.assert_called_once()
        self.assertEqual(self.service.view()['cash_reserve'],dict(rate=0,fixed=0))

    def test_each_distinct_signal_can_submit_past_old_daily_quota(self):
        self.live()
        with patch('core.live_trading.brokers.holdings',side_effect=lambda *_a,**_k:self.snapshot_now()),patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
            for n,status in enumerate(['unknown','rejected','cancelled','filled','accepted','accepted']):
                self.observe(str(n));self.service.drain(reports=False)
                self.assertEqual(self.run_row()['status'],'accepted')
                self.store.execute('UPDATE trading_runs SET status=? WHERE id=?',(status,self.run_row()['id']))
            self.assertEqual(submit.call_count,6)

    def test_stale_quote_waits_without_device_io_then_uses_fresh_data(self):
        self.live();self.observe('waiting');self.now+=timedelta(seconds=100)
        with patch('core.live_trading.brokers.holdings',side_effect=lambda *_a,**_k:self.snapshot_now()) as holdings,patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
            self.service.drain(reports=False)
            self.assertEqual(self.run_row()['status'],'pending');holdings.assert_not_called();submit.assert_not_called()
            self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
            self.store.execute("UPDATE trading_runs SET payload=json_set(payload,'$.retry_after',0)")
            self.service.drain(reports=False)
            self.assertEqual(self.run_row()['status'],'accepted');holdings.assert_called_once();submit.assert_called_once()

    def test_newer_signal_cancels_old_queued_intent_before_device_io(self):
        self.arm();self.observe('old');self.now+=timedelta(seconds=1);self.observe('new')
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot_now()) as holdings:
            self.service.drain(reports=False)
        rows=self.store.query('SELECT * FROM trading_runs ORDER BY rowid')
        self.assertEqual([r['status'] for r in rows],['skipped','trial']);holdings.assert_called_once()
        self.assertIn('更新信号',json.loads(rows[0]['payload'])['message'])

    def test_new_signal_during_native_preparation_cancels_original_confirmation(self):
        self.live();self.observe('old');confirmed=[]
        def prepare(*_a,authorize,**_k):
            self.now+=timedelta(seconds=1);self.observe('new')
            authorize();confirmed.append(True)
            return dict(status='accepted')
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot_now()),patch('core.live_trading.brokers.submit_order',side_effect=prepare):self.service.drain(reports=False)
        self.assertEqual(confirmed,[])
        self.assertEqual([r['status'] for r in self.store.query('SELECT * FROM trading_runs ORDER BY rowid')],['skipped','pending'])

    def test_changed_confirmation_minute_cannot_repeat_a_submitted_shape(self):
        self.live()
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='shape|09:59|10:01',price=30)
        with patch('core.live_trading.brokers.holdings',side_effect=lambda *_a,**_k:self.snapshot_now()),patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
            self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,True);self.service.drain(reports=False)
            self.now+=timedelta(minutes=1);event.update(time='10:02',key='shape|09:59|10:02')
            self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
            self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,True);self.service.drain(reports=False)
        submit.assert_called_once();self.assertEqual(len(self.store.query('SELECT * FROM trading_runs')),1)

    def test_unsent_shape_does_not_block_later_fresh_confirmation(self):
        self.live()
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='shape|09:59|10:01',price=30)
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot_now(funds=dict(available='1'))),patch('core.live_trading.brokers.submit_order') as submit:
            self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,True);self.service.drain(reports=False)
            submit.assert_not_called();self.assertEqual(self.run_row()['status'],'skipped')
        self.now+=timedelta(minutes=1);event.update(time='10:02',key='shape|09:59|10:02');self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot_now()),patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
            self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,True);self.service.drain(reports=False)
            submit.assert_called_once();self.assertEqual(self.run_row()['status'],'accepted')

    def test_old_limits_migrate_without_changing_sizes_or_stopping_execution(self):
        self.arm();before=self.service.rule('a','sh603938')
        stored={k:v for k,v in before.items() if k not in ('revision','armed_at')}
        self.store.execute('UPDATE trading_rules SET payload=? WHERE account_id=?',(json.dumps(dict(stored,daily_orders=1,max_deviation_pct=.1)),'a'))
        restored=LiveTrading(self.app);after=restored.rule('a','sh603938')
        self.assertFalse(restored.settings()['paused'])
        self.assertEqual(after['armed_at'],before['armed_at'])
        self.assertEqual({k:v for k,v in after.items() if k not in ('revision','armed_at')},stored)

    def test_revision_or_sampling_gap_does_not_veto_new_current_minute_signal(self):
        self.arm();bar=dict(time='10:00',close='30',volume=10000,average='30.5',complete=True)
        with patch('core.turning_shapes.signals',return_value=[]):self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,False)
        self.now+=timedelta(seconds=50);self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='shape|09:59|10:01',price=30)
        with patch('core.turning_shapes.signals',return_value=[event]):
            self.service.ingest('sh603938',[dict(bar,average='30.6'),dict(bar,time='10:01')],self.app.quotes['sh603938'],self.now,False,'分钟数据修订')
        self.assertEqual(self.run_row()['status'],'pending')
        self.assertTrue(json.loads(self.run_row()['payload'])['admission']['allowed'])

    def test_recovered_historical_signal_is_not_admitted_on_new_tail(self):
        self.arm();bar=dict(time='10:00',close='30',volume=10000,average='30.5',complete=True)
        with patch('core.turning_shapes.signals',return_value=[]):self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,False)
        self.now+=timedelta(minutes=2)
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='old-shape',price=30)
        with patch('core.turning_shapes.signals',return_value=[event]):
            self.service.ingest('sh603938',[bar,dict(bar,time='10:03')],self.app.quotes['sh603938'],self.now,False)
        self.assertEqual(self.run_row()['status'],'skipped')

    def test_cross_day_pending_intent_never_replays(self):
        self.arm();self.observe('yesterday');self.now+=timedelta(days=1)
        with patch('core.live_trading.brokers.holdings') as holdings:self.service.drain(reports=False)
        self.assertEqual(self.run_row()['status'],'skipped');holdings.assert_not_called()

    def test_delayed_minute_data_is_not_mistaken_for_a_current_signal(self):
        self.arm();bar=dict(time='10:00',close='30',volume=10000,average='30.5',complete=True)
        with patch('core.turning_shapes.signals',return_value=[]):self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,False)
        self.now+=timedelta(minutes=2);self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='delayed-shape',price=30)
        with patch('core.turning_shapes.signals',return_value=[event]):
            self.service.ingest('sh603938',[bar,dict(bar,time='10:01')],self.app.quotes['sh603938'],self.now,False)
        self.assertEqual(self.run_row()['status'],'skipped')

    def test_target_recheck_can_proceed_while_other_codes_remain_unresolved(self):
        self.arm()
        partial=self.snapshot_now(complete=False,positions=[self.snapshot['positions'][0],dict(name='未映射股票',quantity=500,sellable=500)])
        self.service.apply_snapshot('a',partial)
        target=self.snapshot_now(complete=False,position_only=True)
        with patch('core.live_trading.brokers.holdings',return_value=target) as holdings:
            self.observe('target');self.service.drain(reports=False)
        self.assertEqual(self.run_row()['status'],'trial')
        holdings.assert_called_once_with(self.store,'a',target_code='sh603938')
        state=self.store.query("SELECT * FROM trading_sync WHERE account_id='a'")[0]
        self.assertEqual(state['status'],'partial')
        self.assertEqual(json.loads(state['payload'])['unresolved'][0]['name'],'未映射股票')

    def test_paused_account_is_not_an_obstacle_to_starting_other_accounts(self):
        self.arm();rule=self.service.rule('b','sh603938')
        self.service.save_rule('b','sh603938',dict(buy_enabled=True),rule['revision'])
        self.service.pause_account('b',True);self.service.configure(dict(paused=True))
        def read(_store,ident,**_kwargs):
            self.assertEqual(ident,'a')
            return self.snapshot_now()
        with patch('core.live_trading.brokers.holdings',side_effect=read) as holdings:
            self.service.prepare()
        self.assertFalse(self.service.settings()['paused']);holdings.assert_called_once()

    def test_recovered_history_row_does_not_cancel_a_current_queued_intent(self):
        self.arm();self.observe('current');self.now+=timedelta(seconds=1)
        event=dict(kind='bottom',time='09:59',key='recovered-history',price=30)
        self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,False,'历史信号，未补单')
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot_now()):self.service.drain(reports=False)
        rows=self.store.query('SELECT status FROM trading_runs ORDER BY rowid')
        self.assertEqual([r['status'] for r in rows],['trial','skipped'])

    def test_truncated_minutes_wait_then_recover_the_existing_intent(self):
        self.live();bar=dict(time='10:00',close='30',volume=10000,average='30.5',complete=True)
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='shape|09:59|10:01',price=30)
        bars=[bar,dict(bar,time='10:01')]
        with patch('core.turning_shapes.signals',return_value=[]):self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,False)
        with patch('core.turning_shapes.signals',return_value=[event]):self.service.ingest('sh603938',bars,self.app.quotes['sh603938'],self.now,True)
        with patch('core.turning_shapes.signals',return_value=[]):self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,False)
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot_now()) as holdings,patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
            self.service.drain(reports=False)
            self.assertEqual(self.run_row()['status'],'pending');holdings.assert_not_called();submit.assert_not_called()
            with patch('core.turning_shapes.signals',return_value=[event]):self.service.ingest('sh603938',bars,self.app.quotes['sh603938'],self.now,True)
            self.store.execute("UPDATE trading_runs SET payload=json_set(payload,'$.retry_after',0)")
            self.service.drain(reports=False)
            self.assertEqual(self.run_row()['status'],'accepted');submit.assert_called_once()

    def test_new_signal_in_activation_minute_is_proven_by_a_later_baseline(self):
        self.arm();self.service.started_at=self.now.isoformat()
        self.store.execute('UPDATE trading_rules SET armed_at=?',(self.now.isoformat(),))
        bar=dict(time='10:01',close='30',volume=10000,average='30.5',complete=True)
        self.now+=timedelta(seconds=5)
        with patch('core.turning_shapes.signals',return_value=[]):self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,False)
        self.now+=timedelta(seconds=5)
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='new-after-activation',price=30)
        with patch('core.turning_shapes.signals',return_value=[event]):self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,True)
        self.assertEqual(self.run_row()['status'],'pending')
        self.assertGreater(json.loads(self.run_row()['payload'])['admission']['baseline_at'],self.service.started_at)

    def test_preexisting_signal_in_activation_minute_is_not_replayed(self):
        self.arm();self.service.started_at=self.now.isoformat()
        bar=dict(time='10:01',close='30',volume=10000,average='30.5',complete=True)
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='already-present',price=30)
        with patch('core.turning_shapes.signals',return_value=[event]):
            self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,False)
            self.now+=timedelta(seconds=5)
            self.service.ingest('sh603938',[bar],self.app.quotes['sh603938'],self.now,True)
        self.assertEqual(self.store.query('SELECT * FROM trading_runs'),[])

    def test_trial_shape_does_not_block_new_live_confirmation_of_same_candidate(self):
        self.arm()
        event=dict(kind='bottom',time='10:01',candidateTime='09:59',key='shape|09:59|10:01',price=30)
        with patch('core.live_trading.brokers.holdings',side_effect=lambda *_a,**_k:self.snapshot_now()),patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted')) as submit:
            self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,True);self.service.drain(reports=False)
            self.assertEqual(self.run_row()['status'],'trial');submit.assert_not_called()
            self.service.configure(dict(mode='live',confirm_live=True));self.service.configure(dict(paused=False))
            self.now+=timedelta(minutes=1);self.app.quotes['sh603938']['timestamp']=self.now.isoformat()
            event.update(time='10:02',key='shape|09:59|10:02')
            self.service.observe('sh603938',[event],self.app.quotes['sh603938'],self.now,True);self.service.drain(reports=False)
            self.assertEqual(self.run_row()['status'],'accepted');submit.assert_called_once()
