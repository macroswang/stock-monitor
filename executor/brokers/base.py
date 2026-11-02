"""券商适配器的统一接口。

每个券商 App 的包名、登录页、交易页、确认弹窗都不同，因此一家一个适配器，
上层（设置界面 / 服务层）只依赖这里的接口。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..adb import Adb


@dataclass(frozen=True)
class CredentialField:
    key: str
    label: str
    secret: bool = True


@dataclass(frozen=True)
class BrokerSpec:
    id: str
    name: str
    package: str
    fields: tuple[CredentialField, ...]
    note: str = ""
    supports_order: bool = False
    supports_query: bool = False
    supports_cancel: bool = False
    supports_order_report: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "package": self.package,
            "fields": [
                {"key": f.key, "label": f.label, "secret": f.secret} for f in self.fields
            ],
            "note": self.note,
            "supports_order": self.supports_order,
            "supports_query": self.supports_query,
            "supports_cancel": self.supports_cancel,
            "supports_order_report": self.supports_order_report,
        }


@dataclass
class BrokerCredentials:
    """A broker account plus the credentials needed to log in."""

    broker: str
    account: str
    secrets: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        return self.secrets.get(key)


class BrokerAdapter:
    """Base class: every method is a single, well-scoped device operation."""

    spec: BrokerSpec

    def __init__(self, adb: Adb | None = None):
        self.adb = adb or Adb()

    def status(self) -> dict:
        raise NotImplementedError

    def login(self, credentials: BrokerCredentials) -> dict:
        raise NotImplementedError

    def ensure_ready(self, credentials: BrokerCredentials) -> dict:
        raise NotImplementedError

    def orders(self, kind: str = "today") -> dict:
        """``kind`` is today / history; returns 委托列表。"""
        raise NotImplementedError("该券商尚未实现委托查询")

    def trades(self, kind: str = "today") -> dict:
        """``kind`` is today / history; returns 成交列表。"""
        raise NotImplementedError("该券商尚未实现成交查询")

    def order_report(self,order_id,day,expected):
        raise ValueError('该券商当前查询页没有可核验的委托编号，保留待核实状态')

    def account(self) -> dict:
        """资金与持仓快照，用于对账。"""
        raise NotImplementedError("该券商尚未实现资金持仓查询")

    def holdings(self, account: str | None = None, known_codes: dict | None = None) -> dict:
        raise NotImplementedError('该券商尚未实现完整持仓同步')

    def cancel(
        self,
        scope: str = "all",
        code: str | None = None,
        side: str | None = None,
        dry_run: bool = True,
    ) -> dict:
        raise NotImplementedError("该券商尚未实现撤单")

    def preview_order(
        self,
        side: str,
        code: str,
        quantity: int,
        price: str | None = None,
    ) -> dict:
        raise NotImplementedError("该券商尚未实现下单预览")

    def submit_order(
        self,
        side: str,
        code: str,
        quantity: int,
        price: str | None = None,
        max_value: float | None = 1000.0,
        dry_run: bool = False,
        before_confirm=None,
    ) -> dict:
        raise NotImplementedError("该券商尚未实现下单")
