"""华泰涨乐通适配器：包装现有的 zhangle / trade / orderbook / cancel 页面对象。"""
from __future__ import annotations

from .base import BrokerAdapter, BrokerCredentials, BrokerSpec, CredentialField
from ..cancel import CancelPage, plan_cancel
from ..orderbook import OrderBook
from ..trade import TradePage
from ..zhangle import PACKAGE, Zhangle

SPEC = BrokerSpec(
    id="zhangle",
    name="华泰涨乐通",
    package="com.lphtsccft",
    fields=(
        CredentialField("account", "客户号", secret=False),
        CredentialField("password", "交易密码"),
    ),
    note="交易页需要单独登录一次；下单会被逐项校验后才确认。",
    supports_order=True,
    supports_query=True,
    supports_cancel=False,
)


class ZhangleAdapter(BrokerAdapter):
    spec = SPEC

    def _client(self) -> Zhangle:
        return Zhangle(self.adb)

    def status(self) -> dict:
        return self._client().status().as_dict()

    def login(self, credentials: BrokerCredentials) -> dict:
        """Log in and leave the app on the trade page.

        The app session and the trade module are separate logins in 涨乐通, so
        a login that stops at the home page is not enough for the user.
        """
        return self.ensure_ready(credentials)

    def ensure_ready(self, credentials: BrokerCredentials) -> dict:
        return self._client().ensure_trade_ready(
            account=credentials.account, password=credentials.get("password")
        )

    def preview_order(
        self,
        side: str,
        code: str,
        quantity: int,
        price: str | None = None,
    ) -> dict:
        page = TradePage(self.adb)
        form = page.preview(side=side, code=code, quantity=quantity, price=price)
        return {"submitted": False, **form.as_dict()}

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
        page = TradePage(self.adb)
        return page.submit(
            side=side,
            code=code,
            quantity=quantity,
            price=price,
            max_value=max_value,
            dry_run=dry_run,
            before_confirm=before_confirm,
        )

    # ----- 查询 ------------------------------------------------------------
    def orders(self, kind: str = "today") -> dict:
        book = OrderBook(self.adb)
        if kind == "history":
            return book.history_orders().as_dict()
        if kind != "today":
            raise ValueError("kind 只能是 today 或 history")
        return book.today_orders().as_dict()

    def trades(self, kind: str = "today") -> dict:
        book = OrderBook(self.adb)
        if kind == "history":
            return book.history_trades().as_dict()
        if kind != "today":
            raise ValueError("kind 只能是 today 或 history")
        return book.today_trades().as_dict()

    def account(self) -> dict:
        return OrderBook(self.adb).account()

    # ----- 撤单 ------------------------------------------------------------
    def cancel(
        self,
        scope: str = "all",
        code: str | None = None,
        side: str | None = None,
        dry_run: bool = True,
    ) -> dict:
        plan = plan_cancel(
            OrderBook(self.adb).today_orders().rows, scope=scope, code=code, side=side
        )
        # ``CancelPage`` refuses a plan that would hit other orders, so a
        # single-stock request never silently cancels something else.
        return CancelPage(self.adb).cancel(plan, dry_run=dry_run)
