"""同花顺（银河证券）适配器。

同花顺是聚合平台，App 账号与券商账号分开；这里只接券商交易模块。资金账号
必须在同花顺里事先添加好，本适配器只校验尾号并提交交易密码。

交易页的买入/卖出表单尚未实测，因此 ``supports_order`` 暂为 ``False``；
委托/成交/持仓/资金已经实测，``supports_query`` 为 ``True``。
"""
from __future__ import annotations

from .base import BrokerAdapter, BrokerCredentials, BrokerSpec, CredentialField
from ..ths import PACKAGE, ThsTrade
from ..ths_trade import ThsQuery

SPEC = BrokerSpec(
    id="ths",
    name="同花顺（银河证券）",
    package="com.hexin.plat.android",
    fields=(
        CredentialField("account", "银河资金账号", secret=False),
        CredentialField("password", "交易密码"),
    ),
    note="需先在同花顺里添加并选中银河证券账户；这里只提交交易密码，不会新增账户，资金账号仅用于核对尾号。",
    supports_order=False,
    supports_query=True,
)


class ThsAdapter(BrokerAdapter):
    spec = SPEC

    def _client(self) -> ThsTrade:
        return ThsTrade(self.adb)

    def status(self) -> dict:
        return self._client().status().as_dict()

    def login(self, credentials: BrokerCredentials) -> dict:
        return self.ensure_ready(credentials)

    def ensure_ready(self, credentials: BrokerCredentials) -> dict:
        # 同花顺没有「App 登录」和「交易登录」两层：交易模块登录就是唯一入口。
        return self._client().ensure_logged_in(
            account=credentials.account,
            password=credentials.get("password"),
        )

    # ----- 查询 ------------------------------------------------------------
    def orders(self, kind: str = "today") -> dict:
        if kind not in ("today", "history"):
            raise ValueError("kind 只能是 today 或 history")
        key = "today_orders" if kind == "today" else "history_orders"
        return ThsQuery(self.adb).query(key)

    def trades(self, kind: str = "today") -> dict:
        if kind not in ("today", "history"):
            raise ValueError("kind 只能是 today 或 history")
        key = "today_trades" if kind == "today" else "history_trades"
        return ThsQuery(self.adb).query(key)

    def account(self) -> dict:
        return ThsQuery(self.adb).account()

    # ----- 撤单 ------------------------------------------------------------
    def cancel(
        self,
        scope: str = "all",
        code: str | None = None,
        side: str | None = None,
        dry_run: bool = True,
    ) -> dict:
        raise ValueError("同花顺撤单按钮尚未实测，暂时请在同花顺 App 内撤单")
