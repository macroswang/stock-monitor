import unittest
from unittest.mock import Mock,patch
from executor.adb import Node
from executor.ths import ThsError,read_status
from executor.ths_order import ThsOrderPage,read_form,requires_confirmation,parse_confirmation,parse_result
from executor.security_code import code_and_name,zhangle_code,ths_code
from executor.ths_trade import parse_funds


def n(text='',rid='',y=0,selected=False,edit=False,x=0):
    return Node(text,'com.hexin.plat.android:id/'+rid if rid else '', 'android.widget.EditText' if edit else 'android.widget.TextView',(x,y,x+200,y+40),True,True,False,False,selected)


def form(side='buy'):
    return [n('买入','btn',100,side=='buy'),n('卖出','btn',100,side=='sell'),
            n('000981','auto_stockcode',250,edit=True),n('山子高科','stockname',250),
            n('2.00',y=350,edit=True),n('100',y=450,edit=True),n('','btn_transaction',600)]


def settings(value='未开启'):
    return [n('委托撤单免二次确认',y=100),n(value,'tv_func_status',100,x=300)]


def confirmation(side='buy',code='000981',quantity='100',price='2.00',name='山子高科'):
    return [n('委托买入确认' if side=='buy' else '委托卖出确认','dialog_title',700),n(name,'stock_name_value',800),
            n(code,'stock_code_value',850),n(quantity,'number_value',900),n(price,'price_value',950),
            n('取消','cancel_btn',1000),n('确认买入' if side=='buy' else '确认卖出','ok_btn',1000)]


class NativeFormTests(unittest.TestCase):
    def test_real_layout_uses_selected_tab_and_unidentified_edit_fields(self):
        for side in ('buy','sell'):
            parsed=read_form(form(side))
            self.assertEqual((parsed.side,parsed.code,parsed.price,parsed.quantity),(side,'000981','2.00','100'))

    def test_search_overlay_never_exposes_background_form_as_ready(self):
        self.assertIsNone(read_form(form()+[n('','stock_search')]))
        self.assertIsNone(read_form(form()+[n('000981','auto_stockcode',200,edit=True)]))

    def test_ambiguous_direction_and_missing_inputs_are_rejected(self):
        nodes=form();nodes[1]=n('卖出','btn',100,True)
        self.assertIsNone(read_form(nodes));self.assertIsNone(read_form(form()[:-2]))

    def test_price_and_quantity_placeholders_remain_empty(self):
        nodes=form();nodes[4]=n('价格',y=350,edit=True);nodes[5]=n('数量',y=450,edit=True)
        self.assertEqual((read_form(nodes).price,read_form(nodes).quantity),('',''))

    def test_preview_invalid_values_do_not_open_any_device_page(self):
        for quantity,price in [(0,'2.00'),(True,'2.00'),(1.5,'2.00'),(100,'NaN'),(100,'-2')]:
            adb=Mock();page=ThsOrderPage(adb)
            with self.assertRaises(ValueError):page.preview('buy','000981',quantity,price)
            adb.nodes.assert_not_called();adb.tap_node.assert_not_called()


class ConfirmationSettingTests(unittest.TestCase):
    def test_only_explicit_disabled_skip_confirmation_setting_is_safe(self):
        self.assertTrue(requires_confirmation(settings()))
        self.assertFalse(requires_confirmation(settings('已开启')))

    def test_missing_ambiguous_or_unrelated_status_stops_before_order_button(self):
        for nodes in [[],settings('未知'),settings()+[n('未开启','tv_func_status',100,x=500)],
                      [n('委托撤单免二次确认',y=100),n('未开启','tv_func_status',200,x=300)]]:
            with self.assertRaises(ThsError):requires_confirmation(nodes)

    def test_setting_inspection_only_opens_and_dismisses_settings(self):
        adb=Mock();page=ThsOrderPage(adb);page.snapshot=Mock(return_value=form()+[n('','quick_setting_image')])
        page.snapshot.side_effect=[form()+[n('','quick_setting_image')],[n('','iv_close')]]
        page.wait=Mock(side_effect=[settings(),form()])
        self.assertTrue(page.confirmation_required())
        self.assertEqual(adb.tap_node.call_count,2);adb.keyevent.assert_not_called()


