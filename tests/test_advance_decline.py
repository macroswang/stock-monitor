import unittest
from datetime import date

from core.breadth import add_advance_decline, attach_historical_ad_reference, _next_verified_trading_day


def row(day, advance, decline, **changes):
    return dict(date=day, advance=advance, decline=decline, expected=100, covered=100,
                missing=0, status='closed', source='example', universe='example pool', **changes)


class AdvanceDeclineTests(unittest.TestCase):
    def test_calculates_daily_ratio_and_cumulative_difference(self):
        data = [row('2026-10-22', 30, 60), row('2026-10-23', 60, 30), row('2026-10-26', 80, 20)]
        out = add_advance_decline(data)
        self.assertEqual([x['adl'] for x in out], [-30, 0, 60])
        self.assertEqual([x['adr'] for x in out], [.5, 2, 4])
        self.assertEqual(out[-1]['adl_start'], '2026-10-22')
        self.assertEqual(out[-1]['adl_samples'], 3)
        self.assertFalse(out[-1]['adl_gap_before'])
        self.assertNotIn('adl', data[0])

    def test_gap_source_and_incomplete_reset_without_connecting(self):
        rows = [row('2026-10-22', 30, 60), row('2026-10-26', 60, 30), row('2026-10-27', 80, 20), row('2026-10-28', 40, 50)]
        rows[2]['source'] = 'another source'
        rows[3]['missing'] = 1
        out = add_advance_decline(rows)
        self.assertEqual([x['adl'] for x in out], [-30, 30, 60, None])
        self.assertTrue(out[1]['adl_gap_before'])
        self.assertTrue(out[2]['adl_gap_before'])
        self.assertTrue(out[3]['adl_gap_before'])

    def test_zero_denominator_and_provisional_does_not_seed_future(self):
        rows = [row('2026-10-22', 30, 0), row('2026-10-23', 20, 30), row('2026-10-26', 70, 20)]
        rows[1]['status'] = 'provisional'
        out = add_advance_decline(rows)
        self.assertIsNone(out[0]['adr'])
        self.assertEqual(out[1]['adl'], 20)
        self.assertEqual(out[2]['adl'], 50)
        self.assertEqual(out[2]['adl_start'], '2026-10-26')
        self.assertTrue(out[2]['adl_gap_before'])

    def test_unknown_calendar_never_infers_a_segment(self):
        out = add_advance_decline([row('2027-01-04', 30, 60)])
        self.assertIsNone(out[0]['adl'])
        self.assertIsNone(out[0]['adr'])
        self.assertIsNone(_next_verified_trading_day(date(2026, 12, 31)))

    def test_same_day_history_is_separate_and_not_shown_for_provisional(self):
        historical = [dict(row('2026-10-22', 30, 60), historical=True),
                      dict(row('2026-10-23', 60, 30), historical=True)]
        mixed = [historical[0], row('2026-10-23', 50, 40)]
        mixed[-1]['source'] = 'another source'
        result = attach_historical_ad_reference(add_advance_decline(mixed), historical)
        self.assertEqual(result[-1]['adl'], 10)
        self.assertEqual(result[-1]['ad_history']['adl'], 0)
        self.assertEqual(result[-1]['ad_history']['adr'], 2)
        self.assertEqual(result[-1]['ad_history']['source'], 'example')
        mixed[-1]['status'] = 'provisional'
        result = attach_historical_ad_reference(add_advance_decline(mixed), historical)
        self.assertNotIn('ad_history', result[-1])

    def test_historical_continuity_survives_intervening_live_snapshot(self):
        historical = [dict(row('2026-10-22', 30, 60), historical=True),
                      dict(row('2026-10-23', 60, 30), historical=True),
                      dict(row('2026-10-26', 80, 20), historical=True)]
        mixed = [r.copy() for r in historical]
        mixed[1].update(historical=False, source='live')
        result = attach_historical_ad_reference(add_advance_decline(mixed), historical)
        self.assertEqual(result[1]['ad_history']['adl'], 0)
        self.assertEqual(result[2]['adl'], 60)
        self.assertEqual(result[2]['adl_start'], '2026-10-22')
        self.assertFalse(result[2]['adl_gap_before'])


if __name__ == '__main__':
    unittest.main()
