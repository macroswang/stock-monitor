"""华泰涨乐通适配器：包装现有的 zhangle / trade / orderbook / cancel 页面对象。"""
from __future__ import annotations
from datetime import date

from .base import BrokerAdapter, BrokerCredentials, BrokerSpec, CredentialField
from ..cancel import CancelPage, plan_cancel
from ..orderbook import OrderBook
from ..trade import TradePage
from ..zhangle import PACKAGE, Zhangle
_maintenance_sessions={}

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
    supports_order_report=True,
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
        client=self._client()
        result=client.ensure_trade_ready(
            account=credentials.account, password=credentials.get("password")
        )
        key=(self.adb.serial,credentials.account)
        if result.get('maintenance') is True:_maintenance_sessions[key]=date.today()
        elif result.get('authenticated_now') is True:_maintenance_sessions.pop(key,None)
        result['maintenance']=_maintenance_sessions.get(key)==date.today()
        self._verified_account=credentials.account if result.get('account_verified') is True else None
        return result

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

    def order_report(self,order_id,day,expected):
        from ..order_report import zhangle_report
        from core.provider import now_cn
        return zhangle_report(self.adb,getattr(self,'_verified_account',None),order_id,day,expected,now_cn())

    def filled_orders(self,day):
        from ..order_report import zhangle_filled_orders
        from core.provider import now_cn
        return zhangle_filled_orders(self.adb,getattr(self,'_verified_account',None),day,now_cn())

    def account(self) -> dict:
        return OrderBook(self.adb).account()

    def holdings(self, account: str | None = None, known_codes: dict | None = None,target_code=None) -> dict:
        from ..holdings import collect
        from ..orderbook import POSITION_RECYCLER_ID, parse_positions, parse_funds
        nodes = OrderBook(self.adb).open_holdings()
        verify=(lambda ns: Zhangle.verify_trade_account(ns,account)) if account else None
        from ..security_code import zhangle_code
        def resolve(row,ns):
            code=(known_codes or {}).get(row['name'])
            return dict(row,code=code,code_source='account_verified_cache') if code else zhangle_code(self.adb,row,ns,verify)
        names=[name for name,code in (known_codes or {}).items() if target_code and code[-6:]==target_code[-6:]]
        return collect(self.adb,nodes,POSITION_RECYCLER_ID,lambda ns,_bounds: parse_positions(ns),parse_funds(nodes),verify=verify,resolve=resolve if verify else None,target_code=target_code,target_name=names[0] if len(names)==1 else None)

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
