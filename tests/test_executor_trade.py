import unittest

from executor.adb import parse_nodes
from executor.trade import (
    TradeForm,
    is_trade_form,
    parse_confirm,
    parse_result,
    read_form,
)

TRADE_FOCUS = "Window{c11369e u0 com.lphtsccft/com.lphtsccft.zhangle.trading.normaltrade.HtscNormalTradeActivity}"

SELL_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
  <node text="卖出" resource-id="" class="android.widget.TextView"
        bounds="[216,136][432,227]" clickable="true" enabled="true" password="false" checked="false"/>
  <node text="000981 山子高科" resource-id="com.lphtsccft:id/trade_editText"
        class="android.widget.EditText" bounds="[16,309][804,389]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="2.13" resource-id="com.lphtsccft:id/et_content"
        class="android.widget.EditText" bounds="[72,449][748,529]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="卖出数量" resource-id="com.lphtsccft:id/et_content"
        class="android.widget.EditText" bounds="[72,589][748,669]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="可卖" resource-id="com.lphtsccft:id/tv_max_volume_label"
        class="android.widget.TextView" bounds="[687,669][735,729]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="12800" resource-id="com.lphtsccft:id/tv_max_volume"
        class="android.widget.TextView" bounds="[735,669][804,729]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="卖出" resource-id="com.lphtsccft:id/tv_trade"
        class="android.widget.TextView" bounds="[16,809][804,893]"
        clickable="true" enabled="true" password="false" checked="false"/>
</hierarchy>
"""

EMPTY_SELL_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
  <node text="请输入代码/名称/拼音" resource-id="com.lphtsccft:id/trade_editText"
        class="android.widget.EditText" bounds="[16,238][804,318]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="卖出价格" resource-id="com.lphtsccft:id/et_content"
        class="android.widget.EditText" bounds="[72,378][748,458]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="卖出数量" resource-id="com.lphtsccft:id/et_content"
        class="android.widget.EditText" bounds="[72,478][748,558]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="--" resource-id="com.lphtsccft:id/tv_max_volume_label"
        class="android.widget.TextView" bounds="[730,558][778,618]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="--" resource-id="com.lphtsccft:id/tv_max_volume"
        class="android.widget.TextView" bounds="[778,558][804,618]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="卖出" resource-id="com.lphtsccft:id/tv_trade"
        class="android.widget.TextView" bounds="[16,698][804,782]"
        clickable="true" enabled="true" password="false" checked="false"/>
</hierarchy>
"""


class TradeFormTests(unittest.TestCase):
    def test_read_filled_sell_form(self):
        form = read_form(parse_nodes(SELL_XML))
        self.assertEqual(
            form,
            TradeForm(
                side="sell",
                code="000981",
                price="2.13",
                quantity="",
                max_label="可卖",
                max_volume="12800",
                submit_text="卖出",
            ),
        )

    def test_read_empty_sell_form(self):
        form = read_form(parse_nodes(EMPTY_SELL_XML))
        self.assertEqual(form.side, "sell")
        self.assertEqual(form.code, "")
        self.assertEqual(form.price, "")
        self.assertEqual(form.quantity, "")
        self.assertEqual(form.max_volume, "--")

    def test_placeholders_are_not_treated_as_values(self):
        nodes = parse_nodes(EMPTY_SELL_XML)
        form = read_form(nodes)
        self.assertNotEqual(form.price, "卖出价格")
        self.assertNotEqual(form.quantity, "卖出数量")

    def test_trade_form_detection(self):
        nodes = parse_nodes(SELL_XML)
        self.assertTrue(is_trade_form(nodes, TRADE_FOCUS))
        self.assertTrue(is_trade_form(nodes, "Window{1 u0 com.lphtsccft/other.Activity}"))
        self.assertFalse(is_trade_form(parse_nodes("<hierarchy/>"), "Window{1 u0 x/y.Activity}"))


