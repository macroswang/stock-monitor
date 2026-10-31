import unittest
from datetime import date
from scripts.analyze_p250_history import next_research_day
from scripts.research_p250_history import before


class ResearchCalendarTests(unittest.TestCase):
    def test_2025_holidays_and_year_boundary(self):
        self.assertEqual(next_research_day(date(2025,9,30)),date(2025,10,9))
        self.assertEqual(next_research_day(date(2025,12,31)),date(2026,1,5))
        self.assertIsNone(next_research_day(date(2024,12,30)))

    def test_lookback_respects_calendar(self):
        dates=before('2026-06-01',171)
        self.assertEqual(len(dates),171)
        self.assertEqual(dates[-1],'2026-05-29')
        self.assertEqual(dates[0],'2025-09-09')


if __name__=='__main__':unittest.main()
