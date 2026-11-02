"""反例回归：只用假设备，绝不向券商提交测试委托。"""
import subprocess
import unittest
from unittest.mock import Mock, patch

from executor.adb import Adb, AdbError, parse_nodes
from executor.cancel import CancelPage, CancelError, plan_cancel
from executor.trade import TradePage, TradeError, TradeForm, parse_confirm, parse_result, OrderResult
from tests import test_executor_trade as trade_fixtures
from tests.test_executor_cancel import order


class OrderSafetyTests(unittest.TestCase):
    def test_pause_after_form_button_blocks_final_confirmation(self):
        page=self.page()
        guard=Mock(side_effect=[None,ValueError('用户已暂停')])
        with self.assertRaisesRegex(ValueError,'暂停'):
            page.submit('sell','000981',100,'2.13',before_confirm=guard)
        self.assertEqual(guard.call_count,2)
        self.assertEqual(page.adb.tap_node.call_count,1,'只能打开确认弹窗，不能确认委托')
        page._cancel_dialog.assert_called_once()

    def test_unknown_or_changed_dialog_cannot_be_confirmed(self):
        page = self.page()
        form_nodes = page.snapshot.side_effect
        page.snapshot = Mock(side_effect=[next(form_nodes), ("", parse_nodes(trade_fixtures.DialogTests.RESULT_ERROR_XML))])
        with self.assertRaises(TradeError):
            page.submit("sell", "000981", 100, "2.13", before_confirm=Mock())
        self.assertEqual(page.adb.tap_node.call_count, 1, "只能点过表单按钮，不能点变更后的弹窗")

    def test_unjournaled_real_submit_cannot_touch_submit_button(self):
        page = self.page()
        with self.assertRaisesRegex(TradeError, "持久化"):
            page.submit("sell", "000981", 100, "2.13")
        page.adb.tap_node.assert_not_called()

    def test_invalid_amount_and_quantity_stopped_before_preview(self):
        for kwargs in ({"max_value": float('nan')}, {"max_value": -1}, {"quantity": 1.2}, {"price": "NaN"}):
            page = self.page()
            args = dict(side="sell", code="000981", quantity=100, price="2.13")
            args.update(kwargs)
            with self.assertRaises(TradeError):page.submit(**args)
            page.preview.assert_not_called()

    def test_conflicting_response_and_network_failure_remain_unknown(self):
        for message in ("委托成功，查询失败", "网络超时，提交失败"):
            xml = trade_fixtures.DialogTests.RESULT_ERROR_XML.replace("当前时间不允许委托", message)
            self.assertEqual(parse_result(parse_nodes(xml)).kind, "unknown")

    def page(self, side="sell"):
        page = TradePage(Mock())
        page.preview = Mock(return_value=TradeForm(side, "000981", "2.13", "100", "", "", "卖出"))
        form_xml = trade_fixtures.SELL_XML.replace('text="卖出数量"', 'text="100"')
        if side == "buy":
            form_xml = form_xml.replace("卖出", "买入")
        page.snapshot = Mock(side_effect=[("", parse_nodes(form_xml)), ("", parse_nodes(trade_fixtures.DialogTests.CONFIRM_XML))])
        page._wait_confirm = Mock(return_value=parse_confirm(parse_nodes(trade_fixtures.DialogTests.CONFIRM_XML)))
        page._wait_result = Mock(return_value=OrderResult("success", "", "已受理"))
        page._cancel_dialog = Mock()
        page._dialog_button = Mock(return_value=Mock())
        return page

    def test_no_amount_cap_accepts_large_exact_plan_but_keeps_price_identity(self):
        from dataclasses import replace
        def large_page():
            page=self.page()
            page.preview.return_value=replace(page.preview.return_value,price='30.00')
            page.snapshot.side_effect=[(focus,[replace(n,text=n.text.replace('2.13','30.00')) for n in nodes]) for focus,nodes in page.snapshot.side_effect]
            page._wait_confirm.return_value=replace(page._wait_confirm.return_value,price='30.00')
            return page
        page=large_page();result=page.submit('sell','000981',100,'30.00',max_value=None,dry_run=True)
        self.assertEqual(result['status'],'preview');page._cancel_dialog.assert_called_once()
        page=large_page();page._wait_confirm.return_value=replace(page._wait_confirm.return_value,price='31.00')
        with self.assertRaises(TradeError):page.submit('sell','000981',100,'30.00',max_value=None,dry_run=True)
        page._cancel_dialog.assert_called_once()

    def test_cancel_must_never_fall_back_to_positive_button(self):
        page = TradePage(Mock())
        nodes = [n for n in parse_nodes(trade_fixtures.DialogTests.CONFIRM_XML) if not n.resource_id.endswith("tv_negative")]
        page.snapshot = Mock(return_value=("", nodes))
        with self.assertRaises(TradeError):
            page._cancel_dialog()
        page.adb.tap_node.assert_not_called()

    def test_wrong_direction_never_confirmed(self):
        page = self.page("buy")
        with self.assertRaises(TradeError):
            page.submit("buy", "000981", 100, "2.13", before_confirm=Mock())
        page._dialog_button.assert_not_called()

    def test_rejected_order_is_not_reported_submitted(self):
        page = self.page()
        page._wait_result = Mock(return_value=OrderResult("error", "系统提示", "余额不足"))
        result = page.submit("sell", "000981", 100, "2.13", before_confirm=Mock())
        self.assertFalse(result["submitted"])
        self.assertEqual(result["status"], "rejected")

    def test_missing_reply_is_unknown_not_success(self):
        page = self.page()
        page._wait_result = Mock(return_value=None)
        result = page.submit("sell", "000981", 100, "2.13", before_confirm=Mock())
        self.assertFalse(result["submitted"])
        self.assertEqual(result["status"], "unknown")

    def test_identical_price_format_is_accepted(self):
        page = self.page()
        result = page.submit("sell", "000981", 100, "2.130", dry_run=True)
        self.assertFalse(result["submitted"])

    def test_empty_order_query_does_not_prove_cancellation(self):
        page = CancelPage(Mock())
        with patch("executor.cancel.OrderBook") as book:
            book.return_value.today_orders.side_effect = RuntimeError("断连")
            self.assertFalse(page._verify(plan_cancel([order()]), .01))

    def test_filled_order_is_not_cancelled(self):
        page = CancelPage(Mock())
        with patch("executor.cancel.OrderBook") as book:
            book.return_value.today_orders.return_value.rows = [order(state="已成", filled=2300)]
            self.assertFalse(page._verify(plan_cancel([order()]), .01))

    def test_single_stock_is_not_single_order(self):
        with self.assertRaises(CancelError):
            plan_cancel([order(time="10:00:00"), order(time="10:01:00")], code="000981")

    def test_password_never_in_timeout_error_or_cause(self):
        secret = "testSensitive987"
        with patch("executor.adb.subprocess.run", side_effect=subprocess.TimeoutExpired(["input", "text", secret], 1)):
            with self.assertRaises(AdbError) as caught:
                Adb(adb="fake").input_text(secret)
        self.assertNotIn(secret, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
