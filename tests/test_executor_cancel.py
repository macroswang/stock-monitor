import unittest

from executor.adb import parse_nodes
from executor.cancel import (
    CancelError,
    CancelPage,
    find_bar_top,
    parse_dialog,
    plan_cancel,
)
from executor.orderbook import OrderRow


def order(
    code="000981",
    direction="卖出",
    state="已报",
    quantity=2300,
    filled=0,
    name="山子高科",
    time="13:07:02",
):
    return OrderRow(
        kind="order",
        name=name,
        code=code,
        direction=direction,
        date="2026-10-30",
        time=time,
        price=2.25,
        quantity=quantity,
        filled=filled,
        state=state,
    )


def pixels_with_line(width: int, height: int, line: int | None, color=(238, 238, 238)):
    buffer = bytearray()
    for y in range(height):
        row = color if y == line else (255, 255, 255)
        for _ in range(width):
            buffer.extend((row[0], row[1], row[2], 255))
    return bytes(buffer)


class FakeAdb:
    """Records nothing; any device access in a refused plan is a bug."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            raise AssertionError(f"不应该调用 adb.{name}")

        return call


class PlanCancelTests(unittest.TestCase):
    def test_all_scope_targets_every_cancellable_order(self):
        orders = [
            order(),
            order(code="600000", direction="买入", name="浦发银行"),
            order(state="已成", filled=2300),
        ]
        plan = plan_cancel(orders, scope="all")

        self.assertEqual(plan.scope, "all")
        self.assertEqual(plan.button, "全撤")
        self.assertEqual(len(plan.targets), 2)
        self.assertEqual(plan.blocked, [])

    def test_side_scope_filters_by_direction(self):
        orders = [
            order(),
            order(code="600000", direction="买入", name="浦发银行"),
        ]

        self.assertEqual(len(plan_cancel(orders, scope="buy").targets), 1)
        self.assertEqual(plan_cancel(orders, scope="buy").targets[0].code, "600000")
        self.assertEqual(plan_cancel(orders, scope="sell").button, "撤卖")

    def test_empty_side_raises(self):
        with self.assertRaises(CancelError):
            plan_cancel([order(direction="卖出")], scope="buy")

    def test_no_cancellable_orders_raises(self):
        with self.assertRaises(CancelError):
            plan_cancel([order(state="已成", filled=2300)], scope="all")
        with self.assertRaises(CancelError):
            plan_cancel([], scope="all")

    def test_single_code_without_competition_is_allowed(self):
        orders = [
            order(code="000981"),
            order(code="600000", direction="买入", name="浦发银行"),
        ]
        plan = plan_cancel(orders, code="000981")

        self.assertEqual(plan.scope, "sell")
        self.assertEqual([row.code for row in plan.targets], ["000981"])
        self.assertEqual(plan.blocked, [])

    def test_single_code_that_would_hit_other_orders_is_blocked(self):
        orders = [
            order(code="000981"),
            order(code="600123", name="兰花科创"),
        ]
        plan = plan_cancel(orders, code="000981")

        self.assertEqual([row.code for row in plan.targets], ["000981"])
        self.assertEqual([row.code for row in plan.blocked], ["600123"])

        page = CancelPage(FakeAdb())
        with self.assertRaises(CancelError) as caught:
            page.cancel(plan, dry_run=True)
        self.assertIn("误伤", str(caught.exception))
        self.assertFalse(page.adb.calls, "被拦下的计划不应该碰设备")

    def test_code_on_both_sides_is_refused(self):
        orders = [
            order(code="000981", direction="卖出"),
            order(code="000981", direction="买入", name="山子高科"),
        ]
        with self.assertRaises(CancelError):
            plan_cancel(orders, code="000981")

    def test_unknown_code_raises(self):
        with self.assertRaises(CancelError):
            plan_cancel([order()], code="600000")

    def test_invalid_scope_rejected(self):
        with self.assertRaises(ValueError):
            plan_cancel([order()], scope="everything")

    def test_plan_serialises_without_secrets(self):
        payload = plan_cancel([order()], scope="sell").as_dict()

        self.assertEqual(payload["button"], "撤卖")
        self.assertEqual(payload["targets"][0]["code"], "000981")
        self.assertTrue(payload["targets"][0]["cancellable"])


class ScreenGeometryTests(unittest.TestCase):
    def test_finds_divider_above_bottom_bar(self):
        pixels = pixels_with_line(12, 40, line=30)
        self.assertEqual(find_bar_top(pixels, 12, 40), 31)

    def test_ignores_non_uniform_rows(self):
        width, height = 12, 40
        buffer = bytearray(pixels_with_line(width, height, line=None))
        # 在第 35 行塞一个深色像素，模拟按钮文字，不能被当成分隔线
        index = (35 * width + 3) * 4
        buffer[index : index + 3] = b"\x20\x20\x20"
        self.assertEqual(
            find_bar_top(bytes(buffer), width, height),
            int(height * 1770 / 1920),
        )

    def test_fallback_is_ratio_based(self):
        white = pixels_with_line(12, 40, line=None)
        self.assertEqual(find_bar_top(white, 12, 40), 36)


class CancelDialogTests(unittest.TestCase):
    def test_parses_confirm_dialog(self):
        xml = """<hierarchy rotation="1">
  <node text="撤单确认" resource-id="com.lphtsccft:id/tv_title_text"
        class="android.widget.TextView" bounds="[0,0][10,10]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="确定撤销 山子高科 卖出 2300 股？" resource-id="com.lphtsccft:id/tv_message_text"
        class="android.widget.TextView" bounds="[0,10][10,20]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="取消" resource-id="com.lphtsccft:id/tv_negative"
        class="android.widget.TextView" bounds="[0,20][10,30]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="确定" resource-id="com.lphtsccft:id/tv_positive"
        class="android.widget.TextView" bounds="[0,30][10,40]"
        clickable="true" enabled="true" password="false" checked="false"/>
</hierarchy>"""
        dialog = parse_dialog(parse_nodes(xml))

        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.title, "撤单确认")
        self.assertIn("2300", dialog.message)
        self.assertEqual(dialog.as_dict()["title"], "撤单确认")

    def test_no_dialog_returns_none(self):
        xml = """<hierarchy rotation="1">
  <node text="撤单" resource-id="com.lphtsccft:id/title_bar_center"
        class="android.widget.TextView" bounds="[0,0][10,10]"
        clickable="false" enabled="true" password="false" checked="false"/>
</hierarchy>"""
        self.assertIsNone(parse_dialog(parse_nodes(xml)))


if __name__ == "__main__":
    unittest.main()
