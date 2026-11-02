import unittest

from executor.adb import parse_nodes
from executor.orderbook import (
    active_tab,
    cycle,
    date_range,
    is_empty,
    parse_funds,
    parse_positions,
    parse_rows,
)

PKG = "com.lphtsccft:id/"


def node(text, rid, bounds, clickable="false", checked="false", selected="false"):
    return (
        f'  <node text="{text}" resource-id="{PKG}{rid}" class="android.widget.TextView"'
        f' bounds="{bounds}" clickable="{clickable}" enabled="true" password="false"'
        f' checked="{checked}" selected="{selected}"/>\n'
    )


ROW_1 = [
    ("", "stock_main_item", "[36,976][1044,1096]"),
    ("山子高科", "stock_name", "[36,996][288,1040]"),
    ("卖出", "item_trade_dir", "[288,996][439,1040]"),
    ("2026-10-30", "item_trade_trust_date", "[439,996][641,1040]"),
    ("2.250", "item_trade_trust_num", "[641,996][893,1040]"),
    ("000981", "stock_code", "[36,1046][288,1076]"),
    ("13:07:02", "item_trade_trust_time", "[439,1046][641,1076]"),
    ("2,300 | 0", "item_trade_trust_success", "[641,1046][893,1076]"),
    ("已报", "item_trade_trust_state", "[893,976][1044,1096]"),
]

ROW_2 = [
    ("", "stock_main_item", "[36,1098][1044,1218]"),
    ("山子高科", "stock_name", "[36,1118][288,1162]"),
    ("买入", "item_trade_dir", "[288,1118][439,1162]"),
    ("2026-10-29", "item_trade_trust_date", "[439,1118][641,1162]"),
    ("2.270", "item_trade_trust_num", "[641,1118][893,1162]"),
    ("000981", "stock_code", "[36,1168][288,1198]"),
    ("11:16:21", "item_trade_trust_time", "[439,1168][641,1198]"),
    ("2,000 | 2,000", "item_trade_trust_success", "[641,1168][893,1198]"),
    ("已成", "item_trade_trust_state", "[893,1098][1044,1218]"),
]

ROW_3 = [
    ("", "stock_main_item", "[36,1220][1044,1340]"),
    ("山子高科", "stock_name", "[36,1240][288,1284]"),
    ("撤卖", "item_trade_dir", "[288,1240][439,1284]"),
    ("2026-10-28", "item_trade_trust_date", "[439,1240][641,1284]"),
    ("2.320", "item_trade_trust_num", "[641,1240][893,1284]"),
    ("000981", "stock_code", "[36,1290][288,1320]"),
    ("09:51:06", "item_trade_trust_time", "[439,1290][641,1320]"),
    ("4,000 | 0", "item_trade_trust_success", "[641,1290][893,1320]"),
    ("已撤", "item_trade_trust_state", "[893,1220][1044,1340]"),
]


def build_rows_xml(*rows):
    body = node("", "inner_order_recycler", "[0,976][1080,1808]")
    for row in rows:
        body += "".join(node(*item) for item in row)
    return f"<hierarchy rotation=\"1\">\n{body}</hierarchy>"


TRADES_XML = f"""<hierarchy rotation="1">
{node("", "inner_order_recycler", "[0,1043][1080,1808]")}
{node("", "stock_main_item", "[36,1043][1044,1163]", clickable="true")}
{node("山子高科", "stock_name", "[36,1063][288,1107]")}
{node("买入", "item_trade_dir", "[288,1063][439,1107]")}
{node("2026-10-29", "item_trade_trust_date", "[439,1063][641,1107]")}
{node("2.270", "item_trade_trust_price", "[641,1063][893,1107]")}
{node("000981", "stock_code", "[36,1113][288,1143]")}
{node("13:46:37", "item_trade_trust_time", "[439,1113][641,1143]")}
{node("2,000.00", "item_trade_trust_success", "[641,1113][893,1143]")}
{node("", "stock_main_item", "[36,1165][1044,1285]", clickable="true")}
{node("山子高科", "stock_name", "[36,1185][288,1229]")}
{node("卖出", "item_trade_dir", "[288,1185][439,1229]")}
{node("2026-10-28", "item_trade_trust_date", "[439,1185][641,1229]")}
{node("2.320", "item_trade_trust_price", "[641,1185][893,1229]")}
{node("000981", "stock_code", "[36,1235][288,1265]")}
{node("10:20:29", "item_trade_trust_time", "[439,1235][641,1265]")}
{node("-2,000.00", "item_trade_trust_success", "[641,1235][893,1265]")}
</hierarchy>
"""

PAGE_XML = f"""<hierarchy rotation="1">
{node("持仓", "tab_name", "[42,743][106,775]")}
{node("委托/成交", "tab_name", "[146,740][306,777]", selected="true")}
{node("今日委托", "tab_name", "[36,819][172,869]", selected="true")}
{node("今日成交", "tab_name", "[188,819][324,869]")}
{node("历史委托", "tab_name", "[340,819][476,869]")}
{node("历史成交", "tab_name", "[492,819][628,869]")}
{node("2026-10-26", "start_time", "[36,904][501,952]")}
{node("2026-11-01", "end_time", "[579,904][1044,952]")}
{node("竞价交易", "radio_entrust_type_1", "[36,904][180,952]", clickable="true", checked="true")}
{node("盘后固定价格交易", "radio_entrust_type_2", "[204,904][452,952]", clickable="true")}
{node("没有数据", "sub_tv1", "[488,1340][592,1366]")}
</hierarchy>
"""

