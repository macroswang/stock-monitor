import unittest

from scripts.trin_scope_diagnostics import compute
from scripts.trin_exploratory_outcomes import summarize


class TrinDiagnosticTests(unittest.TestCase):
    def test_scope_and_turnover_vs_shares(self):
        def row(code, close, vol, amount, is_st='0'):
            return dict(code=code, close=str(close), preclose='10', volume=str(vol),
                        amount=str(amount), tradestatus='1', isST=is_st)
        rows=[row('sh.600001',11,1000,11000),row('sz.000001',9,500,4500),
              row('sh.600002',10,100,1000),row('sh.689009',11,9000,99000),
              row('sz.300001',11,2000,22000,'1')]
        result=compute(rows,'main','shares')
        self.assertEqual((result['advance'],result['decline'],result['flat']),(1,1,1))
        self.assertEqual(result['trin'],.5)
        self.assertAlmostEqual(compute(rows,'main','amount')['trin'],4500/11000)
        self.assertEqual(compute(rows,'exclude_st','shares')['trin'],.5)
        self.assertEqual(compute(rows,'all','shares')['advance'],2)

    def test_event_filter_and_index_return_summary(self):
        rows=[{'signal_date':'a','trin':.6,'breadth':.1,'shanghai_open_close_pct':1,'csi300_open_close_pct':2},
              {'signal_date':'b','trin':1.1,'breadth':.1,'shanghai_open_close_pct':-1,'csi300_open_close_pct':-2},
              {'signal_date':'c','trin':.5,'breadth':.5,'shanghai_open_close_pct':0,'csi300_open_close_pct':0}]
        both=summarize(rows,'both')
        self.assertEqual(both['dates'],['a'])
        self.assertEqual(both['csi300_next_open_close']['mean_pct'],2)
        self.assertEqual(summarize(rows,'all')['csi300_next_open_close']['positive_count'],1)


if __name__=='__main__':unittest.main()
