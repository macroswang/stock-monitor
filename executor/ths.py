"""同花顺 App 里的「银河证券」交易模块。

同花顺是聚合平台：App 账号（手机号）和券商账号是两套东西。这里只处理
**券商交易模块**——用户已经在同花顺里添加过银河证券账户，本模块只负责选中
该账户、输入交易密码、确认登录结果。

已实测的页面结构（Android 11.64.07，1080×1920 @ 320dpi）::

    底部导航 tab_widget
      RelativeLayout content-desc="交易"     ← 用 content-desc 定位，不用坐标

    交易页（未登录）
      nobindlist / frontview
        txt_qsname          中国银河证券
        txt_account         客户号
        txt_account_value   4004****0162
      btn_add               添加账户
      btn_manage            账户管理

    登录面板（底部抽屉）
      login_component_base_view
        close_button
        qs_name             中国银河证券
        account             **0162
        weituo_edit_trade_password   交易密码（唯一输入框）
        weituo_btn_login    登录（密码为空时按钮是禁用/浅色的）

重要：本模块**不会**在 App 里新增账户。资金账号必须事先在同花顺里添加好；
我们只校验当前选中的账户尾号与本地记录一致，再提交密码，避免把 A 券商的
密码发到 B 券商的登录框里。

原生买卖表单与二次确认在 ``ths_order`` 中实现；正式提交必须经过观量的持久化请求入口。
自动撤单仍未开放。
"""
from __future__ import annotations

import time
import re
from dataclasses import dataclass

from .adb import Adb, AdbError, Node, find_by_id, find_by_text, wait_until
from .identity import account_matches

PACKAGE = "com.hexin.plat.android"
TRADE_TAB_DESC = "交易"

TRADE_PAGE_ID = "nobindlist"
ACCOUNT_VALUE_ID = "txt_account_value"
QS_NAME_ID = "txt_qsname"
ADD_ACCOUNT_ID = "btn_add"

PANEL_ID = "login_component_base_view"
PANEL_QS_ID = "qs_name"
PANEL_ACCOUNT_ID = "account"
PASSWORD_ID = "weituo_edit_trade_password"
LOGIN_BUTTON_ID = "weituo_btn_login"
CLOSE_ID = "close_button"
ACCOUNT_CARD_ID = "frontview_account_info"
ACCOUNT_CARD_FALLBACK_ID = "nobindlist"
LOGGED_IN_ID = "capital_value_text"
BUY_MENU_ID = "menu_buy"

PASSWORD_PLACEHOLDER = "请输入交易密码"

_ERROR_NEEDLES = ("密码错误", "密码有误", "错误", "失败", "锁定", "冻结", "不正确", "无效")
_MANUAL_NEEDLES = ("短信", "验证码", "动态口令", "人脸", "面容", "指纹", "设备", "证书", "ukey", "UKey")
_SUCCESS_NEEDLES = ("买入", "卖出", "撤单", "委托", "持仓", "可用")


class ThsError(RuntimeError):
    """Raised when the 同花顺 trade module is not in the expected state."""


class ThsRejected(ThsError):
    """The broker rejected the login (wrong password, locked account)."""


class ThsManualRequired(ThsError):
    """SMS / face / device verification: a human must finish it."""


@dataclass(frozen=True)
class ThsStatus:
    app_foreground: bool
    on_trade_tab: bool
    login_panel_open: bool
    broker_name: str
    account_masked: str
    logged_in: bool | None
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "app_foreground": self.app_foreground,
            "on_trade_tab": self.on_trade_tab,
            "login_panel_open": self.login_panel_open,
            "broker_name": self.broker_name,
            "account_masked": self.account_masked,
            "logged_in": self.logged_in,
            "reason": self.reason,
        }


def _text(node: Node | None) -> str:
    return node.text.strip() if node is not None else ""


