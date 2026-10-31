import unittest
from scripts.research_author_p_hypothesis import analyze


def stock(symbol,close):return {'symbol':symbol,'close':str(close)}


class PHypothesisTests(unittest.TestCase):
    def test_missing_day_resets_stock_window_and_equal_is_not_above(self):
        dates=['2026-09-21','2026-09-22','2026-09-23']
        data={dates[0]:[stock('600001.SH',10),stock('000001.SZ',10)],
              dates[1]:[stock('600001.SH',12)],
              dates[2]:[stock('600001.SH',12),stock('000001.SZ',14)]}
        result=analyze(dates,lambda d:data[d],windows=(2,))
        self.assertEqual(result[1]['windows']['2'],{'eligible':1,'above':1,'percent':100.0})
        self.assertEqual(result[2]['windows']['2'],{'eligible':1,'above':0,'percent':0.0})

    def test_gap_duplicate_and_nonfinite_are_rejected(self):
        with self.assertRaises(ValueError):analyze(['2026-09-21','2026-09-23'],lambda d:[stock('600001.SH',10)],windows=(2,))
        with self.assertRaises(ValueError):analyze(['2026-09-21'],lambda d:[stock('600001.SH',10),stock('600001.SH',11)],windows=(2,))
        with self.assertRaises(ValueError):analyze(['2026-09-21'],lambda d:[stock('600001.SH','NaN')],windows=(2,))

    def test_decimal_prices_equal_to_mean_are_not_counted_above(self):
        days=['2026-09-21','2026-09-22','2026-09-23']
        result=analyze(days,lambda d:[stock('600001.SH','2.32')],windows=(3,))
        self.assertEqual(result[-1]['windows']['3']['above'],0)


if __name__=='__main__':unittest.main()
