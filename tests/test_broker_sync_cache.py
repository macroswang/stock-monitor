import tempfile
import unittest
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core import brokers
from core.store import Store
from core.live_trading import LiveTrading
from core.provider import now_cn
from executor.brokers.base import BrokerCredentials


class BrokerCodeCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'monitor.sqlite3');self.addCleanup(self.store.db.close)
        self.service=LiveTrading(SimpleNamespace(store=self.store,quotes={}))
        for ident,account in [('a','123450001'),('b','987650002')]:
            self.store.execute('INSERT INTO broker_accounts(id,broker,account) VALUES(?,?,?)',(ident,'zhangle',account))
        guard=patch('core.brokers.device_operation',return_value=nullcontext());guard.start();self.addCleanup(guard.stop)
        self.client=Mock();self.client.holdings.return_value=dict(positions=[],complete=True)

    def seed(self,ident,code):
        self.service.apply_snapshot(ident,dict(account_id=ident,account_verified=True,observed_at=now_cn().isoformat(),complete=True,
            positions=[dict(name='同名测试股',code=code,quantity=100,sellable=100,price=2,code_source='broker_native_form')]))

    def read(self,ident,account):
        self.client.ensure_ready.return_value=dict(account_verified=True,account_display=account)
        with patch('core.brokers._adapter',return_value=({},BrokerCredentials('zhangle',account),self.client)):
            return brokers.holdings(self.store,ident)

    def test_same_name_in_other_account_never_supplies_this_accounts_code(self):
        self.seed('a','sz000981');self.seed('b','sz000001')
        self.read('a','123450001')
        self.assertEqual(self.client.holdings.call_args.kwargs['known_codes'],{'同名测试股':'000981'})
        self.read('b','987650002')
        self.assertEqual(self.client.holdings.call_args.kwargs['known_codes'],{'同名测试股':'000001'})

    def test_conflicting_cache_entries_are_not_silently_selected(self):
        self.seed('a','sz000981')
        self.store.execute('INSERT INTO trading_mappings VALUES(?,?,?)',('a','同名测试股','sz000001'))
        self.read('a','123450001')
        self.assertEqual(self.client.holdings.call_args.kwargs['known_codes'],{})

    def test_no_positions_in_this_account_means_no_cross_account_cache(self):
        self.seed('b','sz000001')
        self.read('a','123450001')
        self.assertEqual(self.client.holdings.call_args.kwargs['known_codes'],{})
