"""Index the observed public profile and platform chapter summaries, not transcripts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'docs/author-trading-system-20261028'
SAMPLED = {
    '7689639585425056591': '每5秒抽样；关键画面人工核验',
    '7686814313318785167': '每5秒抽样；关键画面人工核验',
    '7685926019916794752': '每3秒抽样；关键画面人工核验',
    '7698551410090119808': '每1秒抽样；关键画面人工核验',
    '7694582681510008803': '每2秒抽样并识别字幕',
    '7698891487421377856': '01:15—02:00 每1秒抽样；关键画面人工核验',
    '7700876657855420904': '00:15—01:00 每1秒抽样；公式画面人工核验',
    '7701667092567538511': '01:00—03:30、04:10—05:26 每2秒抽样；关键字幕、图例和表格画面人工核验',
    '7689353967416166755': '01:15—03:55 每2秒抽样；PCR 图表参数画面人工核验',
    '7700469388663999720': '01:30—05:50 每2秒抽样；代客席位画面人工核验',
    '7697069823088879528': '03:25—04:26 若干时点抽样；指数、总市值和利差画面人工核验',
}


def main():
    catalog = json.loads((DATA / 'author-profile-catalog.json').read_text())
    financial = json.loads((DATA / 'douyin-series-chapters.json').read_text())
    summaries = {}
    for row in financial:
        summaries[row['url'].rsplit('/', 1)[-1]] = {
            'chapters': row['chapters'], 'series': f"金融宝藏第{row['episode']}集",
            'snapshot': row['snapshot'],
        }
    for f in sorted(DATA.glob('other-chapters-*.json')):
        for row in json.loads(f.read_text()):
            if 'error' in row:
                raise ValueError(f"视频读取失败: {row['id']}: {row['error']}")
            summaries[row['id']] = {
                'chapters': row.get('chapters', []),
                'publication': row.get('publication', ''), 'snapshot': f.name,
            }
    rows = []
    for item in catalog['items']:
        row = {**item, **summaries.get(item['id'], {})}
        row['sampling'] = SAMPLED.get(item['id'])
        row['status'] = ('平台自动章节摘要' if row.get('chapters') else '无平台章节摘要')
        if row['sampling']:
            row['status'] += f"；原画面{row['sampling']}"
        else:
            row['status'] += '；未完成原视频核对'
        rows.append(row)
    if len({x['id'] for x in rows}) != len(rows):
        raise ValueError('主页作品 ID 重复')
    if len(rows) != catalog['visibleCount']:
        raise ValueError('目录数量不一致')
    output = {'source': catalog['source'], 'displayedTotal': catalog['displayedTotal'],
              'visibleCount': len(rows), 'chapterCount': sum(bool(x.get('chapters')) for x in rows),
              'warning': '章节由平台自动生成，非原始逐字稿；实际看过的片段需单独注明。', 'items': rows}
    (DATA / 'author-works-index.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    lines = ['# 作者主页作品目录', '',
             f"主页显示 {output['displayedTotal']} 个作品；页面实际可见并去重 {len(rows)} 个，其中 {output['chapterCount']} 个有平台自动章节摘要。",
             '主页计数与可见列表相差一项，原因未知。章节摘要不是原视频逐字稿；视频抽样有遗漏、画面可能加载延迟，不表示已完整观看。', '']
    for n, row in enumerate(rows, 1):
        title = row['text'].split('\n')[-1].strip()
        lines += [f"{n}. [{title}]({row['url']}) — {row['status']}"]
    (DATA / '作者作品目录.md').write_text('\n'.join(lines)+'\n')
    print(f"可见 {len(rows)}，摘要 {output['chapterCount']}，无摘要 {len(rows)-output['chapterCount']}")


if __name__ == '__main__':
    main()
