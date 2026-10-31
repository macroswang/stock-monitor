import unittest
from scripts.research_turnover_controls_compare import evaluate


class TurnoverControlsTests(unittest.TestCase):
    def test_group_counts_and_classification(self):
        candidate={'code':'sz300222','sina_turn':'5.03','tencent_turn':'5.03',
                   'tencent_price':'7.83','tencent_previous_close':'8.58','tencent_volume':10000,
                   'control_group':'near_5_percent'}
        snapshot={'anchor_timestamp':'2026-10-30T16:14:00+08:00','control_sample':[candidate]}
        row={'date':'2026-10-30','code':'sz.300222','tradestatus':'1','close':'7.8300',
             'preclose':'8.5800','volume':'10035','turn':'4.9635'}
        report=evaluate(snapshot,{'rows':[{'code':'sz300222','rows':[row]}]})
        self.assertEqual(report['near_5_percent']['counts']['changed_threshold_class'],1)
        self.assertEqual(report['near_5_percent']['sina_difference_over_tolerance'],1)
        self.assertEqual(report['other']['counts']['eligible'],0)


if __name__=='__main__': unittest.main()
