"""Recalculate fixed historical scope variants for the episode-21 March chart.

The scope definitions predate this comparison. Similarity is descriptive only;
it cannot identify the author's unreported stock pool or sampling time.
"""
import csv
import hashlib
import json
from pathlib import Path

from scripts.compare_author_trin_classifications import analyze as classifications
from scripts.compare_author_trin_scopes import analyze as exchange_scopes

ROOT=Path(__file__).resolve().parents[1]
BAO=ROOT/'docs/trin-reconstruction-20261028/baostock'
MONEY=ROOT/'docs/trin-reconstruction-20261028/money-tree'
OUT=ROOT/'docs/trin-author-table-comparison-20261029/march-scope-comparison.json'


def main():
    reference=json.loads((ROOT/'fixtures/author-trin-march-reference.json').read_text())
    history=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text())
    bao={};money={};hashes={}
    for item in reference:
        day=item['date'];b=BAO/f'{day}.json';m=MONEY/(day.replace('-','')+'.csv')
        bao[day]=json.loads(b.read_text())
        with m.open(encoding='utf-8-sig',newline='') as stream:money[day]=list(csv.DictReader(stream))
        hashes[day]={'baostock':hashlib.sha256(b.read_bytes()).hexdigest(),
                     'money_tree':hashlib.sha256(m.read_bytes()).hexdigest()}
    by_class=classifications(reference,bao,history)
    by_exchange=exchange_scopes(reference,money)
    output={'warning':'固定分类试算；北交所及 ST 标记未逐股独立核验，来源上游可能相关。相近不代表作者的范围或统计时点。',
            'source':'https://www.douyin.com/video/7700876657855420904',
            'input_sha256':hashes,'classifications':by_class,'exchange_scopes':by_exchange}
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    fixture=[{'date':r['date'],'trin_amount':r['trin_amount']} for r in by_exchange['rows'] if r['scope']=='shszbj_in_cdr']
    (ROOT/'fixtures/author-trin-march-scope.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'class':by_class['summary'],'exchanges':by_exchange['summary'],
                      'march24_class':[{k:r[k] for k in ('scope','trin')} for r in by_class['rows'] if r['date']=='2026-03-24'],
                      'march24_exchanges':[{k:r[k] for k in ('scope','trin_amount')} for r in by_exchange['rows'] if r['date']=='2026-03-24']},ensure_ascii=False))


if __name__=='__main__':main()
