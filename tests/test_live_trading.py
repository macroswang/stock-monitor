import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.live_trading import LiveTrading, order_quantity
from core.provider import CN
from core.store import Store
from core.turning_q1 import signals


class TradingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'monitor.sqlite3');self.addCleanup(self.store.db.close)
        self.now=datetime(2026,11,2,10,1,5,tzinfo=CN)
        clock=patch('core.live_trading.now_cn',return_value=self.now);clock.start();self.addCleanup(clock.stop)
        self.submit=patch('core.live_trading.brokers.submit_order').start();self.addCleanup(patch.stopall)
        self.app=SimpleNamespace(store=self.store,quotes={},provider=Mock())
        self.service=LiveTrading(self.app)
        self.store.setconfig('monitor',True)
        for ident,number in [('a','1234561001'),('b','9876542002')]:
            self.store.execute('INSERT INTO broker_accounts(id,broker,account,label) VALUES(?,?,?,?)',(ident,'zhangle',number,ident))
        self.quote=dict(code='sz000981',price='2.13',timestamp=self.now.isoformat())
        self.app.quotes['sz000981']=self.quote

    def snapshot(self,account='a',positions=None,complete=True):
        return dict(account_id=account,account_verified=True,observed_at=self.now.isoformat(),complete=complete,
                    funds={'available':'10000'},positions=positions if positions is not None else [dict(name='山子高科',code='sz000981',quantity=1200,sellable=900,price=2.13,cost=2.05)])

    def seed(self,account='a'):
        self.service.apply_snapshot(account,self.snapshot(account))

    def arm(self,account='a',**changes):
        self.seed(account)
        rule=self.service.rule(account,'sz000981')
        self.service.save_rule(account,'sz000981',dict(buy_enabled=True,sell_enabled=True,**{'buy_mode':'position','sell_mode':'position','buy_percent':50,'sell_percent':50,'daily_orders':10,**changes}),rule['revision'])
        self.store.execute('UPDATE trading_rules SET armed_at=? WHERE account_id=?',((self.now-timedelta(minutes=5)).isoformat(),account))
        self.store.setconfig('trading_paused',False)
        self.service.started_at=(self.now-timedelta(minutes=5)).isoformat()

    def event(self,key='one',kind='bottom'):
        return dict(kind=kind,time='10:01',key=key,price=2.13,liquidity=dict(meanShares=100000,currentShares=100000))

    def observe(self,account='a',kind='bottom',key='one',continuous=True):
        self.service.observe('sz000981',[self.event(key,kind)],self.quote,self.now,continuous)

    def drain(self):
        with patch('core.live_trading.brokers.holdings',side_effect=lambda _store,ident:self.snapshot(ident)):
            self.service.drain()

    def runs(self):
        return self.store.query('SELECT * FROM trading_runs ORDER BY rowid')

    def test_same_stock_account_rules_and_sources_are_independent(self):
        self.seed('a');self.seed('b')
        a=self.service.rule('a','sz000981')
        self.service.save_rule('a','sz000981',dict(buy_enabled=True),a['revision'])
        self.assertTrue(self.service.rule('a','sz000981')['buy_enabled'])
        self.assertFalse(self.service.rule('b','sz000981')['buy_enabled'])
        self.assertEqual(len(self.store.query('SELECT * FROM watch')),1)
        self.assertEqual({s['account_id'] for s in self.service.sources()['sz000981']},{'a','b'})

    def test_wrong_account_snapshot_cannot_write_positions(self):
        with self.assertRaisesRegex(ValueError,'不一致'):
            self.service.apply_snapshot('a',self.snapshot('b'))
        self.assertEqual(self.store.query('SELECT * FROM trading_positions'),[])

    def test_unverified_or_stale_snapshot_rejected(self):
        for changes in [dict(account_verified=False),dict(observed_at=(self.now-timedelta(minutes=4)).isoformat())]:
            with self.assertRaises(ValueError):self.service.apply_snapshot('a',{**self.snapshot(),**changes})

    def test_partial_or_failed_sync_never_clears_old_positions(self):
        self.arm()
        self.service.apply_snapshot('a',self.snapshot(positions=[],complete=False))
        self.assertEqual(self.store.query('SELECT active FROM trading_positions')[0]['active'],1)
        self.assertTrue(self.service.rule('a','sz000981')['buy_enabled'])
        with patch('core.live_trading.brokers.holdings',side_effect=ValueError('账户切换')):
            with self.assertRaises(ValueError):self.service.sync('a')
        self.assertEqual(self.store.query('SELECT active FROM trading_positions')[0]['active'],1)
        self.assertEqual(self.store.query('SELECT status FROM trading_sync')[0]['status'],'failed')

    def test_complete_clear_disarms_and_reentry_stays_off(self):
        self.arm()
        self.service.apply_snapshot('a',self.snapshot(positions=[]))
        self.assertFalse(self.service.rule('a','sz000981')['buy_enabled'])
        self.seed()
        self.assertFalse(self.service.rule('a','sz000981')['buy_enabled'])

    def test_resync_does_not_compound_base_or_change_rule_revision(self):
        self.arm()
        before=self.service.rule('a','sz000981')
        p=dict(name='山子高科',code='sz000981',quantity=3000,sellable=2000,price=2.13)
        self.service.apply_snapshot('a',self.snapshot(positions=[p]))
        self.assertEqual(self.service.rule('a','sz000981'),before)

    def test_missing_code_is_pending_even_when_name_is_in_watchlist(self):
        self.seed()
        p=dict(name='山子高科',quantity=100,sellable=100)
        result=self.service.apply_snapshot('b',self.snapshot('b',[p]))
        self.assertEqual(result['unresolved'],1)
        self.assertEqual(self.store.query("SELECT * FROM trading_positions WHERE account_id='b'"),[])

    def test_manual_mapping_checks_name_token_and_account(self):
        p=dict(name='山子高科',quantity=100,sellable=100,price=2.13)
        result=self.service.apply_snapshot('a',self.snapshot(positions=[p]))
        self.app.provider.quote.return_value={'code':'sz000981','name':'另一只股票'}
        with self.assertRaisesRegex(ValueError,'名称'):self.service.map_position('a',result['token'],'山子高科','000981')
        self.app.provider.quote.return_value={'code':'sz000981','name':'山子高科'}
        with self.assertRaisesRegex(ValueError,'更新'):self.service.map_position('b',result['token'],'山子高科','000981')
        self.service.map_position('a',result['token'],'山子高科','000981')
        self.assertEqual(self.store.query('SELECT account_id FROM trading_mappings'),[{'account_id':'a'}])
        self.assertEqual(self.store.query('SELECT account_id FROM trading_positions'),[{'account_id':'a'}])

    def test_invalid_rules_and_stale_edit_rejected(self):
        self.seed();old=self.service.rule('a','sz000981')
        for changes in [dict(buy_percent=0),dict(sell_percent=101),dict(buy_enabled='yes'),dict(max_deviation_pct=float('nan')),dict(buy_lots=True),dict(buy_lots=1.5),dict(buy_mode='bad'),dict(daily_orders=0),dict(signal='shape')]:
            with self.assertRaises(ValueError):self.service.save_rule('a','sz000981',changes,old['revision'])
        self.service.save_rule('a','sz000981',dict(buy_mode='position',buy_percent=25),old['revision'])
        with self.assertRaisesRegex(ValueError,'刷新'):self.service.save_rule('a','sz000981',{},old['revision'])

    def test_expired_mapping_confirmation_rolls_back_mapping(self):
        p=dict(name='山子高科',quantity=100,sellable=100,price=2.13)
        result=self.service.apply_snapshot('a',self.snapshot(positions=[p]))
        self.app.provider.quote.return_value={'code':'sz000981','name':'山子高科'}
        later=self.now+timedelta(minutes=4)
        with patch('core.live_trading.now_cn',return_value=later):
            with self.assertRaisesRegex(ValueError,'过期'):
                self.service.map_position('a',result['token'],'山子高科','000981')
        self.assertEqual(self.store.query('SELECT * FROM trading_mappings'),[])

    def test_lot_rounding_and_sellable_basis(self):
        self.seed()
        rule=self.service.rule('a','sz000981')
        self.service.save_rule('a','sz000981',dict(buy_mode='position',buy_percent=50,sell_mode='position',sell_percent=25),rule['revision'])
        self.assertEqual(self.service.plan('a','sz000981','buy')['quantity'],600)
        self.assertEqual(self.service.plan('a','sz000981','sell')['quantity'],300)
        self.assertEqual(order_quantity('sz000981',199,'1','sell'),199)
        self.assertEqual(order_quantity('sz000981',199,'1/2','sell'),0)
        self.assertEqual(order_quantity('sh688001',399,'1/2','buy'),0)
        self.assertEqual(order_quantity('sh688001',499,'1/2','buy'),249)

    def test_default_paused_no_signal_or_broker_dispatch(self):
        self.seed();self.observe();self.drain()
        self.assertEqual(self.runs(),[]);self.submit.assert_not_called()
        with patch('core.turning_shapes.signals') as engine:
            self.service.ingest('sz000981',[],self.quote,self.now,True)
            engine.assert_not_called()

    def test_noncontinuous_old_or_pre_enable_events_never_replayed(self):
        self.arm();self.observe(continuous=False)
        self.assertEqual(self.runs(),[])
        self.service.started_at=self.now.isoformat();self.observe()
        self.assertEqual(self.runs(),[])
        self.service.started_at=(self.now-timedelta(minutes=5)).isoformat()
        self.store.execute('UPDATE trading_rules SET armed_at=?',(self.now.isoformat(),))
        self.observe();self.assertEqual(self.runs(),[])

    def test_revised_vwap_cannot_become_a_new_signal_one_poll_later(self):
        self.arm()
        bars=[dict(time='10:00',close='2.13',volume=100000,average='2.15',complete=True)]
        with patch('core.turning_shapes.signals',return_value=[]):
            self.service.ingest('sz000981',bars,self.quote,self.now,False)
        revised=[dict(bars[0],average='2.30')]
        with patch('core.turning_shapes.signals',return_value=[self.event()]):
            self.service.ingest('sz000981',revised,self.quote,self.now,True)
            self.service.ingest('sz000981',revised,self.quote,self.now,True)
        self.assertEqual(self.runs(),[])

    def test_live_ingestion_only_dispatches_new_confirmations_after_baseline(self):
        self.arm()
        bars=[dict(time='10:00',close='2.13',volume=100000,average='2.15',complete=True)]
        with patch('core.turning_shapes.signals',return_value=[]):
            self.service.ingest('sz000981',bars,self.quote,self.now,False)
        with patch('core.turning_shapes.signals',return_value=[self.event()]):
            self.service.ingest('sz000981',bars+[dict(bars[0],time='10:01')],self.quote,self.now,True)
            self.service.ingest('sz000981',bars+[dict(bars[0],time='10:01')],self.quote,self.now,True)
        self.assertEqual(len(self.runs()),1)

    def test_repeated_signal_trial_is_durable_and_never_calls_broker_submit(self):
        self.arm();self.observe();self.observe();self.drain();self.observe();self.drain()
        self.assertEqual(len(self.runs()),1);self.assertEqual(self.runs()[0]['status'],'trial')
        self.assertEqual(json.loads(self.runs()[0]['payload'])['plan']['quantity'],600)
        self.submit.assert_not_called()
        second=LiveTrading(self.app);self.assertEqual(len(second.store.query('SELECT * FROM trading_runs')),1)

    def test_account_pause_and_rule_change_after_enqueue_stop_execution(self):
        self.arm();self.observe();self.service.pause_account('a',True);self.drain()
        self.assertEqual(self.runs()[0]['status'],'skipped');self.submit.assert_not_called()

    def test_partial_sync_blocks_even_trial(self):
        self.arm();self.observe()
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot(complete=False)):self.service.drain()
        self.assertEqual(self.runs()[0]['status'],'skipped');self.submit.assert_not_called()

    def test_two_accounts_receive_correct_separate_trial_intents(self):
        self.arm('a');self.arm('b');self.observe();self.drain()
        self.assertEqual({r['account_id'] for r in self.runs()},{'a','b'})
        for r in self.runs():self.assertEqual(json.loads(r['payload'])['plan']['account_id'],r['account_id'])
        self.submit.assert_not_called()

    def test_daily_count_prevents_repeat_signals(self):
        self.arm(daily_orders=1);self.observe(key='one');self.drain();self.observe(key='two');self.drain()
        self.assertEqual([r['status'] for r in self.runs()],['trial','skipped'])

    def test_price_deviation_blocks(self):
        self.arm();self.observe();self.app.quotes['sz000981']={**self.quote,'price':'2.50'};self.drain()
        self.assertEqual(self.runs()[0]['status'],'skipped');self.submit.assert_not_called()

    def test_removed_money_quotas_do_not_block_affordable_orders(self):
        self.arm()
        for key in ('one','two','three'):self.observe(key=key);self.drain()
        self.assertEqual([r['status'] for r in self.runs()],['trial']*3)
        self.assertGreater(sum(json.loads(r['payload'])['plan']['value'] for r in self.runs()),3000)

    def test_global_pause_and_resume_does_not_replay_queued_intent(self):
        self.arm();self.observe()
        self.service.configure({'paused':True});self.service.configure({'paused':False});self.drain()
        self.assertEqual(self.runs()[0]['status'],'skipped');self.submit.assert_not_called()

    def test_trial_quota_does_not_consume_real_mode_quota(self):
        self.arm(daily_orders=1);self.observe();self.drain()
        self.store.setconfig('trading_mode','live')
        self.submit.return_value=dict(status='accepted',submitted=True)
        self.observe(key='different-live-signal');self.drain()
        self.assertEqual([r['status'] for r in self.runs()],['trial','accepted'])
        self.assertEqual(self.submit.call_count,1)

    def test_distinct_stocks_cannot_each_spend_the_same_account_cash(self):
        self.arm()
        second=dict(name='宏昌电子',code='sh603002',quantity=1200,sellable=1200,price=2.13)
        snap=self.snapshot(positions=self.snapshot()['positions']+[second]);snap['funds']['available']='2000'
        self.service.apply_snapshot('a',snap)
        r=self.service.rule('a','sh603002')
        self.service.save_rule('a','sh603002',dict(buy_enabled=True,buy_mode='position',buy_percent=50),r['revision'])
        self.store.execute('UPDATE trading_rules SET armed_at=?',((self.now-timedelta(minutes=5)).isoformat(),))
        self.app.quotes['sh603002']={**self.quote,'code':'sh603002'}
        self.observe()
        self.service.observe('sh603002',[self.event('second')],self.app.quotes['sh603002'],self.now,True)
        with patch('core.live_trading.brokers.holdings',return_value=snap):self.service.drain()
        self.assertEqual([r['status'] for r in self.runs()],['trial','skipped'])
        self.assertIn('资金不足',json.loads(self.runs()[1]['payload'])['message'])
        self.submit.assert_not_called()

    def test_unknown_previous_day_blocks_new_real_dispatch(self):
        self.arm();self.observe();self.drain()
        self.store.execute("UPDATE trading_runs SET status='unknown',day='2026-10-30'")
        self.observe(key='new');self.drain()
        self.assertEqual(self.runs()[1]['status'],'skipped');self.submit.assert_not_called()

    def test_account_cannot_be_deleted_with_unresolved_auto_order(self):
        from core import brokers
        self.arm();self.observe();self.drain()
        self.store.execute("UPDATE trading_runs SET status='accepted'")
        with self.assertRaisesRegex(ValueError,'核实'):
            brokers.delete_account(self.store,'a',secrets=Mock())
        self.assertEqual(len(self.store.query("SELECT * FROM broker_accounts WHERE id='a'")),1)

    def test_restart_does_not_replay_pending_or_sending(self):
        self.arm();self.observe()
        LiveTrading(self.app)
        self.assertEqual(self.runs()[0]['status'],'skipped')
        self.store.execute("UPDATE trading_runs SET status='sending'")
        LiveTrading(self.app)
        self.assertEqual(self.runs()[0]['status'],'unknown')

    def test_live_routing_uses_intent_account_and_final_guard_is_passed(self):
        self.arm('b');self.store.setconfig('trading_mode','live')
        self.submit.return_value=dict(status='accepted',submitted=True)
        self.observe();self.drain()
        args=self.submit.call_args
        self.assertEqual(args.args[1:5],('b','buy','000981',600))
        guard=args.kwargs['authorize']
        self.service.pause_account('b',True)
        with self.assertRaises(ValueError):guard()
        self.assertEqual(self.runs()[0]['status'],'accepted')

    def test_manual_verification_requires_actual_quantity_and_order_id(self):
        self.arm();self.observe();self.drain()
        self.store.execute("UPDATE trading_runs SET status='unknown'")
        ident=self.runs()[0]['id']
        for status,oid,filled,note in [('filled','',600,'已核对成交'),('filled','123',300,'已核对成交'),('not_sent','',5,'已核对未发出')]:
            with self.assertRaises(ValueError):self.service.resolve(ident,status,oid,filled,note)
        self.service.resolve(ident,'not_sent','',0,'已核对券商委托和成交均未发出')
        self.assertEqual(self.runs()[0]['status'],'not_sent');self.submit.assert_not_called()