def mask_account(account: str) -> str:
    """同花顺把资金账号显示成 ``4004****0162``（前 4 + 后 4）。"""
    account = (account or "").strip()
    if len(account) < 4:
        return "****"
    if len(account) < 8:
        return "****" + account[-4:]
    return f"{account[:4]}****{account[-4:]}"


def panel_open(nodes: list[Node]) -> bool:
    return find_by_id(nodes, PASSWORD_ID) is not None


def is_trade_page(nodes: list[Node]) -> bool:
    """Trade tab in either state: not logged in, login drawer open, or logged in."""
    if panel_open(nodes):
        return True
    if find_by_id(nodes, TRADE_PAGE_ID) is not None:
        return True
    return find_by_id(nodes, LOGGED_IN_ID) is not None or find_by_id(nodes, BUY_MENU_ID) is not None


def login_panel(nodes: list[Node]) -> dict:
    return {
        "broker": _text(find_by_id(nodes, PANEL_QS_ID)),
        "account_masked": _text(find_by_id(nodes, PANEL_ACCOUNT_ID)),
    }


def read_status(nodes: list[Node], focus: str) -> ThsStatus:
    app_foreground = PACKAGE in focus
    open_panel = panel_open(nodes)
    trade_tab = is_trade_page(nodes)
    broker = _text(find_by_id(nodes, "qs_name_text")) or _text(find_by_id(nodes, QS_NAME_ID)) or _text(find_by_id(nodes, PANEL_QS_ID)) or _text(find_by_id(nodes,'page_title_view'))
    account = _text(find_by_id(nodes, ACCOUNT_VALUE_ID)) or _text(
        find_by_id(nodes, PANEL_ACCOUNT_ID)
    )
    account = account or _text(find_by_id(nodes,'account_info_view'))
    # 11.64.07 登录后的独立控件，文本带“k客户号”前缀，不能沿用密码框字段。
    signed_in_account = _text(find_by_id(nodes, "account_text"))
    if signed_in_account:
        match = re.search(r"[0-9][0-9*]{3,}", signed_in_account)
        account = match.group(0) if match else ""

    if open_panel:
        logged_in: bool | None = False
        reason = "交易模块未登录，需要交易密码"
    elif app_foreground and find_by_id(nodes, LOGGED_IN_ID) is not None and find_by_id(nodes, BUY_MENU_ID) is not None:
        logged_in = True
        reason = ""
    else:
        logged_in = None
        reason = "无法判断交易模块是否已登录"

    return ThsStatus(
        app_foreground=app_foreground,
        on_trade_tab=trade_tab,
        login_panel_open=open_panel,
        broker_name=broker,
        account_masked=account,
        logged_in=logged_in,
        reason=reason,
    )


