"""Bounded diagnostic: current Sina BJ constituents with retrievable history.

This is NOT a certified historic universe: delistings and historical ex-rights
reference prices may be missing. It never opens the application database.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.provider import get,now_cn
from scripts.crosscheck_trin_history import sina_daily

BASE='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'


def stock_list():
    before=int(json.loads(get(BASE+'Market_Center.getHQNodeStockCount?node=hs_a')))
    result=[];finished=False
    for page in range(1,20):
        params=urlencode(dict(page=page,num=80,sort='symbol',asc=1,node='hs_a',symbol='',_s_r_a='page'))
        rows=json.loads(get(BASE+'Market_Center.getHQNodeData?'+params))
        if not isinstance(rows,list) or not rows:raise ValueError('Sina stock-list page missing')
        for row in rows:
            if row.get('symbol','').startswith('bj'):result.append(row)
            else:finished=True
        if finished:break
    after=int(json.loads(get(BASE+'Market_Center.getHQNodeStockCount?node=hs_a')))
    if not finished or before!=after or len({r['symbol'] for r in result})!=len(result):
        raise ValueError('current Beijing stock list incomplete')
    return result


def main(output):
    output.parent.mkdir(parents=True,exist_ok=True)
    current=stock_list();print('current Beijing listed symbols',len(current),flush=True)
    def fetch(row):
        time.sleep(.2);code=row['symbol']
        try:
            data=sina_daily(code)
            return dict(code=code,status='ok',rows=[r for r in data if r['date'] in
                ['2026-03-20','2026-03-23','2026-03-24','2026-03-25','2026-10-21','2026-10-22','2026-10-23']])
        except Exception as e:return dict(code=code,status='error',error=type(e).__name__)
    with ThreadPoolExecutor(max_workers=2) as pool:series=list(pool.map(fetch,current))
    result=dict(observed_at=now_cn().isoformat(),provider='Sina public daily stock history',current_list=current,
                stocks=series,limitations=['current constituents only; historical delistings omitted',
                   'previous unadjusted close used; ex-rights cases unverified',
                   'missing historical rows cannot be assumed to have been unlisted or suspended'])
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('completed',len(series),'errors',sum(r['status']!='ok' for r in series),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args().output)