class Q1BackendTests(unittest.TestCase):
    def test_frozen_frontend_golden_points_match_backend(self):
        cases=json.loads((Path(__file__).parent/'ui/fixtures/turning-q1.json').read_text())
        for c in cases:
            got=signals(c['bars'])
            self.assertEqual([r['key'] for r in got],[r['key'] for r in c['expected']])
            for actual,expected in zip(got,c['expected']):
                for key,value in expected.items():
                    if isinstance(value,(float,int)):self.assertAlmostEqual(actual[key],value,places=9)
                    elif isinstance(value,dict):
                        for k,v in value.items():self.assertAlmostEqual(actual[key][k],v,places=9)
                    else:self.assertEqual(actual[key],value)

    def test_prefix_and_future_changes_do_not_change_confirmed_points(self):
        cases=json.loads((Path(__file__).parent/'ui/fixtures/turning-q1.json').read_text())
        for c in cases[:2]:
            all_points=signals(c['bars'])
            for i in range(20,len(c['bars']),7):
                end=c['bars'][i]['time'];expected=[m for m in all_points if m['time']<=end]
                self.assertEqual(signals(c['bars'][:i+1]),expected)
                changed=[b if j<=i else dict(b,close='999',average='1',volume=1) for j,b in enumerate(c['bars'])]
                self.assertEqual([m for m in signals(changed) if m['time']<=end],expected)
