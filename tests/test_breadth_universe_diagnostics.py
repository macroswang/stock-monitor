import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from core.breadth import universe


def fake_source(mode):
    count_calls = {'sh_a': 0, 'sz_a': 0}
    totals = {'sh_a': 480, 'sz_a': 520}

    def get(url):
        query = parse_qs(urlsplit(url).query)
        node = query['node'][0]
        if 'getHQNodeStockCount' in url:
            count_calls[node] += 1
            value = totals[node] + (1 if mode == 'changed' and node == 'sz_a' and count_calls[node] > 1 else 0)
            return json.dumps(value)
        page = int(query['page'][0])
        start = (page - 1) * 80
        total = totals[node]
        prefix, base = ('sh', 600000) if node == 'sh_a' else ('sz', 1)
        items = [{'symbol': f'{prefix}{base + i:06d}'} for i in range(start, min(start + 80, total))]
        if mode == 'short' and node == 'sz_a' and page == 7:
            items.pop()
        if mode == 'duplicate' and node == 'sz_a' and page == 7:
            items[-1] = {'symbol': 'sz000001'}
        if mode == 'wrong_node' and node == 'sz_a' and page == 7:
            items[-1] = {'symbol': 'sh600001'}
        return json.dumps(items)
    return get


class UniverseDiagnosticsTest(unittest.TestCase):
    def test_rejects_short_duplicate_and_changed_lists(self):
        for mode, message in [('short', '分页返回 519'), ('duplicate', '仅 519 个不同代码'),
                              ('changed', '1000 → 1001')]:
            with self.subTest(mode=mode), patch('core.breadth.get', fake_source(mode)), \
                 patch('core.breadth.time.sleep'):
                with self.assertRaisesRegex(ValueError, message):
                    universe()

    def test_rejects_code_from_the_wrong_exchange_node(self):
        with patch('core.breadth.get', fake_source('wrong_node')), patch('core.breadth.time.sleep'):
            with self.assertRaisesRegex(ValueError, '深证A股代码表包含非目标证券'):
                universe()

    def test_complete_list_passes(self):
        with patch('core.breadth.get', fake_source('complete')), patch('core.breadth.time.sleep'):
            self.assertEqual(len(universe()), 1000)

    def test_valid_but_empty_page_is_retried_and_persistent_empty_is_rejected(self):
        good = fake_source('complete')
        calls = {'page3': 0, 'urls': []}

        def transient(url):
            if ('getHQNodeData' in url and parse_qs(urlsplit(url).query)['node'] == ['sh_a']
                    and parse_qs(urlsplit(url).query)['page'] == ['3']):
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
            if ('getHQNodeData' in url and parse_qs(urlsplit(url).query)['node'] == ['sh_a']
                    and parse_qs(urlsplit(url).query)['page'] == ['3']):
                return '[]'
            return good(url)

        with patch('core.breadth.get', empty), patch('core.breadth.time.sleep'):
            with self.assertRaisesRegex(ValueError, '分页返回 400'):
                universe()

    def test_transient_page_failure_is_retried_but_persistent_failure_is_rejected(self):
        good = fake_source('complete')
        calls = {'page3': 0}

        def transient(url):
            if ('getHQNodeData' in url and parse_qs(urlsplit(url).query)['node'] == ['sh_a']
                    and parse_qs(urlsplit(url).query)['page'] == ['3']):
                calls['page3'] += 1
                if calls['page3'] == 1:
                    raise TimeoutError('temporary')
            return good(url)

        with patch('core.breadth.get', transient), patch('core.breadth.time.sleep'):
            self.assertEqual(len(universe()), 1000)
        self.assertEqual(calls['page3'], 2)

        def failing(url):
            if ('getHQNodeData' in url and parse_qs(urlsplit(url).query)['node'] == ['sh_a']
                    and parse_qs(urlsplit(url).query)['page'] == ['3']):
                raise TimeoutError('persistent')
            return good(url)

        with patch('core.breadth.get', failing), patch('core.breadth.time.sleep'):
            with self.assertRaises(TimeoutError):
                universe()


if __name__ == '__main__':
    unittest.main()
