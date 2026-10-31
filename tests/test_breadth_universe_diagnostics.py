import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from core.breadth import universe


def fake_source(mode):
    count_calls = 0

    def get(url):
        nonlocal count_calls
        if 'getHQNodeStockCount' in url:
            count_calls += 1
            return json.dumps(1001 if mode == 'changed' and count_calls > 1 else 1000)
        page = int(parse_qs(urlsplit(url).query)['page'][0])
        start = (page - 1) * 80
        items = [{'symbol': f'sh{600000 + i:06d}'} for i in range(start, min(start + 80, 1000))]
        if mode == 'short' and page == 13:
            items.pop()
        if mode == 'duplicate' and page == 13:
            items[-1] = {'symbol': 'sh600000'}
        return json.dumps(items)
    return get


class UniverseDiagnosticsTest(unittest.TestCase):
    def test_rejects_short_duplicate_and_changed_lists(self):
        for mode, message in [('short', '分页返回 999'), ('duplicate', '仅 999 个不同代码'),
                              ('changed', '1000 → 1001')]:
            with self.subTest(mode=mode), patch('core.breadth.get', fake_source(mode)), \
                 patch('core.breadth.time.sleep'):
                with self.assertRaisesRegex(ValueError, message):
                    universe()

    def test_complete_list_passes(self):
        with patch('core.breadth.get', fake_source('complete')), patch('core.breadth.time.sleep'):
            self.assertEqual(len(universe()), 1000)

    def test_valid_but_empty_page_is_retried_and_persistent_empty_is_rejected(self):
        good = fake_source('complete')
        calls = {'page3': 0, 'urls': []}

        def transient(url):
            if 'getHQNodeData' in url and parse_qs(urlsplit(url).query)['page'] == ['3']:
                calls['page3'] += 1
                calls['urls'].append(url)
                if calls['page3'] == 1:
                    return '[]'
            return good(url)

        with patch('core.breadth.get', transient), patch('core.breadth.time.sleep'):
            self.assertEqual(len(universe()), 1000)
        self.assertEqual(calls['page3'], 2)
        self.assertNotEqual(calls['urls'][0], calls['urls'][1])
        self.assertIn('_', parse_qs(urlsplit(calls['urls'][1]).query))

        def empty(url):
            if 'getHQNodeData' in url and parse_qs(urlsplit(url).query)['page'] == ['3']:
                return '[]'
            return good(url)

        with patch('core.breadth.get', empty), patch('core.breadth.time.sleep'):
            with self.assertRaisesRegex(ValueError, '分页返回 920'):
                universe()

    def test_transient_page_failure_is_retried_but_persistent_failure_is_rejected(self):
        good = fake_source('complete')
        calls = {'page3': 0}

        def transient(url):
            if 'getHQNodeData' in url and parse_qs(urlsplit(url).query)['page'] == ['3']:
                calls['page3'] += 1
                if calls['page3'] == 1:
                    raise TimeoutError('temporary')
            return good(url)

        with patch('core.breadth.get', transient), patch('core.breadth.time.sleep'):
            self.assertEqual(len(universe()), 1000)
        self.assertEqual(calls['page3'], 2)

        def failing(url):
            if 'getHQNodeData' in url and parse_qs(urlsplit(url).query)['page'] == ['3']:
                raise TimeoutError('persistent')
            return good(url)

        with patch('core.breadth.get', failing), patch('core.breadth.time.sleep'):
            with self.assertRaises(TimeoutError):
                universe()


if __name__ == '__main__':
    unittest.main()
