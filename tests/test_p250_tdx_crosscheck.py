import unittest

from scripts.crosscheck_p250_tdx import BAR, bars_for_dates


def row(day, close, volume):
    return BAR.pack(day, close, close, close, close, 10000.0, volume, 0)


class TdxCrosscheckTests(unittest.TestCase):
    def test_selects_dated_active_close_in_fen(self):
        data = row(20250909, 1234, 100) + row(20250910, 1235, 0) + row(20250911, 1236, 500)
        self.assertEqual(bars_for_dates(data, {20250909, 20250910}), {20250909: 1234})

    def test_rejects_duplicate_dates_and_truncated_records(self):
        with self.assertRaisesRegex(ValueError, 'non-increasing'):
            bars_for_dates(row(20250909, 1234, 100) * 2, {20250909})
        with self.assertRaisesRegex(ValueError, 'truncated'):
            bars_for_dates(row(20250909, 1234, 100)[:-1], {20250909})


if __name__ == '__main__':
    unittest.main()
