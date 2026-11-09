import tempfile
import unittest
from unittest.mock import patch

from core.stock_search import search, _CACHE
from core.store import Store


class StockSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(str(self.tmp.name + '/m.sqlite3'))
        self.addCleanup(self.store.db.close)
        self.store.execute("INSERT OR REPLACE INTO instruments VALUES(?,?)", ('sh601318', '中国平安'))
        self.store.execute("INSERT OR REPLACE INTO instruments VALUES(?,?)", ('sh600519', '贵州茅台'))
        self.store.execute("INSERT OR REPLACE INTO instruments VALUES(?,?)", ('sz002712', '思美传媒'))
        _CACHE.clear()

    def test_search_by_pinyin_initials_and_name_and_code(self):
        with patch('core.market_pulse.name_universe', return_value={}):
            _CACHE.clear()
            rows = search(self.store, 'zgpa')
            self.assertEqual(rows[0]['code'], 'sh601318')
            self.assertEqual(rows[0]['initials'], 'zgpa')
            self.assertEqual(search(self.store, 'gzmt')[0]['name'], '贵州茅台')
            self.assertEqual(search(self.store, '平安')[0]['code'], 'sh601318')
            self.assertEqual(search(self.store, '600519')[0]['code'], 'sh600519')
            self.assertEqual(search(self.store, 'smcm')[0]['code'], 'sz002712')
            self.assertEqual(search(self.store, ''), [])


if __name__ == '__main__':
    unittest.main()