class SubmitBoundaryTests(unittest.TestCase):
    def page(self,side='buy',changed=None):
        page=ThsOrderPage(Mock(),expected_account='123456789')
        fs=form(side);fs.append(n('买 入' if side=='buy' else '卖 出',y=600))
        page.preview=Mock(return_value=read_form(fs));page.confirmation_required=Mock(return_value=True)
        page.snapshot=Mock(side_effect=[fs,confirmation(side)])
        page.wait=Mock(return_value=confirmation(side,**(changed or {})))
        page.cancel_confirmation=Mock();page.verify_account=Mock()
        return page

    def test_buy_and_sell_confirmation_native_values_are_parsed(self):
        for side in ('buy','sell'):
            c=parse_confirmation(confirmation(side))
            self.assertEqual((c.side,c.code,c.quantity,c.price),(side,'000981',100,'2.00'))
            self.assertIsNone(read_form(form()+confirmation(side)))

    def test_missing_duplicate_or_ambiguous_confirmation_fields_are_rejected(self):
        for nodes in [confirmation()[:-1],confirmation()+[n('000981','stock_code_value')],confirmation(price='NaN'),confirmation(quantity='0'),confirmation(code='bad')]:
            self.assertIsNone(parse_confirmation(nodes))

    def test_real_without_gateway_or_expected_account_never_opens_preview(self):
        for callback,account in [(None,'123456789'),(Mock(),None)]:
            page=self.page();page.expected_account=account
            with self.assertRaises(ThsError):page.submit('buy','000981',100,'2.00',before_confirm=callback)
            page.preview.assert_not_called()

    def test_disabled_second_confirmation_blocks_before_first_order_button(self):
        page=self.page();page.confirmation_required.return_value=False
        with self.assertRaisesRegex(ThsError,'免二次确认'):page.submit('buy','000981',100,'2.00',dry_run=True)
        page.adb.tap_node.assert_not_called()

    def test_amount_cap_blocks_before_first_order_button(self):
        page=self.page()
        with self.assertRaisesRegex(ThsError,'金额'):page.submit('buy','000981',100,'2.00',max_value=100,dry_run=True)
        page.adb.tap_node.assert_not_called()

    def test_dry_run_opens_confirmation_then_only_cancels(self):
        for side in ('buy','sell'):
            page=self.page(side)
            result=page.submit(side,'000981',100,'2.00',dry_run=True)
            self.assertEqual(result['status'],'preview');self.assertFalse(result['submitted'])
            self.assertEqual(page.adb.tap_node.call_count,1);page.cancel_confirmation.assert_called_once()

    def test_no_amount_cap_accepts_large_exact_plan_and_still_rejects_price_changes(self):
        from dataclasses import replace
        def large_page(changed=None):
            page=self.page(changed=changed)
            fs=form();fs[4]=replace(fs[4],text='30.00');fs.append(n('买 入',y=600))
            page.preview.return_value=read_form(fs)
            page.snapshot.side_effect=[fs,confirmation(price='30.00')]
            page.wait.return_value=confirmation(price='30.00',**(changed or {}))
            return page
        page=large_page();result=page.submit('buy','000981',100,'30.00',max_value=None,dry_run=True)
        self.assertEqual(result['status'],'preview');self.assertEqual(page.adb.tap_node.call_count,1)
        page=large_page(dict(quantity='200'))
        with self.assertRaises(ThsError):page.submit('buy','000981',100,'30.00',max_value=None,dry_run=True)
        page.cancel_confirmation.assert_called_once();self.assertEqual(page.adb.tap_node.call_count,1)

    def test_every_mismatched_confirmation_is_cancelled(self):
        for changes in [dict(code='000001'),dict(quantity='200'),dict(price='2.01'),dict(name='另一只股票')]:
            page=self.page(changed=changes)
            with self.assertRaisesRegex(ThsError,'不符'):page.submit('buy','000981',100,'2.00',dry_run=True)
            page.cancel_confirmation.assert_called_once();self.assertEqual(page.adb.tap_node.call_count,1)

    def test_opposite_side_confirmation_cannot_be_confirmed(self):
        page=self.page();page.wait.return_value=confirmation('sell')
        with self.assertRaisesRegex(ThsError,'不符'):page.submit('buy','000981',100,'2.00',dry_run=True)
        page.cancel_confirmation.assert_called_once()

    def test_pause_between_form_and_confirmation_never_touches_final_button(self):
        page=self.page();guard=Mock(side_effect=[None,ValueError('已暂停')])
        with self.assertRaisesRegex(ValueError,'暂停'):page.submit('buy','000981',100,'2.00',before_confirm=guard)
        self.assertEqual(guard.call_count,2);self.assertEqual(page.adb.tap_node.call_count,1);page.cancel_confirmation.assert_called_once()

    def test_changed_dialog_is_not_confirmed(self):
        page=self.page();page.snapshot.side_effect=[form()+[n('买 入',y=600)],confirmation(code='000001')]
        with self.assertRaisesRegex(ThsError,'变化'):page.submit('buy','000981',100,'2.00',before_confirm=Mock())
        self.assertEqual(page.adb.tap_node.call_count,1)

    def test_result_timeout_after_final_click_is_unknown(self):
        page=self.page();page.wait.side_effect=[confirmation(),TimeoutError()]
        result=page.submit('buy','000981',100,'2.00',before_confirm=Mock())
        self.assertEqual(result['status'],'unknown');self.assertFalse(result['submitted'])
    def test_manual_submit_returns_after_final_tap_without_reading_receipt(self):
        page=self.page();page.wait.side_effect=[confirmation(),AssertionError('must not read receipt')]
        result=page.submit('buy','000981',100,'2.00',before_confirm=Mock(),wait_for_receipt=False)
        self.assertEqual(result['status'],'unknown');self.assertTrue(result['submitted']);self.assertTrue(result['receipt_pending'])
        self.assertEqual(page.wait.call_count,1);self.assertEqual(page.adb.tap_node.call_count,2)

    def test_network_or_conflicting_messages_are_never_a_rejection_or_success(self):
        for text in ('委托成功，查询失败','网络超时','查询失败','委托成功，但出现错误'):
            self.assertEqual(parse_result([n('提示','dialog_title'),n(text,'dialog_message')])['status'],'unknown')
        result=parse_result([n('提示','dialog_title'),n('委托成功 合同编号：TEST001','dialog_message')])
        self.assertEqual((result['status'],result['order_id']),('accepted','TEST001'))


