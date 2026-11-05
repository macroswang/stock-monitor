import unittest
from unittest.mock import Mock, patch

from executor.adb import parse_nodes
from executor.ths import (
    ThsError,
    ThsTrade,
    login_panel,
    mask_account,
    panel_open,
    read_status,
)

PKG = "com.hexin.plat.android:id/"


def node(text, rid="", bounds="[0,0][10,10]", desc="", clickable="false", cls="android.widget.TextView"):
    return (
        f'  <node text="{text}" resource-id="{PKG}{rid}" class="{cls}" content-desc="{desc}"'
        f' bounds="{bounds}" clickable="{clickable}" enabled="true" password="false"'
        f' checked="false" selected="false"/>\n'
    )


TRADE_PAGE_XML = f"""<hierarchy rotation="1">
{node("", "tab_a", "[113,60][274,132]", clickable="true")}
{node("", "nobindlist", "[0,144][1080,284]")}
{node("中国银河证券", "txt_qsname", "[160,166][364,216]")}
{node("k客户号", "txt_account", "[160,222][251,261]")}
{node("4004****0162", "txt_account_value", "[251,222][426,254]")}
{node("", "frontview_account_info", "[126,166][1046,261]", clickable="true", cls="android.widget.RelativeLayout")}
{node("添加账户", "btn_add", "[0,305][540,405]", clickable="true")}
{node("账户管理", "btn_manage", "[540,305][1080,405]", clickable="true")}
{node("", "", "[536,1818][724,1920]", desc="交易", clickable="true", cls="android.widget.RelativeLayout")}
</hierarchy>
"""

PANEL_XML = f"""<hierarchy rotation="1">
{node("", "login_component_base_view", "[0,986][1080,1920]")}
{node("", "close_button", "[0,986][92,1087]", clickable="true", cls="android.widget.LinearLayout")}
{node("中国银河证券", "qs_name", "[475,995][643,1043]")}
{node("**0162", "account", "[475,1043][565,1077]")}
{node("请输入交易密码", "weituo_edit_trade_password", "[138,1088][1050,1180]",
      clickable="true", cls="android.widget.EditText")}
{node("登录", "weituo_btn_login", "[30,1205][1050,1297]")}
</hierarchy>
"""


def panel_ready_xml(bullets: int) -> str:
    """The 登录 button turns clickable once the password is typed."""
    masked = "\u2022" * bullets
    return f"""<hierarchy rotation="1">
{node("", "login_component_base_view", "[0,986][1080,1920]")}
{node("中国银河证券", "qs_name", "[475,995][643,1043]")}
{node("**0162", "account", "[475,1043][565,1077]")}
{node(masked, "weituo_edit_trade_password", "[138,1088][1050,1180]",
      clickable="true", cls="android.widget.EditText")}
{node("登录", "weituo_btn_login", "[30,1205][1050,1297]", clickable="true")}
</hierarchy>
"""

LOGGED_IN_XML = f"""<hierarchy rotation="1">
{node("中国银河证券", "qs_name_text")}
{node("k客户号 4004****0162", "account_text")}
{node("12,345.67", "capital_value_text")}
{node("买入", "menu_buy", clickable="true")}
{node("", "nobindlist", "[0,144][1080,284]")}
{node("买入", "", "[0,300][270,380]", clickable="true")}
{node("卖出", "", "[270,300][540,380]", clickable="true")}
{node("撤单", "", "[540,300][810,380]", clickable="true")}
{node("可用", "", "[0,400][200,440]")}
{node("12,345.67", "", "[200,400][600,440]")}
{node("", "", "[536,1818][724,1920]", desc="交易", clickable="true", cls="android.widget.RelativeLayout")}
</hierarchy>
"""

FOCUS = "Window{5e6fd82 u0 com.hexin.plat.android/com.hexin.plat.android.Hexin}"
OTHER_FOCUS = "Window{111 u0 com.lphtsccft/com.lphtsccft.zhangle.main.MainActivity}"


