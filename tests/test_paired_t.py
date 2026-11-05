import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.live_trading import LiveTrading
from core.provider import CN
from core.store import Store
from core.trading_costs import paired_profit


class PairedTTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'monitor.sqlite3');self.addCleanup(self.store.db.close)
        self.now=datetime(2026,11,5,10,1,5,tzinfo=CN)
        clock=patch('core.live_trading.now_cn',side_effect=lambda:self.now);clock.start();self.addCleanup(clock.stop)
        self.app=SimpleNamespace(store=self.store,quotes={},provider=Mock())
        self.service=LiveTrading(self.app);self.store.setconfig('monitor',True)
        self.store.execute("INSERT INTO broker_accounts(id,broker,account) VALUES('a','zhangle','1234561001')")
        self.snapshot=dict(account_id='a',account_verified=True,observed_at=self.now.isoformat(),complete=True,
                           funds={'available':'10000'},positions=[dict(name='山子高科',code='sz000981',quantity=10100,sellable=10100,price=2.20,cost=4.01)])
        self.service.apply_snapshot('a',self.snapshot)
        old=self.service.rule('a','sz000981')
        self.service.save_rule('a','sz000981',dict(strategy_mode='paired_t',paired_enabled=True,t_lots=10,minimum_net_profit=20),old['revision'])
        armed=(self.now-timedelta(minutes=5)).isoformat()
        self.store.execute("UPDATE trading_rules SET armed_at=? WHERE account_id='a'",(armed,))
        self.store.setconfig('trading_paused',False);self.service.started_at=armed

    def signal(self,kind,key,price):
        self.app.quotes['sz000981']=dict(code='sz000981',price=str(price),timestamp=self.now.isoformat())
        event=dict(kind=kind,time=self.now.strftime('%H:%M'),key=key,price=price,liquidity=dict(meanShares=100000,currentShares=100000))
        self.service.observe('sz000981',[event],self.app.quotes['sz000981'],self.now,True)

    def drain(self):
        snapshot=lambda *_a,**_k:{**self.snapshot,'observed_at':self.now.isoformat()}
        with patch('core.live_trading.brokers.holdings',side_effect=snapshot):self.service.drain(reports=False)

    def cycles(self):return self.store.query('SELECT * FROM trading_cycles ORDER BY created_at,rowid')

    def filled_sell(self):
        self.store.setconfig('trading_mode','live')
        self.signal('top','real-sell',2.20)
        run=self.store.query('SELECT * FROM trading_runs')[0]
        payload=json.loads(run['payload']);payload.update(mode='live',plan=dict(quantity=1000,price='2.20'))
        payload['verification']=dict(origin='broker_auto',status='filled',filled=1000,average='2.20',order_id='contract-1')
        self.store.execute("UPDATE trading_runs SET status='filled',payload=? WHERE id=?",(json.dumps(payload),run['id']))
        self.service.sync_cycles();return run

    def test_trial_sell_cannot_trigger_real_buy_after_switch(self):
        self.signal('top','trial-sell',2.20);self.drain()
        self.service.configure(dict(mode='live',confirm_live=True));self.service.configure(dict(paused=False))
        self.now+=timedelta(minutes=1);self.signal('bottom','real-bottom',2.15)
        with patch('core.live_trading.brokers.submit_order') as submit:self.drain();submit.assert_not_called()
        self.assertEqual(self.cycles()[0]['state'],'aborted')

    def test_live_cycle_survives_trial_switch_and_resumes_only_in_live(self):
        self.filled_sell()
        self.service.configure(dict(mode='trial'));self.service.configure(dict(paused=False))
        self.now+=timedelta(minutes=1);self.signal('bottom','trial-bottom',2.15);self.drain()
        self.assertEqual(self.cycles()[0]['state'],'waiting_buy')
        self.assertFalse(self.store.query("SELECT * FROM trading_runs WHERE side='buy'"))
        self.service.configure(dict(mode='live',confirm_live=True));self.service.configure(dict(paused=False))
        self.now+=timedelta(minutes=1);self.signal('bottom','real-bottom',2.15)
        def submit(*args,**kwargs):kwargs['authorize']();return dict(status='accepted',submitted=True)
        with patch('core.live_trading.brokers.submit_order',side_effect=submit) as gateway:
            self.drain();gateway.assert_called_once()
            self.assertEqual(gateway.call_args.args[2:5],('buy','000981',1000))
        self.assertEqual(self.cycles()[0]['state'],'buy_pending')

    def test_mixed_legacy_cycle_cannot_complete(self):
        self.filled_sell();self.signal('bottom','buy',2.15)
        run=self.store.query("SELECT * FROM trading_runs WHERE side='buy'")[0]
        payload=json.loads(run['payload']);payload.update(mode='trial',plan=dict(quantity=1000,price='2.15'))
        self.store.execute("UPDATE trading_runs SET status='trial',payload=? WHERE id=?",(json.dumps(payload),run['id']))
        self.service.sync_cycles();self.assertEqual(self.cycles()[0]['state'],'needs_review')

    def test_disable_and_resume_preserves_waiting_cycle_and_sizes(self):
        self.filled_sell();rule=self.service.rule('a','sz000981')
        saved=self.service.save_rule('a','sz000981',dict(paired_enabled=False),rule['revision'])
        self.now+=timedelta(minutes=1);self.signal('bottom','disabled',2.15)
        self.assertFalse(self.store.query("SELECT * FROM trading_runs WHERE side='buy'"))
        self.assertEqual(self.cycles()[0]['state'],'waiting_buy');self.assertEqual(saved['t_lots'],10)
        self.service.save_rule('a','sz000981',dict(paired_enabled=True),saved['revision'])
        self.now+=timedelta(minutes=1);self.signal('bottom','resumed',2.15)
        self.assertEqual(self.cycles()[0]['state'],'buy_pending')

    def test_needs_review_recovers_when_broker_evidence_is_completed(self):
        run=self.open_real_request()
        self.service.resolve(run['id'],'filled','contract-1',1000,'已核对券商全部成交')
        self.assertEqual(self.cycles()[0]['state'],'needs_review')
        for order,qty,avg in [('wrong',1000,'2.21'),('contract-1',900,'2.21'),('contract-1',1000,'2.19')]:
            with self.assertRaises(ValueError):self.service.resolve(run['id'],'filled',order,qty,'补充券商成交均价',avg)
        with patch('core.live_trading.brokers.submit_order') as submit:
            self.service.resolve(run['id'],'filled','contract-1',1000,'已核对券商成交均价','2.21');submit.assert_not_called()
        self.assertEqual(self.cycles()[0]['state'],'waiting_buy')
        request=json.loads(self.store.query('SELECT result FROM broker_requests')[0]['result'])
        self.assertEqual(request['verification']['average'],'2.21')

    def open_real_request(self,broker='zhangle'):
        self.store.setconfig('trading_mode','live');self.store.execute('UPDATE broker_accounts SET broker=?',(broker,))
        self.signal('top','open-sell',2.20);run=self.store.query('SELECT * FROM trading_runs')[0]
        payload=json.loads(run['payload']);payload['plan']=dict(account_id='a',code='sz000981',side='sell',quantity=1000,price='2.20')
        self.store.execute("UPDATE trading_runs SET status='unknown',payload=? WHERE id=?",(json.dumps(payload),run['id']))
        request=dict(account_id='a',code='000981',side='sell',quantity=1000,price='2.20',dry_run=False)
        stamp=self.now.isoformat()
        self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+run['id'],'a',json.dumps(request),'unknown',json.dumps(dict(order_id='contract-1')),stamp,stamp))
        return run

    def test_galaxy_historical_report_has_manual_recovery_without_device_reads(self):
        run=self.open_real_request('ths');self.now+=timedelta(days=1)
        with patch('core.broker_reconciliation.now_cn',return_value=self.now),patch('core.broker_reconciliation.brokers.order_report') as reader:
            result=self.service.reconcile(run['id']);reader.assert_not_called()
        self.assertFalse(result['ok']);self.assertIn('人工核实',result['message'])
        self.assertEqual(result['status'],'unknown')
        with patch('core.live_trading.brokers.submit_order') as submit:
            self.service.resolve(run['id'],'filled','contract-1',1000,'已核对银河历史成交明细','2.20');submit.assert_not_called()
        self.assertEqual(self.cycles()[0]['state'],'waiting_buy')
        self.assertEqual(self.store.query('SELECT status FROM broker_requests')[0]['status'],'filled')

    def test_manual_close_requires_settled_orders_and_preserves_audit(self):
        self.signal('top','pending',2.20);cycle=self.cycles()[0]
        with self.assertRaisesRegex(ValueError,'未结束'):self.service.close_cycle(cycle['id'],'券商已处理剩余仓位',True)
        run=self.store.query('SELECT * FROM trading_runs')[0]
        payload=json.loads(run['payload']);payload['verification']=dict(status='cancelled',filled=500)
        self.store.execute("UPDATE trading_runs SET status='cancelled',payload=? WHERE id=?",(json.dumps(payload),run['id']))
        self.service.sync_cycles();self.assertEqual(self.cycles()[0]['state'],'needs_review')
        with self.assertRaises(ValueError):self.service.close_cycle(cycle['id'],'已核对',False)
        with patch('core.live_trading.brokers.submit_order') as submit:
            self.service.close_cycle(cycle['id'],'已在券商核对并处理剩余仓位',True);submit.assert_not_called()
        closed=self.cycles()[0];self.assertEqual(closed['state'],'closed_manual')
        self.assertIn('manual_close',json.loads(closed['payload']))
        self.signal('top','next',2.20);self.assertEqual(len(self.cycles()),2)

    def test_only_open_live_paired_requests_poll_across_days(self):
        run=self.filled_sell();stamp=self.now.isoformat()
        request=dict(account_id='a',code='000981',side='sell',quantity=1000,price='2.20',dry_run=False)
        self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+run['id'],'a',json.dumps(request),'unknown',json.dumps(dict(order_id='contract-1')),stamp,stamp))
        self.now+=timedelta(days=1)
        with patch('core.broker_reconciliation.now_cn',return_value=self.now),patch.object(self.service.reconciler,'reconcile') as reconcile:
            self.service.reconciler.poll();reconcile.assert_called_once_with('a','auto_'+run['id'])
            reconcile.reset_mock();self.store.execute("UPDATE trading_cycles SET state='completed'")
            self.service.reconciler.poll();reconcile.assert_not_called()

    def test_disable_during_preparation_blocks_final_buy_and_keeps_cycle(self):
        self.filled_sell();self.signal('bottom','buy-preparation',2.15);clicked=[]
        def submit(*args,**kwargs):
            rule=self.service.rule('a','sz000981')
            self.service.save_rule('a','sz000981',dict(paired_enabled=False),rule['revision'])
            kwargs['authorize']();clicked.append(True)
            return dict(status='accepted',submitted=True)
        with patch('core.live_trading.brokers.submit_order',side_effect=submit):self.drain()
        self.assertEqual(clicked,[]);self.assertEqual(self.cycles()[0]['state'],'waiting_buy')

    def test_restart_preserves_live_waiting_cycle_without_new_submission(self):
        self.filled_sell()
        with patch('core.live_trading.brokers.submit_order') as submit:
            self.service=LiveTrading(self.app);self.service.sync_cycles();submit.assert_not_called()
        self.assertEqual(self.cycles()[0]['state'],'waiting_buy')
        self.assertEqual(self.service.cycle_mode(self.cycles()[0]),'live')

    def test_history_limits_keep_open_cycle_and_both_legs_available(self):
        first=self.open_real_request('ths')
        self.service.resolve(first['id'],'filled','contract-1',1000,'已核对券商全部成交','2.20')
        self.now+=timedelta(minutes=1);self.signal('bottom','old-buy',2.15)
        cycle=self.cycles()[0]
        for n in range(220):
            stamp=(self.now+timedelta(minutes=1,seconds=n)).isoformat()
            payload=json.dumps(dict(mode='live',signal=dict(kind='top',time='10:03')))
            self.store.execute('INSERT INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',
                (f'new-{n}','a','sh603938','sell',f'signal-{n}',stamp[:10],'skipped',payload,stamp,stamp))
        for n in range(120):
            stamp=(self.now+timedelta(minutes=1,seconds=n)).isoformat()
            self.store.execute('INSERT INTO trading_cycles VALUES(?,?,?,?,?,?,?,?,?,?)',
                (f'other-{n}','a','sh603938','completed',100,'unrelated',None,json.dumps(dict(mode='live')),stamp,stamp))
        view=self.service.view();runs={r['id'] for r in view['runs']};cycles={c['id'] for c in view['cycles']}
        self.assertTrue({cycle['first_run_id'],cycle['second_run_id']}<=runs)
        self.assertIn(cycle['id'],cycles)
        self.assertEqual(len(runs),202);self.assertEqual(len(cycles),101)
        self.assertNotIn('new-0',runs);self.assertNotIn('other-0',cycles)

    def test_fee_gate_includes_both_minimum_commissions_and_tax(self):
        rule=self.service.rule('a','sz000981')
        result=paired_profit('2.20','2.15',1000,rule)
        self.assertEqual(result['gross'],50.0)
        self.assertEqual(result['commission'],10.0)
        self.assertGreater(result['fees'],10.0)
        self.assertGreater(result['net'],20.0)

    def test_trial_cycle_waits_for_profitable_bottom_then_allows_unlimited_next_round(self):
        self.signal('top','top-1',2.20);self.drain()
        self.assertEqual(self.cycles()[0]['state'],'waiting_buy')
        self.signal('bottom','bottom-too-small',2.19);self.drain()
        self.assertEqual(self.cycles()[0]['state'],'waiting_buy')
        skipped=self.store.query("SELECT payload FROM trading_runs WHERE status='skipped' ORDER BY rowid DESC LIMIT 1")[0]
        self.assertIn('低于门槛',json.loads(skipped['payload'])['message'])
        self.signal('bottom','bottom-pass',2.15);self.drain()
        self.assertEqual(self.cycles()[0]['state'],'completed')
        self.signal('top','top-2',2.22);self.drain()
        self.assertEqual(len(self.cycles()),2)
        self.assertEqual(self.cycles()[1]['state'],'waiting_buy')

    def test_unknown_first_leg_locks_pair_without_blocking_independent_rules_elsewhere(self):
        self.signal('top','top-unknown',2.20)
        run=self.store.query("SELECT * FROM trading_runs WHERE side='sell'")[0]
        self.store.execute("UPDATE trading_runs SET status='unknown' WHERE id=?",(run['id'],))
        self.service.sync_cycles('a','sz000981')
        self.signal('top','top-again',2.21)
        self.signal('bottom','bottom-blocked',2.10)
        self.assertEqual(len(self.cycles()),1)
        self.assertEqual(self.cycles()[0]['state'],'sell_pending')
        messages=[json.loads(r['payload']).get('message','') for r in self.store.query("SELECT payload FROM trading_runs WHERE status='skipped'")]
        self.assertTrue(any('尚未完成' in message for message in messages))
        self.assertTrue(any('尚未确认首腿成交' in message for message in messages))

    def test_verified_full_sell_without_average_uses_conservative_limit_floor(self):
        self.signal('top','top-verified',2.20)
        run=self.store.query("SELECT * FROM trading_runs WHERE side='sell'")[0]
        payload=json.loads(run['payload']);payload['plan']=dict(price='2.20',quantity=1000)
        payload['verification']=dict(origin='broker_auto',status='filled',filled=1000,order_id='142783')
        self.store.execute("UPDATE trading_runs SET status='filled',payload=? WHERE id=?",(json.dumps(payload),run['id']))
        self.service.sync_cycles('a','sz000981')
        cycle=self.cycles()[0];self.assertEqual(cycle['state'],'waiting_buy')
        saved=json.loads(cycle['payload']);self.assertEqual(saved['sell_price'],'2.20')
        self.assertEqual(saved['sell_price_basis'],'verified_limit_floor')


if __name__=='__main__':unittest.main()
