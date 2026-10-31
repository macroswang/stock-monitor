"""Explore the fixed weak-market condition over cached earlier stock histories.

Early BaoStock daily closes were checked against TDX, but precloses, volumes
and amounts were not fully cross-checked. No product or account data is edited.
"""
import hashlib
import json
import statistics
from datetime import date, timedelta
from pathlib import Path

from scripts.analyze_trin_history import compute

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/market-regime-research-20261029'
P250=ROOT/'docs/p250-research-20261029'


def load_index():
    t=json.loads((OUT/'tencent-index-2025-2026.json').read_text())['data']['sh000001']['day']
    s=json.loads((OUT/'sina-index-2025-2026.json').read_text())
    s_by_day={r['day']:r for r in s}
    if len(s_by_day)!=len(s) or len({r[0] for r in t})!=len(t):raise ValueError('指数重复日期')
    calendars={2025:json.loads((P250/'exchange-calendar-2025.json').read_text())['closed_ranges'],
               2026:json.loads((ROOT/'fixtures/exchange-calendar-2026.json').read_text())['closed_ranges']}
    current=date.fromisoformat(t[0][0]);end=date.fromisoformat(t[-1][0]);expected=[]
    while current<=end:
        day=current.isoformat()
        if current.weekday()<5 and not any(a<=day<=b for a,b in calendars[current.year]):expected.append(day)
        current+=timedelta(days=1)
    if [r[0] for r in t]!=expected:raise ValueError('指数交易日不完整')
    if any(r[0] not in s_by_day or abs(float(r[1])-float(s_by_day[r[0]]['open']))>0.0051
           or abs(float(r[2])-float(s_by_day[r[0]]['close']))>0.0051 for r in t):
        raise ValueError('指数来源日期或开收盘价不一致')
    return [{'date':r[0], 'open':float(r[1]), 'close':float(r[2]),
             'ma20':sum(float(x[2]) for x in t[i-19:i+1])/20 if i>=19 else None}
            for i,r in enumerate(t)]


def load_breadth():
    collection=json.loads((P250/'baostock-collection.json').read_text())
    checks=json.loads((P250/'tdx-close-crosscheck.json').read_text())
    check_by_day={r['date']:r for r in checks['rows']}
    if collection['failures'] or len(collection['records'])!=len(collection['expected']):raise ValueError('早期行情缺失')
    merged={}
    for day in collection['expected']:
        c=check_by_day.get(day)
        if not c or c['only_baostock'] or c['only_tdx'] or c['close_mismatches'] or c['matched']!=c['baostock']:
            raise ValueError('早期日线名单或收盘价未核对：'+day)
        payload=json.loads((P250/'baostock'/f'{day}.json').read_text())
        if payload['date']!=day or any(r['date']!=day for r in payload['daily']):raise ValueError('早期股票日期不匹配')
        payload['universe']=[{'code':r['code']} for r in payload['daily']]
        value=compute(payload,'shsz_no_cdr','amount')
        if value['trin'] is None:raise ValueError('早期宽度异常：'+day)
        merged[day]={'date':day,'breadth':100*value['up_ratio'],'trin':value['trin'],
                     'advance':value['counts']['up'],'decline':value['counts']['down'],
                     'source':'BaoStock; TDX checked close only'}
    verified=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text())
    overlaps=[]
    for row in verified:
        day=row['date']
        if day in merged:
            old=merged[day]
            if (old['advance']!=row['advance'] or old['decline']!=row['decline']
                    or abs(old['trin']-row['trin_amount'])>1e-9):raise ValueError('重叠日广度不一致：'+day)
            overlaps.append(day)
        if row['status']=='closed' and row['missing']==0 and row.get('trin_amount') is not None:
            merged[day]={'date':day,'breadth':row['advancing_percent'],'trin':row['trin_amount'],
                         'advance':row['advance'],'decline':row['decline'],
                         'source':'independently cross-checked historical fixture'}
    return merged,overlaps


def stats(rows):
    result={}
    for key in ('one_day','five_day'):
        values=[r[key] for r in rows]
        result[key]={'n':len(values),'positive':sum(x>0 for x in values),
                     'mean':statistics.mean(values) if values else None,
                     'median':statistics.median(values) if values else None}
    return result


def main():
    index=load_index();breadth,overlaps=load_breadth();out=[]
    for i,bar in enumerate(index):
        day=bar['date'];b=breadth.get(day)
        if not b or bar['ma20'] is None or i+5>=len(index):continue
        f=index[i+1:i+6]
        if any(min(x['open'],x['close'])<=0 for x in f):raise ValueError('指数价格无效')
        out.append(dict(date=day,source=b['source'],breadth=b['breadth'],trin=b['trin'],
                        weak=b['breadth']<20 and bar['close']<bar['ma20'],
                        weak_low_trin=b['breadth']<20 and bar['close']<bar['ma20'] and b['trin']<0.7,
                        one_day=(f[0]['close']/f[0]['open']-1)*100,
                        five_day=(f[4]['close']/f[0]['open']-1)*100))
    groups={}
    for label,rows in [('all',out),('before_2026_06_01',[r for r in out if r['date']<'2026-06-01']),
                       ('since_2026_06_01',[r for r in out if r['date']>='2026-06-01'])]:
        groups[label]={name:stats([r for r in rows if name=='all' or r[name]]) for name in ('all','weak','weak_low_trin')}
    index_files=['tencent-index-2025-2026.json','sina-index-2025-2026.json']
    result={'index_inputs':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in index_files},
            'overlap_dates':overlaps,'start':out[0]['date'],'end':out[-1]['date'],
            'warning':'研究性补采；早期仅核对股票名单及收盘价，昨收与成交额未全量独立核验；数据来源上游可能相同；回看设计未预注册，指数代理未含成本。',
            'summary':groups,'rows':out}
    (OUT/'extended-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'start':result['start'],'end':result['end'],'overlaps':overlaps,'summary':groups},ensure_ascii=False))


if __name__=='__main__':main()