class DialogTests(unittest.TestCase):
    """Fixtures copied from the real 委托确认 / 系统提示 dialogs."""

    CONFIRM_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
  <node text="委托卖出" resource-id="com.lphtsccft:id/tv_title_text"
        class="android.widget.TextView" bounds="[468,767][612,817]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="股东账号:&#160;0169721247&#10;证券代码:&#160;000981&#10;证券名称:&#160;山子高科&#10;委托价格:&#160;2.13&#10;委托数量:&#160;100&#10;是否同意发出该笔委托?"
        resource-id="com.lphtsccft:id/tv_message_text" class="android.widget.TextView"
        bounds="[202,837][878,1113]" clickable="false" enabled="true"
        password="false" checked="false"/>
  <node text="取消" resource-id="com.lphtsccft:id/tv_negative"
        class="android.widget.TextView" bounds="[162,1134][540,1233]"
        clickable="true" enabled="true" password="false" checked="false"/>
  <node text="确定" resource-id="com.lphtsccft:id/tv_positive"
        class="android.widget.TextView" bounds="[541,1134][918,1233]"
        clickable="true" enabled="true" password="false" checked="false"/>
</hierarchy>
"""

    RESULT_ERROR_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
  <node text="系统提示" resource-id="com.lphtsccft:id/tv_title_text"
        class="android.widget.TextView" bounds="[468,883][612,933]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="当前时间不允许委托" resource-id="com.lphtsccft:id/tv_message_text"
        class="android.widget.TextView" bounds="[175,953][905,996]"
        clickable="false" enabled="true" password="false" checked="false"/>
  <node text="确定" resource-id="com.lphtsccft:id/tv_positive"
        class="android.widget.TextView" bounds="[135,1016][945,1116]"
        clickable="true" enabled="true" password="false" checked="false"/>
</hierarchy>
"""

    def test_parse_confirm_from_real_dialog(self):
        confirm = parse_confirm(parse_nodes(self.CONFIRM_XML))
        self.assertIsNotNone(confirm)
        self.assertEqual(confirm.title, "委托卖出")
        self.assertEqual(confirm.code, "000981")
        self.assertEqual(confirm.name, "山子高科")
        self.assertEqual(confirm.price, "2.13")
        self.assertEqual(confirm.quantity, "100")
        self.assertIn("是否同意发出该笔委托", confirm.raw)

    def test_parse_result_from_real_rejection(self):
        result = parse_result(parse_nodes(self.RESULT_ERROR_XML))
        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "error")
        self.assertEqual(result.title, "系统提示")
        self.assertEqual(result.message, "当前时间不允许委托")

    def test_parse_result_ignores_confirm_dialog(self):
        self.assertIsNone(parse_result(parse_nodes(self.CONFIRM_XML)))

    def test_parse_result_success_message(self):
        xml = self.RESULT_ERROR_XML.replace("当前时间不允许委托", "委托已提交")
        result = parse_result(parse_nodes(xml))
        self.assertEqual(result.kind, "success")

    def test_native_submitted_success_contract_is_recognized_without_assuming_fill(self):
        xml=self.RESULT_ERROR_XML.replace('当前时间不允许委托','委托提交成功,合同号:142783')
        result=parse_result(parse_nodes(xml));self.assertEqual(result.kind,'success')
        self.assertEqual(result.as_dict()['order_id'],'142783')
        for text in ('委托提交成功,合同号:142783，网络超时','委托提交成功,合同号:142783，失败'):
            parsed=parse_result(parse_nodes(self.RESULT_ERROR_XML.replace('当前时间不允许委托',text)))
            self.assertEqual(parsed.kind,'unknown');self.assertNotIn('order_id',parsed.as_dict())

    def test_no_dialog_returns_none(self):
        nodes = parse_nodes(SELL_XML)
        self.assertIsNone(parse_confirm(nodes))
        self.assertIsNone(parse_result(nodes))


if __name__ == "__main__":
    unittest.main()
