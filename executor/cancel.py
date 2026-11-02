"""涨乐通「撤单」页（WebView）预览。

撤单页是 H5（``web_container``），``uiautomator`` 读不到任何节点，只能截图。
好在版式非常固定：中间是委托列表，底部固定三个按钮「全撤 / 撤买 / 撤卖」，
横跨整个屏幕宽度。

旧实现通过底部批撤按钮操作，无法保证不影响屏幕外或新增的订单。
当前只提供计划预览，真实撤单必须等唯一委托号和逐笔控件适配后再开放。

计划预览流程：

1. 用**原生**的「今日委托」列表算出哪些委托可撤（见 :mod:`executor.orderbook`）；
2. 校验目标集合，绝不允许顺手撤掉其它方向的委托；
3. 进入撤单页，返回按钮位置，绝不点击撤单按钮。

第 3 步是这个模块唯一"不精确"的地方：底部按钮的 y 坐标靠扫描截图找分隔线，
找不到就退回固定比例。任何一步对不上都直接报错，不会静默继续。
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from .adb import Adb, AdbError, Node, find_by_id, find_by_text, wait_until
from .orderbook import OrderBook, OrderRow
from .trade import (
    DIALOG_CANCEL_ID,
    DIALOG_MESSAGE_ID,
    DIALOG_OK_ID,
    DIALOG_TITLE_ID,
    TRADE_ACTIVITY,
    TradePage,
)

CANCEL_TAB_TEXT = "撤单"
WEB_CONTAINER_ID = "web_container"

# 底部按钮：scope -> 按钮文字。x 坐标按 1/6、1/2、5/6 均分。
SCOPES = {"all": "全撤", "buy": "撤买", "sell": "撤卖"}
_X_RATIO = {"all": 1 / 6, "buy": 1 / 2, "sell": 5 / 6}
_FALLBACK_BAR_RATIO = 1770 / 1920


class CancelError(RuntimeError):
    """Raised when a cancel cannot be planned or verified."""


@dataclass(frozen=True)
class CancelPlan:
    scope: str
    targets: list[OrderRow] = field(default_factory=list)
    blocked: list[OrderRow] = field(default_factory=list)

    @property
    def button(self) -> str:
        return SCOPES[self.scope]

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "button": self.button,
            "targets": [row.as_dict() for row in self.targets],
            "blocked": [row.as_dict() for row in self.blocked],
        }


def _describe(row: OrderRow) -> str:
    quantity = "" if row.quantity is None else f" {row.quantity:g}股"
    return f"{row.date} {row.time} {row.name}({row.code}) {row.direction}{quantity} @{row.price}"


def plan_cancel(
    orders: list[OrderRow],
    scope: str = "all",
    code: str | None = None,
    side: str | None = None,
) -> CancelPlan:
    """Decide which bottom button to press. Pure function, unit tested.

    ``code`` narrows the intent to one stock.  Because the H5 page only offers
    all/buy/sell, single-stock cancelling is only allowed when no *other*
    cancellable order shares the same side; otherwise the request is refused
    and the caller sees exactly which orders would be hit by mistake.
    """
    cancellable = [row for row in orders if row.cancellable]
    if not cancellable:
        raise CancelError("今天没有可撤的委托")

    if code:
        wanted = [
            row
            for row in cancellable
            if row.code == code and (side is None or row.side == side)
        ]
        if not wanted:
            raise CancelError(f"{code} 没有可撤的委托")
        if len(wanted) != 1:
            raise CancelError("同股票同方向存在多笔委托，不能当成单笔撤销；请在券商内选择具体委托")
        sides = {row.side for row in wanted}
        if len(sides) != 1 or None in sides:
            raise CancelError(f"{code} 买卖两个方向都有可撤委托，请手动处理")
        chosen = sides.pop()
        others = [row for row in cancellable if row.side == chosen and row not in wanted]
        return CancelPlan(scope=chosen, targets=wanted, blocked=others)

    if scope not in SCOPES:
        raise ValueError("scope 只能是 all / buy / sell")
    if scope == "all":
        return CancelPlan(scope="all", targets=cancellable)
    targets = [row for row in cancellable if row.side == scope]
    if not targets:
        label = "买入" if scope == "buy" else "卖出"
        raise CancelError(f"今天没有可撤的{label}委托")
    return CancelPlan(scope=scope, targets=targets)


def _uniform_color(pixels: bytes, width: int, y: int, tolerance: int = 8, step: int = 5):
    base = y * width * 4
    r0, g0, b0 = pixels[base], pixels[base + 1], pixels[base + 2]
    for x in range(0, width, step):
        index = base + x * 4
        if (
            abs(pixels[index] - r0) > tolerance
            or abs(pixels[index + 1] - g0) > tolerance
            or abs(pixels[index + 2] - b0) > tolerance
        ):
            return None
    return (r0, g0, b0)


def find_bar_top(pixels: bytes, width: int, height: int) -> int:
    """Find the divider line above the bottom button bar.

    Scan upward from the last row; the first uniform non-white light row is the
    separator.  Falls back to a fixed ratio when nothing is found.
    """
    for y in range(height - 1, max(height // 2, 0), -1):
        color = _uniform_color(pixels, width, y)
        if color and color != (255, 255, 255) and min(color) > 150:
            return y + 1
    return int(height * _FALLBACK_BAR_RATIO)


def button_points(adb: Adb) -> dict[str, tuple[int, int]]:
    """Return the tap point of 全撤 / 撤买 / 撤卖 on the WebView page."""
    try:
        width, height, pixels = adb.screencap_raw()
        top = find_bar_top(pixels, width, height)
    except AdbError:
        size = adb.screen_size() or (1080, 1920)
        width, height = size
        top = int(height * _FALLBACK_BAR_RATIO)
    y = (top + height) // 2
    return {scope: (int(width * ratio), y) for scope, ratio in _X_RATIO.items()}


@dataclass(frozen=True)
class CancelDialog:
    title: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


def parse_dialog(nodes: list[Node]) -> CancelDialog | None:
    message = find_by_id(nodes, DIALOG_MESSAGE_ID)
    if message is None:
        return None
    title = find_by_id(nodes, DIALOG_TITLE_ID)
    return CancelDialog(
        title=title.text.strip() if title else "",
        message=message.text.strip(),
    )


class CancelPage:
    def __init__(self, adb: Adb | None = None):
        self.adb = adb or Adb()

    def _snapshot(self) -> tuple[str, list[Node]]:
        return self.adb.current_focus(), self.adb.nodes()

    # ----- navigation ------------------------------------------------------
    def open(self, timeout: float = 20.0) -> list[Node]:
        """Enter the trade activity and switch to the 撤单 tab.

        The H5 page exposes no nodes, so the active tab cannot be detected.
        Tapping 撤单 unconditionally is safe and makes the result deterministic.
        """
        focus, nodes = self._snapshot()
        if TRADE_ACTIVITY not in focus:
            TradePage(self.adb).open(timeout=timeout)
            _, nodes = self._snapshot()
        tab = find_by_text(nodes, CANCEL_TAB_TEXT)
        if tab is None:
            raise CancelError("交易页找不到顶部“撤单”标签")
        self.adb.tap_node(tab)
        # The H5 page has no readable nodes; give it a moment to render.
        time.sleep(2.0)
        if TRADE_ACTIVITY not in self.adb.current_focus():
            raise CancelError("没有进入撤单页")
        nodes = self._snapshot()[1]
        if find_by_id(nodes, WEB_CONTAINER_ID) is None:
            raise CancelError("撤单页没有加载（找不到 web_container）")
        return nodes

    # ----- execute ---------------------------------------------------------
    def cancel(
        self,
        plan: CancelPlan,
        dry_run: bool = True,
        confirm_timeout: float = 8.0,
        verify_timeout: float = 12.0,
    ) -> dict:
        if plan.blocked:
            raise CancelError(
                "撤单会误伤其它委托：" + "；".join(_describe(row) for row in plan.blocked)
            )
        if not plan.targets:
            raise CancelError("没有可撤的委托")
        # 当前 H5 仅有按方向批撤且无法读取完整列表、唯一委托号。即使当前屏幕
        # 只有一笔，也不能排除屏幕外或查询后新增的委托；比例坐标不得用于真实撤单。
        if not dry_run:
            raise CancelError("尚未验证按唯一委托号撤单，请在券商 App 内撤单；观量仅支持撤单预览")

        self.open()
        points = button_points(self.adb)
        point = points[plan.scope]
        result = {
            "submitted": False,
            "scope": plan.scope,
            "button": plan.button,
            "point": list(point),
            "targets": [row.as_dict() for row in plan.targets],
        }
        return result

    def _verify(self, plan: CancelPlan, timeout: float) -> bool:
        def identity(row):
            return (row.extra.get("order_id"), row.date, row.time, row.code, row.side, row.price, row.quantity)
        wanted = {identity(row) for row in plan.targets}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                orders = OrderBook(self.adb).today_orders().rows
            except Exception:
                return False
            # 不见了、已成交、已报待撤都不是撤单成功证据；同键多行也不猜测。
            matching = [row for row in orders if identity(row) in wanted]
            if len(matching) == len(wanted) and {identity(row) for row in matching} == wanted and all(row.state in ("已撤", "部撤") for row in matching):
                return True
            time.sleep(min(1.2, max(0, deadline-time.monotonic())))
        return False
