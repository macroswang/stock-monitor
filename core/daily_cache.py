"""Persistent daily request coverage, paced requests and failure cooldowns."""
import threading,time
from datetime import date,timedelta
from decimal import Decimal,InvalidOperation
from .provider import now_cn

class DailyCache:
    def observe(self,code,quote):
        """Reuse quote IO for a provisional candle; never replace finalized daily data."""
        now=now_cn();day=quote.get('date','')
        if day!=now.date().isoformat() or now.weekday()>4 or quote.get('timestamp','')<day+'T09:30':return
        try:
            values={k:Decimal(str(quote[k])) for k in ('open','price','high','low','volume')}
            if not all(v.is_finite() for v in values.values()):return
            if min(values[k] for k in ('open','price','high','low'))<=0 or values['volume']<0:return
            if not values['low']<=min(values['open'],values['price'])<=max(values['open'],values['price'])<=values['high']:return
        except (KeyError,InvalidOperation,ValueError):return
        self.app.store.cache(code,'daily_live',day,dict(date=day,open=str(values['open']),close=str(values['price']),
            high=str(values['high']),low=str(values['low']),volume=str(values['volume']),volume_unit='shares',
            source='tencent',adjustment='none',provisional=True,quote_time=quote['timestamp']))

    def rows(self,code):
        rows={r['day']:r for r in self.app.store.getcache(code,'daily')}
        for live in self.app.store.getcache(code,'daily_live'):
            final=rows.get(live['day'])
            if final is None or final['data'].get('cached_at','')<live['day']+'T15:15':rows[live['day']]=live
        return [rows[day] for day in sorted(rows)]

    def __init__(self,app):
        self.app=app;self.lock=threading.RLock();self.last_request=0
        app.store.execute('CREATE TABLE IF NOT EXISTS daily_requests(code TEXT,start TEXT,end TEXT,attempt REAL,ok INTEGER,PRIMARY KEY(code,start,end))')

    def completed_day(self):
        now=now_cn();day=now.date()
        if now.strftime('%H:%M')<'15:15':day-=timedelta(days=1)
        while day.weekday()>4:day-=timedelta(days=1)
        return day

    def update(self,code):
        end=self.completed_day();rows=self.app.store.getcache(code,'daily')
        if rows and rows[-1]['day']>end.isoformat():return []
        start=date.fromisoformat(rows[-1]['day'])+timedelta(days=1) if rows else end-timedelta(days=365)
        if rows and rows[-1]['day']==end.isoformat():
            # An old client may have cached an unfinished daily candle intraday.
            stamp=rows[-1]['data'].get('cached_at','')
            if stamp>=end.isoformat()+'T15:15':return []
            start=end
        return self.fetch(code,start,end)

    def fetch(self,code,start,end):
        end=min(end,self.completed_day())
        if start>end:return []
        with self.lock:
            # Subtract previously queried ranges, including successful empty responses.
            # Empty responses are coverage of a request, never proof of a holiday.
            spans=[(start,end)];now=time.time()
            records=self.app.store.query('SELECT * FROM daily_requests WHERE code=?',(code,))
            for r in records:
                recent=r['end']>=(now_cn().date()-timedelta(days=7)).isoformat()
                ttl=(12*3600 if recent else 7*86400) if r['ok'] else 3600
                if now-r['attempt']>=ttl:continue
                a,b=date.fromisoformat(r['start']),date.fromisoformat(r['end']);remaining=[]
                for lo,hi in spans:
                    if b<lo or a>hi:remaining.append((lo,hi));continue
                    if lo<a:remaining.append((lo,a-timedelta(days=1)))
                    if b<hi:remaining.append((b+timedelta(days=1),hi))
                spans=remaining
            downloaded=[]
            for lo,hi in spans:
                while lo<=hi:
                    finish=min(hi,lo+timedelta(days=365))
                    # One request at a time across all stocks; record attempts before IO.
                    delay=1-(time.monotonic()-self.last_request)
                    if delay>0 and self.app.stop.wait(delay):return downloaded
                    if self.app.stop.is_set():return downloaded
                    args=(code,lo.isoformat(),finish.isoformat())
                    self.app.store.execute('INSERT OR REPLACE INTO daily_requests VALUES(?,?,?,?,0)',args+(time.time(),))
                    self.last_request=time.monotonic()
                    rows=self.app.provider.daily(*args)
                    for row in rows:
                        if lo.isoformat()<=row['date']<=finish.isoformat():
                            self.app.store.cache(code,'daily',row['date'],row);downloaded.append(row['date'])
                    self.app.store.execute('UPDATE daily_requests SET ok=1 WHERE code=? AND start=? AND end=?',args)
                    lo=finish+timedelta(days=1)
            return downloaded
