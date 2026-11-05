import json
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock,patch
from core.provider import CN
from executor.adb import Node
from executor.ths_orders import parse_current,discover_current,current_pages,OrderNotFound,order_key
from tests import test_ths_receipt_recovery as recovery


def screen(filled=0,status='已报',side='买入'):
    """Replay the actual ID-less native table; change only broker row values."""
    nodes=[Node(**n) for n in json.loads((Path(__file__).parent/'fixtures/ths_current_orders.json').read_text())]
    result=[]
    for n in nodes:
        if 419<=n.bounds[1]<=519:continue
        text=n.text
        if n.bounds[1]==318 and n.bounds[0]==810:text=side
        if n.bounds[1]==360:
            if n.bounds[0]==270:text='30.260' if filled else '--'
            if n.bounds[0]==540:text=str(filled)
            if n.bounds[0]==810:text=status
        result.append(replace(n,text=text))
    return result


class CurrentOrderTests(unittest.TestCase):
    def setUp(self):
        self.day='2026-11-05';self.submitted=self.day+'T13:54:02+08:00'
        self.now=datetime(2026,11,5,16,0,tzinfo=CN)
        self.plan=dict(name='三孚股份',code='603938',side='buy',quantity=200,price='30.26')

    def read(self,pages):
        adb=Mock()
        with patch('executor.ths_orders.current_pages',return_value=iter(pages)):
            result=discover_current(adb,'1234560001',self.day,self.plan,self.submitted,self.now)
        adb.tap_node.assert_not_called();adb.shell.assert_not_called()
        return result

    def test_actual_idless_native_table_parses_unfilled_partial_and_filled_orders(self):
        for qty,status,expected in [(0,'已报','accepted'),(100,'部成','partial'),(200,'已成','filled')]:
            with self.subTest(status=status):
                row=parse_current(screen(qty,status),self.day)[0]
                self.assertEqual((row['status'],row['filled'],row['quantity'],row['price']),(expected,qty,200,'30.260'))
                report=self.read([[row]])
                self.assertEqual(report['code'],'603938');self.assertEqual(report['order_id'],'')
                self.assertEqual(report['native_order_key'],order_key(row))
                self.assertEqual('average' in report,qty>0)

    def test_both_buy_and_sell_are_supported_without_a_contract_number(self):
        self.plan['side']='sell'
        row=parse_current(screen(100,'部成','卖出'),self.day)[0]
        self.assertEqual(self.read([[row]])['status'],'partial')

    def test_cancelled_rows_remain_read_only_and_reference_ignores_decimal_formatting(self):
        row=parse_current(screen(0,'已撤','撤买'),self.day)[0]
        self.assertEqual(self.read([[row]])['status'],'cancelled')
        self.assertEqual(order_key(row),order_key(dict(row,price='30.26')))

    def test_wrong_name_time_price_quantity_side_day_and_ambiguous_rows_never_match(self):
        row=parse_current(screen(),self.day)[0]
        for change in [dict(name='其它股票'),dict(time='13:54:20'),dict(time='13:53:59'),dict(side='sell'),dict(price='30.25'),dict(quantity=100)]:
            with self.subTest(change=change),self.assertRaises(OrderNotFound):self.read([[dict(row,**change)]])
        for pages in ([[row,row]],[[row],[dict(row,time='13:54:03')]]):
            with self.assertRaises(ValueError):self.read(pages)
        with self.assertRaises(ValueError):
            discover_current(Mock(),'1234560001','2026-11-04',self.plan,self.submitted,self.now)

    def test_old_contract_fallback_survives_an_unsupported_native_table(self):
        from executor.ths_orders import OrderUnavailable
        from executor.ths_report import discover
        row=dict(name='三孚股份',date=self.day,time='13:54:03',side='buy',code='603938',order_id='T001',filled=200,average='30.26',amount='6052')
        with patch('executor.ths_orders.discover_current',side_effect=OrderUnavailable('older native table')),patch('executor.ths_report.contract_pages',return_value=iter([[row]])):
            result=discover(Mock(),'1234560001',self.day,self.plan,self.submitted,self.now)
        self.assertEqual(result['order_id'],'T001');self.assertEqual(result['kind'],'contract_fills')

    def test_overlapping_native_pages_do_not_duplicate_one_order(self):
        row=parse_current(screen(),self.day)[0]
        other=dict(row,time='13:00:00')
        self.assertEqual(self.read([[row,other],[other]])['native_order_key'],order_key(row))

    def test_bad_headers_incomplete_cells_invalid_state_and_inconsistent_fill_are_rejected(self):
        for nodes in ([n for n in screen() if n.text!='状态'],[n for n in screen() if tuple(n.bounds[0:2])!= (540,360)],
                      screen(100,'已报'),screen(0,'部成'),screen(100,'已成'),screen(201,'部成'),screen(0,'未知状态')):
            with self.subTest(nodes=nodes),self.assertRaises(ValueError):parse_current(nodes,self.day)

    def test_native_pagination_verifies_account_and_never_taps_an_order_row(self):
        from executor.ths_report import verify
        adb=Mock();adb.nodes.return_value=screen();adb.current_focus.return_value='com.hexin.plat.android'
        query=Mock();query.open_home.return_value=screen()
        with patch('executor.ths_orders.ThsQuery',return_value=query):
            pages=list(current_pages(adb,'1234560001',self.day))
        self.assertEqual(len(pages),1);adb.tap_node.assert_not_called()
        self.assertEqual([c.args[1] for c in query._tap_text.call_args_list],['查询','当日委托'])
        for call in adb.shell.call_args_list:self.assertEqual(call.args[:2],('input','swipe'))
        verify(screen(),adb.current_focus(),'1234560001')
        with patch('executor.ths_orders.ThsQuery',return_value=query),self.assertRaises(ValueError):
            list(current_pages(adb,'1234569999',self.day))

    def test_a_changed_native_snapshot_never_recovers_a_stale_state(self):
        adb=Mock();adb.nodes.side_effect=[screen(),screen(),screen(100,'部成')]
        adb.current_focus.return_value='com.hexin.plat.android'
        query=Mock();query.open_home.return_value=screen()
        with patch('executor.ths_orders.ThsQuery',return_value=query),self.assertRaises(ValueError):
            list(current_pages(adb,'1234560001',self.day))
        adb.tap_node.assert_not_called()


