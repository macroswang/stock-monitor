"""Lost native receipt -> unique broker contract -> real chart projection.

Temporary SQLite and simulated read-only reports; no device/order operations.
"""
import copy
import json
import unittest
from datetime import datetime
from unittest.mock import Mock,patch
from executor.adb import Node
from executor.ths_order import parse_result
from executor.ths_report import discover
from core.provider import CN
from core.trading_chart import chart
from tests import test_broker_reconciliation as fixtures


class ReceiptRecoveryTests(unittest.TestCase):
    seed=fixtures.ReconciliationTests.seed
    rows=fixtures.ReconciliationTests.rows
    reconcile=fixtures.ReconciliationTests.reconcile

    def setUp(self):
        fixtures.ReconciliationTests.setUp(self)
        self.store.execute("UPDATE broker_accounts SET broker='ths' WHERE id='a'")
        ack=dict(status='unknown',submitted=False,message='系统信息',confirm=dict(code='000981',side='sell',quantity=600,price='2.13'))
        req,run=self.rows();payload=json.loads(run['payload'])
        payload.update(signal=dict(key='top',kind='top',time='10:59',price=2.13),price_checks=dict(before_submit=dict(checked_at=self.stamp)))
        self.store.execute("UPDATE broker_requests SET status='unknown',result=? WHERE request_id='auto_one'",(json.dumps(ack),))
        self.store.execute("UPDATE trading_runs SET status='unknown',payload=? WHERE id='one'",(json.dumps(payload),))
        self.fills={k:v for k,v in self.report.items() if k not in ('quantity','price','status')}
        self.fills.update(kind='contract_fills',average='2.14',amount='1284',source='ths_native_contract_group',receipt_recovery=dict(submitted_at=self.stamp))
        reader=patch('core.broker_reconciliation.brokers.discover_order_report',return_value=self.fills)
        self.discovery=reader.start();self.addCleanup(reader.stop)
        guard=patch('core.brokers.submit_order',side_effect=AssertionError('No order IO'))
        self.order=guard.start();self.addCleanup(guard.stop)

    def test_missing_receipt_recovers_contract_and_projects_s_with_fill(self):
        self.assertTrue(self.reconcile()['ok'])
        req,run=self.rows();self.assertEqual((req['status'],run['status']),('filled','filled'))
        self.assertEqual(json.loads(req['result'])['acknowledgement']['message'],'系统信息')
        point=chart(self.store,'sz000981','2026-11-02')['points'][0]
        self.assertEqual((point['status'],point['order_id'],point['filled'],point['fill_price']),('filled','test001',600,'2.14'))
        self.discovery.assert_called_once();self.reader.assert_not_called();self.order.assert_not_called()

    def test_wrong_account_code_time_quantity_or_submission_proof_cannot_settle(self):
        cases=[dict(account_id='b'),dict(account_verified=False),dict(code='603938'),dict(side='buy'),dict(filled=599,amount='1281.86'),
               dict(time='10:59:20'),dict(time='10:58:50'),dict(average='2.12',amount='1272'),dict(receipt_recovery=dict(submitted_at='2026-11-02T10:58:00+08:00'))]
        for change in cases:
            with self.subTest(change=change):
                self.discovery.return_value={**self.fills,**change}
                self.assertFalse(self.reconcile()['ok'])
                self.assertEqual(self.rows()[0]['status'],'unknown')
        self.order.assert_not_called()

    def test_contract_already_assigned_to_other_request_never_recovers(self):
        self.seed('two',order_id='test001')
        self.assertFalse(self.reconcile()['ok']);self.assertEqual(self.rows()[0]['status'],'unknown')

    def test_background_poll_can_query_ths_without_a_receipt_number(self):
        self.rec.poll()
        self.assertEqual(self.rows()[0]['status'],'filled');self.discovery.assert_called_once()


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.day='2026-11-05';self.submitted='2026-11-05T13:54:02+08:00'
        self.now=datetime(2026,11,5,14,30,tzinfo=CN)
        self.plan=dict(code='603938',side='buy',quantity=200,price='30.26')
        self.row=dict(name='三孚股份',date=self.day,time='13:54:03',side='buy',code='603938',order_id='TEST1424134',filled=200,average='30.260',amount='6052.000')

    def read(self,pages):
        with patch('executor.ths_report.contract_pages',return_value=iter(pages)):
            return discover(Mock(),'synthetic-account',self.day,self.plan,self.submitted,self.now)

    def test_unique_full_contract_and_overlapping_pages_are_read_only(self):
        result=self.read([[self.row],[self.row]])
        self.assertEqual(result['order_id'],'TEST1424134');self.assertEqual(result['receipt_recovery']['submitted_at'],self.submitted)
        self.assertRegex(result['evidence_hash'],r'^[0-9a-f]{64}$')

    def test_ambiguous_contracts_partial_late_and_wrong_direction_are_not_guessed(self):
        for pages in ([[self.row,{**self.row,'order_id':'SECOND'}]],[[{**self.row,'filled':100}]],[[{**self.row,'time':'14:00:00'}]],
                      [[{**self.row,'side':'sell'}]],[[{**self.row,'code':'000981'}]],[[{**self.row,'average':'30.27','amount':'6054'}]],[]):
            with self.subTest(pages=pages),self.assertRaises(ValueError):self.read(pages)
        with self.assertRaises(ValueError):self.read([[self.row],[{**self.row,'amount':'1'}]])


class ModalReceiptTests(unittest.TestCase):
    def node(self,text,bounds,rid='',cls='android.widget.TextView'):
        return Node(text,'com.hexin.plat.android:id/'+rid if rid else '',cls,bounds,True,True,False,False)

    def screen(self,text):
        n=self.node
        return [n('',(0,0,1080,1920),cls='android.widget.FrameLayout'),
                n('委托成功 合同号：BACKGROUND',(0,100,500,200)),
                n('',(80,650,1000,1200),cls='android.widget.LinearLayout'),
                n('系统信息',(100,680,980,730),'dialog_title'),n(text,(100,780,980,950)),n('确定',(100,1050,980,1150),'ok_btn')]

    def test_generic_title_waits_for_body_instead_of_finishing_early(self):
        self.assertIsNone(parse_result([self.node('系统信息',(100,680,980,730),'dialog_title')]))

    def test_unlabelled_popup_body_is_read_without_background_text(self):
        result=parse_result(self.screen('委托提交成功，合同号：TEST001'))
        self.assertEqual((result['status'],result['order_id']),('accepted','TEST001'))
        self.assertNotIn('BACKGROUND',result['message'])

    def test_network_conflict_rejection_and_unscoped_success_are_not_accepted(self):
        for text in ('委托成功，网络超时','委托提交成功，但失败','合同号：TEST001','委托成功，合同号：A，委托号：B'):
            self.assertEqual(parse_result(self.screen(text))['status'],'unknown')
        self.assertEqual(parse_result(self.screen('资金不足，委托失败'))['status'],'rejected')
        nodes=self.screen('委托提交成功，合同号：TEST001');del nodes[2]
        self.assertIsNone(parse_result(nodes))
