import unittest
from scripts.research_adjusted_ma import analyze_adjusted


class AdjustedMAResearchTests(unittest.TestCase):
    def test_previous_close_rescales_only_earlier_prices(self):
        days=['2026-09-21','2026-09-22']
        data={days[0]:[{'symbol':'600001.SH','close':'10','pre_close':'10'}],
              days[1]:[{'symbol':'600001.SH','close':'5.5','pre_close':'5'}]}
        r=analyze_adjusted(days,lambda d:data[d],windows=(2,))
        self.assertIsNone(r[0]['windows']['2']['percent'])
        self.assertEqual(r[1]['adjusted_stocks'],1)
        self.assertEqual(r[1]['windows']['2']['above'],1)

    def test_missing_session_resets_window(self):
        days=['2026-09-21','2026-09-22','2026-09-23']
        data={days[0]:[{'symbol':'600001.SH','close':'10','pre_close':'10'}],
              days[1]:[],days[2]:[{'symbol':'600001.SH','close':'5','pre_close':'5'}]}
        r=analyze_adjusted(days,lambda d:data[d],windows=(2,))
        self.assertEqual(r[-1]['windows']['2']['eligible'],0)
        self.assertEqual(r[-1]['adjusted_stocks'],0)

    def test_invalid_factor_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze_adjusted(['2026-09-21'],lambda d:[{'symbol':'600001.SH','close':'10','pre_close':'NaN'}],windows=(2,))


if __name__=='__main__':unittest.main()
