"""Read-only public-data TRIN audit. Never opens the user's application database."""
import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.breadth import collect, number, universe


def write(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def main(output):
    output.mkdir(parents=True,exist_ok=True)
    result,raw=collect()
    write(output/'report.json',result)
    write(output/'raw.json',raw)
    if result['missing']:
        raise ValueError('全市场覆盖不完整，未通过验证')
    other=universe()
    write(output/'sina-crosscheck-raw.json',other)
    groups={k:[0,0] for k in ('advance','decline','flat')}
    discrepancies=[]
    active=0
    for quote in raw['quotes']:
        code=quote['code']
        if not quote['volume']:
            continue
        active+=1
        peer=other.get(code)
        if not peer:
            discrepancies.append(dict(code=code,reason='代码缺失'))
            continue
        p,base,v=(number(peer[k]) for k in ('trade','settlement','volume'))
        reasons=[]
        if p!=number(quote['price']):reasons.append('价格不同')
        if base!=number(quote['previous_close']):reasons.append('昨收不同')
        diff=abs(int(v)-quote['volume'])
        if diff>100:reasons.append('成交股数差异超过100股')
        if reasons:discrepancies.append(dict(code=code,reasons=reasons,tencent=quote,sina=peer))
        key='advance' if p>base else 'decline' if p<base else 'flat'
        groups[key][0]+=1;groups[key][1]+=int(v)
    a,d=groups['advance'],groups['decline']
    value=a[0]*d[1]/(d[0]*a[1]) if d[0] and a[1] else None
    check=dict(date=result['date'],active_compared=active,discrepancies=discrepancies,
               tencent_trin=result['trin'],sina_trin=value,groups=groups,
               absolute_trin_difference=abs(value-result['trin']) if value is not None and result['trin'] is not None else None,
               rounding_tolerance_shares=100,
               limitation='新浪快照仅带时分秒，日期由腾讯逐股完整时间戳锚定；此比较不独立认证新浪日期。盘中采集时间不同可能出现量价差异。',
               result='PASS' if not discrepancies else 'DIFFERENCES')
    write(output/'crosscheck.json',check)
    print(json.dumps(dict(date=result['date'],trin=result['trin'],covered=result['covered'],expected=result['expected'],status=result['status'],crosscheck=check['result'],discrepancies=len(discrepancies),output=str(output.resolve())),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output)
