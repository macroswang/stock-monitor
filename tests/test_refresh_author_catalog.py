import unittest

from scripts.refresh_author_catalog import reconcile


def snapshot(count, links, complete=True):
    entries = ''.join(f'  - link "布鲁斯的金融宝藏：标题"\n    - /url: /{kind}/{item_id}\n' for kind, item_id in links)
    return f'- tab "作品 {count}" [selected]\n{entries}' + ('暂时没有更多了' if complete else '')


class CatalogTest(unittest.TestCase):
    def test_preserves_old_evidence_and_counts_new_type(self):
        old = {'items': [{'id': '123', 'chapters': ['平台摘要'], 'status': '待核对'}]}
        got = reconcile(snapshot(2, [('video', '123'), ('note', '456')]), old)
        self.assertEqual((got['videoCount'], got['noteCount']), (1, 1))
        self.assertEqual(got['items'][0]['chapters'], ['平台摘要'])
        self.assertEqual(got['items'][1]['url'], 'https://www.douyin.com/note/456')

    def test_rejects_incomplete_or_duplicate_lists(self):
        old = {'items': []}
        for value in (snapshot(2, [('video', '1')]),
                      snapshot(2, [('video', '1'), ('video', '1')]),
                      snapshot(1, [('video', '1')], complete=False)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reconcile(value, old)


if __name__ == '__main__':
    unittest.main()
