"""Recompute BJ block-inclusion sensitivity for exactly the verified examples.

Uses Money Tree's base, then adds TDX-minus-Money differences only for the five
separately disclosed block trades. This is mixed-source research, not a daily
feed and not an assertion of the author's unknown data definition.
"""
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from scripts.analyze_trin_crosssections import compute
from scripts.check_beijing_block_examples import compare

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/trin-author-table-comparison-20261029'
MONEY=ROOT/'docs/trin-reconstruction-20261028/money-tree'
D=Decimal


def calculate(rows, adjustments):
    base=compute(rows,{'SH','SZ','BJ'},True)
    if base['invalid']:raise ValueError('原始样本未通过校验')
    indexed={r['symbol']:r for r in rows}
    if len(indexed)!=len(rows):raise ValueError('重复股票')
    totals={'up_volume':D(base['up_volume_shares']),'down_volume':D(base['down_volume_shares']),
            'up_amount':D(base['up_amount_yuan']),'down_amount':D(base['down_amount_yuan'])}
    for item in adjustments:
        if not item['volume_matches'] or not item['amount_matches_within_32_yuan']:
            raise ValueError('大宗差额未吻合')
        r=indexed[item['code']+'.BJ'];delta_volume=D(item['volume_difference']);delta_amount=D(item['amount_difference_yuan'])
        if delta_volume<=0 or delta_amount<=0:raise ValueError('非正的成交差额')
        close,pre=D(r['close']),D(r['pre_close'])
        group='up' if close>pre else 'down' if close<pre else 'flat'
        if group!='flat':
            totals[group+'_volume']+=delta_volume
            totals[group+'_amount']+=delta_amount
    up,down=base['counts']['up'],base['counts']['down']
    if min(up,down,*totals.values())<=0:raise ValueError('TRIN 分母无效')
    return {'base_trin_amount':base['trin_amount'],
            'adjusted_trin_amount':float(D(up)*totals['down_amount']/(D(down)*totals['up_amount'])),
            'adjusted_trin_volume':float(D(up)*totals['down_volume']/(D(down)*totals['up_volume'])),
            'counts':base['counts'],'adjusted_group_totals':{k:str(v) for k,v in totals.items()},
            'adjusted_codes':[r['code'] for r in adjustments]}


def main():
    examples=json.loads((ROOT/'fixtures/beijing-block-trade-examples.json').read_text())
    checked=json.loads((OUT/'march-beijing-tdx-crosscheck.json').read_text())
    verified=compare(examples,checked)
    all_mismatches={(r['date'],code) for r in checked['rows'] for code in r['bar_mismatches']}
    if all_mismatches!={(r['date'],r['code']) for r in verified}:raise ValueError('并非所有差异都有核对的大宗案例')
    if any(r['missing_in_tdx'] or r['previous_close_disagreements'] for r in checked['rows']):raise ValueError('北交所匹配不完整')
    if any(set(v['fields'])-{'volume','amount'} for r in checked['rows'] for v in r['bar_mismatches'].values()):raise ValueError('存在其他价格差异')
    authors=json.loads((ROOT/'fixtures/author-trin-march-reference.json').read_text())
    output=[];hashes={}
    for author in authors:
        day=author['date'].replace('-','');path=MONEY/(day+'.csv')
        hashes[day]=hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes[day]!=checked['money_tree_sha256'][day]:raise ValueError('原始底表与交叉核对记录不一致')
        with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        if not rows or any(r['trade_date']!=day for r in rows):raise ValueError('日期不符')
        item=calculate(rows,[r for r in verified if r['date']==day])
        output.append({'date':author['date'],'author_trin':author['trin'],**item})
    report={'rows':output,'source_hashes':hashes,
            'warning':'仅对五笔已披露北交所大宗进行混合来源研究；沪深及其余股票仍取 Money Tree，未证明完整大宗覆盖、作者口径或实时可得性。'}
    (OUT/'march-verified-block-inclusion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    fixture=[{'date':r['date'],'trin_amount':r['adjusted_trin_amount']} for r in output]
    (ROOT/'fixtures/author-march-verified-block-inclusion.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()
