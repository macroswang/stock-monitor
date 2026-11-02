"""涨乐通交易主页的「委托 / 成交 / 持仓」查询。

交易主页（``MainActivity`` 里的 ``trade_normal_main_layout``）下半部分是一个
**原生** ViewPager：``detail_viewpager`` → ``持仓`` / ``委托/成交``。
``委托/成交`` 里面再分 ``今日委托`` / ``今日成交`` / ``历史委托`` / ``历史成交``。
这一整套都是原生控件，``uiautomator dump`` 能读到节点，因此不需要截图或 OCR。

注意：交易页（``HtscNormalTradeActivity``）里另有一个 WebView 版的
「委托」标签，那个读不到节点，本模块**不用**它。

行结构（今日委托 / 历史委托）::

    stock_main_item
      stock_name               山子高科
      stock_code               000981
      item_trade_dir           卖出 / 买入 / 撤卖 / 撤买
      item_trade_trust_date    2026-10-30
      item_trade_trust_time    13:07:02
      item_trade_trust_num     2.250            委托价格
      item_trade_trust_success 2,300 | 0        委托数量 | 成交数量
      item_trade_trust_state   已报 / 已成 / 已撤 / 部撤

行结构（今日成交 / 历史成交）::

    stock_main_item
      stock_name / stock_code
      item_trade_dir           买入 / 卖出 / --
      item_trade_trust_date / item_trade_trust_time
      item_trade_trust_price   2.270            成交均价
      item_trade_trust_success 2,000.00         成交数量（卖出为负）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .adb import (
    Adb,
    Node,
    find_by_id,
    find_by_text,
    find_selected,
    wait_until,
)

ORDER_PAGE_ID = "order_main_layout"
INNER_PAGE_ID = "inner_order_main_layout"
ORDER_TAB_TEXT = "委托/成交"
HOLDING_TAB_TEXT = "持仓"

TAB_KEYS = {
    "today_orders": "今日委托",
    "today_trades": "今日成交",
    "history_orders": "历史委托",
    "history_trades": "历史成交",
}
_TAB_LABELS = tuple(TAB_KEYS.values())

ROW_ID = "stock_main_item"
RECYCLER_ID = "inner_order_recycler"
EMPTY_ID = "sub_tv1"

NAME_ID = "stock_name"
CODE_ID = "stock_code"
DIR_ID = "item_trade_dir"
DATE_ID = "item_trade_trust_date"
TIME_ID = "item_trade_trust_time"
ORDER_PRICE_ID = "item_trade_trust_num"
TRADE_PRICE_ID = "item_trade_trust_price"
AMOUNT_ID = "item_trade_trust_success"
STATE_ID = "item_trade_trust_state"

# 只有这些状态的委托还可能被撤单。
CANCELLABLE_STATES = ("未报", "待报", "已报", "部成", "已报待撤", "部撤")

# 资金卡片字段：resource-id -> (输出字段名, 中文标签 id)
FUND_FIELDS = (
    ("zzc_value", "total_assets"),
    ("jr_value", "today_profit"),
    ("ccsy_value", "holding_profit"),
    ("zsz_value", "market_value"),
    ("ky_value", "available"),
    ("kq_value", "withdrawable"),
    ("zcw_value", "position_ratio"),
)

POSITION_RECYCLER_ID = "fund_recycler"
POSITION_ROW_ID = "content_layout"
POSITION_FIELDS = (
    ("item_sz", "profit"),
    ("item_cw", "profit_ratio"),
    ("item_xj", "quantity"),
    ("item_cb", "sellable"),
    ("item_jryk", "price"),
    ("item_ykbl", "cost"),
    ("item_5_top", "today_profit"),
    ("item_5_bottom", "today_ratio"),
)

_CODE = re.compile(r"\d{6}")
_NUMBER = re.compile(r"-?[\d,]+(?:\.\d+)?")


class OrderBookError(RuntimeError):
    """Raised when the 委托/成交 page is not in the expected state."""


@dataclass(frozen=True)
class OrderRow:
    kind: str  # "order" | "trade"
    name: str
    code: str
    direction: str
    date: str
    time: str
    price: float | None
    quantity: float | None
    filled: float | None
    state: str
    extra: dict = field(default_factory=dict)

    @property
    def side(self) -> str | None:
        """买入/撤买 -> buy，卖出/撤卖 -> sell。"""
        if "买" in self.direction:
            return "buy"
        if "卖" in self.direction:
            return "sell"
        return None

    @property
    def cancelled(self) -> bool:
        return "撤" in self.direction or "撤" in self.state

    @property
    def cancellable(self) -> bool:
        if self.kind != "order":
            return False
        if self.state not in CANCELLABLE_STATES:
            return False
        return not self.cancelled and self.filled != self.quantity

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "code": self.code,
            "direction": self.direction,
            "side": self.side,
            "date": self.date,
            "time": self.time,
            "price": self.price,
            "quantity": self.quantity,
            "filled": self.filled,
            "state": self.state,
            "cancellable": self.cancellable,
            **self.extra,
        }


@dataclass(frozen=True)
class OrderList:
    kind: str
    rows: list[OrderRow]
    date_range: str = ""
    cycle: str = ""

    @property
    def cancellable(self) -> list[OrderRow]:
        return [row for row in self.rows if row.cancellable]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "date_range": self.date_range,
            "cycle": self.cycle,
            "coverage": "visible_rows",
            "complete": False,
            "count": len(self.rows),
            "cancellable_count": len(self.cancellable),
            "rows": [row.as_dict() for row in self.rows],
        }


def _number(text: str) -> float | None:
    match = _NUMBER.search(text.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _text(node: Node | None) -> str:
    return node.text.strip() if node is not None else ""


def _inside(node: Node, bounds: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = node.bounds
    bx1, by1, bx2, by2 = bounds
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return bx1 <= cx <= bx2 and by1 <= cy <= by2


def _scoped(nodes: list[Node], resource_id: str) -> list[Node]:
    """Restrict parsing to the list container so other pages cannot leak in."""
    container = find_by_id(nodes, resource_id)
    if container is None:
        return []
    return [node for node in nodes if _inside(node, container.bounds)]


def _rows(nodes: list[Node]) -> list[dict[str, Node]]:
    """Group the flat node list into one dict per ``stock_main_item`` row."""
    rows: list[dict[str, Node]] = []
    current: dict[str, Node] | None = None
    for node in nodes:
        rid = node.resource_id.rsplit("/", 1)[-1]
        if rid == ROW_ID:
            current = {}
            rows.append(current)
            continue
        if current is not None and rid:
            current.setdefault(rid, node)
    return rows


def parse_rows(nodes: list[Node], kind: str) -> list[OrderRow]:
    """Parse the native 委托 or 成交 list. Pure function, unit tested."""
    scoped = _scoped(nodes, RECYCLER_ID) or nodes
    out: list[OrderRow] = []
    for raw in _rows(scoped):
        name = _text(raw.get(NAME_ID))
        code_text = _text(raw.get(CODE_ID))
        match = _CODE.search(code_text)
        if not name and not match:
            continue
        # 列表末尾被裁掉一半的行只有名称，字段不全，不能当作委托/成交记录。
        if kind == "order" and not _text(raw.get(STATE_ID)):
            continue
        if kind == "trade" and not _text(raw.get(AMOUNT_ID)):
            continue
        amount = _text(raw.get(AMOUNT_ID))
        filled = None
        quantity = _number(amount)
        if "|" in amount:
            left, right = amount.split("|", 1)
            quantity = _number(left)
            filled = _number(right)
        price_text = _text(raw.get(ORDER_PRICE_ID if kind == "order" else TRADE_PRICE_ID))
        if quantity is not None and kind == "trade":
            quantity = abs(quantity)
        out.append(
            OrderRow(
                kind=kind,
                name=name,
                code=match.group(0) if match else "",
                direction=_text(raw.get(DIR_ID)),
                date=_text(raw.get(DATE_ID)),
                time=_text(raw.get(TIME_ID)),
                price=_number(price_text),
                quantity=quantity,
                filled=filled,
                state=_text(raw.get(STATE_ID)),
                extra={"raw": {key: _text(node) for key, node in raw.items()}},
            )
        )
    return out


def active_tab(nodes: list[Node]) -> str:
    node = find_selected(nodes, _TAB_LABELS)
    return node.text if node else ""


def is_empty(nodes: list[Node]) -> bool:
    node = find_by_id(nodes, EMPTY_ID)
    return bool(node and node.text.strip())


def date_range(nodes: list[Node]) -> str:
    start = find_by_id(nodes, "start_time")
    end = find_by_id(nodes, "end_time")
    if start is None or end is None:
        return ""
    return f"{start.text.strip()} ~ {end.text.strip()}"


def cycle(nodes: list[Node]) -> str:
    for node in nodes:
        if "radio_entrust_type" in node.resource_id and node.checked:
            return node.text.strip()
    return ""


def parse_funds(nodes: list[Node]) -> dict:
    funds = {}
    for resource_id, key in FUND_FIELDS:
        funds[key] = _text(find_by_id(nodes, resource_id))
    return funds


def parse_positions(nodes: list[Node]) -> list[dict]:
    """Read the native 持仓 list.

    Important: this view exposes the stock **name** and the market value, but
    not the 6-digit code — ``stock_code`` in this row actually holds 市值
    (e.g. ``27,264.00``).  So ``code`` is usually empty here; use the 委托/成交
    lists when a real code is needed.
    """
    scoped = _scoped(nodes, POSITION_RECYCLER_ID) or nodes
    positions: list[dict] = []
    current: dict[str, Node] | None = None
    for node in scoped:
        rid = node.resource_id.rsplit("/", 1)[-1]
        if rid == POSITION_ROW_ID:
            current = {}
            positions.append({"__nodes__": current})  # type: ignore[dict-item]
            continue
        if current is not None and rid:
            current.setdefault(rid, node)
    result = []
    for item in positions:
        raw: dict[str, Node] = item.pop("__nodes__")  # type: ignore[assignment]
        name = _text(raw.get(NAME_ID))
        if not name:
            continue
        value_text = _text(raw.get(CODE_ID))
        match = _CODE.search(value_text)
        row = {
            "name": name,
            # 只有当该列恰好显示 6 位代码时才填，否则留空。
            "code": match.group(0) if match and "," not in value_text else "",
            "market_value": _number(value_text),
        }
        for resource_id, key in POSITION_FIELDS:
            row[key] = _number(_text(raw.get(resource_id)))
        result.append(row)
    return result


class OrderBook:
    """Page object for the native 委托/成交/持仓 area."""

    def __init__(self, adb: Adb | None = None):
        self.adb = adb or Adb()

    def _snapshot(self) -> tuple[str, list[Node]]:
        return self.adb.current_focus(), self.adb.nodes()

    # ----- navigation ------------------------------------------------------
    def open(self, timeout: float = 20.0) -> list[Node]:
        """Make sure the native 委托/成交 page is visible, tapping the tab once."""
        _, nodes = self._snapshot()
        if find_by_id(nodes, ORDER_PAGE_ID) is not None:
            return nodes
        # 交易下单页（HtscNormalTradeActivity）里没有这个原生列表，先退回去。        if find_by_id(nodes, "trade_normal_viewpager") is not None:
            self.adb.keyevent(4)
            loaded = wait_until(
                lambda: (
                    lambda pair: pair[1]
                    if find_by_id(pair[1], ORDER_PAGE_ID)
                    or self._tab(pair[1], ORDER_TAB_TEXT)
                    else None
                )(self._snapshot()),
                timeout=timeout,
                interval=0.7,
            )
            if not loaded:
                raise OrderBookError("无法从交易页返回交易主页")
            nodes = loaded
            if find_by_id(nodes, ORDER_PAGE_ID) is not None:
                return nodes
        tab = self._tab(nodes, ORDER_TAB_TEXT)
        if tab is None:
            raise OrderBookError(
                "当前不是交易主页，找不到“委托/成交”标签；请先进入“交易”页"
            )
        self.adb.tap_node(tab)
        loaded = wait_until(
            lambda: (
                lambda pair: pair[1] if find_by_id(pair[1], ORDER_PAGE_ID) else None
            )(self._snapshot()),
            timeout=timeout,
            interval=0.7,
        )
        if not loaded:
            raise OrderBookError("打开“委托/成交”页面失败")
        return loaded

    def _tab(self, nodes: list[Node], text: str) -> Node | None:
        for node in nodes:
            if node.text == text and node.resource_id.endswith("tab_name"):
                return node
        return find_by_text(nodes, text)

    def select(self, key: str, timeout: float = 15.0) -> list[Node]:
        if key not in TAB_KEYS:
            raise ValueError(f"未知的查询页: {key}")
        label = TAB_KEYS[key]
        nodes = self.open()
        if active_tab(nodes) == label:
            return nodes
        tab = self._tab(nodes, label)
        if tab is None:
            raise OrderBookError(f"找不到“{label}”标签")
        self.adb.tap_node(tab)

        def switched():
            current = self._snapshot()[1]
            return current if active_tab(current) == label else None

        loaded = wait_until(switched, timeout=timeout, interval=0.6)
        if not loaded:
            raise OrderBookError(f"切换到“{label}”失败")
        return loaded

    def open_holdings(self, timeout: float = 15.0) -> list[Node]:
        _, nodes = self._snapshot()
        if find_by_id(nodes, POSITION_RECYCLER_ID) is not None:
            return nodes
        order_page = find_by_id(nodes, ORDER_PAGE_ID)
        if order_page is not None:
            tab = self._tab(nodes, HOLDING_TAB_TEXT)
            if tab is None:
                raise OrderBookError("找不到“持仓”标签")
            self.adb.tap_node(tab)
            loaded = wait_until(
                lambda: (
                    lambda pair: pair[1]
                    if find_by_id(pair[1], POSITION_RECYCLER_ID)
                    else None
                )(self._snapshot()),
                timeout=timeout,
                interval=0.6,
            )
            if not loaded:
                raise OrderBookError("切换到“持仓”失败")
            return loaded
        if find_by_id(nodes, POSITION_RECYCLER_ID) is None:
            raise OrderBookError("当前不在交易主页，读不到持仓")
        return nodes

    # ----- queries ---------------------------------------------------------
    def query(self, key: str) -> OrderList:
        nodes = self.select(key)
        kind = "trade" if key.endswith("trades") else "order"
        return OrderList(
            kind=kind,
            rows=parse_rows(nodes, kind),
            date_range=date_range(nodes),
            cycle=cycle(nodes),
        )

    def today_orders(self) -> OrderList:
        return self.query("today_orders")

    def today_trades(self) -> OrderList:
        return self.query("today_trades")

    def history_orders(self) -> OrderList:
        return self.query("history_orders")

    def history_trades(self) -> OrderList:
        return self.query("history_trades")

    def account(self) -> dict:
        nodes = self.open_holdings()
        return {
            "funds": parse_funds(nodes),
            "positions": parse_positions(nodes),
        }
