import unittest
from tests import test_paper


class PaperTradePlanTests(unittest.TestCase):
    setUp = test_paper.PaperTests.setUp
    tearDown = test_paper.PaperTests.tearDown
    snapshot = test_paper.PaperTests.snapshot

    def order(self, **changes):
        stamp = '2026-10-19 09:31'
        quote = self.paper.call('paper_quote', {'code': 'sh600000', 'stamp': stamp})
        args = dict(account=self.a, id='plan-0001', code=quote['code'], stamp=stamp,
                    token=quote['token'], side='buy', shares=100, limit_price='10',
                    plan={'reason': '分批观察', 'invalidation_price': '9.50'})
        args.update(changes)
        return self.paper.call('paper_order', args)

    def test_plan_and_review_survive_without_changing_financial_state(self):
        order = self.order()
        self.assertEqual(order['plan'], {'reason': '分批观察', 'invalidation_price': 950, 'risk_budget': None})
        before = self.snapshot()
        self.paper.call('paper_review', {'account': self.a, 'id': order['id'], 'review': '按计划等待'})
        after = self.snapshot()
        self.assertEqual(after['orders'][0]['review'], '按计划等待')
        self.assertEqual(after['orders'][0]['plan'], order['plan'])
        for key in ('available_cash', 'frozen_cash', 'equity', 'profit', 'fills'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(before['account']['cash'], after['account']['cash'])
        self.assertEqual(self.order()['review'], '按计划等待')

    def test_bad_plan_and_cross_account_review_are_rejected(self):
        for invalid in ('-1', '1.001', 'nan'):
            with self.assertRaises((ValueError, ArithmeticError)):
                self.order(plan={'invalidation_price': invalid})
        self.assertEqual(self.snapshot()['orders'], [])
        self.order()
        other = self.paper.call('paper_create', {'cash': 10000})['id']
        with self.assertRaises(ValueError):
            self.paper.call('paper_review', {'account': other, 'id': 'plan-0001', 'review': '错误账户'})
        with self.assertRaises(ValueError):
            self.paper.call('paper_review', {'account': self.a, 'id': 'plan-0001', 'review': 'x' * 501})

    def test_risk_limit_checks_round_trip_fees_without_changing_cash(self):
        rejected = self.order(plan={'invalidation_price':'9.50', 'risk_budget':'50.00'})
        self.assertEqual(rejected['status'], 'rejected')
        self.assertIn('超过风险上限', rejected['reason'])
        self.assertEqual(self.snapshot()['frozen_cash'], 0)
        accepted = self.order(id='plan-0002', plan={'invalidation_price':'9.50', 'risk_budget':'100.00'})
        self.assertEqual(accepted['status'], 'open')
        self.assertEqual(accepted['plan']['risk_budget'], 10000)
        self.assertGreater(self.snapshot()['frozen_cash'], 0)

    def test_partial_fill_keeps_plan_and_review_without_changing_ledger(self):
        self.store.cache('sh600000','minute','2026-10-19',dict(source='test',volume_unit='shares',bars=[
            dict(time='09:31',close='10',volume=10000,complete=True),
            dict(time='09:32',close='9.5',volume=10000,complete=True)]))
        self.order(shares=200)
        filled=self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp='2026-10-19 09:32'))
        self.assertEqual(filled['orders'][0]['status'], 'partial')
        self.assertEqual(filled['orders'][0]['plan']['reason'], '分批观察')
        self.paper.call('paper_review',dict(account=self.a,id='plan-0001',review='部分成交'))
        after=self.snapshot()
        self.assertEqual(after['orders'][0]['review'], '部分成交')
        self.assertEqual(filled['positions'], after['positions'])
        self.assertEqual(filled['fills'], after['fills'])
        self.assertEqual(filled['frozen_cash'], after['frozen_cash'])

    def test_limit_prices_are_in_revision_token(self):
        stamp='2026-10-19 09:31'
        quote=self.paper.call('paper_quote',dict(code='sh600000',stamp=stamp))
        self.assertIsNone(quote['limit_up'])
        self.store.cache('sh600000','minute','2026-10-19',dict(source='test',volume_unit='shares',
            limit_up='11',limit_down='9',bars=[dict(time='09:31',close='10',volume=100000,complete=True)]))
        changed=self.paper.call('paper_quote',dict(code='sh600000',stamp=stamp))
        self.assertEqual((changed['limit_up'],changed['limit_down']),(1100,900))
        self.assertNotEqual(changed['token'],quote['token'])
        with self.assertRaisesRegex(ValueError,'行情已修订'):
            self.paper.call('paper_order',dict(account=self.a,id='plan-0001',code='sh600000',stamp=stamp,
                token=quote['token'],side='buy',shares=100,limit_price='10'))


if __name__ == '__main__':
    unittest.main()
