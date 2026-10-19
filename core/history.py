"""Read-only historical views; history never enters the live notification outbox."""
from datetime import date
from decimal import Decimal
from .provider import symbol,now_cn
from .validated_engine import evaluate,MINUTES,number
from .rules import Session
from .sources import daily_view

def bounds(args):
    start=date.fromisoformat(args['start']);end=date.fromisoformat(args['end'])
    if start>end:raise ValueError('开始日期不能晚于结束日期')
    return start.isoformat(),end.isoformat()

def analyze(code,day,data,daily=None):
    result=dict(date=day,status='missing_minutes',message='无分钟缓存；不能据此认定没有触发',matches=[],candidates=[])
    if not data:return result
    if data.get('rule_compatible') is False:return dict(result,status='source_unverified',message='新浪历史补充分时可查看；开盘首分钟含集合竞价、分钟边界与腾讯有差异，规则回放暂未认证，不产生确定触发')
    if not data.get('limit_up'):
        return dict(result,status='missing_limit',message='已有分时；缺少当日可靠涨停价，触发计算待补充，不能当作零触发')
    bars=data.get('bars',[])
    chosen=[b for b in bars if b['time'] in MINUTES and b.get('complete') is True]
    if [b['time'] for b in chosen]!=MINUTES:
        return dict(result,status='incomplete',message='当日规则分钟尚未结束或存在缺口；已记录事件仍可查看')
    prepared=dict(data,symbol=code[2:],trading_date=day,time_label_semantics=data.get('time_label_semantics','unverified'),
                  session_closed=True,volume_unit=data.get('volume_unit','shares'),source=data.get('source') or 'tencent')
    high=number(daily['high']) if daily else number(data['day_high']) if data.get('day_high') is not None else None
    limit=number(data['limit_up'])
    if high is not None and high>limit:raise ValueError('历史最高价高于涨停参考价，拒绝回放')
    if high is not None and high<limit:
        report=evaluate(dict(prepared,day_high=str(high)))
        return dict(result,status='ready',message='完整分钟量回放；本日未触及涨停',matches=report['matches'],candidates=report['candidates'])
    session=Session(code[2:],day,limit)
    for b in chosen:session.bar(b)
    session.expire()
    return dict(result,status='close_only',message='按已知分钟收盘价回放；分钟高低价缺失，无法排除瞬时开板后回封',matches=session.events,candidates=session.candidates)

def view(app,args):
    code=symbol(args['code']);start,end=bounds(args)
    daily=[daily_view(code,r['data']) for r in app.daily_cache.rows(code) if start<=r['day']<=end]
    minute={r['day']:r['data'] for r in app.store.getcache(code,'minute') if start<=r['day']<=end}
    recorded=app.event_rows(code=code,start=start,end=end,limit=None)
    days=sorted(set(r['date'] for r in daily)|set(minute)|{e['trading_date'] for e in recorded})
    lookup={r['date']:r for r in daily};analyses=[];events={e['key']:e for e in recorded}
    for day in days:
        try:r=analyze(code,day,minute.get(day),lookup.get(day))
        except ValueError as e:r=dict(date=day,status='invalid',message=str(e),matches=[],candidates=[])
        for event in r['matches']:
            enriched=app.store.enrich_event(dict(event,symbol=code[2:],trading_date=day,
                reference_price=event.get('reference_price',event.get('historical_close')),source=minute[day].get('source','tencent')))
            events.setdefault(event['key'],dict(enriched,mode='history',local_delivery=None,delivery=None))
        r['recorded_count']=sum(e['trading_date']==day for e in recorded)
        r['signal_count']=sum(e['trading_date']==day for e in events.values())
        r['has_minutes']=day in minute
        r['limit_up']=minute.get(day,{}).get('limit_up')
        r['limit_basis']=minute.get(day,{}).get('limit_basis','验证样本历史参考价' if r['limit_up'] else '')
        analyses.append(r)
    return dict(code=code,start=start,end=end,daily=daily,days=analyses,events=list(events.values()),
        minute_days=sorted(minute),source=app.source_info(code))
