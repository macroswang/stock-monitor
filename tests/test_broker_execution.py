"""请求持久化与故障恢复回归，全部使用临时数据库和假券商。"""
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import brokers
from core.store import Store
from executor.brokers.base import BrokerCredentials


class ExecutionJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.store = Store(self.path)
        self.addCleanup(self.store.db.close)
        self.client = Mock()
        self.client.spec.supports_order = True
        self.client.ensure_ready.return_value = {"account_verified": True}
        self.creds = BrokerCredentials("zhangle", "123456789")
        for patcher in (patch("core.brokers.device_operation", return_value=nullcontext()),
                        patch("core.brokers._adapter", return_value=({}, self.creds, self.client))):
            patcher.start(); self.addCleanup(patcher.stop)

    def submit(self, key="test-order-00000001", **kwargs):
        args = dict(account_id="account-a", side="buy", code="000981", quantity=100, price="2.13", request_id=key)
        args.update(kwargs)
        return brokers.submit_order(self.store, **args)

    def test_duplicate_request_does_not_repeat_click(self):
        def accepted(**kwargs):
            kwargs["before_confirm"]()
            return {"status": "accepted", "submitted": True}
        self.client.submit_order.side_effect = accepted
        first = self.submit()
        self.assertEqual(self.submit(), first)
        self.assertEqual(self.client.submit_order.call_count, 1)

    def test_same_request_with_changed_price_is_refused(self):
        self.client.submit_order.return_value = {"status": "rejected", "submitted": False}
        self.submit()
        with self.assertRaises(ValueError):
            self.submit(price="2.14")

    def test_disconnect_never_replays_same_request_but_independent_request_can_submit(self):
        def lost(**kwargs):
            kwargs["before_confirm"]()
            raise RuntimeError("读取结果时断连")
        self.client.submit_order.side_effect = lost
        result = self.submit()
        self.assertEqual(result["status"], "unknown")
        self.store.db.close()
        self.store = Store(self.path)
        self.addCleanup(self.store.db.close)
        self.assertEqual(self.submit(), result)
        self.client.submit_order.side_effect=lambda **kw: {"status":"accepted","submitted":True}
        self.assertEqual(self.submit("test-order-00000002")["status"],"accepted")
        self.assertEqual(self.submit(),result)
        self.assertEqual(self.client.submit_order.call_count, 2)

    def test_crash_before_final_result_never_automatically_replays(self):
        def crash(**kwargs):
            kwargs["before_confirm"]()
            raise SystemExit()
        self.client.submit_order.side_effect = crash
        with self.assertRaises(SystemExit):
            self.submit()
        self.assertEqual(self.submit()["status"], "unknown")
        self.assertEqual(self.client.submit_order.call_count, 1)

    def test_wrong_or_unverified_account_stops_before_submit(self):
        self.client.ensure_ready.return_value = {"account_verified": False}
        self.assertEqual(self.submit()["status"], "failed")
        self.client.submit_order.assert_not_called()

    def test_exception_before_dispatch_is_not_unknown(self):
        self.client.ensure_ready.side_effect = RuntimeError("账号不一致")
        self.assertEqual(self.submit()["status"], "failed")
        self.client.submit_order.assert_not_called()

    def test_manual_resolution_requires_evidence(self):
        self.client.submit_order.return_value = {"status": "unknown", "submitted": False}
        self.submit()
        with self.assertRaises(ValueError):
            brokers.resolve_request(self.store, "test-order-00000001", "accepted", "已经核对")
        brokers.resolve_request(self.store, "test-order-00000001", "not_sent", "券商今日委托和成交均已人工核对")
        self.assertEqual(brokers.requests(self.store, "account-a")[0]["status"], "not_sent")

    def test_real_cancel_rejected_before_device_adapter(self):
        with self.assertRaises(brokers.BrokerError):
            brokers.cancel(self.store, "account-a", dry_run=False)
        self.client.cancel.assert_not_called()

    def test_missing_request_id_rejected_before_device_adapter(self):
        with self.assertRaises(ValueError):
            self.submit(key=None)
        self.client.submit_order.assert_not_called()


    def test_maintenance_prevents_real_submit_but_allows_cancelled_rehearsal(self):
        self.client.ensure_ready.return_value={'account_verified':True,'maintenance':True}
        result=self.submit();self.assertEqual(result['status'],'failed');self.client.submit_order.assert_not_called()
        self.client.submit_order.return_value={'status':'preview','submitted':False}
        result=self.submit('test-maintenance-0002',dry_run=True)
        self.assertEqual(result['status'],'preview')
