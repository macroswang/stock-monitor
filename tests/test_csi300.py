import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.breadth import summarize
from core.csi300 import CSI300, compare, parse_members
from core.provider import CN
from core.store import Store


class CSI300Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'fixtures/csi300-cons-20261030.xls'
        cls.members = parse_members(path.read_bytes(), datetime(2026, 10, 31, tzinfo=CN))

    def raw_and_recorded(self):
        rows = []
        for i, code in enumerate(self.members['codes']):
            price = '11' if i < 100 else '9' if i < 290 else '10'
            rows.append(dict(code=code, price=price, previous_close='10', volume=1000,
                             amount_yuan=str(int(price)*1000), timestamp='2026-10-30T15:00:00+08:00'))
        raw = dict(date='2026-10-30', codes=self.members['codes'], quotes=rows, suspended=[],
                   collected_at='2026-10-30T15:16:00+08:00')
        return raw, summarize(rows, raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])

    def test_official_list_requires_valid_date_and_unique_codes(self):
        self.assertEqual(self.members['date'], '2026-10-30')
        self.assertEqual(len(set(self.members['codes'])), 300)
        path = Path(__file__).resolve().parents[1] / 'fixtures/csi300-cons-20261030.xls'
        with self.assertRaises(ValueError):
            parse_members(path.read_bytes(), datetime(2026, 10, 29, tzinfo=CN))

    def test_group_counts_and_turnover_reproduce_full_market(self):
        raw, recorded = self.raw_and_recorded()
        result = compare(self.members, raw, recorded)
        self.assertEqual((result['advance'], result['decline'], result['flat'], result['suspended']), (100, 190, 10, 0))
        self.assertEqual(result['advance_amount_percent'], 100)
        self.assertEqual(result['decline_amount_percent'], 100)
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(result['member_collected_at'], '2026-10-31T00:00:00+08:00')
        self.assertEqual(result['available_at'], '2026-10-31T00:00:00+08:00')

    def test_member_capture_time_is_required_and_cannot_precede_member_date(self):
        raw, recorded = self.raw_and_recorded()
        for stamp in (None, '2026-10-31T00:00:00', '2026-10-29T23:59:59+08:00'):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                compare({**self.members, 'collected_at': stamp}, raw, recorded)

    def test_missing_member_date_or_inconsistent_raw_is_rejected(self):
        raw, recorded = self.raw_and_recorded()
        with self.assertRaises(ValueError):
            compare({**self.members, 'date': '2026-10-29'}, raw, recorded)
        with self.assertRaises(ValueError):
            compare({**self.members, 'codes': self.members['codes'][:-1]}, raw, recorded)
        with self.assertRaises(ValueError):
            compare(self.members, raw, {**recorded, 'advance': recorded['advance'] + 1})
        raw['quotes'].pop()
        with self.assertRaises(ValueError):
            compare(self.members, raw, recorded)

    def test_zero_volume_is_suspended_not_an_up_or_down_stock(self):
        raw, _ = self.raw_and_recorded()
        raw['quotes'][0]['volume'] = 0
        recorded = summarize(raw['quotes'], raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])
        result = compare(self.members, raw, recorded)
        self.assertEqual((result['advance'], result['suspended']), (99, 1))

    def test_no_declining_group_leaves_its_share_undefined(self):
        raw, _ = self.raw_and_recorded()
        for quote in raw['quotes']:
            quote['price'] = '11'
        recorded = summarize(raw['quotes'], raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])
        result = compare(self.members, raw, recorded)
        self.assertIsNone(result['decline_amount_percent'])
        self.assertEqual(result['advance_amount_percent'], 100)

    def test_recorded_reference_uses_checked_raw_and_never_looks_ahead(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            try:
                service = CSI300(store)
                before = datetime.fromisoformat('2026-10-31T03:14:30+08:00')
                after = datetime.fromisoformat('2026-10-31T03:15:00+08:00')
                with patch('core.csi300.now_cn', return_value=before), patch('core.breadth.now_cn', return_value=before):
                    self.assertIsNone(service.view('2026-10-30'))
                with patch('core.csi300.now_cn', return_value=after), patch('core.breadth.now_cn', return_value=after):
                    result = service.view('2026-10-30')
                    self.assertIsNone(service.view('2026-10-29'))
                self.assertEqual((result['advance'], result['decline'], result['flat']), (102, 189, 9))
                self.assertAlmostEqual(result['advance_amount_percent'], 35.36877513462418)
                self.assertAlmostEqual(result['decline_amount_percent'], 100 * 319102500000 / 1284115260000)
                self.assertEqual(result['collected_at'], '2026-10-31T03:14:31.055070+08:00')
                self.assertEqual(result['member_collected_at'], '2026-10-31T03:14:31.055070+08:00')
                self.assertEqual(result['available_at'], '2026-10-31T03:14:31.055070+08:00')
                self.assertEqual(store.query('SELECT * FROM cache'), [])
            finally:
                store.db.close()

    def test_corrupt_members_or_raw_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'empty.sqlite3')
            bad = Path(directory) / 'bad.xls'
            bad.write_bytes(b'bad')
            now = datetime.fromisoformat('2026-10-31T04:00:00+08:00')
            try:
                with patch('core.csi300.now_cn', return_value=now), patch('core.breadth.now_cn', return_value=now), \
                     patch('core.csi300.REFERENCE_MEMBERS', bad):
                    self.assertIsNone(CSI300(store).view('2026-10-30'))
                with patch('core.csi300.now_cn', return_value=now), patch('core.breadth.now_cn', return_value=now), \
                     patch('core.breadth.MA_CLOSE_REFERENCE_1030', bad):
                    self.assertIsNone(CSI300(store).view('2026-10-30'))
            finally:
                store.db.close()


if __name__ == '__main__':
    unittest.main()
