import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from core.store import Store
from core.paper import Paper


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.store=Store(self.path/'monitor.sqlite3');self.paper=Paper(self.path/'paper.sqlite3',self.store)
        self.store.remember('sh600000','测试股票')
        for day in ['2026-10-19','2026-10-20']:
            self.store.cache('sh600000','minute',day,dict(source='test',volume_unit='shares',bars=[
                dict(time='09:31',close='10',volume=100000,complete=True),
                dict(time='09:32',close='11',volume=100000,complete=True),
                dict(time='09:33',close='9',volume=100000,complete=False)]))
        self.a=self.paper.call('paper_create',dict(cash='100000',name='A'))['id']

    def tearDown(self):
        self.paper.db.close();self.store.db.close();self.tmp.cleanup()

    def order(self,side='buy',shares=1000,stamp='2026-10-19 09:31',key='order-0001'):
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp=stamp))
        with self.paper.lock,self.paper.db:
            return self.paper.fill(self.paper.load(self.a),dict(account=self.a,id=key,code=q['code'],stamp=stamp,token=q['token'],side=side,shares=shares))

    def snapshot(self):return self.paper.call('paper_snapshot',dict(account=self.a))

    def test_hand_entered_cash_and_no_account_default(self):
        self.assertEqual(self.snapshot()['account']['cash'],10000000)
        for cash in ['0','-1','nan','inf','1000000001']:
            with self.assertRaises((ValueError,ArithmeticError)):self.paper.call('paper_create',dict(cash=cash))

    def test_buy_cash_includes_fees_and_t1_then_fifo_sale(self):
        buy=self.order();self.assertEqual(buy['fees'],510)
        s=self.snapshot();self.assertEqual(s['account']['cash'],8999490);self.assertEqual(s['positions'][0]['available'],0)
        self.assertEqual(self.order('sell',key='same-day')['status'],'rejected')
        sell=self.order('sell',stamp='2026-10-20 09:32',key='next-day')
        self.assertEqual(sell['fees'],1061);self.assertEqual(sell['realized'],98429)
        s=self.snapshot();self.assertEqual(s['positions'],[]);self.assertEqual(s['profit'],98429);self.assertEqual(s['account']['realized'],98429)

    def test_seed_sell_first_buyback_and_equity_identity(self):
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=2000,cost=10))
        self.assertEqual(self.snapshot()['positions'][0]['available'],2000)
        self.order('sell',2000,stamp='2026-10-19 09:32')
        self.order('buy',2000,stamp='2026-10-20 09:31',key='buy-back')
        s=self.snapshot();self.assertEqual(s['profit'],s['account']['realized']+s['unrealized'])
        self.assertEqual(s['positions'][0]['available'],0)
        with self.assertRaises(ValueError):self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=100,cost=10))

    def test_retries_and_id_conflict_are_atomic(self):
        first=self.order();self.assertEqual(self.order(),first)
        self.assertEqual(len(self.snapshot()['orders']),1)
        with self.assertRaises(ValueError):self.order(shares=100,key='order-0001')
        self.assertEqual(len(self.snapshot()['orders']),1)

    def test_concurrent_duplicate_submit_is_single_fill(self):
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.order(),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(self.snapshot()['orders']),1)

    def test_insufficient_cash_t1_and_board_lot_rejections_preserve_cash(self):
        for side,shares,key in [('buy',1,'bad-lot1'),('buy',20000,'no-cash1'),('sell',100,'no-stock')]:
            self.assertEqual(self.order(side,shares,key=key)['status'],'rejected')
        self.assertEqual(self.snapshot()['account']['cash'],10000000)

    def test_reverse_clock_and_invalid_minute_rejected(self):
        self.order(stamp='2026-10-20 09:32')
        with self.assertRaises(ValueError):self.order(stamp='2026-10-19 09:31',key='earlier1')
        with self.assertRaises(ValueError):self.order(stamp='2026-10-20 09:33',key='pending1')
        with self.assertRaises(ValueError):self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-20 12:00'))

    def test_valuation_uses_only_completed_prices_before_account_clock(self):
        self.order();s=self.snapshot();self.assertEqual(s['positions'][0]['price'],1000)
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(self.snapshot()['positions'][0]['price'],1100)
        self.assertEqual(self.snapshot()['account']['cash'],s['account']['cash'])

    def test_quote_revision_requires_reconfirmation(self):
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp='2026-10-19 09:31'))
        self.store.cache('sh600000','minute','2026-10-19',dict(bars=[dict(time='09:31',close='12',volume=100000,complete=True)]))
        with self.assertRaises(ValueError):self.paper.call('paper_order',dict(account=self.a,id='revision',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=100))
        self.assertEqual(self.snapshot()['orders'],[])

    def test_partial_fifo_costs_and_odd_lot_liquidation(self):
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=155,cost='10.03'))
        self.assertEqual(self.order('sell',55)['status'],'rejected')
        self.assertEqual(self.order('sell',155,key='all-odd1')['status'],'filled')
        self.assertEqual(self.snapshot()['positions'],[])

    def test_capacity_and_slippage(self):
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=100001,cost='.01'))
        self.assertEqual(self.order('sell',100001)['status'],'rejected')
        b=self.paper.call('paper_create',dict(cash=100000,slippage_bps=5))['id'];self.a=b
        self.assertEqual(self.order()['price'],1001)

    def test_persistence_and_account_isolation(self):
        self.order();self.paper.db.close();self.paper=Paper(self.path/'paper.sqlite3',self.store)
        self.assertEqual(len(self.snapshot()['positions']),1)
        b=self.paper.call('paper_create',dict(cash=12000))['id']
        self.assertEqual(self.paper.call('paper_snapshot',dict(account=b))['positions'],[])
        self.assertEqual(len(self.snapshot()['orders']),1)
