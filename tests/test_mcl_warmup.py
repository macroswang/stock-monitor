import unittest
from scripts.analyze_mcl_warmup import run


class WarmupTests(unittest.TestCase):
    def test_calculation_and_holiday_continuity(self):
        rows=[dict(date='2026-09-24',advance=10,decline=5),
              dict(date='2026-09-28',advance=15,decline=5),
              dict(date='2026-09-29',advance=5,decline=5)]
        values=run(rows,'2026-09-24')
        self.assertEqual(values['2026-09-24']['mcl'],0)
        self.assertAlmostEqual(values['2026-09-28']['mcl'],.25)
        self.assertEqual(values['2026-09-29']['samples'],3)

    def test_rejects_missing_duplicate_or_missing_start(self):
        rows=[dict(date='2026-09-24',advance=10,decline=5),
              dict(date='2026-09-29',advance=5,decline=5)]
        with self.assertRaises(ValueError):run(rows,'2026-09-24')
        with self.assertRaises(ValueError):run(rows,'2026-09-25')
        with self.assertRaises(ValueError):run(rows[:1]*2,'2026-09-24')


if __name__=='__main__':unittest.main()
