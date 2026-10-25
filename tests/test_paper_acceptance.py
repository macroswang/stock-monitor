"""Cross-feature acceptance: resource isolation, randomized ledger reconciliation and restart."""
import json
import random
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_paper

class PaperAcceptanceTests(unittest.TestCase):
    setUp=test_paper.PaperTests.setUp
    tearDown=test_paper.PaperTests.tearDown
    snapshot=test_paper.PaperTests.snapshot

    def submit(self, key, side, shares, limit, stamp='2026-10-19 09:31'):
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp=stamp))
        return self.paper.call('paper_order',dict(account=self.a,id=key,code=q['code'],stamp=stamp,token=q['token'],side=side,shares=shares,limit_price=limit))

    def test_sell_fee_shortfall_cannot_spend_other_buy_order_reserve(self):
        self.a=self.paper.call('paper_create',dict(cash=10))['id']
        self.store.cache('sh600000','minute','2026-10-19',dict(source='test',volume_unit='shares',bars=[dict(time='09:31',close='.01',volume=100000,complete=True),dict(time='09:32',close='.01',volume=100000,complete=True)]))
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=100,cost='.01'))
        self.assertEqual(self.submit('reserve-buy','buy',100,.01)['status'],'open')
        result=self.submit('fee-shortfall','sell',100,.01)
        self.assertEqual(result['status'],'rejected')
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertGreaterEqual(self.snapshot()['available_cash'],0)

    def test_sell_fee_margin_is_reserved_until_cancelled(self):
        self.a=self.paper.call('paper_create',dict(cash=10))['id']
        self.store.cache('sh600000','minute','2026-10-19',dict(source='test',bars=[dict(time='09:31',close='.01',volume=100000,complete=True)]))
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=100,cost='.01'))
        self.assertEqual(self.submit('reserve-sell','sell',100,.01)['status'],'open')
        self.assertEqual(self.snapshot()['frozen_cash'],400)
        self.assertEqual(self.submit('blocked-buy','buy',100,.01)['status'],'rejected')
        self.paper.call('paper_cancel',dict(account=self.a,id='reserve-sell'))
        self.assertEqual(self.snapshot()['frozen_cash'],0)

    def test_large_low_price_sale_reserves_first_partial_minimum_fee(self):
        self.a=self.paper.call('paper_create',dict(cash=19))['id']
        self.store.cache('sh600000','minute','2026-10-19',dict(volume_unit='shares',bars=[dict(time=t,close='.01',volume=10000,complete=True) for t in ['09:31','09:32']]))
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=1000,cost='.01'))
        self.submit('large-reserve-buy','buy',100,.01)
        self.assertEqual(self.submit('partial-fee-block','sell',1000,.01)['status'],'rejected')
        self.paper.call('paper_cancel',dict(account=self.a,id='large-reserve-buy'))
        self.assertEqual(self.submit('partial-fee-sell','sell',1000,.01)['status'],'open')
        self.assertEqual(self.snapshot()['frozen_cash'],400)
        s=self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(s['fill_count'],1);self.assertEqual(s['positions'][0]['shares'],900)
        self.assertEqual(s['frozen_cash'],0);self.assertGreaterEqual(s['available_cash'],0)

    def test_fills_page_contains_only_successful_executions(self):
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp='2026-10-19 09:31'))
        with self.paper.db:
            self.paper.fill(self.paper.load(self.a),dict(id='legacy-reject',code=q['code'],stamp=q['stamp'],token=q['token'],side='sell',shares=100))
        s=self.snapshot();self.assertEqual(s['fill_count'],0);self.assertEqual(s['fills'],[])
        self.assertEqual(s['orders'][0]['status'],'rejected')

    def test_impossible_minute_rejected_even_with_malformed_cached_label(self):
        self.store.cache('sh600000','minute','2026-10-19',dict(bars=[dict(time='09:99',close='10',volume=1000,complete=True)]))
        with self.assertRaises(ValueError):self.paper.call('paper_quote',dict(code='sh600000',stamp='2026-10-19 09:99'))

    def test_execution_failure_rolls_back_cash_lots_parent_and_fill_index(self):
        self.submit('atomic-order','buy',100,12)
        before=self.snapshot()
        with patch.object(self.paper,'index_fill',side_effect=RuntimeError('injected disk error')):
            with self.assertRaisesRegex(RuntimeError,'injected'):
                self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(self.snapshot(),before)
        result=self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(result['fill_count'],1)
        self.assertEqual(result['orders'][0]['status'],'filled')

    def test_two_connections_duplicate_submit_and_advance_commit_once(self):
        from core.paper import Paper
        peer=Paper(self.path/'paper.sqlite3',self.store)
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp='2026-10-19 09:31'))
        args=dict(account=self.a,id='concurrent-order',code=q['code'],stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price=12)
        try:
            with ThreadPoolExecutor(2) as pool:
                results=list(pool.map(lambda p:p.call('paper_order',args),[self.paper,peer]))
            self.assertEqual(results[0],results[1])
            with ThreadPoolExecutor(2) as pool:
                list(pool.map(lambda p:p.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32')),[self.paper,peer]))
            s=self.snapshot();self.assertEqual(s['fill_count'],1);self.assertEqual(s['order_count'],1)
            self.assertEqual(s['positions'][0]['shares'],100)
        finally:peer.db.close()

    def test_restart_partial_order_preserves_minimum_fee_and_cancellation(self):
        from core.paper import Paper
        self.store.cache('sh600000','minute','2026-10-19',dict(volume_unit='shares',bars=[dict(time=t,close='10',volume=10000,complete=True) for t in ['09:31','09:32','09:33']]))
        self.submit('restart-partial','buy',300,10)
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        before=self.snapshot();self.assertEqual(before['orders'][0]['status'],'partial')
        self.paper.db.close();self.paper=Paper(self.path/'paper.sqlite3',self.store)
        self.assertEqual(self.snapshot(),before)
        self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:33'))
        self.paper.call('paper_cancel',dict(account=self.a,id='restart-partial'))
        s=self.snapshot();self.assertEqual(s['orders'][0]['filled'],200)
        self.assertEqual(sum(o['commission'] for o in s['fills']),500)
        self.assertEqual(s['frozen_cash'],0);self.assertEqual(s['positions'][0]['shares'],200)

    def test_randomized_multi_day_orders_reconcile_independent_cash_shares_and_fees(self):
        from core.paper import Paper
        rng=random.Random(20261025);times=[f'{m//60:02}:{m%60:02}' for m in range(571,631)]
        days=['2026-10-19','2026-10-20','2026-10-21']
        for day in days:
            bars=[dict(time=t,close=f'{10+rng.randint(-10,10)/100:.2f}',volume=10000,complete=True) for t in times]
            bars.append(dict(time='15:00',close='10',volume=100000,complete=True))
            self.store.cache('sh600000','minute',day,dict(source='test',volume_unit='shares',previous_close='10',bars=bars))
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=2000,cost='10'))
        initial_cash=10000000-2000000
        counter=0
        for day in days:
            for time in times:
                stamp=day+' '+time
                self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp=stamp))
                if rng.random()<.7:
                    counter+=1;self.submit(f'random-{counter:04}',rng.choice(['buy','sell']),rng.choice([100,200,500]),rng.choice([9.8,10,10.2]),stamp)
                active=[o for o in self.paper.pending(self.a) if o['status'] in ('open','partial')]
                if active and rng.random()<.25:self.paper.call('paper_cancel',dict(account=self.a,id=rng.choice(active)['id']))
                s=self.snapshot();fills=self.paper.call('paper_export',dict(account=self.a,kind='fills'))
                expected_cash=initial_cash+sum((o['amount'] if o['side']=='sell' else -o['amount'])-o['fees'] for o in fills)
                expected_shares=2000+sum(o['shares'] if o['side']=='buy' else -o['shares'] for o in fills)
                self.assertEqual(s['account']['cash'],expected_cash);self.assertEqual(sum(p['shares'] for p in s['positions']),expected_shares)
                self.assertEqual(s['total_fees'],sum(o['fees'] for o in fills));self.assertGreaterEqual(s['available_cash'],0)
                self.assertEqual(s['profit'],s['account']['realized']+s['unrealized'])
                for p in s['positions']:self.assertGreaterEqual(p['available'],0)
                for o in self.paper.pending(self.a):
                    executions=[f for f in fills if f.get('parent_id')==o['id']]
                    self.assertEqual(o['filled'],sum(f['shares'] for f in executions));self.assertEqual(o['fees'],sum(f['fees'] for f in executions))
            self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp=day+' 15:00'))
            self.assertEqual(self.snapshot()['frozen_cash'],0)
            before=self.snapshot();self.paper.db.close();self.paper=Paper(self.path/'paper.sqlite3',self.store)
            after=self.snapshot();self.assertEqual(before,after)
        self.assertGreater(len(self.paper.call('paper_export',dict(account=self.a,kind='fills'))),20)