class FakeAdb:
    def __init__(self, xml, focus=FOCUS, after_input=None, after_tap=None):
        self.xml = xml
        self.after_input = after_input
        self.after_tap = after_tap
        self.focus = focus
        self.typed = None
        self.opened = False
        self.calls = []

    def current_focus(self):
        return self.focus

    def nodes(self, retries: int = 3):
        if self.opened and self.after_tap is not None:
            return parse_nodes(self.after_tap)
        if self.typed is not None and self.after_input is not None:
            return parse_nodes(self.after_input)
        return parse_nodes(self.xml)

    def tap_node(self, node):
        self.calls.append(("tap", node.text))
        if self.after_tap is not None and node.resource_id.endswith(
            ("frontview_account_info", "nobindlist")
        ):
            self.opened = True

    def tap(self, x, y):
        self.calls.append(("tap_xy", x, y))

    def input_text(self, text):
        self.calls.append(("input", text))
        self.typed = text

    def clear_text(self, length=24):
        self.calls.append(("clear", length))

    def keyevent(self, code):
        self.calls.append(("key", code))

    def start_app(self, activity, package):
        self.calls.append(("start", package))


class MaskAccountTests(unittest.TestCase):
    def test_masks_like_tonghuashun(self):
        self.assertEqual(mask_account("4004000000000162"), "4004****0162")
        self.assertEqual(mask_account("40040162"), "4004****0162")
        self.assertEqual(mask_account("123456789"), "1234****6789")
        self.assertEqual(mask_account("123"), "****")


class ReadStatusTests(unittest.TestCase):
    def test_buy_text_alone_does_not_prove_logged_in(self):
        status = read_status(parse_nodes(f'<hierarchy>{node("买入")}</hierarchy>'), FOCUS)
        self.assertIsNot(status.logged_in, True)

    def test_other_app_cannot_be_logged_in(self):
        self.assertIsNot(read_status(parse_nodes(LOGGED_IN_XML), OTHER_FOCUS).logged_in, True)
    def test_logged_out_trade_page(self):
        status = read_status(parse_nodes(TRADE_PAGE_XML), FOCUS)

        self.assertTrue(status.app_foreground)
        self.assertTrue(status.on_trade_tab)
        self.assertFalse(status.login_panel_open)
        self.assertEqual(status.broker_name, "中国银河证券")
        self.assertEqual(status.account_masked, "4004****0162")
        self.assertIsNone(status.logged_in, "未登录且无面板时不能武断判断")

    def test_login_panel_is_not_logged_in(self):
        nodes = parse_nodes(PANEL_XML)
        status = read_status(nodes, FOCUS)

        self.assertTrue(panel_open(nodes))
        self.assertFalse(status.logged_in)
        self.assertIn("交易密码", status.reason)
        self.assertEqual(login_panel(nodes)["account_masked"], "**0162")

    def test_logged_in_page_is_detected(self):
        status = read_status(parse_nodes(LOGGED_IN_XML), FOCUS)
        self.assertTrue(status.logged_in)

    def test_other_app_is_not_foreground(self):
        status = read_status(parse_nodes(TRADE_PAGE_XML), OTHER_FOCUS)
        self.assertFalse(status.app_foreground)