class SecurityCodeTests(unittest.TestCase):
    def test_code_is_accepted_only_with_matching_broker_security_name(self):
        self.assertEqual(code_and_name('000981 山子高科','山子高科'),'000981')
        for text in ('000981 另一只股票','000981','123456.00','市值 000981'):
            with self.assertRaises(ValueError):code_and_name(text,'山子高科')

    def test_zhangle_resolver_never_touches_submit_and_restores_account(self):
        adb=Mock();name=n('山子高科','stock_name');entry=n('买入','pop_buy');field=n('000981 山子高科','trade_editText',edit=True)
        adb.nodes.side_effect=[[entry],[field],[]]
        verify=Mock()
        with patch('executor.security_code.TradePage') as page:
            result=zhangle_code(adb,dict(name='山子高科'),[name],verify)
            self.assertEqual(result['code'],'000981');page.return_value.close.assert_called_once()
        self.assertEqual([c.args[0] for c in adb.tap_node.call_args_list],[name,entry]);self.assertEqual(verify.call_count,2)

    def test_zhangle_mismatched_name_closes_form_without_a_code(self):
        adb=Mock();adb.nodes.side_effect=[[n('买入','pop_buy')],[n('000981 另一只股票','trade_editText',edit=True)],[]]
        with patch('executor.security_code.TradePage') as page:
            with self.assertRaisesRegex(ValueError,'不符'):
                zhangle_code(adb,dict(name='山子高科'),[n('山子高科','stock_name')],Mock())
            page.return_value.close.assert_called_once()

    def test_ths_resolver_checks_name_and_account_then_returns_to_holdings(self):
        adb=Mock();tabs=[n('持仓','btn')];adb.nodes.return_value=tabs
        verify=Mock()
        with patch('executor.ths_order.ThsOrderPage') as page:
            page.return_value.wait.side_effect=[form(),[n('','position_table_view')]]
            result=ths_code(adb,dict(name='山子高科'),[n('山子高科'),n('买入','function_text')],verify)
        self.assertEqual(result['code'],'000981');self.assertEqual(verify.call_count,3)
        self.assertEqual([c.args[0].text for c in adb.tap_node.call_args_list],['买入','持仓'])


class HoldingsHeaderTests(unittest.TestCase):
    def test_subpage_header_preserves_broker_and_capital_account_identity(self):
        status=read_status([n('中国银河证券','page_title_view'),n('**1234','account_info_view')],'com.hexin.plat.android')
        self.assertEqual(status.broker_name,'中国银河证券');self.assertEqual(status.account_masked,'**1234')

    def test_available_cash_is_read_from_actual_holdings_card(self):
        ns=[n('总资产','capital_cell_title'),n('10000.00','capital_cell_value'),n('可用','capital_cell_title'),n('2500.00','capital_cell_value'),n('可取','capital_cell_title'),n('--','capital_cell_value')]
        funds=parse_funds(ns)
        self.assertEqual(funds['available'],'2500.00');self.assertEqual(funds['total_assets'],'10000.00');self.assertEqual(funds['withdrawable'],'--')


class AccountBindingTests(unittest.TestCase):
    def page(self):
        adb=Mock();adb.current_focus.return_value='com.hexin.plat.android/.Hexin'
        return ThsOrderPage(adb,'123456789')

    def bound(self):
        page=self.page()
        page.verify_account(form()+[n('中国银河证券','page_title_view'),n('**6789','account_info_view')])
        page._pending_plan=parse_confirmation(confirmation())
        return page

    def test_headerless_native_confirmation_is_bound_to_fresh_exact_plan(self):
        self.bound().verify_account(confirmation())

    def test_headerless_dialog_cannot_skip_initial_capital_account_verification(self):
        page=self.page();page._pending_plan=parse_confirmation(confirmation())
        with self.assertRaises(ThsError):page.verify_account(confirmation())

    def test_changed_plan_visible_wrong_account_and_foreign_app_are_rejected(self):
        page=self.bound()
        for nodes in [confirmation(code='000001'),confirmation()+[n('中国银河证券','page_title_view'),n('**1111','account_info_view')]]:
            with self.assertRaises(ThsError):page.verify_account(nodes)
        page.adb.current_focus.return_value='other.app/.Activity'
        with self.assertRaises(ThsError):page.verify_account(confirmation())

    def test_expired_binding_cannot_be_reused(self):
        page=self.bound()
        with patch('executor.ths_order.time.monotonic',return_value=page._verified_form_at+31):
            with self.assertRaises(ThsError):page.verify_account(confirmation())
