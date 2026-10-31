"""Read-only after-close crosscheck of public stock turnover quote fields.

Sina's list has no trade date. Tencent's dated quotes provide a limited date
anchor when same-stock prices and volumes agree; this does not prove the Sina
turnover field's timestamp or that the upstream sources are independent.
"""
import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from core.breadth import parse_quotes, universe
from core.provider import CN, get, now_cn

OUT = Path(__file__).resolve().parents[1] / 'docs/author-trading-system-20261028/turnover-close-crosscheck-20261031.json'
URL = 'https://qt.gtimg.cn/q='


def compare(code, sina, tencent, raw_field, day):
    """Return a reason or checked values; Tencent rounds turnover to 0.01%."""
    if not tencent or tencent['timestamp'][:10] != day:
        return {'error':'腾讯报价日期缺失或不匹配'}
    try:
        volume, price = int(sina['volume']), Decimal(str(sina['trade']))
        st, tt = Decimal(str(sina['turnoverratio'])), Decimal(raw_field)
        if volume <= 0 or not all(x.is_finite() for x in (price,st,tt)) or min(price,st,tt) < 0:
            raise ValueError
        tolerance = 0 if code.startswith(('sh688','sh689')) else 50
        if price != Decimal(tencent['price']) or abs(volume-tencent['volume']) > tolerance:
            return {'error':'两源价格或成交股数不一致'}
        if abs(st-tt) > Decimal('0.0051'):
            return {'error':'两源换手率超出显示精度', 'sina_turn':str(st), 'tencent_turn':str(tt),
                    'above_or_equal':st>=5, 'threshold_ambiguous':tt==Decimal('5.00'),
                    'threshold_disagrees':tt!=Decimal('5.00') and (st>=5)!=(tt>5)}
        return {'sina_turn':str(st),'tencent_turn':str(tt),
                'threshold_ambiguous':tt==Decimal('5.00'), 'above_or_equal':st>=5}
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return {'error':'换手率或行情字段缺失'}


def quote_batch(codes):
    text = get(URL+','.join(codes), 'gb18030')
    parsed = parse_quotes(text, set(codes))
    fields = {}
    for code, body in re.findall(r'v_(\w+)="([^"]*)"', text):
        if code in parsed:
            parts = body.split('~')
            fields[code] = parts[38] if len(parts)>38 else ''
    return parsed, fields


def select_controls(rows, n=60):
    """Fixed hash ordering avoids selecting controls by provider disagreement."""
    order=lambda row:hashlib.sha256(('turnover-control-v1:'+row['code']).encode()).digest()
    near=sorted((r for r in rows if abs(Decimal(r['sina_turn'])-5)<=Decimal('0.1')),key=order)[:n]
    far=sorted((r for r in rows if abs(Decimal(r['sina_turn'])-5)>Decimal('0.1')),key=order)[:n]
    return [{**r,'control_group':'near_5_percent'} for r in near]+[{**r,'control_group':'other'} for r in far]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--include-controls', action='store_true')
    args=parser.parse_args()
    started = now_cn()
    anchor_raw = get(URL+'sh000001','gb18030')
    match = re.search(r'v_sh000001="([^"]+)"',anchor_raw)
    if not match: raise ValueError('缺少指数日期锚点')
    anchor = datetime.strptime(match.group(1).split('~')[30],'%Y%m%d%H%M%S').replace(tzinfo=CN)
    if anchor > started or anchor.strftime('%H:%M') < '15:00' or (started.date()-anchor.date()).days > 5:
        raise ValueError('指数锚点不是近期收盘')
    day = anchor.date().isoformat()
    listing = universe()
    codes = sorted(listing)
    quotes, fields = {}, {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for q,f in pool.map(quote_batch,[codes[i:i+160] for i in range(0,len(codes),160)]):
            quotes.update(q);fields.update(f)
    summary, examples, boundary_disagreements, followup_candidates, control_pool = {}, {}, [], [], []
    for code in codes:
        sino = listing[code]
        if int(sino.get('volume',0)) == 0:
            key = '新浪成交量为零'
        else:
            result = compare(code,sino,quotes.get(code),fields.get(code,''),day)
            key = result.get('error','通过两源比较')
            if key == '两源换手率超出显示精度':
                for label in ('above_or_equal','threshold_ambiguous','threshold_disagrees'):
                    name = 'difference_'+label
                    summary[name] = summary.get(name,0) + int(result[label])
                if result['threshold_disagrees']:
                    boundary_disagreements.append({'code':code, 'sina_turn':result['sina_turn'],
                                                   'tencent_turn':result['tencent_turn'],
                                                   'tencent_timestamp':quotes[code]['timestamp']})
            if key == '通过两源比较':
                for label in ('above_or_equal','threshold_ambiguous'):
                    summary[label] = summary.get(label,0) + int(result[label])
                if args.include_controls and not result['threshold_ambiguous']:
                    control_pool.append({'code':code,'sina_turn':result['sina_turn'],
                                         'tencent_turn':result['tencent_turn'],
                                         'tencent_timestamp':quotes[code]['timestamp'],
                                         'tencent_price':quotes[code]['price'],
                                         'tencent_previous_close':quotes[code]['previous_close'],
                                         'tencent_volume':quotes[code]['volume']})
            if key == '两源换手率超出显示精度' or (key == '通过两源比较' and result['threshold_ambiguous']):
                followup_candidates.append({'code':code, 'sina_turn':result['sina_turn'],
                                            'tencent_turn':result['tencent_turn'],
                                            'tencent_timestamp':quotes[code]['timestamp'],
                                            'tencent_price':quotes[code]['price'],
                                            'tencent_previous_close':quotes[code]['previous_close'],
                                            'tencent_volume':quotes[code]['volume'],
                                            'reason':key})
        summary[key] = summary.get(key,0)+1
        if key != '通过两源比较' and len(examples.setdefault(key,[]))<5:
            examples[key].append({'code':code, **{k:v for k,v in result.items() if k in ('sina_turn','tencent_turn')}} if key != '新浪成交量为零' else {'code':code})
    checked = summary.get('通过两源比较',0)
    report = {'started_at':started.isoformat(),'finished_at':now_cn().isoformat(),
              'anchor_timestamp':anchor.isoformat(),'sina_trade_date':'未提供；仅按同股价格、成交股数与腾讯日期锚定作有限核对',
              'scope':'新浪沪深股票列表（含科创板及689类）；零成交单独计数；5%以上按不小于5%',
              'summary':summary,'checked_denominator':checked,
              'share_percent_of_checked':100*summary.get('above_or_equal',0)/checked if checked else None,
              'error_examples':examples, 'boundary_disagreements':boundary_disagreements,
              'followup_candidates':followup_candidates,
              'warning':'单次收盘后采样；两个来源上游血缘未知，腾讯换手率保留两位小数且5.00%边界不确定。未确认新浪换手率字段日期、作者股票范围与分母，不是盘中验证或可直接用于仓位判断。'}
    if args.include_controls:
        report['control_sample']=select_controls(control_pool)
        report['control_selection']='各取最多60只：新浪换手率距离5%不超过0.1个百分点，以及其余股票；组内按固定代码哈希排序；不含腾讯显示5.00%的不明确值。'
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('error_examples','followup_candidates','control_sample')},ensure_ascii=False))


if __name__=='__main__': main()
