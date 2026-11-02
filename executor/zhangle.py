"""涨乐通 login page object and login state machine.

The login activity is marked FLAG_SECURE, therefore this module never relies on
screenshots.  It reads the uiautomator XML tree, uses resource-id based taps and
uses ``adb shell input text`` for the trading password.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from . import credentials
from .adb import Adb, AdbError, Node, find_by_id, find_by_text, wait_until
from .identity import account_matches

PACKAGE = "com.lphtsccft"
LOGIN_ACTIVITY = "com.lphtsccft.zhangle.login.HtscLoginActivity"
MAIN_ACTIVITY = "com.lphtsccft.zhangle.main.MainActivity"
SPLASH_ACTIVITY = "com.lphtsccft.zhangle.startup.SplashScreenActivity"

ACCOUNT_ID = "login_account_edit"
PASSWORD_ID = "login_password_edit"
LOGIN_BUTTON_ID = "login_btn_login"
LOGIN_SETTINGS_ID = "login_tv_account_setting"

# The trade tab keeps its own session inside the app: after the app session is
# gone it still renders `trade_unlogin_main_layout` until a trade login happens.
TRADE_UNLOGIN_ID = "trade_unlogin_main_layout"
TRADE_READY_ID = "trade_normal_main_layout"
TRADE_LOGIN_ENTRY_ID = "trade_title_login"
TRADE_TAB_TEXT = "交易"

_MANUAL_NEEDLES = (
    "短信验证",
    "验证码",
    "人脸识别",
    "人脸验证",
    "身份验证",
    "设备验证",
    "新设备",
    "证书激活",
    "激活证书",
)
_ERROR_NEEDLES = (
    "密码错误",
    "密码不正确",
    "账号或密码",
    "登录失败",
    "登录异常",
    "账户锁定",
    "账号锁定",
    "已被锁定",
    "账号冻结",
    "账户冻结",
)


class LoginError(RuntimeError):
    """Base class for login failures."""


class LoginRejected(LoginError):
    """The broker rejected the login (wrong password, locked account, ...)."""


class ManualVerificationRequired(LoginError):
    """SMS, face, certificate or new-device verification needs a human."""


class StartupConsentRequired(LoginError):
    """The app is showing the one-time privacy/terms dialog."""


@dataclass(frozen=True)
class LoginResult:
    logged_in: bool
    login_screen: bool
    focus: str
    account: str | None
    dry_run: bool = False

    def as_dict(self) -> dict:
        return {
            "logged_in": self.logged_in,
            "login_screen": self.login_screen,
            "focus": self.focus,
            "account": self.account,
            "dry_run": self.dry_run,
        }


def mask_account(account: str | None) -> str | None:
    if not account:
        return None
    if len(account) <= 6:
        return "***"
    return f"{account[:3]}***{account[-3:]}"


def _account_text(node: Node | None) -> str | None:
    """Return the account only if the field contains digits/mask, not a hint."""
    if node is None:
        return None
    text = node.text.strip()
    if not text or not re.fullmatch(r"[0-9*]+", text):
        return None
    return text


def is_login_screen(nodes: list[Node], focus: str) -> bool:
    if LOGIN_ACTIVITY in focus:
        return True
    if find_by_id(nodes, PASSWORD_ID):
        return True
    return any("登录后继续操作" in node.text for node in nodes)


def is_trade_page(nodes: list[Node]) -> bool:
    return (
        find_by_id(nodes, TRADE_UNLOGIN_ID) is not None
        or find_by_id(nodes, TRADE_READY_ID) is not None
    )


def is_trade_locked(nodes: list[Node]) -> bool:
    """True when the trade tab is rendered in its logged-out layout."""
    return find_by_id(nodes, TRADE_UNLOGIN_ID) is not None


def is_logged_in(nodes: list[Node], focus: str) -> bool:
    if is_login_screen(nodes, focus):
        return False
    if MAIN_ACTIVITY not in focus:
        return False
    if find_by_text(nodes, "登录查看"):
        return False
    # The home/account pages can keep rendering cached data after the session
    # expires, so the trade tab is the only page that reports the truth.
    if is_trade_locked(nodes):
        return False
    return any(node.text in ("首页", "交易", "账户") for node in nodes)


def _has_login_entry(nodes: list[Node]) -> bool:
    return find_by_text(nodes, "登录查看") is not None


def has_consent_dialog(nodes: list[Node]) -> bool:
    return (
        find_by_text(nodes, "同意") is not None
        and find_by_text(nodes, "不同意") is not None
        and any("温馨提示" in node.text for node in nodes)
    )


def _manual_reason(nodes: list[Node]) -> str | None:
    for node in nodes:
        for needle in _MANUAL_NEEDLES:
            if needle in node.text:
                return node.text
    return None


def _error_reason(nodes: list[Node]) -> str | None:
    for node in nodes:
        for needle in _ERROR_NEEDLES:
            if needle in node.text:
                return node.text
    for node in nodes:
        if node.resource_id.endswith("dialog_tv_message") and node.text:
            return node.text
    return None


class Zhangle:
    def __init__(self, adb: Adb | None = None):
        self.adb = adb or Adb()

    # ----- reading ---------------------------------------------------------
    def snapshot(self) -> tuple[str, list[Node]]:
        focus = self.adb.current_focus()
        return focus, self.adb.nodes()

    def status(self, focus: str | None = None, nodes: list[Node] | None = None) -> LoginResult:
        if focus is None:
            focus = self.adb.current_focus()
        if nodes is None:
            nodes = self.adb.nodes()
        account_node = find_by_id(nodes, ACCOUNT_ID)
        return LoginResult(
            logged_in=is_logged_in(nodes, focus),
            login_screen=is_login_screen(nodes, focus),
            focus=focus,
            account=mask_account(_account_text(account_node)),
        )

    def is_installed(self) -> bool:
        return self.adb.is_installed(PACKAGE)

    # ----- app lifecycle ---------------------------------------------------
    def launch(self) -> None:
        if self.adb.is_foreground(PACKAGE):
            return
        self.adb.start_app(SPLASH_ACTIVITY, PACKAGE)

    def _wait_for_page(self, timeout: float = 20.0, accept_terms: bool = False) -> tuple[str, list[Node]]:
        consent_tapped = False

        def check():
            nonlocal consent_tapped
            focus, nodes = self.snapshot()
            if has_consent_dialog(nodes):
                if not accept_terms:
                    raise StartupConsentRequired(
                        "App 启动时出现隐私协议确认，请手动点“同意”，或使用 --accept-terms"
                    )
                if not consent_tapped:
                    consent = find_by_text(nodes, "同意")
                    if consent is not None:
                        self.adb.tap_node(consent)
                        consent_tapped = True
                return None
            if is_login_screen(nodes, focus) or is_logged_in(nodes, focus) or _has_login_entry(nodes):
                return focus, nodes
            return None

        page = wait_until(check, timeout=timeout, interval=0.4)
        if not page:
            focus, nodes = self.snapshot()
            raise LoginError(f"等待登录页超时，当前 Activity: {focus}")
        return page

    def _ensure_home(self, timeout: float = 25.0, accept_terms: bool = False) -> tuple[str, list[Node]]:
        """Get 涨乐通 to its home/login page from any state.

        Covers: app not running, app on another tab, app deep inside a
        sub-page, and cold-start privacy consent.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            focus, nodes = self.snapshot()
            if has_consent_dialog(nodes):
                return self._wait_for_page(timeout=8.0, accept_terms=accept_terms)
            if is_login_screen(nodes, focus) or is_logged_in(nodes, focus) or _has_login_entry(nodes):
                return focus, nodes
            if PACKAGE not in focus:
                self.launch()
                time.sleep(2.0)
                continue
            tab = self._bottom_nav(nodes, "首页")
            if tab is not None:
                self.adb.tap_node(tab)
                time.sleep(1.5)
                continue
            self.adb.keyevent(4)
            time.sleep(1.0)
        focus, nodes = self.snapshot()
        if is_login_screen(nodes, focus) or is_logged_in(nodes, focus) or _has_login_entry(nodes):
            return focus, nodes
        raise LoginError("无法回到涨乐通首页或登录页，请手动打开 App 后重试")

    # ----- login -----------------------------------------------------------
    def ensure_logged_in(
        self,
        password: str | None = None,
        account: str | None = None,
        dry_run: bool = False,
        timeout: float = 25.0,
        accept_terms: bool = False,
    ) -> LoginResult:
        if not self.is_installed():
            raise LoginError(f"模拟器中没有安装 {PACKAGE}")

        focus, nodes = self._ensure_home(timeout=timeout, accept_terms=accept_terms)
        if is_logged_in(nodes, focus):
            return self.status(focus, nodes)

        if not is_login_screen(nodes, focus):
            # The home page shows a "登录查看" entry when the session is gone.
            entry = find_by_text(nodes, "登录查看")
            if entry is None:
                raise LoginError("当前页面不是登录页，也找不到“登录查看”入口")
            self.adb.tap_node(entry)
            focus, nodes = self._wait_for_page(timeout=timeout, accept_terms=accept_terms)

        return self._login_from_screen(password, account, dry_run, timeout)

    def _login_from_screen(
        self,
        password: str | None,
        account: str | None,
        dry_run: bool,
        timeout: float,
    ) -> LoginResult:
        focus, nodes = self.snapshot()
        account_node = find_by_id(nodes, ACCOUNT_ID)
        password_node = find_by_id(nodes, PASSWORD_ID)
        button = find_by_id(nodes, LOGIN_BUTTON_ID)
        if not account_node or not password_node or not button:
            raise LoginError("登录页结构不完整：找不到账号、密码或登录按钮")

        resolved_account = account or credentials.get_account() or _account_text(account_node) or ""
        if not resolved_account:
            raise LoginError("账号为空，请先执行 set-account 或设置 ZHANGLE_ACCOUNT")
        if "*" in resolved_account:
            raise LoginError("登录页账号被隐藏，请先执行 set-account 写入完整客户号")

        if account_node.text.strip() != resolved_account:
            self.adb.tap_node(account_node)
            self.adb.clear_text(len(account_node.text) + 8)
            self.adb.input_text(resolved_account)

        resolved_password = password or credentials.get_password() or ""
        if not resolved_password:
            raise LoginError("密码为空，请先执行 set-password 或设置 ZHANGLE_PASSWORD")

        self.adb.tap_node(password_node)
        self.adb.clear_text(len(password_node.text) + 8)
        self.adb.input_text(resolved_password)

        focus, nodes = self.snapshot()
        button = find_by_id(nodes, LOGIN_BUTTON_ID)
        if button is None:
            raise LoginError("输入密码后找不到登录按钮")
        if not button.enabled:
            raise LoginError("已输入密码，但登录按钮仍未启用；请检查密码长度或页面状态")

        if dry_run:
            return LoginResult(
                logged_in=False,
                login_screen=True,
                focus=focus,
                account=mask_account(resolved_account),
                dry_run=True,
            )

        self.adb.tap_node(button)
        return self._wait_for_login_result(timeout)

    def _wait_for_login_result(self, timeout: float) -> LoginResult:
        deadline = time.monotonic() + timeout
        last_focus = ""
        while time.monotonic() < deadline:
            focus, nodes = self.snapshot()
            last_focus = focus
            if is_logged_in(nodes, focus):
                return self.status(focus, nodes)
            manual = _manual_reason(nodes)
            if manual:
                raise ManualVerificationRequired(f"需要人工验证：{manual}")
            error = _error_reason(nodes)
            if error:
                raise LoginRejected(f"登录被拒绝：{error}")
            time.sleep(0.8)
        raise LoginRejected(f"登录超时，当前 Activity: {last_focus}")

    # ----- trade module ----------------------------------------------------
    def trade_status(
        self, focus: str | None = None, nodes: list[Node] | None = None
    ) -> dict:
        """Read-only view of the trade tab (no taps, safe to poll)."""
        if focus is None:
            focus = self.adb.current_focus()
        if nodes is None:
            nodes = self.adb.nodes()
        available = find_by_id(nodes, "ky_value")
        pnl = find_by_id(nodes, "ccsy_value")
        return {
            "on_trade_page": is_trade_page(nodes),
            "trade_locked": is_trade_locked(nodes),
            "focus": focus,
            "available_cash": available.text.strip() if available else None,
            "holding_pnl": pnl.text.strip() if pnl else None,
        }

    def open_trade_tab(self, timeout: float = 15.0) -> tuple[str, list[Node]]:
        focus, nodes = self.snapshot()
        if is_trade_page(nodes):
            return focus, nodes
        tab = self._bottom_nav(nodes, TRADE_TAB_TEXT)
        for _ in range(3):
            if tab is not None:
                break
            # 可能在某个二级页面，先退一层再找底部导航。
            self.adb.keyevent(4)
            time.sleep(1.0)
            focus, nodes = self.snapshot()
            if PACKAGE not in focus:
                self.launch()
                time.sleep(2.0)
                focus, nodes = self.snapshot()
            tab = self._bottom_nav(nodes, TRADE_TAB_TEXT)
        if tab is None:
            raise LoginError("找不到底部“交易”入口")
        self.adb.tap_node(tab)

        def on_trade():
            current_focus, current_nodes = self.snapshot()
            return (current_focus, current_nodes) if is_trade_page(current_nodes) else None

        page = wait_until(on_trade, timeout=timeout, interval=0.4)
        if not page:
            raise LoginError("点击“交易”后没有进入交易页")
        return page

    def ensure_trade_ready(
        self,
        account: str | None = None,
        password: str | None = None,
        dry_run: bool = False,
        timeout: float = 25.0,
        skip_login_check: bool = False,
    ) -> dict:
        """Make the trade tab usable, logging in only when it is locked.

        The app session and the trade-module session are separate: the trade tab
        can still show its logged-out layout while the home page looks normal.
        This method submits the password at most once per call and does nothing
        when the trade tab is already unlocked.
        """
        # 先读一次当前页面。已经在交易主页时无需再次往返首页/登录检查。
        focus, nodes = self.snapshot()
        if PACKAGE in focus and is_trade_page(nodes):
            result = self.status(focus, nodes)
        elif skip_login_check:
            result = self.status(focus, nodes)
        else:
            result = self.ensure_logged_in(password=password, account=account, timeout=timeout)
            focus, nodes = self.snapshot()
        if not is_trade_page(nodes):
            focus, nodes = self.open_trade_tab(timeout=timeout)

        if not is_trade_locked(nodes):
            return {**result.as_dict(), **self.trade_status(focus, nodes), **self.verify_trade_account(nodes, account)}

        entry = find_by_id(nodes, TRADE_LOGIN_ENTRY_ID)
        if entry is None:
            raise LoginError("交易页处于未登录状态，但找不到顶部登录入口")
        self.adb.tap_node(entry)

        def login_page():
            current_focus, current_nodes = self.snapshot()
            return (current_focus, current_nodes) if is_login_screen(current_nodes, current_focus) else None

        page = wait_until(login_page, timeout=timeout, interval=0.8)
        if not page:
            raise LoginError("交易登录页没有出现")
        if dry_run:
            self._login_from_screen(password, account, dry_run=True, timeout=timeout)
            return {
                "ok": True,
                "dry_run": True,
                "account_filled": True,
                "trade_locked": True,
            }

        self._login_from_screen(password, account, dry_run=False, timeout=timeout)
        focus, nodes = self.snapshot()
        if not is_trade_page(nodes):
            focus, nodes = self.open_trade_tab(timeout=timeout)
        status = self.trade_status(focus, nodes)
        if status["trade_locked"]:
            raise LoginError("交易登录后交易页仍未解锁")
        return {**result.as_dict(), **status, **self.verify_trade_account(nodes, account), "logged_in": True}

    @staticmethod
    def verify_trade_account(nodes, account):
        node = find_by_id(nodes, "title_bar_right")
        shown = node.text.strip() if node else ""
        if not account or not account_matches(shown, account):
            raise LoginError("交易主页客户号与所选账号不一致或无法识别，已停止")
        return {"account_verified": True, "account_display": shown,
                "account_verification": "masked" if "*" in shown else "full"}

    # ----- logout (for tests / account switching) --------------------------
    def logout(self, timeout: float = 20.0) -> LoginResult:
        focus, nodes = self.snapshot()
        if is_login_screen(nodes, focus) or _has_login_entry(nodes):
            return self.status(focus, nodes)
        if not is_logged_in(nodes, focus):
            raise LoginError(f"当前不是已登录状态: {focus}")

        account_tab = self._bottom_nav(nodes, "账户")
        if account_tab is None:
            raise LoginError("找不到底部“账户”入口")

        # The account page can take a moment to inflate, and a tap is sometimes
        # swallowed while the previous page is still animating.  Retry the tab
        # once instead of failing the whole logout.
        more = None
        for _ in range(2):
            self.adb.tap_node(account_tab)
            more = wait_until(
                lambda: find_by_id(self.adb.nodes(), "iv_account_title_more"),
                timeout=8,
            )
            if more is not None:
                break
            focus, nodes = self.snapshot()
            if is_login_screen(nodes, focus) or _has_login_entry(nodes):
                return self.status(focus, nodes)
            account_tab = self._bottom_nav(nodes, "账户")
            if account_tab is None:
                break
        if more is None:
            raise LoginError("账户页找不到切换账号入口（请先手动切到“账户”页再重试）")
        self.adb.tap_node(more)

        quit_node = wait_until(
            lambda: find_by_id(self.adb.nodes(), "tv_change_account_quit"),
            timeout=10,
        )
        if quit_node is None:
            raise LoginError("切换账号弹层找不到“退出”")
        self.adb.tap_node(quit_node)

        confirm = wait_until(
            lambda: find_by_id(self.adb.nodes(), "dialog_btn_right"),
            timeout=10,
        )
        if confirm is None or confirm.text != "确定":
            raise LoginError("退出确认弹窗没有出现“确定”按钮")
        self.adb.tap_node(confirm)

        def login_page():
            focus, nodes = self.snapshot()
            if is_login_screen(nodes, focus) or _has_login_entry(nodes):
                return (focus, nodes)
            return None

        page = wait_until(login_page, timeout=timeout, interval=0.8)
        if not page:
            raise LoginError("退出后没有回到登录页或首页登录入口")
        return self.status(page[0], page[1])

    @staticmethod
    def _bottom_nav(nodes: list[Node], text: str) -> Node | None:
        candidates = [node for node in nodes if node.text == text]
        if not candidates:
            return None
        return max(candidates, key=lambda node: node.center[1])
