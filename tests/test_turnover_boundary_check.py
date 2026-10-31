import unittest
from scripts.research_turnover_boundary_check import compare_cases


class TurnoverBoundaryTests(unittest.TestCase):
    def test_requires_same_dated_trading_row(self):
        snap={'anchor_timestamp':'2026-10-30T16:14:00+08:00','boundary_disagreements':[
            {'code':'sz300222','sina_turn':'5.03','tencent_turn':'4.96','tencent_timestamp':'2026-10-30T16:14:06+08:00'}]}
        history={'rows':[{'code':'sz.300222','rows':[{'date':'2026-10-30','turn':'4.9635','tradestatus':'1','close':'7.8300','preclose':'8.5800','volume':'10035'}]}]}
        quotes={'quotes':{'sz300222':{'timestamp':'2026-10-30T16:14:06+08:00','price':'7.83','previous_close':'8.58','volume':10000}}}
        row=compare_cases(snap,history,quotes)[0]
        self.assertFalse(row['bao_above_or_equal_5'])
        self.assertEqual(row['bao_tencent_difference'],'0.0035')
        history['rows'][0]['rows'][0]['date']='2026-10-29'
        with self.assertRaises(ValueError): compare_cases(snap,history,quotes)


if __name__ == '__main__': unittest.main()
