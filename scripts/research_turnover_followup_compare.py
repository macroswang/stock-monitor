"""Compare all flagged post-close turnover cases with dated BaoStock rows."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/author-trading-system-20261028'
SNAPSHOT=DOCS/'turnover-close-followup-20261031.json'
HISTORY=DOCS/'turnover-followup-baostock-20261031.json'
OUTPUT=DOCS/'turnover-followup-comparison-20261031.json'


def analyze(snapshot, history):
    day=snapshot['anchor_timestamp'][:10]
    candidates=snapshot['followup_candidates']
    matched={r['code']:r for r in history['rows']}
    if len(matched)!=len(history['rows']) or set(matched)!={r['code'] for r in candidates}:
        raise ValueError('补采股票名单不一致或重复')
    counts={'eligible':0,'missing_or_invalid':0,'sina_closer':0,'tencent_closer':0,
            'same_difference':0,'bao_5_percent_ambiguous':0,'changed_threshold_class':0}
    rows=[]
    for entry in candidates:
        code=entry['code']; data=matched[code].get('rows',[])
        try:
            if len(data)!=1 or data[0]['date']!=day or data[0]['code'].replace('.','')!=code or data[0]['tradestatus']!='1':
                raise ValueError('日期、代码或交易状态不一致')
            r=data[0]
            if (Decimal(r['close'])!=Decimal(entry['tencent_price'])
                or Decimal(r['preclose'])!=Decimal(entry['tencent_previous_close'])
                or abs(int(r['volume'])-int(entry['tencent_volume']))>(0 if code.startswith(('sh688','sh689')) else 50)):
                raise ValueError('收盘价、昨收或成交量不一致')
            bao,sina,tencent=(Decimal(str(x)) for x in (r['turn'],entry['sina_turn'],entry['tencent_turn']))
            if not all(x.is_finite() and x>=0 for x in (bao,sina,tencent)):
                raise ValueError('换手率无效')
            sd,td=abs(bao-sina),abs(bao-tencent)
            nearest='sina_closer' if sd<td else 'tencent_closer' if td<sd else 'same_difference'
            counts['eligible']+=1;counts[nearest]+=1
            uncertain=bao==Decimal('5')
            counts['bao_5_percent_ambiguous']+=int(uncertain)
            changed=not uncertain and (bao>=5)!=(sina>=5)
            counts['changed_threshold_class']+=int(changed)
            rows.append({'code':code,'bao_turn':str(bao),'sina_turn':str(sina),'tencent_turn':str(tencent),
                         'nearer':nearest,'threshold_uncertain':uncertain,'changed_sina_threshold':changed})
        except (KeyError, TypeError, ValueError, InvalidOperation, IndexError):
            counts['missing_or_invalid']+=1
            rows.append({'code':code,'error':'缺少可核对的同日日线'})
    result={'date':day,'counts':counts,'rows':rows}
    summary=snapshot.get('summary',{})
    expected_keys={'above_or_equal','threshold_ambiguous','通过两源比较','新浪成交量为零',
                   'difference_above_or_equal','difference_threshold_ambiguous',
                   'difference_threshold_disagrees','两源换手率超出显示精度'}
    expected_candidates=summary.get('两源换手率超出显示精度',0)+summary.get('threshold_ambiguous',0)
    # This is a mixed-source sensitivity study, never a same-source live value.
    required={'above_or_equal','difference_above_or_equal','通过两源比较','两源换手率超出显示精度','threshold_ambiguous'}
    if (required<=set(summary)<=expected_keys and len(candidates)==expected_candidates
            and not counts['missing_or_invalid'] and not counts['bao_5_percent_ambiguous']):
        original=summary['above_or_equal']+summary['difference_above_or_equal']
        correction=sum(int(Decimal(row['bao_turn'])>=5)-int(Decimal(row['sina_turn'])>=5) for row in rows)
        denominator=summary['通过两源比较']+summary['两源换手率超出显示精度']
        result['mixed_source_study']={'active_denominator':denominator,'original_sina_count':original,
                                       'after_candidate_replacement_count':original+correction,
                                       'after_candidate_replacement_percent':100*(original+correction)/denominator if denominator else None}
    return result


def main():
    blobs=[SNAPSHOT.read_bytes(),HISTORY.read_bytes()]
    s,h=(json.loads(blob) for blob in blobs)
    if h['input_sha256']!=hashlib.sha256(blobs[0]).hexdigest():raise ValueError('补采输入摘要不一致')
    report=analyze(s,h)
    report['inputs_sha256']={p.name:hashlib.sha256(b).hexdigest() for p,b in zip((SNAPSHOT,HISTORY),blobs)}
    report['warning']='仅核对两源不一致或腾讯显示5.00%的候选；新浪列表未提供日期，上游血缘未知。非全市场独立核验，不能证明作者口径或盘中实时有效。'
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('date','counts','mixed_source_study') if k in report},ensure_ascii=False))


if __name__=='__main__': main()
