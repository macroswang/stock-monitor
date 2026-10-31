"""Cross-check only previously identified BJ discrepancies against Sina daily.

Only public historical quotes are read. The response has no turnover field;
matching volume is not proof of independent upstream data or turnover accuracy.
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from core.provider import get,now_cn

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/trin-author-table-comparison-20261029'
INPUT=OUT/'march-beijing-tdx-crosscheck.json'


def interpret(text,day,money,tdx):
    if '=(' not in text or ')' not in text:raise ValueError('响应格式无效')
    data=json.loads(text.split('=(',1)[1].rsplit(')',1)[0])
    rows=[r for r in data if r.get('day')==day]
    if len(rows)!=1:raise ValueError('目标日期缺失或重复')
    r=rows[0];volume=Decimal(str(r['volume']))
    if not volume.is_finite() or volume<=0:raise ValueError('无效成交量')
    return {'date':day,'sina_ohlc':{k:r[k] for k in ('open','high','low','close')},
            'sina_volume_shares':str(volume),'money_volume_shares':money,'tdx_volume_shares':tdx,
            'matches_money_volume':volume==Decimal(money),'matches_tdx_volume':volume==Decimal(tdx),
            'turnover_available':False}


def main():
    report=json.loads(INPUT.read_text())
    jobs=[(row['date'],code,detail) for row in report['rows'] for code,detail in row['bar_mismatches'].items()]
    def fetch(job):
        raw_day,code,detail=job;day=f'{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:]}'
        symbol='bj'+code;params=urlencode(dict(symbol=symbol,scale=240,ma='no',datalen=250))
        url='https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData?'+params
        try:
            text=get(url);result=interpret(text,day,detail['money_shares'],str(detail['tdx_shares']))
            raw=OUT/('sina-'+symbol+'.raw.txt');raw.write_text(text,encoding='utf-8')
            return {'code':code,'status':'ok','url':url,'raw_file':raw.name,
                    'response_sha256':hashlib.sha256(text.encode()).hexdigest(),**result}
        except Exception as exc:return {'code':code,'date':day,'status':'error','error':type(exc).__name__+': '+str(exc)}
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(fetch,jobs))
    result={'observed_at':now_cn().isoformat(),'selection':'仅 Money Tree 与通达信量额不一致的北交所股票',
            'warning':'新浪日线接口仅比较成交股数；不包含成交额或独立证明三个数据源上游血缘。',
            'rows':results}
    (OUT/'march-beijing-sina-crosscheck.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
