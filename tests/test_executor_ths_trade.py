import unittest

from executor.adb import parse_nodes
from executor.ths_trade import (
    cluster_rows,
    parse_deals,
    parse_funds,
    parse_orders,
    parse_positions,
    parse_stamp,
)

PKG = "com.hexin.plat.android:id/"


def node(text, rid="", bounds="[0,0][10,10]"):
    return (
        f'  <node text="{text}" resource-id="{PKG}{rid}" class="android.widget.TextView"'
        f' bounds="{bounds}" clickable="false" enabled="true" password="false"'
        f' checked="false" selected="false"/>\n'
    )


def order_row(top, state, direction="买入", filled="200"):
    off = top
    return (
        node("三孚股份", "result0", f"[8,{off}][346,{off+38}]")
        + node("20261030 13:42:57", "result1", f"[42,{off+38}][346,{off+76}]")
        + node("29.450", "result2", f"[370,{off-1}][563,{off+37}]")
        + node("29.450", "result3", f"[370,{off+37}][563,{off+76}]")
        + node("200", "first_tv", f"[587,{off-1}][781,{off+37}]")
        + node(filled, "second_tv", f"[587,{off+37}][781,{off+76}]")
        + node(direction, "result6", f"[805,{off-5}][1048,{off+33}]")
        + node(state, "result7", f"[805,{off+33}][1048,{off+81}]")
    )


ORDERS_XML = f"""<hierarchy rotation="1">
{order_row(399, "已成")}
{order_row(522, "已报", direction="卖出", filled="0")}
{order_row(645, "已撤", direction="撤买", filled="0")}
</hierarchy>
"""


def deal_row(top):
    return (
        node("三孚股份", "", f"[33,{top}][576,{top+48}]")
        + node("20261030 13:53:40", "", f"[67,{top+48}][576,{top+84}]")
        + node("29.450", "", f"[576,{top-16}][744,{top+100}]")
        + node("200", "", f"[744,{top-16}][912,{top+100}]")
        + node("买入", "", f"[912,{top}][1064,{top+48}]")
        + node("5890.000", "", f"[912,{top+48}][1064,{top+84}]")
    )


DEALS_XML = f"""<hierarchy rotation="1">
{node("", "recyclerview_id", "[0,480][1080,1817]")}
{deal_row(496)}
{deal_row(613)}
</hierarchy>
"""

POSITIONS_XML = f"""<hierarchy rotation="1">
{node("", "recyclerview_id", "[0,789][1080,1817]")}
{node("三孚股份", "", "[34,805][186,847]")}
{node("19,999.00", "", "[34,847][186,889]")}
{node("-15,032.42", "", "[219,805][414,847]")}
{node("-42.911%", "", "[219,847][414,889]")}
{node("700", "", "[430,805][625,847]")}
{node("700", "", "[430,847][625,889]")}
{node("50.045", "", "[641,805][853,847]")}
{node("28.570", "", "[641,847][853,889]")}
{node("-1,112.00", "", "[869,805][1047,847]")}
{node("-5.210%", "", "[869,847][1047,889]")}
</hierarchy>
"""

FUNDS_XML = f"""<hierarchy rotation="1">
{node("21,695.65", "capital_value_text", "[42,370][540,414]")}
{node("-15,032.42", "yingkui_value_text", "[582,370][1080,414]")}
{node("19,999.00", "shizhi_value_text", "[42,517][540,561]")}
{node("-1,112.00", "dryk_value_text", "[582,517][732,561]")}
{node("-4.88%", "drykb_value_text", "[732,527][817,560]")}
</hierarchy>
"""


class OrderParsingTests(unittest.TestCase):
    def test_parses_three_rows_with_state_and_side(self):
        orders = parse_orders(parse_nodes(ORDERS_XML))

        self.assertEqual(len(orders), 3)
        first = orders[0]
        self.assertEqual(first.name, "三孚股份")
        self.assertEqual(first.date, "2026-10-30")
        self.assertEqual(first.time, "13:42:57")
        self.assertEqual(first.price, 29.45)
        self.assertEqual(first.quantity, 200)
        self.assertEqual(first.filled, 200)
        self.assertEqual(first.side, "buy")
        self.assertEqual(first.state, "已成")
        self.assertFalse(first.cancellable)

        self.assertTrue(orders[1].cancellable, "已报且未成交，可以撤单")
        self.assertEqual(orders[1].side, "sell")
        self.assertFalse(orders[2].cancellable, "已撤不能再撤")

    def test_stamp_parsing(self):
        self.assertEqual(parse_stamp("20261030 13:42:57"), ("2026-10-30", "13:42:57"))
        self.assertEqual(parse_stamp("--"), ("--", ""))


class DealParsingTests(unittest.TestCase):
    def test_parses_deals_in_document_order(self):
        nodes = parse_nodes(DEALS_XML)
        deals = parse_deals(nodes, (0, 480, 1080, 1817))

        self.assertEqual(len(deals), 2)
        first = deals[0]
        self.assertEqual(first.name, "三孚股份")
        self.assertEqual(first.date, "2026-10-30")
        self.assertEqual(first.time, "13:53:40")
        self.assertEqual(first.price, 29.45)
        self.assertEqual(first.quantity, 200)
        self.assertEqual(first.direction, "买入")
        self.assertEqual(first.amount, 5890.0)
        self.assertEqual(deals[1].date, "2026-10-30")


class PositionParsingTests(unittest.TestCase):
    def test_parses_holdings(self):
        positions = parse_positions(parse_nodes(POSITIONS_XML), (0, 789, 1080, 1817))

        self.assertEqual(len(positions), 1)
        item = positions[0]
        self.assertEqual(item["name"], "三孚股份")
        self.assertEqual(item["market_value"], 19999.0)
        self.assertEqual(item["quantity"], 700.0)
        self.assertEqual(item["sellable"], 700.0)
        self.assertEqual(item["cost"], 50.045)
        self.assertEqual(item["price"], 28.57)
        self.assertEqual(item["profit_ratio"], -42.911)


class FundParsingTests(unittest.TestCase):
    def test_reads_capital_card(self):
        funds = parse_funds(parse_nodes(FUNDS_XML))

        self.assertEqual(funds["total_assets"], "21,695.65")
        self.assertEqual(funds["holding_profit"], "-15,032.42")
        self.assertEqual(funds["market_value"], "19,999.00")
        self.assertEqual(funds["today_profit"], "-1,112.00")
        self.assertEqual(funds["today_ratio"], "-4.88%")


class ClusterTests(unittest.TestCase):
    def test_splits_rows_but_keeps_document_order(self):
        nodes = parse_nodes(DEALS_XML)
        rows = cluster_rows(nodes, (0, 480, 1080, 1817))

        self.assertEqual(len(rows), 2)
        self.assertEqual([n.text for n in rows[0]][:3], ["三孚股份", "20261030 13:53:40", "29.450"])


if __name__ == "__main__":
    unittest.main()