class ThsTrade:
    def __init__(self, adb: Adb | None = None):
        self.adb = adb or Adb()

    def _snapshot(self, retries: int = 3) -> tuple[str, list[Node]]:
        return self.adb.current_focus(), self.adb.nodes(retries=retries)

    def status(self) -> ThsStatus:
        focus, nodes = self._snapshot()
        return read_status(nodes, focus)

    # ----- navigation ------------------------------------------------------
    def launch(self) -> None:
        self.adb.launch_package(PACKAGE)

    def open_trade_tab(self, timeout: float = 30.0) -> list[Node]:
        """Bring 同花顺 to the 交易 tab from any state.

        Handles: app not running, another bottom tab, a deep sub-page, and the
        splash/ad screen shown on a cold start.  The app is given a few seconds
        to settle before any BACK press, otherwise a cold start would be
        dismissed and the app would close.
        """
        deadline = time.monotonic() + timeout
        settle = 0
        blind = 0
        while time.monotonic() < deadline:
            try:
                focus, nodes = self._snapshot(retries=1)
                blind = 0
            except AdbError:
                # 首页的广告轮播由 Handler 驱动，uiautomator 永远等不到 idle。
                # 无法读节点时按底部导航的固定比例点一次“交易”。
                focus = self.adb.current_focus()
                if PACKAGE in focus and blind < 2:
                    blind += 1
                    self._tap_trade_by_ratio()
                    time.sleep(2.5)
                else:
                    time.sleep(2.0)
                continue
            if PACKAGE not in focus:
                self.launch()
                # Launcher activity -> Hexin means the main frame is up; polling
                # the focus is far cheaper than a 10s uiautomator dump.
                wait_until(
                    lambda: ".Hexin" in self.adb.current_focus(), timeout=12.0, interval=0.3
                )
                time.sleep(0.6)
                # 首页的轮播读不到节点，直接按底部导航比例切到“交易”，
                # 省掉一次 10 秒的 uiautomator idle 等待。
                self._tap_trade_by_ratio()
                time.sleep(2.0)
                settle = 0
                continue
            if is_trade_page(nodes):
                return nodes
            tab = self._trade_tab(nodes)
            if tab is not None:
                self.adb.tap_node(tab)
                time.sleep(1.5)
                settle = 0
                continue
            # No bottom navigation yet: splash, ad, or a full-screen sub-page.
            if settle < 3:
                settle += 1
                time.sleep(1.8)
                continue
            settle = 0
            self.adb.keyevent(4)
            time.sleep(1.0)
        _, nodes = self._snapshot()
        if is_trade_page(nodes):
            return nodes
        raise ThsError("无法切换到同花顺“交易”标签，请确认 App 已登录且能正常打开")

    def _tap_trade_by_ratio(self) -> None:
        """Tap the 交易 tab using the fixed bottom-bar geometry.

        Only used when the page cannot be dumped (animated home page/splash).
        """
        width, height = self.adb.display_size()
        self.adb.tap(int(width * 0.583), int(height * 0.971))

    def _trade_tab(self, nodes: list[Node]) -> Node | None:
        """The tab bar sets content-desc on a clickable RelativeLayout.

        Falling back to the child label keeps this working on builds that move
        the description onto the text view.
        """
        for node in nodes:
            if node.description == TRADE_TAB_DESC and node.clickable:
                return node
        for node in nodes:
            if node.bounds[1] >= 1700 and node.text == TRADE_TAB_DESC and node.clickable:
                return node
        for node in nodes:
            if node.bounds[1] >= 1700 and node.text == TRADE_TAB_DESC:
                return node
        return None

    # ----- login -----------------------------------------------------------
    def open_login_panel(self, nodes: list[Node] | None = None, timeout: float = 15.0) -> list[Node]:
        """Tap the 银河 account card so the password drawer appears.

        On the 交易 tab the drawer is closed by default; the adapter must not
        assume it is already visible.
        """
        nodes = nodes if nodes is not None else self.open_trade_tab(timeout=timeout)
        if panel_open(nodes):
            return nodes
        card = find_by_id(nodes, ACCOUNT_CARD_ID) or find_by_id(nodes, ACCOUNT_CARD_FALLBACK_ID)
        if card is None:
            raise ThsError("找不到银河证券账户卡片，请确认同花顺已添加该账户并停在“交易”页")
        self.adb.tap_node(card)
        loaded = wait_until(
            lambda: (
                lambda pair: pair[1] if panel_open(pair[1]) else None
            )(self._snapshot()),
            timeout=timeout,
            interval=0.3,
        )
        if not loaded:
            raise ThsError("点击账户卡片后没有出现交易密码面板")
        return loaded

    def ensure_logged_in(
        self,
        account: str,
        password: str | None,
        timeout: float = 30.0,
        dry_run: bool = False,
    ) -> dict:
        """Log in only when the panel is actually shown.

        Already logged in → returns immediately without typing anything, so
        repeated calls never burn a password attempt.
        """
        nodes = self.open_trade_tab(timeout=max(timeout, 45.0))
        if not panel_open(nodes):
            status = read_status(nodes, self.adb.current_focus())
            if status.logged_in:
                # Balances/menu may render before the broker/account labels.
                # Only reread incomplete identity, without tapping or retyping.
                # An explicit mismatch is never retried or accepted from cache.
                for attempt in range(3):
                    if ((status.broker_name and "银河" not in status.broker_name)
                            or (status.account_masked and not account_matches(status.account_masked, account))):
                        raise ThsError("交易主页券商或资金账号与绑定账户不一致，已停止")
                    if status.logged_in and status.broker_name and status.account_masked:
                        return {"logged_in": True, "already": True, **status.as_dict(), "account_verified": True, "account_display": status.account_masked}
                    if attempt == 2 or not status.app_foreground or status.login_panel_open:
                        raise ThsError("交易主页身份信息未加载完整或登录状态已改变，已停止")
                    time.sleep(0.2)
                    focus, nodes = self._snapshot(retries=1)
                    status = read_status(nodes, focus)
            nodes = self.open_login_panel(nodes, timeout=timeout)
        if not password:
            raise ThsError("需要交易密码")

        self.verify_account(nodes, account)

        field = find_by_id(nodes, PASSWORD_ID)
        if field is None:
            raise ThsError("找不到交易密码输入框")
        self.adb.tap_node(field)
        self.adb.clear_text(24)
        self.adb.input_text(password)

        ready = wait_until(self._ready_button, timeout=8.0, interval=0.4)
        if not ready:
            raise ThsError("输入交易密码后“登录”按钮仍不可点击，已停止")
        button, filled = ready
        if filled != len(password):
            raise ThsError(
                f"密码框里有 {filled} 个字符，与预期的 {len(password)} 个不一致；已停止，未提交"
            )

        if dry_run:
            return {
                "logged_in": False,
                "dry_run": True,
                "account_masked": mask_account(account),
            }

        self.adb.tap_node(button)
        result = self._wait_result(timeout)
        _, nodes = self._snapshot()
        status = read_status(nodes, self.adb.current_focus())
        if not status.logged_in or not account_matches(status.account_masked, account) or "银河" not in status.broker_name:
            raise ThsError("登录后的券商或资金账号无法核验，已停止")
        return {**result, "account_verified": True, "account_display": status.account_masked}

    def _ready_button(self):
        """The 登录 button only becomes clickable once the password is filled."""
        _, nodes = self._snapshot()
        button = find_by_id(nodes, LOGIN_BUTTON_ID)
        if button is None or not button.clickable:
            return None
        field = find_by_id(nodes, PASSWORD_ID)
        return button, len(field.text) if field else 0

    def verify_account(self, nodes: list[Node], account: str) -> None:
        """Refuse to type a password into the wrong 券商/账户."""
        info = login_panel(nodes)
        expected = mask_account(account)
        if not account_matches(info["account_masked"], account) or "银河" not in info["broker"]:
            raise ThsError(
                f"同花顺当前选中的账户是 {info['account_masked']}，与本地记录的 {expected} 不一致；"
                "已停止，未提交密码"
            )

    def _wait_result(self, timeout: float) -> dict:
        def check():
            _, nodes = self._snapshot()
            raw = " ".join(node.text for node in nodes if node.text)
            if any(needle in raw for needle in _MANUAL_NEEDLES):
                return ("manual", raw)
            if any(needle in raw for needle in _ERROR_NEEDLES):
                return ("error", raw)
            if read_status(nodes, self.adb.current_focus()).logged_in:
                return ("success", raw)
            return None

        outcome = wait_until(check, timeout=timeout, interval=0.4)
        if not outcome:
            raise ThsError("点击登录后页面没有变化，结果未知；请人工检查后再重试")
        kind, raw = outcome
        if kind == "manual":
            raise ThsManualRequired("登录需要短信/人脸/设备验证，请人工完成后再继续")
        if kind == "error":
            raise ThsRejected("券商拒绝了登录：" + _short(raw))
        return {"logged_in": True, "already": False, "raw": _short(raw)}


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"
