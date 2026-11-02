"""券商账号：非敏感信息进 SQLite，密码存在本机凭据文件。

密码**不再写入系统钥匙串**，而是保存在数据目录下的 ``broker-secrets.json``，
文件权限 600（只有当前用户可读）。这样做是因为 App 每次重新构建后签名会变，
macOS 就会反复弹“monitor-core 想使用钥匙串”的授权框。

设置界面只会拿到 ``password_saved`` 布尔值，永远拿不到明文密码。旧版本写在
钥匙串里的密码仅在用户显式执行 migrate-secrets 时迁移。
"""
from __future__ import annotations

import json
import os
import re
import uuid
import tempfile
import sys
from functools import wraps
from pathlib import Path

from .provider import now_cn
from executor.adb import Adb
from executor.runtime import device_operation

SERVICE = "com.xreddot.stockmonitor.broker"
SECRETS_FILE = "broker-secrets.json"
_ACCOUNT = re.compile(r"[0-9]{4,20}")


def data_dir() -> Path:
    """Same directory the desktop app passes as ``STOCK_MONITOR_DATA``."""
    return Path(os.environ.get("STOCK_MONITOR_DATA", str(Path.home() / ".stock-monitor")))


class BrokerError(RuntimeError):
    """Raised when the credential store or the broker adapter fails."""


