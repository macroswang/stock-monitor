import unittest
from datetime import datetime
from unittest.mock import patch
from core.paper_session import trading_error
from tests import test_paper

class TradingSessionTests(unittest.TestCase):
    def test_beijing_sessions_boundaries_and_real_closed_dates(self):
        samples={
            '2026-10-23T09:29:59+08:00':False,'2026-10-23T09:30:00+08:00':True,
            '2026-10-23T11:30:00+08:00':True,'2026-10-23T11:30:01+08:00':False,
            '2026-10-23T12:59:59+08:00':False,'2026-10-23T13:00:00+08:00':True,
            '2026-10-23T14:56:59+08:00':True,'2026-10-23T14:57:00+08:00':False,
            '2026-10-23T15:00:00+08:00':False,'2026-10-23T21:00:00+08:00':False,
            '2026-10-25T10:00:00+08:00':False,'2026-10-10T10:00:00+08:00':False,
            '2026-01-01T10:00:00+08:00':False,'2026-02-23T10:00:00+08:00':False,
            '2026-04-06T10:00:00+08:00':False,'2026-05-05T10:00:00+08:00':False,
            '2026-06-19T10:00:00+08:00':False,'2026-09-25T10:00:00+08:00':False,
            '2026-10-01T10:00:00+08:00':False,'2026-10-08T10:00:00+08:00':True,
            '2026-10-23T02:00:00+00:00':True,'2026-10-23T18:00:00+00:00':False,
            '2027-01-04T10:00:00+08:00':False,
        }
        for stamp,allowed in samples.items():
            with self.subTest(stamp=stamp):self.assertEqual(not trading_error(datetime.fromisoformat(stamp)),allowed)

class PaperWallClockTests(unittest.TestCase):
    setUp=test_paper.PaperTests.setUp
    tearDown=test_paper.PaperTests.tearDown
    snapshot=test_paper.PaperTests.snapshot

    def args(self):
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp='2026-10-19 09:31'))
        return dict(account=self.a,id='real-time-guard',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price=12)

    def test_closed_wall_clock_rejects_historical_orders_without_ledger_changes(self):
        args=self.args();before=self.snapshot()
        for stamp in ['2026-10-25T10:00:00+08:00','2026-10-23T12:00:00+08:00','2026-10-23T18:00:00+08:00','2026-10-01T10:00:00+08:00']:
            with self.subTest(now=stamp):
                self.market_now.return_value=datetime.fromisoformat(stamp)
                with self.assertRaisesRegex(ValueError,'当前北京时间.*禁止模拟委托和成交'):self.paper.call('paper_order',args)
                self.assertEqual(self.snapshot(),before)
                self.assertEqual(self.paper.call('paper_export',dict(account=self.a,kind='fills')),[])

    def test_pending_orders_cannot_fill_via_advance_or_new_order_during_lunch(self):
        args=self.args();self.paper.call('paper_order',args);before=self.snapshot()
        self.market_now.return_value=datetime.fromisoformat('2026-10-23T12:00:00+08:00')
        with self.assertRaisesRegex(ValueError,'不在交易时间'):self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(self.snapshot(),before)
        with self.assertRaisesRegex(ValueError,'不在交易时间'):self.paper.call('paper_order',dict(args,id='closed-second-order'))
        self.assertEqual(self.snapshot(),before)
        # Cancellation only releases reservations and remains available.
        self.paper.call('paper_cancel',dict(account=self.a,id=args['id']))
        self.assertEqual(self.snapshot()['frozen_cash'],0);self.assertEqual(self.snapshot()['fill_count'],0)

    def test_historical_fill_is_allowed_when_real_market_is_open(self):
        self.market_now.return_value=datetime.fromisoformat('2026-10-23T13:00:00+08:00')
        self.paper.call('paper_order',self.args())
        s=self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(s['fill_count'],1)

    def test_boundary_closure_at_execution_rolls_back_whole_batch(self):
        self.paper.call('paper_order',self.args());before=self.snapshot()
        with patch('core.paper.trading_error',side_effect=['','当前北京时间：不在交易时间内，禁止模拟委托和成交。']):
            with self.assertRaisesRegex(ValueError,'不在交易时间'):self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(self.snapshot(),before)
