"""Compare three values shown in episode 21 to independent historical data."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def compare(authors,history):
    by_date={r['date']:r for r in history}
    rows=[]
    for author in authors:
        r=by_date.get(author['date'])
        if not r or not r.get('historical') or r.get('status')!='closed' or r.get('missing')!=0:
            raise ValueError('缺少核对后的收盘数据：'+author['date'])
        rows.append({'date':author['date'],'author_trin_shown':author['shown'],
                     'shares_trin':r['trin'],'amount_trin':r['trin_amount'],
                     'shares_abs_difference':abs(r['trin']-author['trin']),
                     'amount_abs_difference':abs(r['trin_amount']-author['trin'])})
    return rows


def main():
    authors=json.loads((ROOT/'fixtures/author-trin-march-reference.json').read_text())
    history=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text())
    rows=compare(authors,history)
    result={'source':'https://www.douyin.com/video/7700876657855420904',
            'video_position':'约 02:00；图中三日 TRIN 的人工辨认',
            'warning':'截图数值已舍入；作者股票池、统计时点和完整口径未知。结果是对照，不证明复现。',
            'rows':rows}
    out=ROOT/'docs/trin-author-table-comparison-20261029/march-comparison.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
