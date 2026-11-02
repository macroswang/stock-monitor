import unittest

from executor.adb import Node, find_by_id, parse_nodes
from executor.zhangle import (
    _error_reason,
    _manual_reason,
    has_consent_dialog,
    is_logged_in,
    is_login_screen,
    is_trade_locked,
    is_trade_page,
    mask_account,
)

LOGIN_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
  <node text="登录后继续操作" resource-id="com.lphtsccft:id/finger_login_text"
        class="android.widget.TextView" bounds="[0,346][1080,401]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="666621833623" resource-id="com.lphtsccft:id/login_account_edit"
        class="android.widget.EditText" bounds="[122,460][990,570]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="请输入交易密码" resource-id="com.lphtsccft:id/login_password_edit"
        class="android.widget.EditText" bounds="[122,571][1050,681]"
        clickable="true" enabled="true" password="true" checked="false"/>
  <node text="登录" resource-id="com.lphtsccft:id/login_btn_login"
        class="android.widget.Button" bounds="[60,798][1020,886]"
        clickable="true" enabled="false" password="false" checked="false"/>
</hierarchy>
"""

LOGGED_IN_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
  <node text="首页" resource-id="" class="android.widget.TextView"
        bounds="[16,1824][190,1904]" clickable="true" enabled="true"
        password="false" checked="false"/>
  <node text="交易" resource-id="" class="android.widget.TextView"
        bounds="[539,1824][714,1904]" clickable="true" enabled="true"
        password="false" checked="false"/>
  <node text="账户" resource-id="" class="android.widget.TextView"
        bounds="[889,1824][1064,1904]" clickable="true" enabled="true"
        password="false" checked="false"/>
</hierarchy>
"""

HOME_LOGGED_OUT_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
  <node text="登录查看" resource-id="com.lphtsccft:id/tv_login"
        class="android.widget.TextView" bounds="[936,1752][1056,1794]"
        clickable="true" enabled="true" password="false" checked="false"/>
</hierarchy>
"""


class LoginPageTests(unittest.TestCase):
    def test_parse_login_nodes(self):
        nodes = parse_nodes(LOGIN_XML)
        self.assertEqual(len(nodes), 4)
        password = find_by_id(nodes, "login_password_edit")
        self.assertIsNotNone(password)
        self.assertTrue(password.password)
        self.assertEqual(password.center, (586, 626))

    def test_login_screen_detected_by_activity_and_nodes(self):
        nodes = parse_nodes(LOGIN_XML)
        self.assertTrue(is_login_screen(nodes, "Window{1 u0 com.lphtsccft/com.lphtsccft.zhangle.login.HtscLoginActivity}"))
        self.assertFalse(is_logged_in(nodes, "Window{1 u0 com.lphtsccft/com.lphtsccft.zhangle.login.HtscLoginActivity}"))

    def test_logged_in_detected_by_main_activity_and_bottom_nav(self):
        nodes = parse_nodes(LOGGED_IN_XML)
        self.assertTrue(is_logged_in(nodes, "Window{1 u0 com.lphtsccft/com.lphtsccft.zhangle.main.MainActivity}"))
        self.assertFalse(is_login_screen(nodes, "Window{1 u0 com.lphtsccft/com.lphtsccft.zhangle.main.MainActivity}"))

    def test_home_with_login_entry_is_not_logged_in(self):
        nodes = parse_nodes(HOME_LOGGED_OUT_XML)
        self.assertFalse(is_logged_in(nodes, "Window{1 u0 com.lphtsccft/com.lphtsccft.zhangle.main.MainActivity}"))

    def test_mask_account(self):
        self.assertEqual(mask_account("666621833623"), "666***623")
        self.assertEqual(mask_account("123456"), "***")
        self.assertIsNone(mask_account(""))

    def test_manual_and_error_reasons(self):
        manual = parse_nodes(
            '<hierarchy><node text="请输入短信验证码" resource-id="" class="android.widget.TextView" '
            'bounds="[0,0][10,10]" clickable="false" enabled="true" password="false" checked="false"/></hierarchy>'
        )
        self.assertEqual(_manual_reason(manual), "请输入短信验证码")
        error = parse_nodes(
            '<hierarchy><node text="密码错误，请重试" resource-id="" class="android.widget.TextView" '
            'bounds="[0,0][10,10]" clickable="false" enabled="true" password="false" checked="false"/></hierarchy>'
        )
        self.assertEqual(_error_reason(error), "密码错误，请重试")

    def test_find_by_id_accepts_short_suffix(self):
        node = Node("", "com.lphtsccft:id/login_btn_login", "", (0, 0, 10, 10), True, True, False, False)
        self.assertIs(find_by_id([node], "login_btn_login"), node)

    def test_startup_consent_dialog(self):
        nodes = parse_nodes(
            '<hierarchy>'
            '<node text="温馨提示" resource-id="" class="android.widget.TextView" '
            'bounds="[0,0][10,10]" clickable="false" enabled="true" password="false" checked="false"/>'
            '<node text="同意" resource-id="" class="android.widget.Button" '
            'bounds="[0,0][10,10]" clickable="true" enabled="true" password="false" checked="false"/>'
            '<node text="不同意" resource-id="" class="android.widget.Button" '
            'bounds="[0,0][10,10]" clickable="true" enabled="true" password="false" checked="false"/>'
            '</hierarchy>'
        )
        self.assertTrue(has_consent_dialog(nodes))


class TradePageTests(unittest.TestCase):
    MAIN = "Window{1 u0 com.lphtsccft/com.lphtsccft.zhangle.main.MainActivity}"

    @staticmethod
    def _nodes(main_id: str) -> list:
        return parse_nodes(
            "<hierarchy>"
            f'<node text="" resource-id="com.lphtsccft:id/{main_id}" class="android.widget.FrameLayout" '
            'bounds="[0,140][1080,1808]" clickable="false" enabled="true" password="false" checked="false"/>'
            '<node text="交易" resource-id="" class="android.widget.TextView" '
            'bounds="[539,1824][714,1904]" clickable="false" enabled="true" password="false" checked="false"/>'
            "</hierarchy>"
        )

    def test_locked_trade_page_is_detected(self):
        nodes = self._nodes("trade_unlogin_main_layout")
        self.assertTrue(is_trade_page(nodes))
        self.assertTrue(is_trade_locked(nodes))
        self.assertFalse(is_logged_in(nodes, self.MAIN))

    def test_unlocked_trade_page_is_detected(self):
        nodes = self._nodes("trade_normal_main_layout")
        self.assertTrue(is_trade_page(nodes))
        self.assertFalse(is_trade_locked(nodes))
        self.assertTrue(is_logged_in(nodes, self.MAIN))

    def test_non_trade_page_is_not_reported_locked(self):
        nodes = parse_nodes(HOME_LOGGED_OUT_XML)
        self.assertFalse(is_trade_page(nodes))
        self.assertFalse(is_trade_locked(nodes))


if __name__ == "__main__":
    unittest.main()
