"""Display-only pool summaries; bounded minute IO and unchanged-data reuse."""
import hashlib,json,threading,time
from concurrent.futures import ThreadPoolExecutor
from .provider import now_cn
from .turning_final import signals as shapes,ZHANGLE,STABLE
from .turning_final_v3 import signals as shapes_v3
from .turning_q1 import signals as quality
from .turning_combined import filter_spacing


def bottom_point(data,mode):
    bars=[b for b in data.get('bars',[]) if b.get('time')=='09:30' or '09:31'<=str(b.get('time',''))<='11:30' or '13:01'<=str(b.get('time',''))<='15:00']
    main=shapes_v3(bars) if mode=='v3' else shapes(bars,STABLE if mode=='stable' else ZHANGLE)
    points={p['time']:dict(p,shape=True) for p in main if p['kind']=='bottom'}
    for point in quality(bars):
        if point['kind']=='bottom':points[point['time']]=dict(points.get(point['time'],{}),**point)
    rows=sorted(points.values(),key=lambda p:p['time']);main=[p for p in rows if p.get('shape')][:3]
    kept=main+[p for p in rows if not p.get('shape')][:max(0,3-len(main))]
    unique={}
    for point in kept:unique.setdefault(int(point['price']*100+.5),point)
    spaced=filter_spacing(unique.values())
    return spaced[-1] if spaced else None


class PoolSignals:
    def __init__(self,app):
        self.app=app;self.lock=threading.RLock();self.running=False;self.day=''
        self.memo={};self.summaries={};self.attempts={};self.idle_attempts=set();self.last_check=0;self.last_seen=0

    def view(self,mode='zhangle'):
        from .pool import _trading_day
        mode=mode if mode in ('zhangle','stable','v3') else 'zhangle';day=_trading_day(now_cn());now=time.monotonic()
        with self.lock:
            self.last_seen=now
            if day!=self.day:
                self.day=day;self.memo.clear();self.summaries.clear();self.attempts.clear();self.idle_attempts.clear()
            if not self.running and now-self.last_check>=30:
                self.running=True;self.last_check=now
                threading.Thread(target=self._scan,args=(day,mode),daemon=True).start()
            return dict(day=day,signals=dict(self.summaries.get(mode,{})),running=self.running)

    def _remember(self,code,day,mode,raw):
        data=json.loads(raw);fingerprint=hashlib.sha256(json.dumps(data.get('bars',[]),separators=(',',':')).encode()).digest();key=(code,mode)
        with self.lock:
            if day!=self.day or self.memo.get(key)==fingerprint:return
        point=bottom_point(data,mode)
        with self.lock:
            if day!=self.day:return
            self.memo[key]=fingerprint;result=self.summaries.setdefault(mode,{})
            if point:result[code]=dict(day=day,time=point['time'],price=point['price'])
            else:result.pop(code,None)

    def _scan(self,day,mode):
        try:
            rows=self.app.store.query("SELECT c.code,c.payload FROM cache c JOIN pool p ON p.code=c.code WHERE p.archived=0 AND c.kind='minute' AND c.day=?",(day,))
            cached={r['code']:r['payload'] for r in rows}
            for code,raw in cached.items():self._remember(code,day,mode,raw)
            now=now_cn();clock=now.strftime('%H:%M:%S')
            live=day==now.date().isoformat() and ('09:20:00'<=clock<'11:30:00' or '13:00:00'<=clock<'15:00:00')
            codes=[r['code'] for r in self.app.store.query('SELECT code FROM pool WHERE archived=0')]
            def update(code):
                if self.app.stop.is_set() or day!=self.day or time.monotonic()-self.last_seen>45:return
                raw=cached.get(code);data=json.loads(raw) if raw else None
                if live:
                    fresh=data and data.get('cached_at','')>=now.replace(second=0,microsecond=0).isoformat()
                    if fresh or time.monotonic()-self.attempts.get(code,-1e9)<60:return
                elif (data and (day<now.date().isoformat() or clock>='15:00:00') and any(b.get('time')=='15:00' for b in data.get('bars',[]))) or (data and clock<'15:00:00') or code in self.idle_attempts:return
                self.attempts[code]=time.monotonic()
                if not live:self.idle_attempts.add(code)
                try:
                    self.app.minute_cache.ensure(code,day,refresh=True,on_demand=True)
                    result=self.app.store.getcache(code,'minute',day)
                    if result:self._remember(code,day,mode,json.dumps(result[0]['data'],ensure_ascii=False))
                except (ValueError,OSError):pass  # Keep any prior valid summary; the chart exposes retry details.
            with ThreadPoolExecutor(max_workers=2) as worker:list(worker.map(update,codes))
        finally:
            with self.lock:self.running=False
