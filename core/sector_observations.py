"""Incremental, display-only sector observations; the reference rules stay shared."""
from datetime import datetime, timedelta
import base64
import json
import math
import zlib
from time import monotonic

from .provider import CN
from .sector_events import build_observations, session

SOURCE='东方财富行业板块资金流'
LEGACY='sector_intraday_v1'
COMPRESSED='sector_intraday_v2'


def encode_snapshot(snapshot):
    # Lossless: retain the complete source evidence, not only chart fields.
    raw=json.dumps(snapshot,ensure_ascii=False,separators=(',',':')).encode()
    return json.dumps({'codec':'zlib-json-v1','data':base64.b64encode(zlib.compress(raw,3)).decode()},separators=(',',':'))


def decode_snapshot(payload,kind):
    value=json.loads(payload)
    if kind==COMPRESSED:
        if value.get('codec')!='zlib-json-v1':raise ValueError('不支持的板块快照编码')
        value=json.loads(zlib.decompress(base64.b64decode(value['data'])))
    return value


class ObservationAccumulator:
    def __init__(self,day):
        self.day=day
        self.groups={}
        self.ordinal=0
        self.projected=None
        self.projected_at=None
        self.next_future=None
        self.visible_count=0
        self.projection_generation=0
        self.mixed_offsets=False
        self.event_key=None;self.event_result=None;self.event_at=None;self.event_until=None

    def add(self,snapshot):
        if snapshot.get('date')!=self.day or snapshot.get('source')!=SOURCE:return
        for row in snapshot.get('observations',[]):
            try:
                stamp=datetime.fromisoformat(row['source_time'])
                change=float(row['change_percent']);net=float(row['net_yuan'])
                if stamp.tzinfo is None or stamp.astimezone(CN).date().isoformat()!=self.day or not session(stamp) or not math.isfinite(change) or not math.isfinite(net):continue
                code,name=row['code'],row['name'];key=stamp.isoformat()
                if stamp.utcoffset()!=timedelta(hours=8):self.mixed_offsets=True
                group=self.groups.setdefault(code,{})
                if key not in group:
                    group[key]=(stamp,self.ordinal,name,dict(time=key,change=change,net=net))
                    self.ordinal+=1;self.projected=None
            except (KeyError,TypeError,ValueError,OverflowError):continue

    def report(self,now):
        now=now.astimezone(CN);cutoff=now+timedelta(seconds=5)
        if self.projected is None or self.projected_at is None or now<self.projected_at or self.next_future is not None and self.next_future<=cutoff:
            series={};future=[]
            for code,points in self.groups.items():
                valid=[p for p in points.values() if p[0]<=cutoff]
                future.extend(p[0] for p in points.values() if p[0]>cutoff)
                if valid:
                    series[code]=dict(name=min(valid,key=lambda p:p[1])[2],points=sorted((p[3] for p in valid),key=lambda p:p['time']))
            self.projected=series;self.next_future=min(future,default=None);self.projected_at=now;self.visible_count=sum(len(g['points']) for g in series.values());self.projection_generation+=1
        # Re-evaluate freshness/session on EVERY read, even with no new input.
        event_key=(self.projection_generation,now.date(),session(now))
        if self.event_key==event_key and self.event_at<=now<self.event_until:
            return dict(self.event_result,series=self.projected)
        # The reference's latest 8-minute base plus prior <=3-minute confirmation
        # fit within this 12-minute suffix. Fall back for nonchronological feeds.
        tail=[];until=now+timedelta(hours=12)
        for code,group in self.projected.items():
            points=group['points'];end=datetime.fromisoformat(points[-1]['time'])
            if end>now:until=min(until,end)
            elif 0<=(now-end).total_seconds()<=180:until=min(until,end+timedelta(seconds=180,microseconds=1))
            if end.date()!=now.date() or session(end)!=session(now) or session(now) is None or not 0<=(now-end).total_seconds()<=180:continue
            suffix=[]
            for point in reversed(points):
                stamp=datetime.fromisoformat(point['time'])
                if stamp<end-timedelta(minutes=12):break
                suffix.append(point)
            # Mixed UTC offsets can sort differently from chronological time.
            if self.mixed_offsets:suffix=points
            tail.extend(dict(code=code,name=group['name'],source_time=p['time'],change_percent=p['change'],net_yuan=p['net']) for p in suffix)
        result=build_observations([dict(date=self.day,source=SOURCE,observations=tail)],now,self.day)
        self.event_key=event_key;self.event_result={k:v for k,v in result.items() if k!='series'};self.event_at=now;self.event_until=until
        return dict(result,series=self.projected)


class SectorObservationCache:
    """One day per service; load bounded batches and only append new snapshots."""
    def __init__(self,store,code):
        self.store,self.code=store,code
        self.day=None;self.revision=None;self.count=0;self.last=None;self.accumulator=None
        self.loaded_snapshots=0
        self.last_access=None

    def expire_if_idle(self,seconds=300):
        if self.last_access is not None and monotonic()-self.last_access>=seconds:
            self.accumulator=None;self.revision=None;self.last=None;self.count=0;self.last_access=None

    def result(self,now):
        result=self.accumulator.report(now)
        return dict(result,series_revision='|'.join(map(str,(self.day,*self.revision,self.accumulator.visible_count))))

    def read(self,day,now):
        self.expire_if_idle();self.last_access=monotonic()
        revision=tuple(self.store.cache_revision(self.code,k) for k in (LEGACY,COMPRESSED))
        if self.day==day and self.revision==revision and self.accumulator is not None:
            return self.result(now)
        where='code=? AND kind IN (?,?) AND day>=? AND day<?'
        args=(self.code,LEGACY,COMPRESSED,day+'T00',day+'T24')
        count=self.store.query('SELECT count(*) AS n FROM cache WHERE '+where,args)[0]['n']
        append=(self.day==day and self.revision is not None and self.accumulator is not None and
                sum(revision)-sum(self.revision)==count-self.count and count>self.count)
        if append:
            added=self.store.query('SELECT count(*) AS n FROM cache WHERE '+where+' AND (day,kind)>(?,?)',(*args,*self.last))[0]['n']
            append=added==count-self.count
        if not append:
            self.accumulator=ObservationAccumulator(day);self.last=None;self.count=0;self.day=day
        while True:
            after=' AND (day,kind)>(?,?)' if self.last else ''
            rows=self.store.query('SELECT day,kind,payload FROM cache WHERE '+where+after+' ORDER BY day,kind LIMIT 16',(*args,*self.last) if self.last else args)
            if not rows:break
            for row in rows:
                self.accumulator.add(decode_snapshot(row['payload'],row['kind']))
                self.last=(row['day'],row['kind']);self.loaded_snapshots+=1
        self.count=count;self.revision=revision
        return self.result(now)
