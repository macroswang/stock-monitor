import unittest
from decimal import Decimal

from scripts.research_trend_etf_cash import simulate


class TrendEtfCashTests(unittest.TestCase):
    def test_prior_close_controls_next_open_and_both_fees_apply(self):
        index=[{'date':'2026-01-01','close':10,'ma20':9},
               {'date':'2026-01-02','close':8,'ma20':9},
               {'date':'2026-01-03','close':10,'ma20':9}]
        etf={d:[d,'10','10','10.1','9.9','100'] for d in ('2026-01-02','2026-01-03')}
        result=simulate(index,etf,'2026-01-02','2026-01-03',capital=Decimal('10000'))
        self.assertEqual([x['direction'] for x in result['trades']], ['buy','sell'])
        self.assertEqual([x['signal_date'] for x in result['trades']], ['2026-01-01','2026-01-02'])
        self.assertEqual([x['quantity'] for x in result['trades']], [900,900])
        self.assertEqual(result['final_value'], '9988.20')

    def test_unreachable_slipped_open_does_not_invent_a_fill(self):
        index=[{'date':'2026-01-01','close':10,'ma20':9},
               {'date':'2026-01-02','close':10,'ma20':9}]
        etf={'2026-01-02':['2026-01-02','10','10','10','10','100']}
        result=simulate(index,etf,'2026-01-02','2026-01-02',capital=Decimal('10000'))
        self.assertEqual(result['trade_count'],0)
        self.assertEqual(len(result['skipped']),1)
        self.assertEqual(result['final_value'],'10000.00')


if __name__=='__main__':unittest.main()