ACCOUNT_XML = f"""<hierarchy rotation="1">
{node("27,400.58", "zzc_value", "[36,856][906,916]")}
{node("-1,408.00", "jr_value", "[36,962][372,1014]")}
{node("-19,049.81", "ccsy_value", "[372,962][708,1014]")}
{node("27,264.00", "zsz_value", "[708,962][1044,1014]")}
{node("136.58", "ky_value", "[36,1060][372,1112]")}
{node("136.58", "kq_value", "[372,1060][708,1112]")}
{node("99.50%", "zcw_value", "[708,1060][1044,1112]")}
{node("", "fund_recycler", "[0,814][1080,1808]")}
{node("", "content_layout", "[0,1214][1080,1334]")}
{node("山子高科", "stock_name", "[36,1232][226,1272]")}
{node("27,264.00", "stock_code", "[36,1276][222,1316]")}
{node("-19,049.81", "item_sz", "[230,1232][386,1272]")}
{node("-41.13%", "item_cw", "[230,1276][386,1316]")}
{node("12,800", "item_xj", "[386,1232][542,1272]")}
{node("10,500", "item_cb", "[386,1276][542,1316]")}
{node("2.130", "item_jryk", "[542,1232][698,1272]")}
{node("3.618", "item_ykbl", "[542,1276][698,1316]")}
{node("-1,408.00", "item_5_top", "[698,1232][854,1272]")}
{node("-4.91%", "item_5_bottom", "[698,1276][854,1316]")}
</hierarchy>
"""


class OrderBookParseTests(unittest.TestCase):
    def test_current_native_aliases_do_not_hide_an_existing_filled_order(self):
        xml=build_rows_xml(ROW_1)
        for old,new in [('item_trade_trust_state','item_trade_state'),('item_trade_trust_success','item_trade_success'),('item_trade_trust_time','item_trade_time'),('item_trade_trust_num','item_trade_trust_price')]:
            xml=xml.replace(old,new)
        xml=xml.replace('2,300 | 0','2,300').replace('已报','已成')
        rows=parse_rows(parse_nodes(xml),'order')
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0].code,rows[0].quantity,rows[0].filled,rows[0].state),('000981',2300,2300,'已成'))

    def test_parses_order_rows_and_flags_cancellable(self):
        nodes = parse_nodes(build_rows_xml(ROW_1, ROW_2, ROW_3))
        rows = parse_rows(nodes, "order")

        self.assertEqual([row.state for row in rows], ["已报", "已成", "已撤"])
        self.assertEqual(rows[0].code, "000981")
        self.assertEqual(rows[0].direction, "卖出")
        self.assertEqual(rows[0].side, "sell")
        self.assertEqual(rows[0].price, 2.25)
        self.assertEqual(rows[0].quantity, 2300)
        self.assertEqual(rows[0].filled, 0)
        self.assertTrue(rows[0].cancellable)

        self.assertFalse(rows[1].cancellable, "已成交不能撤")
        self.assertFalse(rows[2].cancellable, "已撤单不能撤")

    def test_cancelled_direction_still_parses_as_sell(self):
        rows = parse_rows(parse_nodes(build_rows_xml(ROW_3)), "order")
        self.assertEqual(rows[0].side, "sell")
        self.assertTrue(rows[0].cancelled)

    def test_parses_trade_rows_and_abs_quantity(self):
        rows = parse_rows(parse_nodes(TRADES_XML), "trade")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].side, "buy")
        self.assertEqual(rows[0].price, 2.27)
        self.assertEqual(rows[0].quantity, 2000)
        self.assertIsNone(rows[0].filled)
        self.assertEqual(rows[1].side, "sell")
        self.assertEqual(rows[1].quantity, 2000, "卖出成交数量为负数时需要取绝对值")
        self.assertEqual(rows[1].price, 2.32)
        self.assertFalse(rows[1].cancellable, "成交记录永远不可撤")

    def test_empty_state_and_active_tab(self):
        nodes = parse_nodes(PAGE_XML)

        self.assertEqual(active_tab(nodes), "今日委托")
        self.assertTrue(is_empty(nodes))
        self.assertEqual(date_range(nodes), "2026-10-26 ~ 2026-11-01")
        self.assertEqual(cycle(nodes), "竞价交易")

    def test_parse_funds_and_positions(self):
        nodes = parse_nodes(ACCOUNT_XML)
        funds = parse_funds(nodes)
        positions = parse_positions(nodes)

        self.assertEqual(funds["total_assets"], "27,400.58")
        self.assertEqual(funds["available"], "136.58")
        self.assertEqual(funds["position_ratio"], "99.50%")

        self.assertEqual(len(positions), 1)
        position = positions[0]
        self.assertEqual(
            position["code"], "", "持仓行不显示代码，节点里的 stock_code 其实是市值"
        )
        self.assertEqual(position["name"], "山子高科")
        self.assertEqual(position["market_value"], 27264.0)
        self.assertEqual(position["quantity"], 12800.0)
        self.assertEqual(position["sellable"], 10500.0)
        self.assertEqual(position["price"], 2.13)
        self.assertEqual(position["cost"], 3.618)


if __name__ == "__main__":
    unittest.main()