class LocalSecrets:
    """Password cache in ``<data>/broker-secrets.json`` with 0600 permissions."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else data_dir() / SECRETS_FILE

    @staticmethod
    def _key(broker: str, account: str, field: str) -> str:
        return f"{broker}|{account}|{field}"

    def _read(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".broker-secrets-", dir=self.path.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=1)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def get(self, broker: str, account: str, field: str) -> str | None:
        return self._read().get(self._key(broker, account, field))

    def set(self, broker: str, account: str, field: str, value: str) -> None:
        data = self._read()
        data[self._key(broker, account, field)] = value
        self._write(data)

    def delete(self, broker: str, account: str, field: str) -> None:
        data = self._read()
        if data.pop(self._key(broker, account, field), None) is not None:
            self._write(data)


class KeychainSecrets:
    """Legacy store, only used to migrate entries written by older builds."""

    @staticmethod
    def _key(broker: str) -> str:
        return f"{SERVICE}.{broker}"

    def get(self, broker: str, account: str, field: str) -> str | None:
        try:
            import keyring
            return keyring.get_password(self._key(broker), f"{account}:{field}")
        except Exception:
            return None

    def set(self, broker: str, account: str, field: str, value: str) -> None:
        import keyring
        keyring.set_password(self._key(broker), f"{account}:{field}", value)

    def delete(self, broker: str, account: str, field: str) -> None:
        try:
            import keyring
            keyring.delete_password(self._key(broker), f"{account}:{field}")
        except Exception:
            return


class _NoKeychain:
    """Default: never touch the system keychain, so macOS never prompts."""

    def get(self, broker: str, account: str, field: str) -> str | None:
        return None

    def set(self, broker: str, account: str, field: str, value: str) -> None:
        return None

    def delete(self, broker: str, account: str, field: str) -> None:
        return None


class SecretStore:
    """Local file only by default.

    Pass ``keychain=KeychainSecrets()`` explicitly for the one-off migration
    command; normal reads and writes never construct a keyring client.
    """

    def __init__(self, path: str | Path | None = None, keychain=None):
        self.local = LocalSecrets(path)
        self.keychain = keychain if keychain is not None else _NoKeychain()

    def get(self, broker: str, account: str, field: str) -> str | None:
        value = self.local.get(broker, account, field)
        if value is not None:
            return value
        legacy = self.keychain.get(broker, account, field)
        if legacy:
            self.local.set(broker, account, field, legacy)
            self.keychain.delete(broker, account, field)
        return legacy

    def set(self, broker: str, account: str, field: str, value: str) -> None:
        self.local.set(broker, account, field, value)
        # Drop any stale keychain copy so macOS stops asking for permission.
        self.keychain.delete(broker, account, field)

    def delete(self, broker: str, account: str, field: str) -> None:
        self.local.delete(broker, account, field)
        self.keychain.delete(broker, account, field)


def migrate_keychain(store) -> dict:
    """One-off: copy old keychain passwords into the local cache.

    Only called from the explicit ``migrate-secrets`` command, because reading
    the keychain is exactly what triggers the macOS permission dialog.
    """
    local = LocalSecrets()
    keychain = KeychainSecrets()
    migrated: list[str] = []
    for row in store.query("SELECT * FROM broker_accounts"):
        spec = _spec(row["broker"])
        for field in spec.fields:
            if not field.secret:
                continue
            value = keychain.get(row["broker"], row["account"], field.key)
            if value:
                local.set(row["broker"], row["account"], field.key, value)
                keychain.delete(row["broker"], row["account"], field.key)
                migrated.append(f"{row['broker']} {mask_account(row['account'])} {field.label}")
    return {"migrated": migrated, "count": len(migrated)}


def mask_account(account: str) -> str:
    if len(account) <= 4:
        return "****"
    return f"{account[:3]}***{account[-3:]}"


def _spec(broker: str):
    from executor.brokers import spec

    return spec(broker)


def specs() -> list[dict]:
    from executor.brokers import specs as _specs

    return [item.as_dict() for item in _specs()]


def list_accounts(store, secrets: SecretStore | None = None) -> list[dict]:
    secrets = secrets or SecretStore()
    rows = store.query("SELECT * FROM broker_accounts ORDER BY created_at, id")
    items = []
    for row in rows:
        spec = _spec(row["broker"])
        secret_fields = [f for f in spec.fields if f.secret]
        saved = all(
            secrets.get(row["broker"], row["account"], f.key) for f in secret_fields
        )
        items.append(
            {
                "id": row["id"],
                "broker": row["broker"],
                "broker_name": spec.name,
                "package": spec.package,
                "account": row["account"],
                "account_masked": mask_account(row["account"]),
                "label": row["label"] or "",
                "enabled": bool(row["enabled"]),
                "is_default": bool(row["is_default"]),
                "password_saved": saved,
                "supports_order": spec.supports_order,
                "supports_query": spec.supports_query,
                "supports_cancel": spec.supports_cancel,
                "supports_order_report": spec.supports_order_report and (spec.id=='ths' or sys.platform=='darwin'),
                "order_report_note": ('按原生合同编号自动核对当日成交；跨日及尚无成交时继续保留待核实' if spec.id=='ths' else '按唯一合同编号自动核实；仅查询已有委托' if spec.supports_order_report and sys.platform=='darwin' else
                                      '当前查询页未提供可核验的唯一委托编号，须人工核实' if not spec.supports_order_report else '当前系统的回报识别器尚未验证，须人工核实'),
            }
        )
    return items


def save_account(
    store,
    broker: str,
    account: str,
    values: dict[str, str] | None = None,
    label: str = "",
    secrets: SecretStore | None = None,
) -> dict:
    secrets = secrets or SecretStore()
    spec = _spec(broker)
    account = (account or "").strip()
    if not _ACCOUNT.fullmatch(account):
        raise ValueError("账号必须是 4—20 位数字")

    values = values or {}
    for field in spec.fields:
        if not field.secret:
            continue
        value = (values.get(field.key) or "").strip()
        if value:
            secrets.set(broker, account, field.key, value)

    existing = store.query(
        "SELECT id FROM broker_accounts WHERE broker=? AND account=?", (broker, account)
    )
    if existing:
        ident = existing[0]["id"]
        store.execute(
            "UPDATE broker_accounts SET label=?, enabled=1 WHERE id=?", (label, ident)
        )
    else:
        ident = uuid.uuid4().hex
        store.execute(
            "INSERT INTO broker_accounts(id,broker,account,label,enabled,is_default,created_at)"
            " VALUES(?,?,?,?,1,0,?)",
            (ident, broker, account, label, now_cn().isoformat()),
        )
    return next(item for item in list_accounts(store, secrets) if item["id"] == ident)


def delete_account(store, account_id: str, secrets: SecretStore | None = None) -> dict:
    secrets = secrets or SecretStore()
    rows = store.query("SELECT * FROM broker_accounts WHERE id=?", (account_id,))
    if not rows:
        raise ValueError("账号不存在")
    if store.query("SELECT request_id FROM broker_requests WHERE account_id=? AND status IN ('prepared','sending','unknown','accepted','partial')", (account_id,)):
        raise ValueError("账号有待核实委托，处理执行记录后才能删除")
    if store.query("SELECT name FROM sqlite_master WHERE type='table' AND name='trading_runs'") and store.query("SELECT id FROM trading_runs WHERE account_id=? AND status IN ('pending','processing','sending','accepted','unknown','partial')",(account_id,)):
        raise ValueError('账号有自动执行任务或未核实委托，请先暂停并处理执行记录后再删除')
    row = rows[0]
    spec = _spec(row["broker"])
    for field in spec.fields:
        if field.secret:
            secrets.delete(row["broker"], row["account"], field.key)
    store.execute("DELETE FROM broker_accounts WHERE id=?", (account_id,))
    return {"deleted": True, "id": account_id}


def credentials(store, account_id: str, secrets: SecretStore | None = None):
    from executor.brokers import BrokerCredentials

    secrets = secrets or SecretStore()
    rows = store.query("SELECT * FROM broker_accounts WHERE id=?", (account_id,))
    if not rows:
        raise ValueError("账号不存在，请先在设置里添加")
    row = rows[0]
    spec = _spec(row["broker"])
    values = {"account": row["account"]}
    if not row["enabled"]:
        raise ValueError("该券商账号已停用")
    for field in spec.fields:
        if field.secret:
            value = secrets.get(row["broker"], row["account"], field.key)
            if not value:
                raise ValueError(f"账号 {mask_account(row['account'])} 还没保存{field.label}")
            values[field.key] = value
    return row, BrokerCredentials(broker=row["broker"], account=row["account"], secrets=values)


def _adapter(store, account_id: str, secrets: SecretStore | None = None):
    from executor.brokers import adapter

    row, creds = credentials(store, account_id, secrets)
    return row, creds, adapter(row["broker"])


def _device_operation(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with device_operation(Adb()):
            return fn(*args, **kwargs)
    return wrapped


def _verify_account(client, creds, store=None):
    """资金账号与股东账号不同，必须核对交易主页的客户号，不能互相代替。"""
    result = client.ensure_ready(creds)
    if result.get("account_verified") is not True:
        raise BrokerError("当前交易账号无法核验，请在券商 App 中确认所选账号后再操作")
    if store is not None and result.get("account_display"):
        from executor.identity import account_matches
        if not account_matches(result['account_display'], creds.account):
            raise BrokerError('券商当前账户与所选账户不一致，已停止')
        matches = [r for r in store.query("SELECT account FROM broker_accounts WHERE broker=?", (creds.broker,)) if account_matches(result["account_display"], r["account"])]
        if len(matches) != 1:
            raise BrokerError("页面账号掩码对应多个本地账号，无法唯一核验，已停止")
    if store is not None:
        rows=store.query('SELECT id FROM broker_accounts WHERE broker=? AND account=?',(creds.broker,creds.account))
        if len(rows)==1:
            key='broker_maintenance:'+rows[0]['id'];today=now_cn().date().isoformat()
            if result.get('maintenance') is True:store.setconfig(key,today)
            elif result.get('authenticated_now') is True:store.setconfig(key,'')
            if store.config().get(key)==today:result=dict(result,maintenance=True)
    return result


@_device_operation
def login(store, account_id: str, secrets: SecretStore | None = None) -> dict:
    _, creds, client = _adapter(store, account_id, secrets)
    return client.login(creds)


@_device_operation
def ensure_ready(store, account_id: str, secrets: SecretStore | None = None) -> dict:
    _, creds, client = _adapter(store, account_id, secrets)
    return client.ensure_ready(creds)


@_device_operation
def preview_order(
    store,
    account_id: str,
    side: str,
    code: str,
    quantity: int,
    price: str | None = None,
    secrets: SecretStore | None = None,
) -> dict:
    _, creds, client = _adapter(store, account_id, secrets)
    _verify_account(client, creds, store)
    return client.preview_order(side=side, code=code, quantity=quantity, price=price)


@_device_operation
def submit_order(
    store,
    account_id: str,
    side: str,
    code: str,
    quantity: int,
    price: str | None = None,
    max_value: float | None = 1000.0,
    dry_run: bool = False,
    secrets: SecretStore | None = None,
    request_id: str | None = None,
    authorize=None,
) -> dict:
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", request_id):
        raise ValueError("委托缺少有效请求号，不能提交")
    payload = json.dumps(dict(account_id=account_id, side=side, code=code, quantity=quantity,
                              price=price, max_value=max_value, dry_run=dry_run), sort_keys=True)
    stamp = now_cn().isoformat()
    # 用事务占用请求号。重复请求只读旧结果，未知结果跨重启保留，不自动再点一次。
    with store.lock, store.db:
        store.db.execute("BEGIN IMMEDIATE")
        old = store.db.execute("SELECT * FROM broker_requests WHERE request_id=?", (request_id,)).fetchone()
        if old:
            if old["payload"] != payload:
                raise ValueError("同一请求号不能修改委托参数")
            return json.loads(old["result"]) if old["result"] else {"request_id": request_id, "submitted": False, "status": "unknown", "message": "该请求已登记，需先核对券商委托，不会重复提交"}
        unresolved = store.db.execute("SELECT request_id FROM broker_requests WHERE account_id=? AND status IN ('prepared','sending','unknown')", (account_id,)).fetchone()
        if unresolved:
            raise BrokerError("此账号有未核实的委托，请先核对并处理执行记录：" + unresolved[0])
        store.db.execute("INSERT INTO broker_requests VALUES(?,?,?,'prepared',NULL,?,?)", (request_id, account_id, payload, stamp, stamp))
    dispatched = False
    def before_confirm():
        nonlocal dispatched
        if authorize is not None:
            authorize()
        with store.lock,store.db:
            stamp=now_cn().isoformat()
            if request_id.startswith('auto_'):
                changed=store.db.execute("UPDATE trading_runs SET status='sending',updated_at=? WHERE id=? AND account_id=? AND status IN ('processing','sending')",(stamp,request_id[5:],account_id)).rowcount
                if changed!=1:raise BrokerError('自动执行记录已改变，已阻止提交')
            store.db.execute("UPDATE broker_requests SET status='sending',updated_at=? WHERE request_id=?", (stamp, request_id))
        dispatched = True
    try:
        _, creds, client = _adapter(store, account_id, secrets)
        if not client.spec.supports_order:
            raise BrokerError("该券商暂不支持真实委托")
        ready=_verify_account(client, creds, store)
        if ready.get('maintenance') is True and not dry_run:raise BrokerError('券商正在清算维护，数据可能不准确，本次不发送委托')
        result = client.submit_order(side=side, code=code, quantity=quantity, price=price,
                                     max_value=max_value, dry_run=dry_run, before_confirm=before_confirm)
        if result.get("status") not in ("accepted", "rejected", "preview", "unknown"):
            result = {"submitted": False, "status": "unknown", "message": "券商返回结果无法确认"}
    except Exception as exc:
        result = {"submitted": False, "status": "unknown" if dispatched else "failed",
                  "message": "提交结果未知，请核对券商委托，禁止直接重试" if dispatched else str(exc)}
    result["request_id"] = request_id
    store.execute("UPDATE broker_requests SET status=?,result=?,updated_at=? WHERE request_id=?",
                  (result["status"], json.dumps(result, ensure_ascii=False), now_cn().isoformat(), request_id))
    return result


def requests(store, account_id):
    from .broker_reconciliation import known_id
    items=[]
    for row in store.query("SELECT * FROM broker_requests WHERE account_id=? ORDER BY created_at DESC LIMIT 20",(account_id,)):
        result=json.loads(row['result'] or '{}')
        try:ident=known_id(result)
        except ValueError:ident=''
        items.append(dict(request_id=row['request_id'],status=row['status'],created_at=row['created_at'],updated_at=row['updated_at'],
                          order_id=ident,verification=result.get('verification'),reconciliation=result.get('reconciliation')))
    return items


@_device_operation
def resolve_request(store, request_id, outcome, note, order_id=""):
    """只能人工核对后处理未知请求；列表中没看到订单不能自动推断未提交。"""
    if outcome not in ("accepted", "not_sent") or not isinstance(note, str) or len(note.strip()) < 4:
        raise ValueError("请填写核实结论和具体依据")
    if outcome == "accepted" and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", order_id or ""):
        raise ValueError("已受理的委托必须填写券商委托号")
    result = dict(request_id=request_id, status=outcome, submitted=outcome=="accepted", order_id=order_id, manual_note=note.strip())
    changed = store.execute("UPDATE broker_requests SET status=?,result=?,updated_at=? WHERE request_id=? AND status IN ('prepared','sending','unknown')",
                            (outcome, json.dumps(result, ensure_ascii=False), now_cn().isoformat(), request_id))
    if not changed:
        raise ValueError("该请求不存在或已经处理")
    return result


@_device_operation
def orders(store, account_id: str, kind: str = "today", secrets: SecretStore | None = None) -> dict:
    _, creds, client = _adapter(store, account_id, secrets)
    _verify_account(client, creds, store)
    result=client.orders(kind)
    _verify_account(client,creds,store)
    return dict(result,account_id=account_id,account_verified=True,observed_at=now_cn().isoformat())


@_device_operation
def trades(store, account_id: str, kind: str = "today", secrets: SecretStore | None = None) -> dict:
    _, creds, client = _adapter(store, account_id, secrets)
    _verify_account(client, creds, store)
    result=client.trades(kind)
    _verify_account(client,creds,store)
    return dict(result,account_id=account_id,account_verified=True,observed_at=now_cn().isoformat())


@_device_operation
def order_report(store,account_id,order_id,day,expected,secrets=None):
    _,creds,client=_adapter(store,account_id,secrets)
    _verify_account(client,creds,store)
    result=client.order_report(order_id,day,expected)
    _verify_account(client,creds,store)
    return dict(result,account_id=account_id,account_verified=True,observed_at=now_cn().isoformat())


@_device_operation
def snapshot(store, account_id: str, secrets: SecretStore | None = None) -> dict:
    _, creds, client = _adapter(store, account_id, secrets)
    _verify_account(client, creds, store)
    result=client.account()
    _verify_account(client,creds,store)
    return dict(result,account_id=account_id,account_verified=True,observed_at=now_cn().isoformat())


@_device_operation
def holdings(store, account_id: str, secrets: SecretStore | None = None,target_code=None) -> dict:
    _, creds, client = _adapter(store, account_id, secrets)
    before=_verify_account(client, creds, store)
    known={}
    if store.query("SELECT name FROM sqlite_master WHERE type='table' AND name='trading_positions'"):
        candidates={}
        for row in store.query('SELECT name,code FROM trading_positions WHERE account_id=?',(account_id,)):
            candidates.setdefault(row['name'],set()).add(row['code'])
        for row in store.query('SELECT name,code FROM trading_mappings WHERE account_id=?',(account_id,)):
            candidates.setdefault(row['name'],set()).add(row['code'])
        known={name:next(iter(codes))[2:] for name,codes in candidates.items() if len(codes)==1}
    kwargs=dict(account=creds.account,known_codes=known)
    if target_code:kwargs['target_code']=target_code
    result = client.holdings(**kwargs)
    # Reading and swiping must not silently cross into another account/session.
    after=_verify_account(client, creds, store)
    if before.get('maintenance') is True or after.get('maintenance') is True:
        result.update(complete=False,position_only=False,warning='券商正在清算维护，持仓仅供查看，待维护结束后重新同步')
    return dict(result, account_id=account_id, account_verified=True, observed_at=now_cn().isoformat())


@_device_operation
def cancel(
    store,
    account_id: str,
    scope: str = "all",
    code: str | None = None,
    side: str | None = None,
    dry_run: bool = True,
    secrets: SecretStore | None = None,
) -> dict:
    if not dry_run:
        raise BrokerError("当前未验证按唯一委托号撤单，请在券商 App 中撤单")
    _, creds, client = _adapter(store, account_id, secrets)
    _verify_account(client, creds, store)
    return client.cancel(scope=scope, code=code, side=side, dry_run=dry_run)
