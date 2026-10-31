"""Evaluate a stratified control sample, without extrapolating it to all stocks."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from scripts.research_turnover_followup_compare import analyze

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/author-trading-system-20261028'
INPUT=DOCS/'turnover-close-control-20261031.json'
HISTORY=DOCS/'turnover-control-baostock-20261031.json'
OUTPUT=DOCS/'turnover-control-comparison-20261031.json'


def evaluate(snapshot,history):
    results={}
    for group in ('near_5_percent','other'):
        sample=[r for r in snapshot['control_sample'] if r['control_group']==group]
        codes={r['code'] for r in sample}
        if len(codes)!=len(sample):raise ValueError('对照组存在重复代码')
        s={'anchor_timestamp':snapshot['anchor_timestamp'],'followup_candidates':sample}
        h={'rows':[r for r in history['rows'] if r['code'] in codes]}
        data=analyze(s,h)
        valid=[r for r in data['rows'] if 'error' not in r]
        data['sina_difference_over_tolerance']=sum(abs(Decimal(r['sina_turn'])-Decimal(r['bao_turn']))>Decimal('.0051') for r in valid)
        data['tencent_difference_over_tolerance']=sum(abs(Decimal(r['tencent_turn'])-Decimal(r['bao_turn']))>Decimal('.0051') for r in valid)
        results[group]=data
    return results


def main():
    raw=[INPUT.read_bytes(),HISTORY.read_bytes()]
    snapshot,history=[json.loads(x) for x in raw]
    if history['input_sha256']!=hashlib.sha256(raw[0]).hexdigest():raise ValueError('补采输入摘要不一致')
    report={'date':snapshot['anchor_timestamp'][:10], 'groups':evaluate(snapshot,history),
            'inputs_sha256':{p.name:hashlib.sha256(b).hexdigest() for p,b in zip((INPUT,HISTORY),raw)},
            'warning':'分层抽样、非全市场逐股核验；新浪无明确日期，上游来源血缘未知。仅事后收盘对照，不能证明作者口径或盘中实时可用。'}
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:{'counts':v['counts'],'sina_diffs':v['sina_difference_over_tolerance'],'tencent_diffs':v['tencent_difference_over_tolerance']} for k,v in report['groups'].items()},ensure_ascii=False))


if __name__=='__main__': main()
