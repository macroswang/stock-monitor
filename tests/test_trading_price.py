"""Directional price protection and incident replay; all broker IO is mocked."""
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
from core.trading_price import PRICE_POLICY, price_guard


class PriceGuardTests(unittest.TestCase):
    def test_favorable_prices_are_allowed_for_each_side(self):
        for side, price in [('sell','29.20'),('sell','35'),('buy','28.89'),('buy','20')]:
            with self.subTest(side=side, price=price):
                check=price_guard(side,'29.04',price,'.5')
                self.assertTrue(check['allowed']);self.assertEqual(check['adverse_deviation_pct'],0)

    def test_unfavorable_prices_are_blocked_for_each_side(self):
        for side, price in [('buy','29.20'),('sell','28.89')]:
            check=price_guard(side,'29.04',price,'.5')
            self.assertFalse(check['allowed']);self.assertGreater(check['adverse_deviation_pct'],.5)

    def test_exact_thresholds_and_tick_boundaries_do_not_use_float_comparisons(self):
        self.assertTrue(price_guard('buy','100','100.5','.5')['allowed'])
        self.assertTrue(price_guard('sell','100','99.5','.5')['allowed'])
        self.assertFalse(price_guard('buy','100','100.50000001','.5')['allowed'])
        self.assertFalse(price_guard('sell','100','99.49999999','.5')['allowed'])
        self.assertEqual(price_guard('buy','29.04','29.04','.5')['boundary_price'],'29.18')
        self.assertEqual(price_guard('sell','29.04','29.04','.5')['boundary_price'],'28.90')

    def test_invalid_prices_and_thresholds_never_pass(self):
        for bad in (None,0,-1,'nan','Infinity',True,'text'):
            for field in range(3):
                values=['29.04','29.04','.5'];values[field]=bad
                with self.subTest(field=field,value=bad),self.assertRaises(ValueError):price_guard('sell',*values)
        with self.assertRaises(ValueError):price_guard('unknown',29,29,.5)
        with self.assertRaises(ValueError):price_guard('sell',29,29,11)


class IncidentExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
        self.now=datetime(2026,11,3,10,2,3,tzinfo=CN)
        clock=patch('core.live_trading.now_cn',side_effect=lambda:self.now);clock.start();self.addCleanup(clock.stop)
        self.app=SimpleNamespace(store=self.store,quotes={},provider=Mock())
        self.service=LiveTrading(self.app);self.code='sh603938'
        for ident in ('a','b'):
            self.store.execute('INSERT INTO broker_accounts(id,broker,account) VALUES(?,?,?)',(ident,'ths','fixture-'+ident))
            self.service.apply_snapshot(ident,self.snapshot(ident))
        rule=self.service.rule('a',self.code)
        self.service.save_rule('a',self.code,dict(sell_enabled=True,buy_enabled=True,sell_lots=2,buy_lots=2),rule['revision'])
        old=(self.now-timedelta(minutes=10)).isoformat()
        self.store.execute('UPDATE trading_rules SET armed_at=?',(old,));self.service.started_at=old
        self.store.setconfig('monitor',True);self.store.setconfig('trading_mode','live');self.store.setconfig('trading_paused',False)
        self.app.quotes[self.code]=dict(price='29.08',timestamp=self.now.isoformat())
        submit=patch('core.live_trading.brokers.submit_order',return_value=dict(status='accepted',submitted=True));self.submit=submit.start();self.addCleanup(submit.stop)

    def snapshot(self,ident='a',**changes):
        return dict(account_id=ident,account_verified=True,complete=True,observed_at=self.now.isoformat(),funds={'available':'100000'},
                    positions=[dict(code=self.code,name='三孚股份',quantity=500,sellable=300,price='29.08')],**changes)

    def observe(self,side='sell'):
        event=dict(kind='top' if side=='sell' else 'bottom',time='10:02',price=29.04,key='incident-'+side,liquidity=dict(meanShares=41220,currentShares=22500))
        self.service.observe(self.code,[event],self.app.quotes[self.code],self.now,True)

    def run_payload(self):
        row=self.store.query('SELECT * FROM trading_runs')[0]
        return row,json.loads(row['payload'])

    def test_incident_sell_rises_during_holdings_check_and_is_not_discarded(self):
        self.observe()
        def holdings(_store,ident,**kwargs):
            self.assertEqual(ident,'a');self.assertEqual(kwargs,dict(target_code=self.code))
            self.now+=timedelta(seconds=24)
            self.app.quotes[self.code]=dict(price='29.20',timestamp=self.now.isoformat())
            result=self.snapshot();result.update(complete=False,position_only=True);return result
        with patch('core.live_trading.brokers.holdings',side_effect=holdings):self.service.drain(reports=False)
        row,payload=self.run_payload();self.assertEqual(row['status'],'accepted')
        self.assertEqual(self.submit.call_args.args[1:6],('a','sell','603938',200,'29.20'))
        self.assertEqual(payload['price_checks']['before_holdings']['quote_price'],'29.08')
        check=payload['price_checks']['after_holdings'];self.assertEqual(check['reference_price'],'29.04');self.assertEqual(check['quote_price'],'29.20');self.assertTrue(check['allowed'])
        self.assertEqual(payload['timings']['holdings_scope'],'target');self.assertGreaterEqual(payload['timings']['elapsed_ms'],27000)
        self.service.observe(self.code,[dict(kind='top',time='10:02',price=29.04,key='incident-sell')],self.app.quotes[self.code],self.now,True)
        self.service.drain(reports=False);self.submit.assert_called_once()

    def test_falling_buy_is_allowed_and_still_checks_target_holdings(self):
        self.app.quotes[self.code]=dict(price='28.89',timestamp=self.now.isoformat());self.observe('buy')
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot()) as holdings:self.service.drain(reports=False)
        self.assertEqual(self.run_payload()[0]['status'],'accepted');holdings.assert_called_once_with(self.store,'a',target_code=self.code)
        self.assertEqual(self.submit.call_args.args[1:6],('a','buy','603938',200,'28.89'))

    def test_adverse_price_fails_before_expensive_device_read(self):
        self.app.quotes[self.code]=dict(price='28.89',timestamp=self.now.isoformat());self.observe()
        with patch('core.live_trading.brokers.holdings') as holdings:self.service.drain(reports=False)
        row,payload=self.run_payload();self.assertEqual(row['status'],'skipped');holdings.assert_not_called();self.submit.assert_not_called()
        self.assertFalse(payload['price_checks']['before_holdings']['allowed']);self.assertIn('28.89',payload['message']);self.assertIn('29.04',payload['message'])

    def test_final_confirmation_rechecks_market_and_original_order_limit(self):
        self.observe()
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot()):self.service.drain(reports=False)
        guard=self.submit.call_args.kwargs['authorize']
        self.app.quotes[self.code]=dict(price='28.89',timestamp=self.now.isoformat())
        with self.assertRaisesRegex(ValueError,'卖出价低于'):guard()
        _,payload=self.run_payload();self.assertEqual(payload['price_checks']['before_submit']['quote_price'],'28.89')
        self.assertFalse(payload['price_checks']['before_submit']['allowed'])
        self.app.quotes[self.code]=dict(price='29.30',timestamp=self.now.isoformat());guard()
        _,payload=self.run_payload();self.assertTrue(payload['price_checks']['before_submit']['allowed']);self.assertEqual(payload['price_checks']['before_submit']['order_price'],'29.08')

    def test_favorable_prices_cannot_bypass_stock_identity_or_market_bounds(self):
        self.observe()
        for side,changes in [('sell',dict(code='sh600000')),('sell',dict(price='35',limit_up='31.94')),('buy',dict(price='20',limit_down='26.14'))]:
            self.store.execute("UPDATE trading_runs SET status='pending',side=?",(side,))
            self.app.quotes[self.code]={**dict(price='29.08',timestamp=self.now.isoformat()),**changes}
            with patch('core.live_trading.brokers.holdings') as holdings:self.service.drain(reports=False)
            self.assertEqual(self.run_payload()[0]['status'],'skipped');holdings.assert_not_called();self.submit.assert_not_called()

    def test_expiry_after_holdings_preserves_actual_recheck_quote_and_timing(self):
        self.observe()
        def late(*_args,**_kwargs):
            self.now+=timedelta(seconds=91)
            self.app.quotes[self.code]=dict(price='29.20',timestamp=self.now.isoformat())
            return self.snapshot()
        with patch('core.live_trading.brokers.holdings',side_effect=late):self.service.drain(reports=False)
        run,payload=self.run_payload();self.assertEqual(run['status'],'skipped');self.submit.assert_not_called()
        check=payload['price_checks']['after_holdings'];self.assertEqual(check['quote_price'],'29.20');self.assertFalse(check['allowed']);self.assertEqual(check['signal_age_ms'],94000)
        self.assertIn('过期',payload['message'])

    def test_restart_uses_persisted_baseline_for_native_target_check_only(self):
        restarted=LiveTrading(self.app)
        result={**self.snapshot(), 'complete':False,'position_only':True}
        with patch('core.live_trading.brokers.holdings',return_value=result) as holdings:
            self.assertTrue(restarted.execution_sync('a',self.code)['position_only'])
        holdings.assert_called_once_with(self.store,'a',target_code=self.code)
        other=self.store.query("SELECT payload FROM trading_positions WHERE account_id='b'")[0]
        self.assertEqual(json.loads(other['payload'])['sellable'],300)

    def test_target_account_identity_and_snapshot_token_cannot_be_bypassed(self):
        old=self.store.query("SELECT payload FROM trading_positions WHERE account_id='a'")[0]['payload']
        for changes in [dict(account_id='b'),dict(account_verified=False),dict(observed_at=(self.now-timedelta(seconds=31)).isoformat())]:
            result={**self.snapshot(),'complete':False,'position_only':True,**changes}
            with patch('core.live_trading.brokers.holdings',return_value=result),self.assertRaises(ValueError):self.service.execution_sync('a',self.code)
            self.assertEqual(self.store.query("SELECT payload FROM trading_positions WHERE account_id='a'")[0]['payload'],old)
        def changed(*_args,**_kwargs):
            self.store.execute("UPDATE trading_sync SET token='changed' WHERE account_id='a'")
            return {**self.snapshot(),'complete':False,'position_only':True}
        with patch('core.live_trading.brokers.holdings',side_effect=changed),self.assertRaisesRegex(ValueError,'快照已改变'):
            self.service.execution_sync('a',self.code)

    def test_incomplete_baseline_falls_back_to_full_verified_sync(self):
        self.service.apply_snapshot('a',{**self.snapshot(),'complete':False})
        with patch('core.live_trading.brokers.holdings',return_value=self.snapshot()) as holdings:
            self.service.execution_sync('a',self.code)
        holdings.assert_called_once_with(self.store,'a')

    def test_price_policy_upgrade_pauses_once_preserves_rules_and_discards_old_intents(self):
        before=self.service.rule('a',self.code);self.observe()
        self.store.execute("DELETE FROM config WHERE key='trading_price_policy'")
        upgraded=LiveTrading(self.app)
        self.assertTrue(upgraded.settings()['paused']);self.assertEqual(upgraded.rule('a',self.code),before)
        self.assertEqual(self.run_payload()[0]['status'],'skipped');self.assertIn('重新启动',upgraded.settings()['signal_notice'])
        upgraded.configure(dict(paused=False));self.assertFalse(LiveTrading(self.app).settings()['paused'])
        self.assertEqual(self.store.config()['trading_price_policy'],PRICE_POLICY)
