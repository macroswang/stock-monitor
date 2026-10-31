import unittest

from scripts.research_broad_weak_position import calculate, summarize


class BroadWeakPositionTest(unittest.TestCase):
    def test_condition_and_hypothetical_trade_timing(self):
        index=[{'date':f'2026-02-{n:02}', 'close':99 if n==1 else 100, 'ma20':100} for n in range(1,9)]
        etf={r['date']:[r['date'],'4.000','4.000','4.100','3.900','100'] for r in index}
        breadth=[{'date':'2026-02-01','advance':10,'decline':20,'breadth':33.3},
                 {'date':'2026-02-02','advance':10,'decline':20,'breadth':33.3}]
        rows,skipped=calculate(index,etf,breadth)
        self.assertFalse(skipped)
        self.assertEqual([r['condition'] for r in rows],[True,False])
        self.assertEqual((rows[0]['sell_date'],rows[0]['buy_date']),('2026-02-02','2026-02-07'))
        self.assertEqual(rows[0]['difference_yuan'],'-20.00')
        self.assertEqual(summarize(rows)['worse'],2)

    def test_duplicate_breadth_dates_are_rejected(self):
        with self.assertRaises(ValueError):calculate([],{},[{'date':'2026-02-01'},{'date':'2026-02-01'}])


if __name__=='__main__':unittest.main()
