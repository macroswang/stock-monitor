"""同花顺（银河）已登录交易页：资金、持仓、委托、成交。

沿用 :mod:`executor.ths` 的导航，只处理**已登录**后的原生页面。
所有节点都是原生控件，不截图、不做 OCR。

交易主页::

    capital_value_text   总资产
    yingkui_value_text   浮动盈亏
    shizhi_value_text    总市值
    dryk_value_text      当日参考盈亏      drykb_value_text  -4.88%
    menu_buy / menu_sale / menu_withdrawal / menu_holdings / menu_search

    「持仓」页
      capital_cell_title + capital_cell_value（总资产/浮动盈亏/当日参考盈亏/总市值/可用/可取）
      recyclerview_id 里每个持仓行：名称、市值、盈亏、盈亏%、持仓、可用、成本、现价、当日盈亏、当日%

    「查询」页
      当日成交 drcj / 当日委托 drwt / 历史成交 lscj / 历史委托 lswt
      委托行：result0 名称 / result1 时间 / result2 委托价 / result3 均价
              first_tv 委托量 / second_tv 成交量 / result6 买卖 / result7 状态
      成交行：名称 / 时间 / 成交价 / 成交量 / 买卖 / 成交额

已知限制：委托和成交列表**都不显示股票代码**，只有名称；持仓行也没有代码。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .adb import Adb, Node, find_by_id, find_by_text, wait_until
from .ths import ThsError, ThsTrade, panel_open

QUERY_MENU = {
    "today_trades": "当日成交",
    "today_orders": "当日委托",
    "history_trades": "历史成交",
    "history_orders": "历史委托",
}
MENU_IDS = {"today_trades": "drcj", "today_orders": "drwt", "history_trades": "lscj", "history_orders": "lswt"}

TRADE_HOME_ID = "capital_value_text"
QUERY_NAV_ID = "navi_buttonbar"
QUERY_ROW_ID = "result0"
EMPTY_TIPS_ID = "empty_tips"
POSITION_LIST_ID = "recyclerview_id"

ORDER_FIELDS = {
    "result0": "name",
    "result1": "time",
    "result2": "price",
    "result3": "average",
    "first_tv": "quantity",
    "second_tv": "filled",
    "result6": "direction",
    "result7": "state",
}

CANCELLABLE_STATES = ("已报", "部成", "未报", "待报", "已报待撤")

_NUMBER = re.compile(r"-?[\d,]+(?:\.\d+)?")
_STAMP = re.compile(r"(\d{8})\s+(\d{2}:\d{2}:\d{2})")


def _text(node: Node | None) -> str:
    return node.text.strip() if node is not None else ""


def _number(text: str) -> float | None:
    match = _NUMBER.search(text.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _inside(node: Node, bounds: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = node.bounds
    bx1, by1, bx2, by2 = bounds
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return bx1 <= cx <= bx2 and by1 <= cy <= by2


def cluster_rows(nodes: list[Node], bounds: tuple[int, int, int, int], gap: int = 60) -> list[list[Node]]:
    """Group text nodes into visual rows.

    The 委托/成交/持仓 lists expose no row container id, so rows are rebuilt
    from coordinates.  Nodes stay in **document order** inside a row (that is
    how the field order is defined); a node whose vertical centre is more than
    ``gap`` below the current row's lowest centre starts a new row.
    """
    items = [node for node in nodes if node.text.strip() and _inside(node, bounds)]
    rows: list[list[Node]] = []
    current: list[Node] = []
    row_bottom: int | None = None
    for node in items:
        center_y = (node.bounds[1] + node.bounds[3]) // 2
        if row_bottom is not None and center_y > row_bottom + gap:
            rows.append(current)
            current = []
            row_bottom = None
        current.append(node)
        row_bottom = center_y if row_bottom is None else max(row_bottom, center_y)
    if current:
        rows.append(current)
    return rows


@dataclass(frozen=True)
class ThsOrder:
    name: str
    date: str
    time: str
    price: float | None
    average: float | None
    quantity: float | None
    filled: float | None
    direction: str
    state: str

    @property
    def side(self) -> str | None:
        if "买" in self.direction:
            return "buy"
        if "卖" in self.direction:
            return "sell"
        return None

    @property
    def cancellable(self) -> bool:
        return self.state in CANCELLABLE_STATES and (
            self.filled is None or self.quantity is None or self.filled < self.quantity
        )

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "date": self.date,
            "time": self.time,
            "price": self.price,
            "average": self.average,
            "quantity": self.quantity,
            "filled": self.filled,
            "direction": self.direction,
            "side": self.side,
            "state": self.state,
            "cancellable": self.cancellable,
        }


@dataclass(frozen=True)
class ThsDeal:
    name: str
    date: str
    time: str
    price: float | None
    quantity: float | None
    direction: str
    amount: float | None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "date": self.date,
            "time": self.time,
            "price": self.price,
            "quantity": self.quantity,
            "direction": self.direction,
            "amount": self.amount,
        }


def parse_stamp(text: str) -> tuple[str, str]:
    match = _STAMP.search(text)
    if not match:
        return text.strip(), ""
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}", match.group(2)


def parse_orders(nodes: list[Node]) -> list[ThsOrder]:
    """委托列表按 ``result0`` 切行；每行字段都有固定 resource-id。"""
    rows: list[dict[str, Node]] = []
    current: dict[str, Node] | None = None
    for node in nodes:
        rid = node.resource_id.rsplit("/", 1)[-1]
        if rid == QUERY_ROW_ID:
            current = {"result0": node}
            rows.append(current)
            continue
        if current is not None and rid in ORDER_FIELDS:
            current.setdefault(rid, node)
    orders = []
    for raw in rows:
        name = _text(raw.get("result0"))
        if not name:
            continue
        date, clock = parse_stamp(_text(raw.get("result1")))
        orders.append(
            ThsOrder(
                name=name,
                date=date,
                time=clock,
                price=_number(_text(raw.get("result2"))),
                average=_number(_text(raw.get("result3"))),
                quantity=_number(_text(raw.get("first_tv"))),
                filled=_number(_text(raw.get("second_tv"))),
                direction=_text(raw.get("result6")),
                state=_text(raw.get("result7")),
            )
        )
    return orders


def parse_deals(nodes: list[Node], bounds: tuple[int, int, int, int]) -> list[ThsDeal]:
    """成交列表没有 resource-id，按坐标切行，再按文档顺序取字段。"""
    deals = []
    for row in cluster_rows(nodes, bounds):
        texts = [node.text.strip() for node in row]
        if len(texts) < 6:
            continue
        name = texts[0]
        date, clock = parse_stamp(texts[1])
        if not date:
            continue
        deals.append(
            ThsDeal(
                name=name,
                date=date,
                time=clock,
                price=_number(texts[2]),
                quantity=_number(texts[3]),
                direction=texts[4],
                amount=_number(texts[5]),
            )
        )
    return deals


def parse_positions(nodes: list[Node], bounds: tuple[int, int, int, int]) -> list[dict]:
    keys = ("name", "market_value", "profit", "profit_ratio", "quantity", "sellable", "cost", "price", "today_profit", "today_ratio")
    positions = []
    for row in cluster_rows(nodes, bounds):
        texts = [node.text.strip() for node in row]
        if len(texts) < 7:
            continue
        item = {"name": texts[0]}
        for key, value in zip(keys[1:], texts[1:]):
            item[key] = _number(value)
        if item.get("quantity") is None:
            continue
        positions.append(item)
    return positions


def parse_funds(nodes: list[Node]) -> dict:
    """交易主页的资金卡片（id 固定）。"""
    return {
        "total_assets": _text(find_by_id(nodes, "capital_value_text")),
        "holding_profit": _text(find_by_id(nodes, "yingkui_value_text")),
        "market_value": _text(find_by_id(nodes, "shizhi_value_text")),
        "today_profit": _text(find_by_id(nodes, "dryk_value_text")),
        "today_ratio": _text(find_by_id(nodes, "drykb_value_text")),
    }


class ThsQuery:
    """已登录后的交易页操作。"""

    def __init__(self, adb: Adb | None = None):
        self.adb = adb or Adb()
        self.ths = ThsTrade(self.adb)

    def _snapshot(self) -> tuple[str, list[Node]]:
        return self.adb.current_focus(), self.adb.nodes()

    def open_home(self, timeout: float = 20.0) -> list[Node]:
        nodes = self.ths.open_trade_tab(timeout=timeout)
        if panel_open(nodes):
            raise ThsError("交易模块未登录，请先登录")
        if find_by_id(nodes, TRADE_HOME_ID) is None:
            raise ThsError("当前不是交易主页，请先回到“交易”标签")
        return nodes

    def _tap_text(self, nodes: list[Node], text: str, timeout: float = 15.0) -> list[Node]:
        node = find_by_text(nodes, text)
        if node is None:
            raise ThsError(f"找不到“{text}”入口")
        self.adb.tap_node(node)

        def changed():
            _, current = self._snapshot()
            return current if not _same_screen(current, nodes) else None

        loaded = wait_until(changed, timeout=timeout, interval=0.6) or self._snapshot()[1]
        return loaded

    def account(self) -> dict:
        nodes = self.open_home()
        funds = parse_funds(nodes)
        nodes = self._tap_text(nodes, "持仓")
        holdings = find_by_id(nodes, POSITION_LIST_ID)
        positions = []
        if holdings is not None:
            positions = parse_positions(nodes, holdings.bounds)
        return {"funds": funds, "positions": positions}

    def query(self, key: str) -> dict:
        if key not in QUERY_MENU:
            raise ValueError(f"未知的查询页: {key}")
        nodes = self.open_home()
        nodes = self._tap_text(nodes, "查询")
        nodes = self._tap_text(nodes, QUERY_MENU[key])

        if key.endswith("orders"):
            orders = parse_orders(nodes)
            return {
                "kind": "order",
                "count": len(orders),
                "cancellable_count": len([o for o in orders if o.cancellable]),
                "rows": [o.as_dict() for o in orders],
            }

        list_node = find_by_id(nodes, POSITION_LIST_ID)
        bounds = list_node.bounds if list_node is not None else (0, 480, 1080, 1817)
        deals = parse_deals(nodes, bounds)
        return {"kind": "trade", "count": len(deals), "rows": [d.as_dict() for d in deals]}


def _same_screen(a: list[Node], b: list[Node]) -> bool:
    """Cheap change detector: compare the set of visible texts."""
    ta = {node.text for node in a if node.text}
    tb = {node.text for node in b if node.text}
    return ta == tb
