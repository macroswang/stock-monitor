"""Reconcile an observed author profile DOM snapshot with the research index.

The profile snapshot is captured by the browser, not fetched by this script.
The older index is preserved; this produces a separate dated inventory.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/author-trading-system-20261028'
PATTERN = re.compile(
    r"^  - ['\"]?link [^\n]*布鲁斯的金融宝藏：[^\n]*\n"
    r"    - /url: (?:https?:)?(?://www\.douyin\.com)?/(video|note)/(\d+)", re.M)
NEW_STATUS = {
    '7702035535511281472': '平台章节摘要及原画面抽样；分组与七个案例已核验，未完整转录',
    '7701738028892688482': '已核对页面标题、发布时间及部分画面；未完成内容复核',
    '7695953808443497954': '图文页面已阅读；作者自述期权做空，缺少可核验成交记录',
}
UPDATED_STATUS = {
    '7698156381056391823': '平台自动章节摘要；原画面 00:40、00:55、01:15、01:55、02:47 抽样，持仓截图需独立核对',
}


def reconcile(snapshot, old):
    if '暂时没有更多了' not in snapshot:
        raise ValueError('主页列表没有加载至末尾')
    match = re.search(r'tab "作品 (\d+)" \[selected\]', snapshot)
    if not match:
        raise ValueError('找不到主页作品总数')
    displayed = int(match.group(1))
    visible = PATTERN.findall(snapshot)
    if len(visible) != len({item_id for _, item_id in visible}):
        raise ValueError('作品链接重复')
    if len(visible) != displayed:
        raise ValueError(f'主页显示 {displayed} 条，实际加载 {len(visible)} 条')
    old_items = old['items']
    old_by_id = {item['id']: item for item in old_items}
    if len(old_items) != len(old_by_id):
        raise ValueError('旧目录存在重复作品')
    result = []
    for kind, item_id in visible:
        existing = old_by_id.get(item_id)
        if existing:
            if kind != 'video':
                raise ValueError('作品类型与旧目录不一致')
            result.append({**existing, 'kind': kind,
                           'status': UPDATED_STATUS.get(item_id, existing['status']),
                           'status_source': '2026-10-29 补充原画面抽样' if item_id in UPDATED_STATUS else '2026-10-28 旧目录，未重新逐条核验'})
        else:
            result.append({'id': item_id, 'kind': kind,
                           'url': f'https://www.douyin.com/{kind}/{item_id}',
                           'status': NEW_STATUS.get(item_id, '新发现，尚未读取内容'),
                           'status_source': '2026-10-29 主页列表'})
    return {'source': '作者主页公开作品列表及可见列表末尾',
            'snapshot': 'profile-20261029-refresh-dom.txt',
            'displayedTotal': displayed, 'visibleCount': len(visible),
            'videoCount': sum(kind == 'video' for kind, _ in visible),
            'noteCount': sum(kind == 'note' for kind, _ in visible),
            'missing_from_current': sorted(set(old_by_id) - {item_id for _, item_id in visible}),
            'warning': '数量一致不代表已完整观看；既有章节是平台自动摘要，核验程度逐条列出。',
            'items': result}


def main():
    snapshot = (DOCS / 'profile-20261029-refresh-dom.txt').read_text(encoding='utf-8')
    old = json.loads((DOCS / 'author-works-index.json').read_text(encoding='utf-8'))
    result = reconcile(snapshot, old)
    (DOCS / 'author-works-index-20261029.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('displayedTotal', 'visibleCount', 'videoCount', 'noteCount', 'missing_from_current')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
