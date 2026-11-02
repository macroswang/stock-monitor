import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from core import brokers
from core.store import Store


class FakeSecrets:
    def __init__(self):
        self.data = {}

    def get(self, broker, account, field):
        return self.data.get((broker, account, field))

    def set(self, broker, account, field, value):
        self.data[(broker, account, field)] = value

    def delete(self, broker, account, field):
        self.data.pop((broker, account, field), None)


class BrokerAccountTests(unittest.TestCase):
    def setUp(self):
        guard = patch("core.brokers.device_operation", side_effect=lambda *_a, **_k: nullcontext())
        guard.start(); self.addCleanup(guard.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "monitor.sqlite3")
        self.secrets = FakeSecrets()

    def test_registry_exposes_zhangle(self):
        ids = {item["id"] for item in brokers.specs()}
        self.assertIn("zhangle", ids)

    def test_registry_exposes_tonghuashun(self):
        specs = {item["id"]: item for item in brokers.specs()}
        self.assertIn("ths", specs)
        ths = specs["ths"]
        self.assertEqual(ths["name"], "同花顺（银河证券）")
        self.assertTrue(ths["supports_order"], "已核验原生表单及确认弹窗，真实入口仍受确认设置和持久化请求约束")
        self.assertTrue(ths["supports_query"], "委托/成交/资金持仓已实测")
        self.assertFalse(ths["supports_cancel"], "撤单按钮尚未实测")
        self.assertEqual([f["key"] for f in ths["fields"]], ["account", "password"])

    def test_save_account_stores_password_in_keychain(self):
        item = brokers.save_account(
            self.store,
            "zhangle",
            "666621833623",
            {"password": "123456"},
            "主账号",
            self.secrets,
        )
        self.assertTrue(item["password_saved"])
        self.assertEqual(item["account_masked"], "666***623")
        self.assertEqual(
            self.secrets.data[("zhangle", "666621833623", "password")], "123456"
        )
        stored = self.store.query("SELECT * FROM broker_accounts")
        self.assertEqual(len(stored), 1)
        self.assertNotIn("123456", str(stored))

    def test_save_without_password_keeps_existing_secret(self):
        brokers.save_account(
            self.store, "zhangle", "666621833623", {"password": "123456"}, "", self.secrets
        )
        item = brokers.save_account(
            self.store, "zhangle", "666621833623", {}, "改名", self.secrets
        )
        self.assertTrue(item["password_saved"])
        self.assertEqual(item["label"], "改名")
        self.assertEqual(len(self.store.query("SELECT * FROM broker_accounts")), 1)

    def test_account_must_be_numeric(self):
        with self.assertRaises(ValueError):
            brokers.save_account(self.store, "zhangle", "abc", {}, "", self.secrets)

    def test_unknown_broker_rejected(self):
        with self.assertRaises(ValueError):
            brokers.save_account(self.store, "yinhe", "12345678", {}, "", self.secrets)

    def test_delete_removes_row_and_secret(self):
        item = brokers.save_account(
            self.store, "zhangle", "666621833623", {"password": "123456"}, "", self.secrets
        )
        brokers.delete_account(self.store, item["id"], self.secrets)
        self.assertEqual(self.store.query("SELECT * FROM broker_accounts"), [])
        self.assertEqual(self.secrets.data, {})

    def test_credentials_requires_saved_password(self):
        item = brokers.save_account(
            self.store, "zhangle", "666621833623", {}, "", self.secrets
        )
        with self.assertRaises(ValueError):
            brokers.credentials(self.store, item["id"], self.secrets)

    def test_login_dispatches_to_adapter(self):
        item = brokers.save_account(
            self.store, "zhangle", "666621833623", {"password": "123456"}, "", self.secrets
        )
        calls = {}

        class FakeAdapter:
            def login(self, credentials):
                calls["account"] = credentials.account
                calls["password"] = credentials.get("password")
                return {"logged_in": True}

        with patch("executor.brokers.adapter", return_value=FakeAdapter()):
            result = brokers.login(self.store, item["id"], self.secrets)
        self.assertEqual(result, {"logged_in": True})
        self.assertEqual(calls, {"account": "666621833623", "password": "123456"})

    def test_submit_requires_confirmation_at_app_layer(self):
        from core.app import App

        app = App(self.tmp.name, start_worker=False)
        app.store.execute("DELETE FROM watch")
        with self.assertRaises(ValueError):
            app.call("broker_submit", {"id": "x", "side": "sell", "code": "000981", "quantity": 100})


if __name__ == "__main__":
    unittest.main()


class _FakeKeychain:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.deleted = []

    def get(self, broker, account, field):
        return self.data.get((broker, account, field))

    def set(self, broker, account, field, value):
        self.data[(broker, account, field)] = value

    def delete(self, broker, account, field):
        self.deleted.append((broker, account, field))
        self.data.pop((broker, account, field), None)


class LocalSecretTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "broker-secrets.json"

    def test_round_trip_and_file_permissions(self):
        store = brokers.LocalSecrets(self.path)
        store.set("ths", "400401000162", "password", "123456")

        self.assertEqual(store.get("ths", "400401000162", "password"), "123456")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

        store.delete("ths", "400401000162", "password")
        self.assertIsNone(store.get("ths", "400401000162", "password"))

    def test_secret_store_never_reads_keychain_when_cached(self):
        brokers.LocalSecrets(self.path).set("ths", "1", "password", "cached")

        class Boom(_FakeKeychain):
            def get(self, *args):
                raise AssertionError("本地已有缓存时不应该读钥匙串")

        store = brokers.SecretStore(self.path, Boom())
        self.assertEqual(store.get("ths", "1", "password"), "cached")

    def test_migrates_legacy_keychain_entry_once(self):
        keychain = _FakeKeychain({("ths", "1", "password"): "legacy"})
        store = brokers.SecretStore(self.path, keychain)

        self.assertEqual(store.get("ths", "1", "password"), "legacy")
        self.assertIn(("ths", "1", "password"), keychain.deleted)
        self.assertEqual(brokers.LocalSecrets(self.path).get("ths", "1", "password"), "legacy")
        self.assertEqual(store.get("ths", "1", "password"), "legacy")

    def test_saving_drops_stale_keychain_copy(self):
        keychain = _FakeKeychain({("ths", "1", "password"): "old"})
        brokers.SecretStore(self.path, keychain).set("ths", "1", "password", "new")

        self.assertEqual(keychain.data, {})
        self.assertEqual(brokers.LocalSecrets(self.path).get("ths", "1", "password"), "new")

    def test_default_store_does_not_touch_keychain_at_all(self):
        store = brokers.SecretStore(self.path)

        self.assertIsInstance(store.keychain, brokers._NoKeychain)
        self.assertIsNone(store.get("ths", "1", "password"))
