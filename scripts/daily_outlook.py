"""Daily research inputs and atomic publication for the installed app.

scan: latest verified industry/concept lists, liquid stocks and dated news.
quotes CODE...: inspect selected stocks and recent sessions.
publish FILE: JSON input {quote_date, coverage:{industry,concept}, sources:
[{region:domestic|international,date,title,url}], ideas:[{sector,sector_code,
codes:[primary,peer,peer],reason,risk,sources:[zero-based source indices],
allow_entry:boolean}]}. Ideas are ordered by research priority. Zero ideas is valid.
"""
import argparse
import concurrent.futures
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import breadth, sector_flow
from core.provider import CN, get, now_cn

DATA = Path(os.getenv('STOCK_MONITOR_DATA', Path.home()/'Library/Application Support/com.xreddot.stockmonitor'))
def cached(kind, day):
    db = DATA/'monitor.sqlite3'
    if not db.exists():
        return None
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
        row = conn.execute('SELECT payload FROM cache WHERE code=? AND kind=? AND day=?',(breadth.CODE,kind,day)).fetchone()
    return json.loads(row[0]) if row else None

def market(now):
    day=sector_flow.expected_day(now)
    if not day:
        raise ValueError('交易日历尚未覆盖当前日期')
    summary=cached(breadth.KIND,day)
    raw=cached('breadth_raw_v1',day)
    if not (summary and raw and summary['collected_at']==raw['collected_at'] and breadth.valid_closed_breadth(summary,day,now)):
        summary,raw=breadth.collect()
    if summary['date']!=day or raw['date']!=day or summary['missing'] or summary['covered']!=summary['expected']:
        raise ValueError('本期沪深行情未完整取得')
    return summary,{q['code']:q for q in raw['quotes']}

def headline_feed(lid):
    url=f'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid={lid}&num=50&page=1'
    rows=json.loads(get(url))['result']['data']
    now=now_cn()
    out=[]
    for r in rows:
        ts=datetime.fromtimestamp(int(r['ctime']),CN)
        if now-timedelta(days=3)<=ts<=now and r.get('title') and r.get('url'):
            out.append({'time':ts.isoformat(),'title':r['title'],'url':r['url']})
    return out

def scan():
    now=now_cn()
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        jobs={'market':pool.submit(market,now)}
        for kind in ('industry','concept'):
            jobs[kind]=pool.submit(sector_flow.fetch,now,kind)
        for name,lid in [('domestic',2517),('international',2518)]:
            jobs[name]=pool.submit(headline_feed,lid)
        result={}
        for key,future in jobs.items():
            try:
                value=future.result()
            except Exception as exc:
                result[key]={'error':str(exc)}
                continue
            if key=='market':
                summary,quotes=value
                result[key]={k:summary[k] for k in ('date','advance','decline','flat','covered','status')}
                liquid=sorted(quotes.values(),key=lambda q:float(q['amount_yuan'] or 0),reverse=True)
                result['most_traded']=[(q['code'],round((float(q['price'])/float(q['previous_close'])-1)*100,2)) for q in liquid[:100] if float(q['previous_close'])>0]
            elif key in ('industry','concept'):
                result[key]={'date':value['date'],'source':value['source'],'rows':[
                    [r['code'],r['name'],round(r['change_percent'],2),round(r['net_yuan']/1e8,2),(r.get('representative') or {}).get('code')]
                    for r in value['sectors']]}
            else:
                result[key]=value
        return result

def require(condition,message):
    if not condition:
        raise ValueError(message)

def publish(d):
    now=now_cn()
    summary,quotes=market(now)
    require(d['quote_date']==summary['date'],'研判行情日期已变化')
    for n in ('industry','concept'):
        require(type(d['coverage'][n]) is int and d['coverage'][n]>=0,'板块覆盖数量错误')
    require(sum(d['coverage'][n] for n in ('industry','concept'))>0,'缺少板块扫描')
    sources=d['sources']
    require(isinstance(sources,list) and len(sources)<=25,'来源列表错误')
    for s in sources:
        age=(now.date()-date.fromisoformat(s['date'])).days
        require(0<=age<=7 and s['title'].strip() and urlparse(s['url']).scheme in ('http','https') and urlparse(s['url']).hostname,'消息来源或日期无效')
    require({'domestic','international'}<={s['region'] for s in sources},'须同时核对国内和海外消息')
    ideas=d['ideas']
    require(isinstance(ideas,list) and len(ideas)<=6,'研究名单最多六项')
    unique=set()
    for i in ideas:
        codes=i['codes']
        require(len(codes)==3 and len(set(codes))==3 and all(isinstance(c,str) and re.fullmatch(r'(sh[69]|sz[03])\d{5}',c) and c in quotes for c in codes),'候选与两只同行必须有本期沪深报价')
        require(codes[0] not in unique,'重复首选股票')
        unique.add(codes[0])
        require(all(isinstance(i[k],str) and i[k].strip() for k in ('sector','sector_code','reason','risk')) and type(i['allow_entry']) is bool,'缺少判断依据')
        require(i['sources'] and all(type(k) is int and 0<=k<len(sources) for k in i['sources']),'缺少对应消息')
    all_codes=list(dict.fromkeys(c for i in ideas for c in i['codes']))
    names=sector_flow._reference_quotes(all_codes) if all_codes else {}
    for i in ideas:
        i['stocks']=[]
        for c in i.pop('codes'):
            q=quotes[c]; ref=names.get(c,{})
            require(ref.get('name') and ref['stamp'].date().isoformat()==summary['date'],'股票名称与报价日期未核对')
            low=float(q['day_low'])
            require(math.isfinite(low) and low>0,'无有效盘中低点')
            i['stocks'].append({'code':c,'name':ref['name'],'low':low})
    d.update(published_at=now.isoformat(),covered=summary['covered'])
    directory=DATA/'daily-outlook'
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/(now.strftime('%Y-%m-%d_%H%M%S_%f')+'.json')
    with tempfile.NamedTemporaryFile(dir=directory,mode='w',encoding='utf-8',delete=False) as f:
        try:
            json.dump(d,f,ensure_ascii=False,allow_nan=False); f.flush(); os.fsync(f.fileno())
        except BaseException:
            os.unlink(f.name);raise
    os.replace(f.name,target)
    return {'published':str(target),'candidates':len(ideas)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command',choices=('scan','quotes','publish'));parser.add_argument('args',nargs='*')
    args=parser.parse_args()
    if args.command=='scan':
        result=scan()
    elif args.command=='publish':
        result=publish(json.loads(Path(args.args[0]).read_text(encoding='utf-8')))
    else:
        summary,quotes=market(now_cn());result={c:quotes.get(c) for c in args.args}
        result['date']=summary['date']
    print(json.dumps(result,ensure_ascii=False))
