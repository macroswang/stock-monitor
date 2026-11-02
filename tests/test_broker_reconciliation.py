import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.broker_reconciliation import Reconciler, validate_report, known_id, request_plan
from core.live_trading import LiveTrading
from core.provider import CN
from core.store import Store


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
        self.now=datetime(2026,11,2,11,0,tzinfo=CN)
        clock=patch('core.broker_reconciliation.now_cn',return_value=self.now);clock.start();self.addCleanup(clock.stop)
        self.service=LiveTrading(SimpleNamespace(store=self.store))
        self.rec=self.service.reconciler
        self.stamp=(self.now-timedelta(minutes=1)).isoformat()
        for ident in ('a','b'):
            self.store.execute('INSERT INTO broker_accounts(id,broker,account) VALUES(?,?,?)',(ident,'zhangle','1234567'+ident))
        self.seed()
        self.report=dict(account_id='a',account_verified=True,observed_at=self.now.isoformat(),found=True,
                         order_id='test001',date='2026-11-02',time='10:59:03',date_source='broker_row',
                         code='000981',side='sell',quantity=600,price='2.13',filled=600,status='filled',
                         source='broker_test_reader',evidence_hash='a'*64)
        reader=patch('core.broker_reconciliation.brokers.order_report',return_value=self.report)
        self.reader=reader.start();self.addCleanup(reader.stop)

    def seed(self,ident='one',account='a',order_id='test001',status='accepted',filled=None):
        result=dict(status=status,submitted=True,result=dict(kind='success',order_id=order_id))
        if filled is not None:result['verification']=dict(order_id=order_id,filled=filled,origin='broker_auto')
        plan=dict(account_id=account,code='sz000981',side='sell',quantity=600,price='2.13',value=1278)
        payload=dict(plan=plan,mode='live',result=result)
        if filled is not None:payload['verification']=result['verification']
        self.store.execute('INSERT INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,account,'sz000981','sell','unique'+ident,'2026-11-02',status,json.dumps(payload),self.stamp,self.stamp))
        req=dict(account_id=account,code='000981',side='sell',quantity=600,price='2.13',dry_run=False)
        self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',('auto_'+ident,account,json.dumps(req),status,json.dumps(result),self.stamp,self.stamp))

    def rows(self):
        r=self.store.query("SELECT * FROM broker_requests WHERE request_id='auto_one'")[0]
        t=self.store.query("SELECT * FROM trading_runs WHERE id='one'")[0]
        return r,t

    def reconcile(self,**kw):return self.rec.reconcile('a','auto_one',**kw)

    def test_exact_report_commits_both_records_and_preserves_ack(self):
        result=self.reconcile();self.assertTrue(result['ok'])
        req,run=self.rows()
        self.assertEqual((req['status'],run['status']),('filled','filled'))
        ack=json.loads(req['result']);payload=json.loads(run['payload'])
        self.assertEqual(ack['result']['kind'],'success')
        self.assertEqual(ack['status'],'filled')
        self.assertEqual(ack['acknowledgement']['status'],'accepted')
        self.assertEqual(ack['verification'],payload['verification'])
        self.assertEqual(payload['verification']['filled'],600)
        self.assertEqual(payload['verification']['origin'],'broker_auto')
        self.assertEqual(self.reader.call_args.args[1:4],('a','test001','2026-11-02'))

    def test_wrong_identity_amount_state_or_time_cannot_settle(self):
        cases=[dict(account_id='b'),dict(account_verified=False),dict(order_id='other'),dict(date='2026-10-30'),
               dict(code='603002'),dict(side='buy'),dict(quantity=601),dict(price='2.14'),dict(filled=599),
               dict(filled=601),dict(filled=True),dict(filled=2.5),dict(status='not_sent'),dict(status='accepted'),
               dict(status='cancelled'),dict(time='09:59:03'),dict(time='11:59:03'),dict(time=''),
               dict(observed_at=(self.now-timedelta(minutes=4)).isoformat()),dict(observed_at='bad'),
               dict(observed_at=(self.now+timedelta(seconds=1)).isoformat()),dict(evidence_hash=''),dict(source='')]
        for change in cases:
            with self.subTest(change=change):
                self.reader.return_value={**self.report,**change}
                result=self.reconcile();self.assertFalse(result['ok'])
                req,run=self.rows();self.assertEqual((req['status'],run['status']),('accepted','accepted'))
                self.assertNotIn('verification',json.loads(run['payload']))

    def test_not_found_and_read_error_leave_pending_not_not_sent(self):
        self.reader.return_value={**self.report,'found':False}
        self.assertFalse(self.reconcile()['ok'])
        self.reader.side_effect=ValueError('当前页面没有唯一委托号')
        self.assertFalse(self.reconcile()['ok'])
        self.assertEqual(self.rows()[0]['status'],'accepted')

    def test_missing_id_never_infers_from_stock_price_and_quantity(self):
        self.store.execute("UPDATE broker_requests SET result='{}' WHERE request_id='auto_one'")
        self.assertFalse(self.reconcile()['ok']);self.reader.assert_not_called()

    def test_conflicting_response_id_rejected(self):
        self.store.execute("UPDATE broker_requests SET result=? WHERE request_id='auto_one'",(json.dumps(dict(order_id='a',result=dict(order_id='b'))),))
        self.assertFalse(self.reconcile()['ok']);self.reader.assert_not_called()

    def test_both_account_and_request_id_required(self):
        with self.assertRaises(ValueError):self.rec.reconcile('b','auto_one')
        self.reader.assert_not_called()

    def test_dry_run_missing_price_or_changed_plan_never_reads_device(self):
        original=self.rows()
        for change in [dict(dry_run=True),dict(price=None),dict(account_id='b'),dict(quantity=True)]:
            payload=json.loads(original[0]['payload']);payload.update(change)
            self.store.execute("UPDATE broker_requests SET payload=? WHERE request_id='auto_one'",(json.dumps(payload),))
            self.assertFalse(self.reconcile()['ok'])
        self.store.execute("UPDATE broker_requests SET payload=? WHERE request_id='auto_one'",(original[0]['payload'],))
        payload=json.loads(original[1]['payload']);payload['plan']['quantity']=500
        self.store.execute("UPDATE trading_runs SET payload=? WHERE id='one'",(json.dumps(payload),))
        self.assertFalse(self.reconcile()['ok']);self.reader.assert_not_called()

    def test_partial_then_cancel_retains_actual_filled_and_rejects_regression(self):
        self.reader.return_value={**self.report,'filled':200,'status':'partial'}
        self.assertTrue(self.reconcile()['ok'])
        self.reader.return_value={**self.report,'filled':100,'status':'partial'}
        self.assertFalse(self.reconcile()['ok'])
        self.reader.return_value={**self.report,'filled':200,'status':'cancelled'}
        self.assertTrue(self.reconcile()['ok'])
        req,run=self.rows();self.assertEqual(run['status'],'cancelled')
        self.assertEqual(json.loads(run['payload'])['verification']['filled'],200)
        with self.assertRaises(ValueError):self.reconcile()

    def test_no_fill_rejection_and_accepted_are_valid(self):
        for status in ('accepted','rejected'):
            with self.subTest(status=status):
                self.reader.return_value={**self.report,'filled':0,'status':status}
                self.assertTrue(self.reconcile()['ok'])

    def test_manual_resolution_during_read_wins(self):
        def update(*a,**kw):
            self.store.execute("UPDATE trading_runs SET status='cancelled' WHERE id='one'")
            return self.report
        self.reader.side_effect=update
        result=self.reconcile();self.assertEqual(result['status'],'changed')
        self.assertEqual(self.rows()[0]['status'],'accepted')
        self.assertEqual(self.rows()[1]['status'],'cancelled')

    def test_request_race_during_read_wins(self):
        def update(*a,**kw):
            self.store.execute("UPDATE broker_requests SET status='not_sent' WHERE request_id='auto_one'")
            return self.report
        self.reader.side_effect=update
        self.assertEqual(self.reconcile()['status'],'changed')
        self.assertEqual(self.rows()[1]['status'],'accepted')

    def test_atomic_rollback_if_second_update_fails(self):
        self.store.execute("CREATE TRIGGER deny_update BEFORE UPDATE ON broker_requests BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(Exception):self.reconcile()
        self.assertEqual(self.rows()[1]['status'],'accepted')

    def test_duplicate_id_within_account_day_cannot_settle_twice(self):
        self.seed('two')
        self.assertFalse(self.reconcile()['ok']);self.reader.assert_not_called()

    def test_same_contract_in_different_account_does_not_cross(self):
        self.seed('two',account='b')
        self.assertTrue(self.reconcile()['ok'])
        self.assertEqual(self.store.query("SELECT status FROM trading_runs WHERE id='two'")[0]['status'],'accepted')

    def test_binding_does_not_confirm_fill_and_typo_can_be_corrected(self):
        self.store.execute("UPDATE broker_requests SET result='{}' WHERE request_id='auto_one'")
        self.reader.return_value={**self.report,'found':False}
        self.assertFalse(self.reconcile(order_id='typo')['ok'])
        self.assertEqual(self.rows()[0]['status'],'accepted')
        self.reader.return_value=self.report
        self.assertTrue(self.reconcile(order_id='test001')['ok'])
        self.assertEqual(len(json.loads(self.rows()[0]['result'])['binding_history']),1)

    def test_known_response_id_cannot_be_replaced_by_user(self):
        self.assertFalse(self.reconcile(order_id='other')['ok']);self.reader.assert_not_called()

    def test_today_inferred_date_cannot_cross_midnight(self):
        row=self.rows()[0];expected,day=request_plan(row)
        report={**self.report,'date_source':'broker_today_query','observed_at':'2026-11-03T00:00:01+08:00'}
        with self.assertRaisesRegex(ValueError,'跨越'):
            validate_report(report,row,'test001',expected,day,{},datetime(2026,11,3,0,0,2,tzinfo=CN))

    def test_pause_still_polls_and_rate_limits_reads(self):
        self.assertTrue(self.service.settings()['paused'])
        self.service.drain();self.reader.assert_called_once()
        self.service.drain();self.reader.assert_called_once()

    def test_failed_poll_is_rate_limited_and_missing_ids_do_not_navigate(self):
        self.reader.side_effect=ValueError('未适配')
        self.rec.poll();self.rec.poll();self.reader.assert_called_once()
        self.store.execute("UPDATE broker_requests SET result='{}'")
        self.rec.poll();self.reader.assert_called_once()

    def test_double_reconcile_is_not_queued(self):
        self.rec.lock.acquire()
        try:self.assertEqual(self.reconcile()['status'],'busy')
        finally:self.rec.lock.release()
        self.reader.assert_not_called()

    def test_manual_partial_preserves_ack_and_can_then_be_tracked(self):
        self.service.resolve('one','partial','test001',200,'已核对券商部分成交')
        req,run=self.rows()
        self.assertEqual((req['status'],run['status']),('partial','partial'))
        result=json.loads(req['result'])
        self.assertEqual(result['acknowledgement']['status'],'accepted')
        self.assertEqual(result['verification']['filled'],200)
        self.assertTrue(self.reconcile()['ok'])
        self.assertEqual(json.loads(self.rows()[1]['payload'])['verification']['origin'],'broker_auto')

    def test_manual_fill_regression_or_identity_change_rejected(self):
        self.service.resolve('one','partial','test001',200,'已核对券商部分成交')
        for status,ident,filled in [('partial','test001',100),('partial','other',200),('partial','test001',0),('cancelled','test001',600)]:
            with self.subTest(status=status,filled=filled),self.assertRaises(ValueError):
                self.service.resolve('one',status,ident,filled,'再次核对券商结果')

    def test_manual_updates_are_atomic_too(self):
        self.store.execute("CREATE TRIGGER deny_run_update BEFORE UPDATE ON trading_runs BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(Exception):self.service.resolve('one','filled','test001',600,'已核对全部成交')
        self.assertEqual(self.rows()[0]['status'],'accepted')


class GatewayAccountProofTests(unittest.TestCase):
    def test_each_query_checks_account_before_and_after(self):
        from contextlib import nullcontext
        from core import brokers
        client=Mock();client.ensure_ready.return_value={'account_verified':True}
        creds=SimpleNamespace(account='1234567890',broker='zhangle')
        store=Mock()
        for name in ('orders','trades','snapshot','order_report'):
            for failed_call in (0,1):
                client.reset_mock();client.ensure_ready.side_effect=[{'account_verified':True} if i!=failed_call else {'account_verified':False} for i in (0,1)]
                client.orders.return_value={};client.trades.return_value={};client.account.return_value={};client.order_report.return_value={}
                args=('a','contract','2026-11-02',{}) if name=='order_report' else ('a',)
                with self.subTest(name=name,failed_call=failed_call),patch('core.brokers.device_operation',return_value=nullcontext()),patch('core.brokers._adapter',return_value=({},creds,client)):
                    with self.assertRaises(brokers.BrokerError):getattr(brokers,name)(store,*args)


class NativeContractFillTests(unittest.TestCase):
    seed=ReconciliationTests.seed
    rows=ReconciliationTests.rows
    reconcile=ReconciliationTests.reconcile
    # Exercise fills using their actual average; never pretend it is the order limit.
    def setUp(self):
        ReconciliationTests.setUp(self)
        req,run=self.rows();ack=json.loads(req['result']);ack.update(order_id='test001',confirm=dict(code='000981',side='sell',quantity=600,price='2.13'))
        self.store.execute("UPDATE broker_requests SET result=? WHERE request_id='auto_one'",(json.dumps(ack),))
        self.fills={k:v for k,v in self.report.items() if k not in ('quantity','price','status')}
        self.fills.update(kind='contract_fills',average='2.14',amount='1284',source='ths_native_contract_group')

    def test_contract_full_and_partial_fills_with_captured_receipt(self):
        self.reader.return_value={**self.fills,'filled':200,'amount':'428'}
        self.assertTrue(self.reconcile()['ok']);self.assertEqual(self.rows()[0]['status'],'partial')
        self.reader.return_value=self.fills
        self.assertTrue(self.reconcile()['ok']);self.assertEqual(self.rows()[0]['status'],'filled')

    def test_no_fabricated_limit_price_and_no_fill_with_missing_receipt(self):
        self.reader.return_value=self.fills
        for change in [dict(confirm={}),dict(status='unknown'),dict(submitted=False),dict(confirm=dict(code='000981',side='sell',quantity=600,price='2.12'))]:
            req=self.rows()[0];result=json.loads(req['result']);result.update(change)
            self.store.execute("UPDATE broker_requests SET result=? WHERE request_id='auto_one'",(json.dumps(result),))
            self.assertFalse(self.reconcile()['ok'])

    def test_contract_fill_outside_limit_bad_total_or_overfill_rejected(self):
        for change in [dict(average='2.12',amount='1272'),dict(amount='1'),dict(filled=601),dict(filled=0,amount='0'),dict(source='guessed')]:
            self.reader.return_value={**self.fills,**change}
            with self.subTest(change=change):self.assertFalse(self.reconcile()['ok'])

    def test_late_fill_within_same_day_is_valid(self):
        self.reader.return_value={**self.fills,'time':'11:00:00'}
        self.store.execute("UPDATE broker_requests SET created_at='2026-11-02T10:00:00+08:00'")
        self.assertTrue(self.reconcile()['ok'])
