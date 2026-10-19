"""Desktop-owned process, JSON-lines IPC on stdin/stdout; no listening network port."""
import concurrent.futures,json,os,sys,threading,time
from datetime import date,timedelta,datetime
from pathlib import Path
from .provider import Tencent,symbol,now_cn,CN
from .rules import Session
from .store import Store
from . import notify
from .validated_engine import evaluate, MINUTES
from .sources import SOURCES,daily_view,provider_name
from .history import view as history_view,bounds
from .daily_cache import DailyCache
from .minute_cache import MinuteCache
from .archive import Archive

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
SEEDS=[('sh603002','宏昌电子'),('sh688680','海优新材'),('sh600392','盛和资源'),('sh603366','日出东方'),
       ('sh601929','吉视传媒'),('sh605358','立昂微'),('sh600560','金自天正'),('sh600580','卧龙电驱'),
       ('sz300672','国科微'),('sh603938','三孚股份'),('sz000815','美利云'),('sz000981','山子高科')]

def trading(now):
    t=now.strftime('%H:%M:%S')
    return now.weekday()<5 and ('09:30:00'<=t<='11:31:00' or '13:00:00'<=t<='15:00:00')

def observed_elapsed(start,end):
    """The scheduled lunch break is not a data outage."""
    seconds=(end-start).total_seconds()
    if start.date()==end.date():
        lunch_start=start.replace(hour=11,minute=30,second=0,microsecond=0)
        lunch_end=start.replace(hour=13,minute=0,second=0,microsecond=0)
        seconds-=max(0,(min(end,lunch_end)-max(start,lunch_start)).total_seconds())
    return seconds

