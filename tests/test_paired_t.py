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
        event=dict(kind=kind,time='10:01',key=key,price=price,liquidity=dict(meanShares=100000,currentShares=100000))
        self.service.observe('sz000981',[event],self.app.quotes['sz000981'],self.now,True)

    def drain(self):
        snapshot=lambda *_a,**_k:{**self.snapshot,'observed_at':self.now.isoformat()}
        with patch('core.live_trading.brokers.holdings',side_effect=snapshot):self.service.drain(reports=False)

    def cycles(self):return self.store.query('SELECT * FROM trading_cycles ORDER BY created_at,rowid')

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
