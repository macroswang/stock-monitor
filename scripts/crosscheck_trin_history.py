"""Cross-check a deterministic, stratified sample against Tencent daily history."""
import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.provider import Tencent,get


def choose(rows):
    valid=[r for r in rows if r['tradestatus']=='1' and Decimal(r['preclose'])>0 and Decimal(r['volume'])>0]
    rise=[r for r in valid if Decimal(r['close'])>Decimal(r['preclose'])]
    fall=[r for r in valid if Decimal(r['close'])<Decimal(r['preclose'])]
    rng=random.Random(20261028);out={}
    for group in (rise,fall):
        for row in sorted(group,key=lambda r:Decimal(r['volume']),reverse=True)[:10]:out[row['code']]=row
        for row in sorted(group,key=lambda r:Decimal(r['amount']),reverse=True)[:10]:out[row['code']]=row
        for row in rng.sample(group,min(10,len(group))):out[row['code']]=row
    return list(out.values())


def sina_daily(code):
    params=urlencode(dict(symbol=code,scale=240,ma='no',datalen=250))
    text=get('https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData?'+params)
    if '=(' not in text or ')' not in text:raise ValueError('Sina daily data missing')
    rows=json.loads(text.split('=(',1)[1].rsplit(')',1)[0])
    return [dict(date=row['day'],open=row['open'],high=row['high'],low=row['low'],close=row['close'],volume=row['volume']) for row in rows]


def main(source,output,dates,provider):
    jobs=[]
    for f in sorted(source.glob('????-??-??.json')):
        data=json.loads(f.read_text(encoding='utf-8'))
        if dates and data['date'] not in dates:continue
        for row in choose(data['daily']):jobs.append((data['date'],row))
    def fetch(job):
        day,row=job;code=row['code'].replace('.','');start=(date.fromisoformat(day)-timedelta(days=7)).isoformat()
        time.sleep(.1)
        try:
            series=Tencent().daily(code,start,day) if provider=='tencent' else sina_daily(code)
            current=next((r for r in series if r['date']==day),None)
            if current is None:return dict(date=day,code=code,status='missing',bao=row)
            previous=next((r for r in reversed(series) if r['date']<day),None)
            diffs=[]
            for field in ('open','close','high','low'):
                if Decimal(current[field])!=Decimal(row[field]):diffs.append(field)
            vol_diff=abs(Decimal(current['volume'])-Decimal(row['volume']))
            if vol_diff>100:diffs.append('volume')
            # Prior close may legitimately differ on an ex-rights date. Preserve
            # both values rather than silently declaring the provider wrong.
            previous_diff=previous is None or Decimal(previous['close'])!=Decimal(row['preclose'])
            return dict(date=day,code=code,status='difference' if diffs else 'match',differences=diffs,
                        volume_difference=str(vol_diff),previous_close_differs=previous_diff,
                        previous_source=previous,bao=row,comparison=current,provider=provider)
        except Exception as e:
            return dict(date=day,code=code,status='error',error=type(e).__name__)
    with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(fetch,jobs))
    summary={}
    for day in sorted({r['date'] for r in result}):
        rows=[r for r in result if r['date']==day]
        summary[day]=dict(total=len(rows),match=sum(r['status']=='match' for r in rows),
            differences=sum(r['status']=='difference' for r in rows),missing=sum(r['status']=='missing' for r in rows),
            errors=sum(r['status']=='error' for r in rows),previous_close_differs=sum(bool(r.get('previous_close_differs')) for r in rows))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(summary=summary,items=result,provider=provider,method='highest volume/amount and fixed-seed samples from up/down groups; source volumes normalized to shares'),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--dates',nargs='*');p.add_argument('--provider',choices=('tencent','sina'),default='tencent')
    a=p.parse_args();main(a.source,a.output,a.dates,a.provider)
