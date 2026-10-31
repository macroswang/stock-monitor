import unittest
from scripts.research_market_regime import calculate


class RegimeResearchTest(unittest.TestCase):
    def test_uses_next_open_not_signal_close_and_rejects_missing_future(self):
        rows=[{'date':f'2026-01-{i:02d}','open':100+i,'close':100+i,'boll_mid':105,
               'gap_before':False} for i in range(1,8)]
        breadth=[{'date':'2026-01-01','status':'closed','missing':0,'advancing_percent':10}]
        result=calculate(breadth,rows)
        self.assertTrue(result[0]['weak'])
        self.assertAlmostEqual(result[0]['one_day'],0)
        self.assertAlmostEqual(result[0]['five_day'],(106/102-1)*100)
        rows[4]['gap_before']=True
        self.assertEqual(calculate(breadth,rows),[])

    def test_excludes_provisional(self):
        rows=[{'date':f'2026-01-{i:02d}','open':1,'close':1,'boll_mid':2,
               'gap_before':False} for i in range(1,8)]
        self.assertEqual(calculate([{'date':'2026-01-01','status':'provisional','missing':0,'advancing_percent':2}],rows),[])


if __name__=='__main__': unittest.main()
