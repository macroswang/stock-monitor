import copy
import json
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from core.app import App
from scripts.audit_home_market_history import CALENDAR, DATA, audit


class HomeMarketHistoryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(DATA.read_text())['days']
        cls.calendar = json.loads(CALENDAR.read_text())
        cls.now = datetime(2026, 11, 1, tzinfo=ZoneInfo('Asia/Shanghai'))

    def test_sample_dates_and_both_trin_calculations(self):
        result = audit(self.rows, self.calendar, self.now)
        self.assertEqual((result['start'], result['end'], result['records']), ('2026-06-18', '2026-10-30', 90))
        self.assertFalse(result['missing_dates'] or result['invalid_dates'] or result['duplicate_dates'])
        self.assertEqual(result['source_transitions'], [{'from': '2026-10-28', 'to': '2026-10-29'}])

    def test_detects_missing_dates_and_inconsistent_totals(self):
        rows = copy.deepcopy(self.rows)
        missing = rows.pop(-2)['date']
        rows[-1]['trin_amount'] *= 2
        result = audit(rows, self.calendar, self.now)
        self.assertIn(missing, result['missing_dates'])
        self.assertIn(rows[-1]['date'], result['invalid_dates'])

    def test_preview_matches_fresh_isolated_backend_history(self):
        fields = ('source', 'universe', 'advance', 'decline', 'flat', 'suspended', 'covered',
                  'advance_volume', 'decline_volume', 'advance_amount', 'decline_amount',
                  'trin', 'trin_amount', 'advancing_percent', 'adl', 'adl_gap_before', 'mcl_samples')
        with tempfile.TemporaryDirectory() as root, patch('core.breadth.now_cn', return_value=self.now):
            app = App(root, False)
            try:
                rows = app.call('breadth', {})['days']
                self.assertEqual([r['date'] for r in rows], [r['date'] for r in self.rows])
                for actual, preview in zip(rows[-90:], self.rows[-90:]):
                    with self.subTest(day=actual['date']):
                        self.assertEqual({k: actual.get(k) for k in fields}, {k: preview.get(k) for k in fields})
            finally:
                app.stop.set()
                app.store.db.close()


if __name__ == '__main__':
    unittest.main()