class App:
    def __init__(self,data_dir,start_worker=True):
        self.dir=Path(data_dir); self.store=Store(self.dir/'monitor.sqlite3')
        self.provider=Tencent(); self.lock=threading.RLock(); self.stop=threading.Event()
        self.health={}; self.sessions={}; self.quotes={}; self.last_poll=None; self.jobs={}
        self.epochs={}; self.daily_checked={}; self.cache_health={}; self.market_checked=None
        if not self.store.config().get('initialized'):
            for code,name in SEEDS:
                self.store.execute('INSERT OR IGNORE INTO watch(code,name) VALUES(?,?)',(code,name))
                self.store.remember(code,name)
                p=ROOT/'fixtures'/f'{code}-2026-10-16-tencent.json'
                if p.exists():
                    d=json.loads(p.read_text()); self.store.cache(code,'minute',d['trading_date'],d)
                p=ROOT/'fixtures'/f'{code}-daily.json'
                if p.exists():
                    raw=json.loads(p.read_text())['data'][code]
                    for r in raw.get('day',[]): self.store.cache(code,'daily',r[0],dict(date=r[0],open=r[1],close=r[2],high=r[3],low=r[4],volume=r[5],source='tencent',adjustment='none'))
            self.store.setconfig('initialized',True)
            self.store.setconfig('monitor',True); self.store.setconfig('phone_enabled',False)
        self.daily_cache=DailyCache(self)
        self.minute_cache=MinuteCache(self)
        self.archive=Archive(self)
        if start_worker:
            threading.Thread(target=self.loop,daemon=True).start()
            threading.Thread(target=self.delivery_loop,daemon=True).start()
            threading.Thread(target=self.daily_loop,daemon=True).start()

    def cache_minutes(self,code,group):
        old=self.store.getcache(code,'minute',group['date'])
        data=dict(group)
        if old:
            prior=old[0]['data']
            for k in ('symbol','limit_up','day_high','trading_date','time_label_semantics','session_closed'):
                if k in prior: data[k]=prior[k]
        quote=self.quotes.get(code)
        if quote and quote.get('date')==group['date']:
            data.update(symbol=code[2:],trading_date=group['date'],limit_up=quote['limit_up'],
                limit_basis='腾讯当日涨停价字段',limit_reference_time=quote['timestamp'],
                time_label_semantics='unverified',session_closed=group['date']<now_cn().date().isoformat() or now_cn().strftime('%H:%M')>='15:00')
            if quote.get('high'):data['day_high']=quote['high']
        self.store.cache(code,'minute',group['date'],data)

    def ingest(self,code,quote,groups,now):
        today=now.date().isoformat()
        self.quotes[code]=quote
        stamp=datetime.fromisoformat(quote['timestamp'])
        age=observed_elapsed(stamp,now)
        if quote['date']!=today or not 0<=age<=30:
            self.health[code]='行情过期／时间异常，暂停实时判断'
            self.sessions.pop(code,None)
            for g in groups: self.cache_minutes(code,g)
            return
        group=next((g for g in groups if g['date']==today),None)
        if not group:
            self.health[code]='缺少当日分钟数据'; self.sessions.pop(code,None); return
        bars=[b for b in group['bars'] if b['time'] in MINUTES and b.get('complete') is True
              and (now-datetime.fromisoformat(today+'T'+b['time']+':00').replace(tzinfo=CN)).total_seconds()>=3]
        session=Session(code[2:],today,quote['limit_up'])
        for b in bars: session.bar(b)
        for g in groups: self.cache_minutes(code,g)
        previous=self.sessions.get(code)
        gap_seconds=observed_elapsed(previous['at'],now) if previous else None
        last_end=datetime.fromisoformat(today+'T'+bars[-1]['time']+':00').replace(tzinfo=CN) if bars else None
        minutes_fresh=last_end is not None and 0<=observed_elapsed(last_end,now)<=93
        signature=[(b['time'],b['volume'],b['close'],b.get('high'),b.get('low')) for b in bars]
        revised=bool(previous and previous['day']==today and signature[:len(previous['bars'])]!=previous['bars'])
        continuous=bool(previous and previous['day']==today and 0<=gap_seconds<=45
                        and previous['healthy'] and minutes_fresh and not revised)
        known=previous['keys'] if previous and previous['day']==today else set()
        known=known | {r['key'] for r in self.store.query('SELECT key FROM events WHERE key LIKE ?',
            (today+'|'+code[2:]+'|%',))}
        for candidate in session.candidates:
            if candidate['key'] in known: candidate['state']='MATCHED_ONCE'
        suppressed=set(previous.get('suppressed_wait',())) if previous and previous['day']==today else set()
        if not continuous:
            suppressed.update(c['key'] for c in session.candidates if c['state']=='WAIT_FIRST_REOPEN')
        for e in session.events:
            if e['key'] not in known:
                event_age=(now-datetime.fromisoformat(today+'T'+e['event_label']+':00').replace(tzinfo=CN)).total_seconds()
                e['observed_at']=now.isoformat()
                e['source']=group.get('source','tencent')
                self.store.event(e,'live' if continuous and e['key'] not in suppressed and 0<=event_age<=45 else 'recovered')
        if continuous and stamp>previous['quote_at'] and now.strftime('%H:%M')<'14:57':
            for e in session.tick(stamp.strftime('%H:%M:%S'),quote['price']):
                if e['key'] not in known:
                    e['observed_at']=now.isoformat()
                    e['source']=group.get('source','tencent')
                    self.store.event(e,'recovered' if e['key'] in suppressed else 'live')
        keys=known | {e['key'] for e in session.events}
        if now.strftime('%H:%M')>='14:57': session.expire()
        self.sessions[code]=dict(day=today,at=now,quote_at=stamp,keys=keys,suppressed_wait=suppressed,bars=signature,
            healthy=minutes_fresh and not session.gap,candidates=session.candidates)
        self.health[code]=('分钟数据延迟，暂停实时判断' if not minutes_fresh else '数据缺口，规则已阻断' if session.gap
            else '分钟数据修订，已恢复历史状态' if revised else '实时采样监控' if continuous else '已恢复历史状态；开始实时采样')
        self.store.cache(code,'state',today,dict(candidates=session.candidates,observed_at=now.isoformat()))

    def poll_one(self,code):
        if self.stop.is_set(): return
        epoch=self.epochs.get(code,0)
        try:
            quote=self.provider.quote(code); groups=self.provider.minutes(code)
            self.minute_cache.note(code)
            now=now_cn()
            with self.lock:
                rows=self.store.query('SELECT enabled FROM watch WHERE code=?',(code,))
                if self.stop.is_set() or not rows or self.epochs.get(code,0)!=epoch: return
                self.quotes[code]=quote
                self.daily_cache.observe(code,quote)
                if quote.get('name'):self.store.remember(code,quote['name'])
                if rows[0]['enabled'] and self.store.config().get('monitor') and trading(now):
                    self.ingest(code,quote,groups,now)
                else:
                    for g in groups: self.cache_minutes(code,g)
                    if not trading(now): self.health[code]='非交易时段 · 已刷新缓存'

        except Exception as e:
            with self.lock:
                if self.epochs.get(code,0)==epoch:
                    self.health[code]='获取失败：'+type(e).__name__; self.sessions.pop(code,None)

    def loop(self):
        initial=True
        while not self.stop.is_set():
            now=now_cn()
            if initial or (self.store.config().get('monitor') and trading(now)):
                codes=[r['code'] for r in self.store.query('SELECT code FROM watch'+('' if initial else ' WHERE enabled=1'))]
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(self.poll_one,codes))
                self.last_poll=now_cn().isoformat(); initial=False
            self.stop.wait(8)

    def daily_loop(self):
        # Keep slow historical IO off the live quote/minute polling path.
        while not self.stop.is_set():
            for row in self.store.query('SELECT code FROM watch'):
                if self.stop.is_set():return
                code=row['code']
                try:
                    self.daily_cache.update(code)
                    self.archive.update(code)
                    self.cache_health.pop(code,None)
                except Exception as e:self.cache_health[code]='日线更新失败，已保留缓存并延后重试：'+type(e).__name__
            self.stop.wait(60)

    def start_job(self,fn):
        import uuid
        job=uuid.uuid4().hex
        self.jobs[job]={'status':'running'}
        def work():
            try: self.jobs[job]={'status':'done','result':fn()}
            except Exception as e: self.jobs[job]={'status':'failed','error':str(e) if isinstance(e,ValueError) else '操作失败：'+type(e).__name__}
        threading.Thread(target=work,daemon=True).start()
        return {'job':job}

    def delivery_loop(self):
        while not self.stop.is_set():
            try: notify.drain(self.store,self.store.config().get('phone_enabled',False))
            except Exception: pass
            self.stop.wait(5)

    def event_rows(self,code=None,start=None,end=None,limit=300,offset=0):
        conditions=[];params=[]
        if code:conditions.append("json_extract(e.payload,'$.symbol')=?");params.append(code[2:])
        if start:conditions.append("json_extract(e.payload,'$.trading_date')>=?");params.append(start)
        if end:conditions.append("json_extract(e.payload,'$.trading_date')<=?");params.append(end)
        sql="SELECT e.*,d.status AS delivery,l.status AS local_delivery,l.detail AS local_detail FROM events e LEFT JOIN delivery d USING(key) LEFT JOIN local_delivery l USING(key)"
        if conditions:sql+=' WHERE '+' AND '.join(conditions)
        sql+=' ORDER BY e.rowid DESC'
        if limit is not None:sql+=' LIMIT ? OFFSET ?';params.extend([limit,offset])
        return [dict(self.store.enrich_event(json.loads(e['payload'])),mode=e['mode'],delivery=e['delivery'],
            local_delivery=e['local_delivery'],local_detail=e['local_detail']) for e in self.store.query(sql,params)]

    def source_info(self,code):
        minute=self.store.getcache(code,'minute');daily=self.store.getcache(code,'daily')
        return dict(selected=self.store.config().get('provider','tencent'),providers=SOURCES,
            quote_time=self.quotes.get(code,{}).get('timestamp'),
            minute_coverage=[minute[0]['day'],minute[-1]['day']] if minute else [],
            daily_coverage=[daily[0]['day'],daily[-1]['day']] if daily else [],
            cache_time=minute[-1]['data'].get('cached_at') if minute else None,
            quote_url='https://qt.gtimg.cn/q='+code,
            minute_url='https://web.ifzq.gtimg.cn/appstock/app/day/query?code='+code,
            history_minute_url='https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData?symbol='+code+'&scale=1&ma=no&datalen=1970',
            daily_url='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param='+code+',day,开始日期,结束日期,2000,')

    def call(self,method,args):
        if method=='snapshot':
            with self.lock:
                watch=self.store.query('SELECT * FROM watch ORDER BY rowid')
                for w in watch:
                    w.update(quote=self.quotes.get(w['code']),health=('已暂停' if not w['enabled'] or not self.store.config().get('monitor') else self.health.get(w['code'],'等待行情刷新')),cache_health=self.cache_health.get(w['code']),
                        candidates=self.sessions.get(w['code'],{}).get('candidates',[]))
                events=self.event_rows()
                return dict(watch=watch,events=events,instruments={r['code']:r['name'] for r in self.store.query('SELECT * FROM instruments')},
                    unread_messages=self.store.query('SELECT count(*) AS n FROM messages WHERE read_at IS NULL')[0]['n'],
                    config=self.store.config(),now=now_cn().isoformat(),market_open=trading(now_cn()),
                    last_poll=self.last_poll,data_dir=str(self.dir),version='0.4.3',rule='running_max_inclusive_v1')
        if method=='add_job': return self.start_job(lambda:self.call('add',args))
        if method=='refresh':
            code=symbol(args['code'])
            return self.start_job(lambda:self.poll_one(code))
        if method=='add':
            code=symbol(args['code']); quote=self.provider.quote(code)
            with self.lock:
                added=self.store.execute('INSERT OR IGNORE INTO watch(code,name) VALUES(?,?)',(code,quote['name']))
                self.quotes[code]=quote
                self.daily_cache.observe(code,quote)
                self.store.remember(code,quote['name'])
                if added: self.epochs[code]=self.epochs.get(code,0)+1
            # The stock is added successfully even when optional historical preloading fails.
            try:
                for g in self.provider.minutes(code): self.cache_minutes(code,g)
                self.daily_cache.update(code)
                self.cache_health.pop(code,None)
            except Exception as e: self.cache_health[code]='已添加；历史数据待补取：'+type(e).__name__
            return dict(quote,cache_warning=self.cache_health.get(code))
        if method in ('remove','toggle'):
            code=symbol(args['code'])
            with self.lock:
                if method=='remove':
                    self.store.execute('DELETE FROM watch WHERE code=?',(code,));self.quotes.pop(code,None)
                else:
                    if not isinstance(args['enabled'],bool): raise ValueError('监控状态必须为开或关')
                    self.store.execute('UPDATE watch SET enabled=? WHERE code=?',(int(args['enabled']),code))
                self.sessions.pop(code,None); self.epochs[code]=self.epochs.get(code,0)+1
            return True
        if method=='config':
            for k,v in args.items():
                if k=='provider':
                    if v not in [p['id'] for p in SOURCES if p['available']]:raise ValueError('该数据来源尚未接入或验证，不能切换')
                    self.store.setconfig(k,v)
                if k in ('monitor','phone_enabled','sound') and isinstance(v,bool):
                    old=self.store.config().get(k)
                    if k=='monitor' and old!=v:
                        with self.lock:
                            self.sessions.clear()
                            for row in self.store.query('SELECT code FROM watch'): self.epochs[row['code']]=self.epochs.get(row['code'],0)+1
                    if k=='phone_enabled' and old!=v:
                        self.store.execute("UPDATE delivery SET status='skipped' WHERE status IN ('pending','retry')")
                    self.store.setconfig(k,v)
            return self.store.config()
        if method=='secret':
            import re
            if not re.fullmatch(r'[A-Za-z0-9_-]{8,200}',args['key']): raise ValueError('请填写设备密钥，不是完整网址')
            notify.key(args['key']); return {'saved':True}
        if method=='test_push':
            title='观量 · 手机推送测试（非卖点信号）';body='这是一条通道测试，不是卖点信号。请确认 iPhone 锁屏是否收到。'
            ident=self.store.message('push_test',title,body,payload={'status':'pending'})
            try:
                result=notify.bark(title,body)
                self.store.execute('UPDATE messages SET payload=? WHERE id=?',(json.dumps({'status':'accepted'}),ident))
                return result
            except Exception:
                self.store.execute('UPDATE messages SET payload=? WHERE id=?',(json.dumps({'status':'failed','detail':'推送未成功，请检查密钥、网络和服务状态'}),ident))
                raise

        if method=='chart':
            code=symbol(args['code']); kind=args.get('kind','minute')
            if kind not in ('minute','daily'): raise ValueError('无效数据类型')
            rows=self.store.getcache(code,kind,args.get('day') if kind=='minute' else None)
            if kind=='daily':rows=[dict(day=r['day'],data=daily_view(code,r['data'])) for r in self.daily_cache.rows(code)]
            return rows
        if method=='download': return self.start_job(lambda:self.call('download_work',args))
        if method=='job': return self.jobs.get(args['job'],{'status':'failed','error':'下载任务不存在，请重新发起'})
        if method=='download_work':
            code=symbol(args['code']); start=date.fromisoformat(args['start']); end=date.fromisoformat(args['end'])
            if start>end: raise ValueError('开始日期不能晚于结束日期')
            kind=args['kind']; days=[]
            if kind=='daily':
                days=self.daily_cache.fetch(code,start,end)
            elif kind=='minute':
                if start==end:
                    result=self.minute_cache.ensure(code,start.isoformat())
                    days=[start.isoformat()] if self.store.getcache(code,'minute',start.isoformat()) else []
                    return dict(downloaded_days=days,requested=[start.isoformat(),end.isoformat()],message=result.get('message','已使用本地分时缓存'))
                for g in self.provider.minutes(code):
                    if start.isoformat()<=g['date']<=end.isoformat(): self.cache_minutes(code,g); days.append(g['date'])
            else: raise ValueError('无效数据类型')
            return dict(downloaded_days=sorted(set(days)),requested=[start.isoformat(),end.isoformat()],
                message='已缓存来源实际返回的数据；未返回日期不代表停牌或休市。分钟接口通常仅提供近期数日，无法补齐任意历史范围。')
        if method=='replay':
            code=symbol(args['code']); rows=self.store.getcache(code,'minute',args['day'])
            if not rows: raise ValueError('没有该日缓存')
            data=rows[0]['data']
            if data.get('rule_compatible') is False:raise ValueError('新浪历史补充口径未认证，不作为腾讯规则触发回放')
            if not data.get('limit_up'): raise ValueError('该缓存缺少已验证历史涨停价，不能认证回放；请使用随附核对样本')
            report=evaluate(data)
            for e in report['matches']:
                e=dict(e,symbol=code[2:],trading_date=data['trading_date'],reference_price=e['historical_close'])
                self.store.event(e,'replay')
            return report
        if method=='history': return history_view(self,args)
        if method=='archive_status':return self.archive.status(symbol(args['code']))
        if method=='archive_fill':return self.start_job(lambda:self.archive.update(symbol(args['code'])))
        if method=='minute_ensure':
            code=symbol(args['code']);day=date.fromisoformat(args['day']).isoformat()
            return self.start_job(lambda:self.minute_cache.ensure(code,day))
        if method=='daily_load':
            code=symbol(args['code']);start,end=bounds(args)
            return self.start_job(lambda:self.daily_cache.fetch(code,date.fromisoformat(start),date.fromisoformat(end)))
        if method=='history_load':
            code=symbol(args['code']);start,end=bounds(args)
            def work():
                daily=self.call('download_work',dict(code=code,start=start,end=end,kind='daily'))
                minute=self.call('download_work',dict(code=code,start=start,end=end,kind='minute'))
                return dict(daily=daily,minute=minute)
            return self.start_job(work)
        if method=='history_reference':
            from .validated_engine import number
            code=symbol(args['code']);day=date.fromisoformat(args['day']).isoformat();limit=number(args['limit_up'])
            cached=self.store.getcache(code,'minute',day);daily=self.store.getcache(code,'daily',day)
            if not cached or not daily:raise ValueError('先取得该日分时和日线，再补充涨停价')
            if limit<=0 or limit<number(daily[0]['data']['high']):raise ValueError('涨停价必须为正数，且不低于当日最高价')
            data=cached[0]['data'];data.update(symbol=code[2:],trading_date=day,limit_up=str(limit),day_high=daily[0]['data']['high'],
                limit_basis='用户确认的历史涨停价',time_label_semantics='unverified',session_closed=day<now_cn().date().isoformat())
            self.store.cache(code,'minute',day,data)
            return True
        if method=='messages':
            conditions=[];params=[]
            if args.get('unread'):conditions.append('m.read_at IS NULL')
            if args.get('category'):conditions.append('m.category=?');params.append(args['category'])
            where=' WHERE '+' AND '.join(conditions) if conditions else ''
            total=self.store.query('SELECT count(*) AS n FROM messages m'+where,params)[0]['n']
            limit=min(100,max(1,int(args.get('limit',30))));offset=max(0,int(args.get('offset',0)))
            rows=self.store.query('SELECT m.*,l.status AS local_delivery,l.detail AS local_detail,d.status AS delivery FROM messages m LEFT JOIN local_delivery l ON l.key=m.event_key LEFT JOIN delivery d ON d.key=m.event_key'+where+' ORDER BY m.created_at DESC,m.rowid DESC LIMIT ? OFFSET ?',params+[limit,offset])
            return dict(items=[dict(r,payload=json.loads(r['payload'])) for r in rows],total=total)
        if method=='message_read':
            if args.get('all'):self.store.execute('UPDATE messages SET read_at=? WHERE read_at IS NULL',(now_cn().isoformat(),))
            else:self.store.execute('UPDATE messages SET read_at=? WHERE id=?',(now_cn().isoformat(),args['id']))
            return True
        if method=='sources': return self.source_info(symbol(args['code']))
        if method=='events':
            start,end=bounds(args)
            items=[e for e in self.event_rows(code=symbol(args['code']) if args.get('code') else None,start=start,end=end,limit=None) if e['mode']!='test']
            offset=max(0,int(args.get('offset',0)));limit=min(100,max(1,int(args.get('limit',30))))
            return dict(items=items[offset:offset+limit],total=len(items))
        if method=='test_local':
            import uuid
            delay=args.get('delay',0)
            if delay not in (0,10): raise ValueError('通知测试只支持立即或延迟10秒')
            now=now_cn(); key='test|'+uuid.uuid4().hex
            event=dict(key=key,symbol='TEST',trading_date=now.date().isoformat(),candidate_time='—',
                confirmation_label='—',event_label=now.strftime('%H:%M:%S'),volumes=[],kind='NOTIFICATION_TEST',
                observed_at=now.isoformat(),reference_price=None,manual_sell_only=True)
            self.store.event(event,'test',delay=delay)
            return {'key':key,'message':'测试已排队；'+('请关闭窗口，10秒后检查后台通知' if delay else '请检查本机通知')+'。这不是卖点信号。'}
        if method=='local_pending':
            pending=[]
            for row in self.store.query("SELECT l.*,e.payload FROM local_delivery l JOIN events e USING(key) WHERE status='pending' AND next_try<=?",(time.time(),)):
                e=json.loads(row['payload'])
                observed=datetime.fromisoformat(e.get('observed_at',e['trading_date']+'T'+e['event_label'])).replace(tzinfo=CN)
                age=(now_cn()-observed).total_seconds()
                if not 0<=age<=180:
                    self.store.execute("UPDATE local_delivery SET status='expired' WHERE key=? AND status='pending'",(row['key'],));continue
                pending.append(e)
            return {'events':pending,'sound':self.store.config().get('sound',True)}
        if method=='local_claim':
            return bool(self.store.execute("UPDATE local_delivery SET status='sending',attempts=attempts+1 WHERE key=? AND status='pending'",(args['key'],)))
        if method=='local_finish':
            status=args['status']
            if status not in ('accepted','failed'):raise ValueError('非法通知结果')
            self.store.execute("UPDATE local_delivery SET status=?,detail=? WHERE key=? AND status='sending'",(status,args.get('detail',''),args['key']))
            return True
        if method=='retry_push':
            self.store.execute("UPDATE delivery SET status='pending',attempts=0,next_try=0 WHERE key=? AND status='failed'",(args['key'],))
            return True
        if method=='backup':
            import sqlite3
            target=self.dir/('backup-'+now_cn().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
            with self.store.lock:
                conn=sqlite3.connect(target); self.store.db.backup(conn); conn.close()
            return {'path':str(target)}
        raise ValueError('不支持的操作')

def main():
    data_dir=os.environ.get('STOCK_MONITOR_DATA',str(Path.home()/'.stock-monitor'))
    app=App(data_dir)
    try:
        for line in sys.stdin:
            try:
                request=json.loads(line); result=app.call(request['method'],request.get('args',{}))
                print(json.dumps({'ok':True,'data':result},ensure_ascii=False),flush=True)
            except Exception as e:
                # Never return credential values, endpoint URLs or raw transport exceptions.
                message=str(e) if isinstance(e,ValueError) else '操作失败（'+type(e).__name__+'），请检查网络或系统配置'
                print(json.dumps({'ok':False,'error':message},ensure_ascii=False),flush=True)
    finally: app.stop.set()

if __name__=='__main__': main()
