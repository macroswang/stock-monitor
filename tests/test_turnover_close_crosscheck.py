import unittest
from scripts.research_turnover_close_crosscheck import compare,select_controls


class TurnoverCrosscheckTests(unittest.TestCase):
    def setUp(self):
        self.sina={'volume':10001,'trade':'10.00','turnoverratio':'5.001'}
        self.tencent={'timestamp':'2026-10-30T15:01:00+08:00','volume':10000,'price':'10.00'}
    def test_rounded_threshold_is_explicitly_ambiguous(self):
        value=compare('sh600000',self.sina,self.tencent,'5.00','2026-10-30')
        self.assertTrue(value['above_or_equal'])
        self.assertTrue(value['threshold_ambiguous'])
    def test_mismatch_is_not_counted(self):
        for changed in ({**self.sina,'volume':12000},{**self.sina,'trade':'10.01'},
                        {**self.sina,'turnoverratio':'5.02'}):
            self.assertIn('error',compare('sh600000',changed,self.tencent,'5.00','2026-10-30'))
        self.assertIn('error',compare('sh600000',self.sina,self.tencent,'5.00','2026-10-29'))
    def test_control_selection_is_stable_disjoint_and_stratified(self):
        rows=[{'code':'a','sina_turn':'4.95'},{'code':'b','sina_turn':'5.08'},
              {'code':'c','sina_turn':'2'},{'code':'d','sina_turn':'9'}]
        selected=select_controls(rows,n=1)
        self.assertEqual(selected,select_controls(list(reversed(rows)),n=1))
        self.assertEqual({r['control_group'] for r in selected},{'near_5_percent','other'})
        self.assertEqual(len({r['code'] for r in selected}),2)


if __name__=='__main__': unittest.main()