class EnsureLoginTests(unittest.TestCase):
    def test_incomplete_signed_in_identity_is_reread_without_actions(self):
        for missing in ('qs_name_text', 'account_text'):
            initial = '\n'.join(line for line in LOGGED_IN_XML.splitlines() if f'id/{missing}"' not in line)
            adb = Mock()
            adb.current_focus.return_value = FOCUS
            adb.nodes.side_effect = [parse_nodes(initial), parse_nodes(LOGGED_IN_XML)]
            with self.subTest(missing=missing), patch('executor.ths.time.sleep'):
                result = ThsTrade(adb).ensure_logged_in(account='4004000000000162', password=None)
                self.assertTrue(result['account_verified'])
                self.assertEqual(adb.nodes.call_count, 2)
                adb.input_text.assert_not_called()
                adb.tap_node.assert_not_called()
                adb.keyevent.assert_not_called()

    def test_incomplete_signed_in_identity_stops_after_bounded_reads(self):
        initial = '\n'.join(line for line in LOGGED_IN_XML.splitlines() if 'id/account_text"' not in line)
        adb = Mock()
        adb.current_focus.return_value = FOCUS
        adb.nodes.return_value = parse_nodes(initial)
        with patch('executor.ths.time.sleep'), self.assertRaisesRegex(ThsError, '未加载完整'):
            ThsTrade(adb).ensure_logged_in(account='4004000000000162', password=None)
        self.assertEqual(adb.nodes.call_count, 3)
        adb.input_text.assert_not_called()
        adb.tap_node.assert_not_called()

    def test_explicit_wrong_signed_in_identity_is_never_retried(self):
        for xml in (LOGGED_IN_XML.replace('4004****0162', '4004****9999'), LOGGED_IN_XML.replace('中国银河证券', '其他证券')):
            adb = Mock()
            adb.current_focus.return_value = FOCUS
            adb.nodes.return_value = parse_nodes(xml)
            with self.subTest(xml=xml), self.assertRaisesRegex(ThsError, '不一致'):
                ThsTrade(adb).ensure_logged_in(account='4004000000000162', password=None)
            self.assertEqual(adb.nodes.call_count, 1)
            adb.input_text.assert_not_called()
            adb.tap_node.assert_not_called()

    def test_identity_reread_that_reveals_wrong_account_stops(self):
        initial = '\n'.join(line for line in LOGGED_IN_XML.splitlines() if 'id/account_text"' not in line)
        adb = Mock()
        adb.current_focus.return_value = FOCUS
        adb.nodes.side_effect = [parse_nodes(initial), parse_nodes(LOGGED_IN_XML.replace('4004****0162', '4004****9999'))]
        with patch('executor.ths.time.sleep'), self.assertRaisesRegex(ThsError, '不一致'):
            ThsTrade(adb).ensure_logged_in(account='4004000000000162', password=None)
        self.assertEqual(adb.nodes.call_count, 2)
        adb.input_text.assert_not_called()
        adb.tap_node.assert_not_called()

    def test_already_logged_in_is_a_noop(self):
        adb = FakeAdb(LOGGED_IN_XML)
        result = ThsTrade(adb).ensure_logged_in(account="4004000000000162", password="123456")

        self.assertTrue(result["already"])
        self.assertEqual(adb.calls, [], "已登录时不应该输入任何内容")

    def test_account_mismatch_aborts_before_typing(self):
        adb = FakeAdb(PANEL_XML)
        with self.assertRaises(ThsError) as caught:
            ThsTrade(adb).ensure_logged_in(account="4004999999999999", password="123456")

        self.assertIn("不一致", str(caught.exception))
        self.assertEqual(adb.calls, [], "账户不匹配时绝不能提交密码")

    def test_known_account_fills_password_and_taps_login(self):
        adb = FakeAdb(PANEL_XML, after_input=panel_ready_xml(6))
        with self.assertRaises(ThsError):
            # 面板始终不关闭 → 结果未知；这里只验证输入与点击顺序
            ThsTrade(adb).ensure_logged_in(account="4004000000000162", password="123456", timeout=0.1)

        kinds = [call[0] for call in adb.calls]
        self.assertIn("input", kinds)
        self.assertEqual(kinds[-1], "tap")
        self.assertEqual(adb.calls[-1][1], "登录")

    def test_truncated_password_is_refused_before_login(self):
        adb = FakeAdb(PANEL_XML, after_input=panel_ready_xml(5))
        with self.assertRaises(ThsError) as caught:
            ThsTrade(adb).ensure_logged_in(account="4004000000000162", password="123456", timeout=0.2)

        self.assertIn("不一致", str(caught.exception))
        self.assertNotIn(("tap", "登录"), adb.calls)

    def test_opens_login_panel_by_tapping_account_card(self):
        adb = FakeAdb(TRADE_PAGE_XML, after_tap=PANEL_XML)
        with self.assertRaises(ThsError):
            ThsTrade(adb).ensure_logged_in(
                account="4004000000000162", password="123456", timeout=0.2
            )

        kinds = [call[0] for call in adb.calls]
        self.assertEqual(kinds[0], "tap", "应当先点账户卡片把密码面板打开")
        self.assertIn("input", kinds)

    def test_dry_run_does_not_tap_login(self):
        adb = FakeAdb(PANEL_XML, after_input=panel_ready_xml(6))
        result = ThsTrade(adb).ensure_logged_in(
            account="4004000000000162", password="123456", dry_run=True
        )

        self.assertTrue(result["dry_run"])
        self.assertNotIn(("tap", "登录"), adb.calls)
        self.assertEqual(result["account_masked"], "4004****0162")


if __name__ == "__main__":
    unittest.main()
