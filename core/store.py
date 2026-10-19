import json, sqlite3, threading, time, uuid
from datetime import datetime, timezone
from .provider import now_cn
from pathlib import Path

class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS watch(code TEXT PRIMARY KEY,name TEXT,enabled INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS instruments(code TEXT PRIMARY KEY,name TEXT);
        CREATE TABLE IF NOT EXISTS cache(code TEXT,kind TEXT,day TEXT,payload TEXT,PRIMARY KEY(code,kind,day));
        CREATE TABLE IF NOT EXISTS events(key TEXT PRIMARY KEY,payload TEXT,mode TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS delivery(key TEXT PRIMARY KEY,status TEXT,attempts INTEGER DEFAULT 0,next_try REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS local_delivery(key TEXT PRIMARY KEY,status TEXT,attempts INTEGER DEFAULT 0,next_try REAL DEFAULT 0,detail TEXT);
        CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,dedupe_key TEXT UNIQUE,category TEXT,title TEXT,body TEXT,event_key TEXT,payload TEXT,created_at TEXT,read_at TEXT);
        CREATE INDEX IF NOT EXISTS messages_created ON messages(created_at DESC);
        PRAGMA user_version=3;''')
        self.db.execute('INSERT OR IGNORE INTO instruments SELECT code,name FROM watch')
        # An interrupted OS submission has an unknown outcome: never automatically duplicate it.
        self.db.execute("UPDATE local_delivery SET status='unknown',detail='上次发送时进程中断，请检查通知中心' WHERE status='sending'")
        self.db.commit()
        # Backfill prior notifications without sending them again.
        for row in self.query("SELECT * FROM events WHERE mode IN ('live','test')"):
            event=self.enrich_event(json.loads(row['payload']))
            stamp=event.get('observed_at') or datetime.fromisoformat(row['created']).replace(tzinfo=timezone.utc).astimezone(now_cn().tzinfo).isoformat()
            self.message('signal' if row['mode']=='live' else 'test',event['notification_title'],event['notification_body'],
                event_key=event['key'],payload=event,created=stamp,dedupe='event|'+event['key'])
    def initialize(self,seeds,rows):
        # One durable transaction: avoid thousands of startup fsyncs on Windows.
        # The initialized flag commits with the data, never ahead of it.
        with self.lock,self.db:
            for code,name in seeds:
                self.db.execute('INSERT OR IGNORE INTO watch(code,name) VALUES(?,?)',(code,name))
                self.db.execute('INSERT OR REPLACE INTO instruments VALUES(?,?)',(code,name))
                self.db.execute('UPDATE watch SET name=? WHERE code=?',(name,code))
            for code,kind,day,payload in rows:
                payload=dict(payload);payload.setdefault('cached_at',now_cn().isoformat())
                self.db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',(code,kind,day,json.dumps(payload,ensure_ascii=False)))
            for key,value in [('initialized',True),('monitor',True),('phone_enabled',False)]:
                self.db.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(key,json.dumps(value)))

    def query(self,sql,args=()):
        with self.lock: return [dict(r) for r in self.db.execute(sql,args).fetchall()]
    def execute(self,sql,args=()):
        with self.lock:
            cur=self.db.execute(sql,args); self.db.commit(); return cur.rowcount
    def cache(self,code,kind,day,payload):
        payload=dict(payload)
        payload.setdefault('cached_at',now_cn().isoformat())
        self.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',(code,kind,day,json.dumps(payload,ensure_ascii=False)))
    def getcache(self,code,kind,day=None):
        rows=self.query('SELECT day,payload FROM cache WHERE code=? AND kind=? '+('AND day=? ' if day else '')+'ORDER BY day',
                        (code,kind,day) if day else (code,kind))
        return [dict(day=r['day'],data=json.loads(r['payload'])) for r in rows]
    def event(self,event,mode,delay=0):
        with self.lock:
            event=self.enrich_event(event)
            cur=self.db.execute('INSERT OR IGNORE INTO events(key,payload,mode) VALUES(?,?,?)',
                (event['key'],json.dumps(event,ensure_ascii=False),mode))
            if cur.rowcount and mode=='live': self.db.execute('INSERT OR IGNORE INTO delivery(key,status) VALUES(?,?)',(event['key'],'pending' if self.config().get('phone_enabled',False) else 'skipped'))
            if cur.rowcount and mode in ('live','test'):
                self.db.execute('INSERT OR IGNORE INTO local_delivery(key,status,next_try) VALUES(?,?,?)',(event['key'],'pending',time.time()+delay))
                self.message('signal' if mode=='live' else 'test',event['notification_title'],event['notification_body'],
                    event_key=event['key'],payload=event,created=event.get('observed_at'),dedupe='event|'+event['key'],commit=False)
            self.db.commit(); return bool(cur.rowcount)
    def remember(self,code,name):
        self.execute('INSERT OR REPLACE INTO instruments VALUES(?,?)',(code,name))
        self.execute('UPDATE watch SET name=? WHERE code=?',(name,code))
    def enrich_event(self,event):
        from .sources import provider_name
        event=dict(event);raw=event.get('symbol','TEST')
        code=event.get('code') or (('sh' if raw.startswith('6') else 'sz')+raw if raw.isdigit() else '')
        names=self.query('SELECT name FROM instruments WHERE code=?',(code,)) if code else []
        name=event.get('name') or (names[0]['name'] if names else '通道测试' if raw=='TEST' else '未知名称')
        event.update(name=name,code=code,source=event.get('source') or 'tencent')
        event['source_name']=provider_name(event['source']) if raw!='TEST' else '本机通知测试'
        is_test=event.get('kind')=='NOTIFICATION_TEST' or raw=='TEST'
        event.setdefault('notification_title','观量 · 后台通知测试（非卖点信号）' if is_test else f'观量 · 卖点规则提醒 · {name}（{raw}）')
        amount=' / '.join(f'{v/10000:.2f}' for v in event.get('volumes',[]))
        event.setdefault('notification_body','本机通知链路测试，不是股票交易信号。' if is_test else
            f"{name}（{raw}）{event.get('trading_date','')} {event.get('event_label','')}；候选 {event.get('candidate_time','')}；三分钟量 {amount} 万股。仅提醒，请手动判断交易。")
        return event
    def message(self,category,title,body,event_key=None,payload=None,created=None,dedupe=None,commit=True):
        with self.lock:
            ident=uuid.uuid4().hex
            self.db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?,NULL)',
                (ident,dedupe,category,title,body,event_key,json.dumps(payload or {},ensure_ascii=False),created or now_cn().isoformat()))
            if commit:self.db.commit()
            return ident
    def config(self):
        return {r['key']:json.loads(r['value']) for r in self.query('SELECT * FROM config')}
    def setconfig(self,key,value): self.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(key,json.dumps(value)))
