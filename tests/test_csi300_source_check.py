import copy
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from core.csi300 import REFERENCE_MEMBERS, parse_members
from scripts.research_csi300_source_check import MARCH, OUT, check


class CSI300SourceCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(OUT.read_text())
        cls.march = json.loads(MARCH.read_text())
        cls.official = parse_members(
            REFERENCE_MEMBERS.read_bytes(),
            datetime(2026, 10, 31, 4, tzinfo=ZoneInfo('Asia/Shanghai')),
        )

    def test_reproduces_archived_source_comparison(self):
        result = check(self.report['snapshots'], self.official, self.march)
        self.assertEqual(result, self.report['result'])
        self.assertTrue(result['march_matches_archived'])
        self.assertTrue(result['oct_matches_official'])
        self.assertEqual(len(result['march_to_june_removed']), 19)
        self.assertEqual(len(result['march_to_june_added']), 19)

    def test_rejects_duplicate_or_future_dated_member(self):
        snapshots = copy.deepcopy(self.report['snapshots'])
        snapshots['2026-03-23'][1] = snapshots['2026-03-23'][0]
        with self.assertRaises(ValueError):
            check(snapshots, self.official, self.march)
        snapshots = copy.deepcopy(self.report['snapshots'])
        snapshots['2026-03-23'][0]['updateDate'] = '2026-03-24'
        with self.assertRaises(ValueError):
            check(snapshots, self.official, self.march)


if __name__ == '__main__':
    unittest.main()