class CurrentOrderReconciliationTests(unittest.TestCase):
    seed=recovery.ReceiptRecoveryTests.seed
    rows=recovery.ReceiptRecoveryTests.rows

    def setUp(self):
        recovery.ReceiptRecoveryTests.setUp(self)
        request,run=self.rows();ack=json.loads(request['result']);ack['confirm']['name']='山子高科'
        self.store.execute('UPDATE broker_requests SET result=? WHERE request_id=?',(json.dumps(ack),'auto_one'))

    def native(self,filled=0):
        report=dict(self.report,order_id='',kind='native_order',source='ths_native_today_order',name='山子高科',filled=filled,
                    status='filled' if filled==600 else 'partial' if filled else 'accepted',average='2.14',
                    receipt_recovery=dict(submitted_at=self.stamp,method='native_order_list'))
        report['native_order_key']=order_key(report)
        return report

    def test_lost_receipt_recovers_unfilled_then_partial_without_inventing_a_broker_id_or_reordering(self):
        for filled,status in [(0,'accepted'),(300,'partial'),(600,'filled')]:
            self.discovery.return_value=self.native(filled)
            self.assertTrue(self.reconcile()['ok'])
            request,run=self.rows();self.assertEqual((request['status'],run['status']),(status,status))
            point=recovery.chart(self.store,'sz000981','2026-11-02')['points'][0]
            self.assertEqual((point['status'],point['order_id'],point['filled']),(status,'',filled))
            self.assertEqual(point['fill_price'],'2.14' if filled else None)
        self.order.assert_not_called();self.reader.assert_not_called()

    def test_native_recovery_requires_original_confirmation_name_and_a_unique_scoped_reference(self):
        for change in [dict(name='其它股票'),dict(native_order_key='bad'),dict(time='10:59:20'),dict(code='603938'),
                       dict(source='guessed'),dict(quantity=599),dict(price='2.14'),dict(account_id='b')]:
            self.discovery.return_value=dict(self.native(),**change)
            self.assertFalse(self.reconcile()['ok']);self.assertEqual(self.rows()[0]['status'],'unknown')
        self.seed('two',order_id='')
        key=self.native()['native_order_key']
        self.store.execute("UPDATE broker_requests SET result=json_set(result,'$.verification.native_order_key',?) WHERE request_id='auto_two'",(key,))
        self.discovery.return_value=self.native()
        self.assertFalse(self.reconcile()['ok']);self.assertEqual(self.rows()[0]['status'],'unknown')

    def test_a_native_row_cannot_be_claimed_from_another_same_time_request_with_a_known_id(self):
        self.seed('two',order_id='existing-contract')
        self.discovery.return_value=self.native()
        self.assertFalse(self.reconcile()['ok']);self.assertEqual(self.rows()[0]['status'],'unknown')

    def reconcile(self,**kwargs):
        return self.rec.reconcile('a','auto_one',**kwargs)
