"""Read-only, bounded live-data audit. No app configuration or trading writes.
A weekend snapshot is never accepted as evidence of intraday update latency.
"""
import argparse
import concurrent.futures
from datetime import datetime, time as clock_time
from decimal import Decimal
import hashlib
import json
import math
import re
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.provider import Tencent,now_cn,CN,symbol
from core.paper_session import trading_error


from core.eastmoney_flow import parse_details


def fetch_details(code):
    params=dict(fields1='f1,f2,f3,f4',fields2='f51,f52,f53,f54,f55',mpi='2000',ut='bd1d9ddb04089700cf9c27f6f7426281',fltt='2',pos='-0',secid=f"{1 if code.startswith('sh') else 0}.{code[2:]}",wbp2u='|0|0|0|web')
    request=Request('https://70.push2.eastmoney.com/api/qt/stock/details/sse?'+urlencode(params),headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
    with urlopen(request,timeout=8) as response:
        total=0
        for _ in range(16):
            line=response.readline(2*1024*1024+1);total+=len(line)
            if total>2*1024*1024:raise ValueError('东财响应过大')
            if line.startswith(b'data:'):return parse_details(json.loads(line[5:].decode('utf-8')),code)
    raise ValueError('未取得东财首个数据事件')


def compare(snapshot,minute,observed):
    comparisons=[]
    for b in minute.get('bars',[]):
        if not b.get('complete') or not ('09:31'<=b['time']<='11:30' or '13:01'<=b['time']<='14:57'):continue
        end=datetime.fromisoformat(minute['date']+'T'+b['time']+':00').replace(tzinfo=CN)
        if (observed-end).total_seconds()<90:continue
        row=snapshot['buckets'].get(b['time']);total=int(b['volume'])
        if total<=0:continue
        comparisons.append(dict(time=b['time'],reference=total,received=row['total'] if row else 0,volume_match=bool(row and row['total']==total),price_match=bool(row and Decimal(row['last_price'])==Decimal(b['close'])),directions={k:row[k] if row else 0 for k in ('buy','sell','neutral','unknown')}))
    return comparisons


def sample(code,raw_dir,index):
    provider=Tencent();began=now_cn();result=dict(code=code,observed_at=began.isoformat())
    try:
        result['stage']='eastmoney_details';snapshot=fetch_details(code)
        raw_name=f'{index:03}-{code}.json';(raw_dir/raw_name).write_text(json.dumps(snapshot['raw'],ensure_ascii=False),encoding='utf-8')
        total=sum(b['total'] for b in snapshot['buckets'].values());unknown=sum(b['unknown'] for b in snapshot['buckets'].values())
        result.update(source_status='ok',source_received_at=now_cn().isoformat(),rows=snapshot['rows'],last_trade=snapshot['last_trade'],raw_file=raw_name,unknown_fraction=unknown/total if total else 1)
        result['stage']='reference_quote';before=provider.quote(code)
        result['stage']='reference_minutes';minutes=provider.minutes(code)
        result['stage']='reference_quote_after';after=provider.quote(code);observed=now_cn()
        current=observed.date().isoformat();reference=next((g for g in minutes if g['date']==before['date']),None)
        quote_stamp=datetime.fromisoformat(after['timestamp'])
        anchored=before['date']==after['date']==current and 0<=(observed-quote_stamp).total_seconds()<=90
        last=snapshot['last_trade'];last_dt=datetime.fromisoformat(current+'T'+last).replace(tzinfo=CN) if last else None
        lag=(observed-last_dt).total_seconds() if last_dt else None
        result.update(status='ok',received_at=observed.isoformat(),source_date_explicit=False,date_anchor=anchored,reference_date=before['date'],quote_time=after['timestamp'],rows=snapshot['rows'],last_trade=last,lag_seconds=round(lag,3) if anchored and lag is not None and lag>=-3 else None,
                      raw_file=raw_name,raw_sha256=hashlib.sha256((raw_dir/raw_name).read_bytes()).hexdigest(),comparisons=compare(snapshot,reference,observed) if reference else [])
    except Exception as error:result.update(status='partial' if result.get('source_status')=='ok' else 'error',error_stage=result.get('stage'),error_type=type(error).__name__,error=str(error)[:160])
    return result


def percentile(values,p):
    return sorted(values)[max(0,math.ceil(len(values)*p)-1)] if values else None


def summarize(records,live):
    stocks={}
    for code in sorted({r['code'] for r in records}):
        rows=[r for r in records if r['code']==code];ok=[r for r in rows if r['status']=='ok'];lags=[r['lag_seconds'] for r in ok if r.get('date_anchor') and r.get('lag_seconds') is not None]
        latest={};past={};revisions=0
        for r in ok:
            for c in r['comparisons']:
                key=(r['reference_date'],c['time']);value=(c['received'],c['volume_match'],c['price_match'],tuple(sorted(c.get('directions',{}).items())))
                if key in past and past[key]!=value:revisions+=1
                past[key]=value;latest[key]=c
        exact=sum(c['volume_match'] and c['price_match'] for c in latest.values())
        ratio=exact/len(latest) if latest else 0;p95=percentile(lags,.95)
        passed=bool(live and len(rows)>=10 and len(ok)/len(rows)>=.95 and len(lags)/len(rows)>=.95 and p95 is not None and p95<=30 and max(lags)<=90 and len(latest)>=5 and ratio>=.95 and revisions==0 and all(r.get('unknown_fraction',1)<=.05 for r in ok))
        stocks[code]=dict(samples=len(rows),source_successful=sum(r.get('source_status')=='ok' for r in rows),successful=len(ok),dated_fresh_samples=len(lags),lag_p95_seconds=p95,lag_max_seconds=max(lags) if lags else None,unique_closed_minutes=len(latest),exact_volume_and_price_minutes=exact,exact_ratio=round(ratio,4),settled_minute_revisions=revisions,passed=passed)
    return dict(result='PASS_MINUTE_DISPLAY_CANDIDATE' if stocks and all(v['passed'] for v in stocks.values()) else 'NOT_VERIFIED_LIVE' if not live else 'FAIL_OR_INSUFFICIENT_EVIDENCE',source='eastmoney_public_details',source_date_explicit=False,date_basis='腾讯当日新鲜报价与同日完整分钟量价交叉核对；东财明细自身不含交易日期',stocks=stocks,limitations=['通过仅表示该采样窗口可作为分钟级展示候选，不承诺整日或逐笔完整性','未通过不修改现有行情源，不按缺失数据推断买卖方向'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--expected-date');parser.add_argument('--duration',type=int,default=0);parser.add_argument('--interval',type=int,default=30);parser.add_argument('--codes',default='sh603938,sz300672,sz000981');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not 0<=args.duration<=900 or args.interval<20:parser.error('duration must be 0..900 and interval >=20 seconds')
    now=now_cn();args.output.mkdir(parents=True,exist_ok=True);records=[]
    if args.live and ((args.expected_date and now.date().isoformat()!=args.expected_date) or trading_error(now)):
        report=dict(result='NOT_RUN_OUTSIDE_REQUESTED_SESSION',observed_at=now.isoformat(),reason=trading_error(now) or '实际日期与要求验证日期不符')
    else:
        codes=list(dict.fromkeys(symbol(c) for c in args.codes.split(',')));start=time.monotonic();index=0
        if len(codes)>3:parser.error('at most three stocks')
        while True:
            if args.live and trading_error(now_cn()):break
            tick=time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:batch=list(pool.map(lambda code:sample(code,args.output,index),codes))
            records.extend(batch)
            with (args.output/'samples.jsonl').open('a',encoding='utf-8') as stream:
                for row in batch:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            print(json.dumps(dict(sample=index,at=now_cn().isoformat(),results=[{k:r.get(k) for k in ('code','status','rows','date_anchor','lag_seconds')} for r in batch]),ensure_ascii=False),flush=True)
            index+=1
            if time.monotonic()-start>=args.duration:break
            time.sleep(max(0,min(args.interval-(time.monotonic()-tick),args.duration-(time.monotonic()-start))))
        report=summarize(records,args.live);report.update(started_at=now.isoformat(),finished_at=now_cn().isoformat(),live_requested=args.live)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
