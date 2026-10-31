import unittest
from scripts.research_turnover_followup_compare import analyze


class TurnoverFollowupTests(unittest.TestCase):
    def test_price_date_volume_and_threshold_requirements(self):
        item={'code':'sz300222','sina_turn':'5.03','tencent_turn':'4.96',
              'tencent_price':'7.83','tencent_previous_close':'8.58','tencent_volume':10000}
        s={'anchor_timestamp':'2026-10-30T16:14:00+08:00','followup_candidates':[item]}
        row={'date':'2026-10-30','code':'sz.300222','tradestatus':'1','close':'7.8300',
             'preclose':'8.5800','volume':'10035','turn':'4.9635'}
        h={'rows':[{'code':'sz300222','rows':[row]}]}
        result=analyze(s,h)
        self.assertEqual(result['counts']['changed_threshold_class'],1)
        self.assertEqual(result['counts']['tencent_closer'],1)
        row['volume']='10200'
        self.assertEqual(analyze(s,h)['counts']['missing_or_invalid'],1)
        row['volume']='10035';row['turn']='5.0000'
        self.assertEqual(analyze(s,h)['counts']['bao_5_percent_ambiguous'],1)

    def test_incomplete_candidates_cannot_emit_corrected_population(self):
        s={'anchor_timestamp':'2026-10-30T16:14:00+08:00','followup_candidates':[],
           'summary':{'通过两源比较':10,'两源换手率超出显示精度':1,'threshold_ambiguous':0}}
        self.assertNotIn('mixed_source_study',analyze(s,{'rows':[]}))


if __name__=='__main__': unittest.main()
