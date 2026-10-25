import json
import unittest
from tests import test_paper

class DayProfitTests(unittest.TestCase):
    setUp=test_paper.PaperTests.setUp
    tearDown=test_paper.PaperTests.tearDown
    snapshot=test_paper.PaperTests.snapshot
    order=test_paper.PaperTests.order

    def previous(self,day,price):
        payload=self.store.getcache('sh600000','minute',day)[0]['data'];payload['previous_close']=price
        self.store.cache('sh600000','minute',day,payload)

    def test_new_cash_account_has_no_day_until_started(self):
        self.assertIsNone(self.snapshot()['day_pnl']['profit'])
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:31'))
        self.assertEqual(self.snapshot()['day_pnl']['profit'],0)

    def test_first_day_flat_start_includes_buy_fees_without_needing_yesterday_price(self):
        self.order()
        s=self.snapshot();self.assertEqual(s['day_pnl']['profit'],-510)
        self.assertEqual(s['day_pnl']['profit'],s['profit']);self.assertEqual(s['day_pnl']['opening_equity'],s['account']['initial'])

    def test_seed_day_profit_excludes_prior_unrealized_profit(self):
        self.previous('2026-10-19','9.80')
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=1000,cost=9))
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:31'))
        s=self.snapshot();self.assertEqual(s['profit'],100000);self.assertEqual(s['day_pnl']['profit'],20000)
        self.assertEqual(s['day_pnl']['date'],'2026-10-19')

    def test_overnight_sale_uses_start_shares_and_yesterday_close_not_fifo_cost(self):
        self.order();self.previous('2026-10-20','10.50')
        self.order('sell',stamp='2026-10-20 09:32',key='day-sell')
        s=self.snapshot();self.assertEqual(s['positions'],[])
        self.assertEqual(s['profit'],98429);self.assertEqual(s['day_pnl']['profit'],48939)
        self.assertEqual(s['day_pnl']['opening_equity'],10049490)

    def test_cash_only_new_day_is_zero_and_uses_replay_date(self):
        self.order();self.previous('2026-10-20','10.50');self.order('sell',stamp='2026-10-20 09:31',key='day-sell')
        self.store.cache('sh600000','minute','2026-10-21',dict(source='test',bars=[dict(time='09:31',close='10',volume=10000,complete=True)]))
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-21 09:31'))
        self.assertEqual(self.snapshot()['day_pnl']['profit'],0)

    def test_missing_or_invalid_previous_close_is_unknown_not_zero(self):
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=1000,cost=9))
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:31'))
        for previous in [None,'0','nan']:
            self.previous('2026-10-19',previous);s=self.snapshot()
            self.assertIsNone(s['day_pnl']['profit']);self.assertIn('昨收',s['day_pnl']['reason'])

    def test_missing_current_position_price_does_not_invent_daily_profit(self):
        self.previous('2026-10-19','9.8')
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=1000,cost=9))
        self.store.cache('sz000001','minute','2026-10-19',dict(bars=[dict(time='09:30',close='10',volume=10000,complete=True)]))
        self.paper.call('paper_advance',dict(account=self.a,code='sz000001',stamp='2026-10-19 09:30'))
        self.assertIsNone(self.snapshot()['day_pnl']['profit'])

    def test_pending_and_cancel_only_do_not_change_daily_profit(self):
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp='2026-10-19 09:31'))
        o=self.paper.call('paper_order',dict(account=self.a,id='pending-day',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price=1))
        self.assertEqual(self.snapshot()['day_pnl']['profit'],0)
        self.paper.call('paper_cancel',dict(account=self.a,id=o['id']));self.assertEqual(self.snapshot()['day_pnl']['profit'],0)

    def test_daily_profit_does_not_change_ledger_or_depend_on_history_page_limit(self):
        self.order();before=self.paper.load(self.a)
        a=self.paper.call('paper_snapshot',dict(account=self.a,history_limit=1));b=self.snapshot()
        self.assertEqual(a['day_pnl'],b['day_pnl']);self.assertEqual(self.paper.load(self.a),before)
