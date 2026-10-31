"""Index observed Douyin page chapters, clearly distinguishing them from transcripts."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'docs/author-trading-system-20261028'
EPISODES = {
    1:'7686279141561598179',
    2:'7689285388485479400', 3:'7689353967416166755', 4:'7689639585425056591',
    5:'7690191990764353999', 6:'7690573967492733135', 7:'7691322359457817507',
    8:'7692783856278389416', 9:'7694432759611486287', 10:'7696442668070866595',
    11:'7697069823088879528', 12:'7697810582636650659', 13:'7697997846737995584',
    14:'7698156381056391823', 15:'7698262666594409448', 16:'7698891487421377856',
    17:'7698957540848250280', 18:'7699507023986335695', 19:'7699681780400649826',
    20:'7700469388663999720', 21:'7700876657855420904', 22:'7701667092567538511',
}
SPECIAL = {2:'douyin-series-early-ax.txt', 3:'douyin-early2-ax.txt', 7:'douyin-pcr-ax.txt'}


def main():
    result = []
    for episode, video_id in EPISODES.items():
        path = DATA / SPECIAL.get(episode, f'douyin-episode-{episode}-ax.txt')
        raw = path.read_text(encoding='utf-8')
        if f'douyin.com/video/{video_id}' not in raw or not re.search(rf'heading 第{episode}集 \|', raw):
            raise ValueError(f'第 {episode} 集页面地址或标题不匹配')
        lines = raw.splitlines()
        start = next((i for i, line in enumerate(lines) if 'text 章节要点' in line), None)
        end = next(i for i, line in enumerate(lines) if re.search(rf'heading 第{episode}集 \|', line))
        chapters = []
        if start is not None and start < end:
            for line in lines[start:end]:
                match = re.search(r'\btext (\d{2}:\d{2}) (.+)$', line)
                if match:
                    chapters.append({'time':match.group(1), 'text':match.group(2)})
        result.append({'series':'金融宝藏','episode':episode,'url':f'https://www.douyin.com/video/{video_id}',
                       'source':'抖音页面章节摘要；不是原始逐字稿，可能存在识别错误',
                       'status':'有章节摘要，待原视频核对' if chapters else '未发现章节摘要，待完整阅读',
                       'chapters':chapters,'snapshot':path.name})
    target = DATA / 'douyin-series-chapters.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(result)} 集；{sum(bool(x["chapters"]) for x in result)} 集有章节摘要：{target}')


if __name__ == '__main__':
    main()
