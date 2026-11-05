"""同花顺（银河证券）适配器。

同花顺是聚合平台，App 账号与券商账号分开；这里只接券商交易模块。资金账号
必须在同花顺里事先添加好，本适配器只校验尾号并提交交易密码。

买卖预填及两种二次确认弹窗已实机核验并取消，未发送真实委托。
真实入口仍必须核验二次确认设置，经过持久化请求和最后授权检查。
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
    note="需先在同花顺选中银河账户。买卖预填及确认弹窗已验证；免二次确认开启时拒绝下单，结果未知时停止重试。",
    supports_order=True,
    supports_query=True,
    supports_order_report=True,
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
        result=self._client().ensure_logged_in(
            account=credentials.account,
            password=credentials.get("password"),
        )
        self._verified_account=credentials.account if result.get('account_verified') is True else None
        return result

    def preview_order(self,side,code,quantity,price=None):
        from ..ths_order import ThsOrderPage
        return dict(ThsOrderPage(self.adb,getattr(self,'_verified_account',None)).preview(side,code,quantity,price).as_dict(),submitted=False)

    def submit_order(self,side,code,quantity,price=None,max_value=1000,dry_run=False,before_confirm=None):
        from ..ths_order import ThsOrderPage
        if not getattr(self,'_verified_account',None):raise ValueError('尚未核验同花顺资金账户，禁止委托')
        return ThsOrderPage(self.adb,self._verified_account).submit(side,code,quantity,price,max_value,dry_run,before_confirm)

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

    def order_report(self,order_id,day,expected):
        from ..ths_report import report
        from core.provider import now_cn
        return report(self.adb,getattr(self,'_verified_account',None),order_id,day,expected,now_cn())

    def discover_order_report(self,day,expected,submitted_at):
        from ..ths_report import discover
        from core.provider import now_cn
        return discover(self.adb,getattr(self,'_verified_account',None),day,expected,submitted_at,now_cn())

    def holdings(self, account: str | None = None, known_codes: dict | None = None,target_code=None) -> dict:
        from ..holdings import collect
        from ..ths_trade import POSITION_LIST_ID, parse_positions, parse_funds
        query = ThsQuery(self.adb)
        nodes = query.open_home()
        funds = parse_funds(nodes)
        nodes = query._tap_text(nodes,'持仓')
        funds.update(parse_funds(nodes))
        def verify(current):
            from ..ths import read_status, ThsError
            from ..identity import account_matches
            status=read_status(current,self.adb.current_focus())
            if not account_matches(status.account_masked,account) or '银河' not in status.broker_name:
                raise ThsError('持仓读取期间券商或账户发生变化，已停止同步')
        from ..security_code import ths_code
        def resolver(row,ns):
            code=(known_codes or {}).get(row['name'])
            return dict(row,code=code,code_source='account_verified_cache') if code else ths_code(self.adb,row,ns,verify)
        names=[name for name,code in (known_codes or {}).items() if target_code and code[-6:]==target_code[-6:]]
        return collect(self.adb,nodes,POSITION_LIST_ID,parse_positions,funds,verify=verify if account else None,resolve=resolver if account else None,target_code=target_code,target_name=names[0] if len(names)==1 else None)

    # ----- 撤单 ------------------------------------------------------------
    def cancel(
        self,
        scope: str = "all",
        code: str | None = None,
        side: str | None = None,
        dry_run: bool = True,
    ) -> dict:
        raise ValueError("同花顺撤单按钮尚未实测，暂时请在同花顺 App 内撤单")
