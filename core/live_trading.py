"""Account-scoped holdings and chart top/bottom automation. Paused by default.

No credentials in this module. All device operations go through brokers, which
verifies the selected account under the shared device lock.
"""
import hashlib
import json
import math
import threading
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

from . import brokers
from .provider import now_cn, symbol
from .turning_shapes import SIGNAL, LABEL
from .trading_quantity import order_quantity,quantity as sized_quantity,migrate_rule
from .trading_quantity import BUY_CASH_RESERVE_RATE, BUY_CASH_RESERVE_FIXED, buy_cash_required


DEFAULT_RULE = dict(buy_enabled=False,sell_enabled=False,buy_mode='lots',sell_mode='lots',
                    buy_lots=1,sell_lots=1,buy_percent=50,sell_percent=50,daily_orders=2,
                    max_deviation_pct=.5,signal=SIGNAL)


def number(value):
    try:
        n = float(str(value).replace(',', ''))
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def stamp_age(stamp, now):
    try:
        return (now-datetime.fromisoformat(stamp)).total_seconds()
    except (ValueError, TypeError):
        return math.inf



class LiveTrading:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.lock = threading.RLock()
        self.started_at = now_cn().isoformat()
        self.frames = {}
        from .broker_reconciliation import Reconciler
        self.reconciler = Reconciler(self.store)
        with self.store.lock:
            self.store.db.executescript('''
            CREATE TABLE IF NOT EXISTS trading_sync(account_id TEXT PRIMARY KEY,token TEXT,payload TEXT,status TEXT,error TEXT,updated_at TEXT,last_success TEXT);
            CREATE TABLE IF NOT EXISTS trading_positions(account_id TEXT,code TEXT,name TEXT,payload TEXT,active INTEGER,updated_at TEXT,PRIMARY KEY(account_id,code));
            CREATE TABLE IF NOT EXISTS trading_rules(account_id TEXT,code TEXT,payload TEXT,revision INTEGER,armed_at TEXT,PRIMARY KEY(account_id,code));
            CREATE TABLE IF NOT EXISTS trading_mappings(account_id TEXT,name TEXT,code TEXT,PRIMARY KEY(account_id,name));
            CREATE TABLE IF NOT EXISTS trading_accounts(account_id TEXT PRIMARY KEY,paused INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS trading_runs(id TEXT PRIMARY KEY,account_id TEXT,code TEXT,side TEXT,signal_key TEXT,day TEXT,status TEXT,payload TEXT,created_at TEXT,updated_at TEXT,UNIQUE(account_id,code,side,signal_key));
            CREATE INDEX IF NOT EXISTS trading_runs_day ON trading_runs(account_id,day);
            ''')
            # Interrupted work is never automatically replayed after a process restart.
            self.store.db.execute("UPDATE trading_runs SET status='unknown' WHERE status='sending'")
            self.store.db.execute("UPDATE trading_runs SET status='skipped' WHERE status IN ('pending','processing')")
            # Quantity semantics changed: preserve prior whole-lot intentions and
            # switches, remove obsolete quotas, then require a fresh activation.
            changed=False
            for row in self.store.db.execute('SELECT r.*,p.payload AS position FROM trading_rules r LEFT JOIN trading_positions p ON p.account_id=r.account_id AND p.code=r.code').fetchall():
                old=json.loads(row['payload'])
                if set(old)==set(DEFAULT_RULE) and old.get('signal')==SIGNAL:continue
                new=migrate_rule(row['code'],old,json.loads(row['position'] or '{}'),DEFAULT_RULE)
                new['signal']=SIGNAL
                self.store.db.execute('UPDATE trading_rules SET payload=?,revision=revision+1,armed_at=? WHERE account_id=? AND code=?',
                                      (json.dumps(new),self.started_at,row['account_id'],row['code']))
                changed=True
            if changed:
                self.store.db.execute("INSERT OR REPLACE INTO config VALUES('trading_paused','true')")
                self.store.db.execute("INSERT OR REPLACE INTO config VALUES('trading_signal_notice',?)",(json.dumps('数量规则已简化为固定手数或当前持仓百分比；金额上限已移除，原买卖开关已保留，自动执行已暂停。'),))
            self.store.db.commit()

    def account(self, ident):
        rows = self.store.query('SELECT * FROM broker_accounts WHERE id=? AND enabled=1', (ident,))
        if len(rows) != 1:
            raise ValueError('证券账户不存在或已停用，请重新选择')
        return rows[0]

    def settings(self):
        c = self.store.config()
        return dict(paused=c.get('trading_paused', True), mode=c.get('trading_mode', 'trial'), signal=SIGNAL,signal_label=LABEL,signal_notice=c.get('trading_signal_notice',''))

    def configure(self, args):
        with self.lock:
            if 'mode' in args and args.get('paused') is False:
                raise ValueError('切换执行模式后须保持暂停，再单独启动')
            if 'mode' in args:
                if args['mode'] not in ('trial', 'live'):
                    raise ValueError('请选择试运行或实盘模式')
                if args['mode'] == 'live' and args.get('confirm_live') is not True:
                    raise ValueError('切换实盘前需要核对交易规则并明确确认')
                self.store.setconfig('trading_mode', args['mode'])
                self.store.setconfig('trading_paused', True)
                self.started_at = now_cn().isoformat()
            if 'paused' in args:
                if type(args['paused']) is not bool:
                    raise ValueError('暂停状态必须为开或关')
                self.store.setconfig('trading_paused', args['paused'])
                if not args['paused']:self.store.setconfig('trading_signal_notice','')
                self.started_at = now_cn().isoformat()
            return self.view()

    def pause_account(self, ident, paused):
        self.account(ident)
        if type(paused) is not bool:
            raise ValueError('暂停状态必须为开或关')
        with self.lock:
            self.store.execute('INSERT OR REPLACE INTO trading_accounts VALUES(?,?)', (ident, int(paused)))
            self.store.execute('UPDATE trading_rules SET armed_at=? WHERE account_id=?', (now_cn().isoformat(), ident))
        return self.view()

    def rule(self, ident, code):
        rows = self.store.query('SELECT * FROM trading_rules WHERE account_id=? AND code=?', (ident, code))
        return dict(json.loads(rows[0]['payload']), revision=rows[0]['revision'], armed_at=rows[0]['armed_at']) if rows else dict(DEFAULT_RULE, revision=0, armed_at=self.started_at)

    def save_rule(self, ident, code, changes, revision):
        code = symbol(code)
        with self.lock:
            self.account(ident)
            positions = self.store.query('SELECT * FROM trading_positions WHERE account_id=? AND code=? AND active=1', (ident, code))
            if not positions:
                raise ValueError('请先同步并确认该账户的持仓')
            old = self.rule(ident, code)
            if type(revision) is not int or revision != old['revision']:
                raise ValueError('规则已被更新，请刷新后再修改')
            if set(changes)-set(DEFAULT_RULE):
                raise ValueError('包含不支持的交易规则字段')
            new = {k: changes.get(k, old[k]) for k in DEFAULT_RULE}
            for key in ('buy_enabled', 'sell_enabled'):
                if type(new[key]) is not bool:
                    raise ValueError('买卖开关必须为开或关')
            for side in ('buy','sell'):
                if new[side+'_mode'] not in ('lots','position'):
                    raise ValueError('请选择固定手数或当前持仓百分比')
                lots=new[side+'_lots'];percent=new[side+'_percent']
                if type(lots) is not int or not 1<=lots<=1000000:raise ValueError('每次手数须为正整数')
                if isinstance(percent,bool) or number(percent) is None or not 0<float(percent)<=100:
                    raise ValueError('持仓百分比须大于0且不超过100%')
                new[side+'_percent']=float(percent)
                if code.startswith('sh688') and new[side+'_enabled'] and new[side+'_mode']=='lots' and lots<2:
                    raise ValueError('该股票固定手数至少为2手')
            if type(new['daily_orders']) is not int or not 1<=new['daily_orders']<=100:
                raise ValueError('每日执行次数须为1至100的整数')
            if isinstance(new['max_deviation_pct'],bool) or number(new['max_deviation_pct']) is None or not 0<float(new['max_deviation_pct'])<=10:
                raise ValueError('价格偏离须大于0且不超过10%')
            new['max_deviation_pct']=float(new['max_deviation_pct'])
            if new['signal'] != SIGNAL:
                raise ValueError('自动交易使用图中已确认的顶／底信号')
            self.store.execute('INSERT OR REPLACE INTO trading_rules VALUES(?,?,?,?,?)',
                               (ident, code, json.dumps(new), old['revision']+1, now_cn().isoformat()))
            return self.rule(ident, code)

    def sync(self, ident):
        self.account(ident)
        try:
            snapshot = brokers.holdings(self.store, ident)
            with self.lock:
                return self.apply_snapshot(ident, snapshot)
        except Exception as exc:
            self.store.execute("INSERT INTO trading_sync(account_id,status,error,updated_at) VALUES(?,'failed',?,?) ON CONFLICT(account_id) DO UPDATE SET status='failed',error=excluded.error,updated_at=excluded.updated_at",
                               (ident, str(exc), now_cn().isoformat()))
            raise

    def sync_all(self):
        results = []
        for a in self.store.query('SELECT id FROM broker_accounts WHERE enabled=1 ORDER BY created_at,id'):
            try:
                results.append(dict(account_id=a['id'], **self.sync(a['id'])))
            except Exception as exc:
                results.append(dict(account_id=a['id'], status='failed', error=str(exc)))
        return dict(results=results)

    def apply_snapshot(self, ident, snapshot):
        self.account(ident)
        if snapshot.get('account_id') != ident or snapshot.get('account_verified') is not True:
            raise ValueError('持仓快照与所选证券账户不一致，已拒绝同步')
        stamp = snapshot.get('observed_at')
        if not 0 <= stamp_age(stamp, now_cn()) <= 180:
            raise ValueError('持仓快照已过期，请重新同步')
        mappings = {r['name']: r['code'] for r in self.store.query('SELECT * FROM trading_mappings WHERE account_id=?', (ident,))}
        resolved, unresolved, seen = [], [], set()
        for raw in snapshot.get('positions', []):
            row = dict(raw)
            try:
                code = symbol(row.get('code') or mappings.get(row.get('name', ''), ''))
                qty, sellable = number(row.get('quantity')), number(row.get('sellable'))
                if qty is None or sellable is None or qty < 0 or sellable < 0 or sellable > qty or int(qty) != qty or int(sellable) != sellable:
                    raise ValueError('持仓或可卖数量不完整')
                if code in seen:
                    raise ValueError('同一股票出现重复持仓，请重新同步')
                seen.add(code)
                row.update(code=code, quantity=int(qty), sellable=int(sellable))
                resolved.append(row)
            except ValueError as exc:
                unresolved.append(dict(row, reason=str(exc)))
        complete = snapshot.get('complete') is True and not unresolved
        token = uuid.uuid4().hex
        updated, added = 0, 0
        with self.store.lock, self.store.db:
            # All state for this snapshot commits together; a failed scan never clears old rows.
            for row in resolved:
                code, name = row['code'], row.get('name') or row['code']
                exists = self.store.db.execute('SELECT 1 FROM trading_positions WHERE account_id=? AND code=?', (ident, code)).fetchone()
                added += not bool(exists)
                updated += bool(exists)
                self.store.db.execute('INSERT OR REPLACE INTO trading_positions VALUES(?,?,?,?,?,?)', (ident, code, name, json.dumps(row), int(row['quantity'] > 0), stamp))
                self.store.db.execute('INSERT OR IGNORE INTO watch(code,name) VALUES(?,?)', (code, name))
                self.store.db.execute('INSERT OR REPLACE INTO instruments VALUES(?,?)', (code, name))
                if not exists:
                    initial = dict(DEFAULT_RULE,buy_lots=2 if code.startswith('sh688') else 1,sell_lots=2 if code.startswith('sh688') else 1)
                    self.store.db.execute('INSERT OR IGNORE INTO trading_rules VALUES(?,?,?,1,?)', (ident, code, json.dumps(initial), now_cn().isoformat()))
            if complete:
                for old in self.store.db.execute('SELECT code FROM trading_positions WHERE account_id=?', (ident,)).fetchall():
                    if old['code'] not in seen:
                        self.store.db.execute('UPDATE trading_positions SET active=0,updated_at=? WHERE account_id=? AND code=?', (stamp, ident, old['code']))
            inactive = self.store.db.execute('SELECT code FROM trading_positions WHERE account_id=? AND active=0', (ident,)).fetchall()
            for p in inactive:
                old = self.rule(ident, p['code'])
                if old['buy_enabled'] or old['sell_enabled']:
                    payload = {k: old[k] for k in DEFAULT_RULE}
                    payload.update(buy_enabled=False, sell_enabled=False)
                    self.store.db.execute('UPDATE trading_rules SET payload=?,revision=revision+1,armed_at=? WHERE account_id=? AND code=?', (json.dumps(payload), now_cn().isoformat(), ident, p['code']))
            status = 'complete' if complete else 'partial'
            payload = dict(snapshot, unresolved=unresolved)
            self.store.db.execute('INSERT INTO trading_sync VALUES(?,?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET token=excluded.token,payload=excluded.payload,status=excluded.status,error=excluded.error,updated_at=excluded.updated_at,last_success=COALESCE(excluded.last_success,trading_sync.last_success)',
                                 (ident, token, json.dumps(payload), status, '' if complete else snapshot.get('warning') or '部分持仓待确认，保留上次数据，暂停该账户自动执行', stamp, stamp if complete else None))
        return dict(status=status, added=added, updated=updated, unresolved=len(unresolved), token=token)

    def map_position(self, ident, token, name, code):
        code = symbol(code)
        self.account(ident)
        quote = self.app.provider.quote(code)
        if quote.get('code') != code or quote.get('name', '').replace(' ', '') != str(name).replace(' ', ''):
            raise ValueError('股票代码对应名称与券商持仓不一致，不能关联')
        with self.lock:
            rows = self.store.query('SELECT * FROM trading_sync WHERE account_id=? AND token=?', (ident, token))
            if not rows:
                raise ValueError('同步结果已更新，请刷新后重新确认')
            payload = json.loads(rows[0]['payload'])
            matches = [p for p in payload.get('unresolved', []) if p.get('name') == name]
            if len(matches) != 1:
                raise ValueError('持仓名称无法唯一识别，请重新读取券商持仓')
            with self.store.lock,self.store.db:
                self.store.db.execute('INSERT OR REPLACE INTO trading_mappings VALUES(?,?,?)', (ident, name, code))
                return self.apply_snapshot(ident, payload)

    def sources(self):
        result = {}
        for p in self.store.query('SELECT p.code,p.account_id,p.active,a.broker,a.account FROM trading_positions p JOIN broker_accounts a ON a.id=p.account_id ORDER BY a.created_at'):
            result.setdefault(p['code'], []).append(dict(account_id=p['account_id'], broker_name=brokers._spec(p['broker']).name, account_masked=brokers.mask_account(p['account']), active=bool(p['active'])))
        return result

    def disable_code(self, code):
        with self.lock:
            for row in self.store.query('SELECT * FROM trading_rules WHERE code=?',(code,)):
                payload=json.loads(row['payload'])
                payload.update(buy_enabled=False,sell_enabled=False)
                self.store.execute('UPDATE trading_rules SET payload=?,revision=revision+1,armed_at=? WHERE account_id=? AND code=?',
                                   (json.dumps(payload),now_cn().isoformat(),row['account_id'],code))

    def resolve(self, ident, status, order_id, filled, note):
        if status not in ('filled','cancelled','rejected','not_sent','partial') or not isinstance(note,str) or len(note.strip())<4:
            raise ValueError('请填写核对后的委托状态及具体依据（至少4字）')
        with self.lock,self.store.lock,self.store.db:
            rows=self.store.query('SELECT * FROM trading_runs WHERE id=?',(ident,))
            if not rows or rows[0]['status'] not in ('unknown','accepted','partial'):
                raise ValueError('该执行记录不需要核实，或仍在提交中')
            run=rows[0];payload=json.loads(run['payload']);quantity=payload.get('plan',{}).get('quantity',0)
            if type(filled) is not int or not 0<=filled<=quantity or (status=='filled' and filled!=quantity) or (status in ('not_sent','rejected') and filled!=0):
                raise ValueError('实际成交股数与核实状态不符')
            if (status=='partial' and not 0<filled<quantity) or (status=='cancelled' and filled>=quantity) or filled<payload.get('verification',{}).get('filled',0):
                raise ValueError('实际成交股数不能回退，且须与委托状态一致')
            if status!='not_sent' and (not isinstance(order_id,str) or not order_id.strip() or len(order_id)>80):
                raise ValueError('请填写券商的唯一委托号')
            payload['verification']=dict(origin='manual',status=status,order_id=order_id,filled=filled,note=note.strip(),at=now_cn().isoformat())
            payload['message']='人工核实：'+note.strip()
            requests=self.store.query('SELECT * FROM broker_requests WHERE request_id=? AND account_id=?',('auto_'+ident,run['account_id']))
            if requests:
                request=requests[0]
                if request['status'] not in ('accepted','unknown','partial','sending','prepared'):raise ValueError('券商请求已更新，请刷新核对')
                result=json.loads(request['result'] or '{}')
                from .broker_reconciliation import known_id
                old_id=known_id(result)
                if old_id and status!='not_sent' and old_id!=order_id:raise ValueError('委托编号与原记录不一致，不能更换')
                result.setdefault('acknowledgement',json.loads(request['result'] or '{}'))
                result.update(status=status,submitted=status!='not_sent',verification=payload['verification'],manual_note=note)
                # Preserve the original acknowledgement and immutable lookup identity.
                if status!='not_sent':result['order_id']=order_id
                self.store.db.execute('UPDATE broker_requests SET status=?,result=?,updated_at=? WHERE request_id=?',
                                      (status,json.dumps(result),now_cn().isoformat(),'auto_'+ident))
            self.store.db.execute('UPDATE trading_runs SET status=?,payload=?,updated_at=? WHERE id=?',
                                  (status,json.dumps(payload),now_cn().isoformat(),ident))
        return self.view()

    def reconcile(self, ident, order_id=''):
        rows=self.store.query('SELECT account_id FROM trading_runs WHERE id=?',(ident,))
        if len(rows)!=1:raise ValueError('执行记录不存在')
        return self.reconciler.reconcile(rows[0]['account_id'],'auto_'+ident,order_id)

    def view(self):
        accounts = []
        for a in brokers.list_accounts(self.store):
            ident = a['id']
            state = self.store.query('SELECT * FROM trading_sync WHERE account_id=?', (ident,))
            sync = state[0] if state else {}
            payload = json.loads(sync['payload']) if sync.get('payload') else {}
            paused = self.store.query('SELECT paused FROM trading_accounts WHERE account_id=?', (ident,))
            accounts.append(dict(id=ident, broker_name=a['broker_name'], account_masked=a['account_masked'], label=a['label'], supports_order=a['supports_order'], supports_order_report=a['supports_order_report'],order_report_note=a['order_report_note'],paused=bool(paused and paused[0]['paused']),
                                 sync_status=sync.get('status', 'never'), sync_error=sync.get('error', ''), last_success=sync.get('last_success'), updated_at=sync.get('updated_at'), token=sync.get('token'),
                                 unresolved=payload.get('unresolved', []), funds=payload.get('funds', {}),funds_observed_at=payload.get('observed_at')))
        positions = []
        for p in self.store.query('SELECT p.* FROM trading_positions p JOIN broker_accounts a ON a.id=p.account_id ORDER BY a.created_at,p.active DESC,p.name'):
            positions.append(dict(account_id=p['account_id'], code=p['code'], name=p['name'], active=bool(p['active']), updated_at=p['updated_at'], **{k:v for k,v in json.loads(p['payload']).items() if k not in ('code','name')}, rule=self.rule(p['account_id'],p['code'])))
        runs = [dict(r, payload=json.loads(r['payload'])) for r in self.store.query('SELECT * FROM trading_runs ORDER BY created_at DESC,rowid DESC LIMIT 200')]
        return dict(settings=self.settings(), accounts=accounts, positions=positions, runs=runs,
                    cash_reserve=dict(rate=BUY_CASH_RESERVE_RATE,fixed=BUY_CASH_RESERVE_FIXED))

    def plan(self, ident, code, side, quote=None, now=None):
        now = now or now_cn()
        self.account(ident)
        rule = self.rule(ident, code)
        rows = self.store.query('SELECT * FROM trading_positions WHERE account_id=? AND code=? AND active=1', (ident, code))
        if side not in ('buy','sell') or not rows:
            raise ValueError('该账户没有此股票的有效持仓')
        p = json.loads(rows[0]['payload'])
        qty = sized_quantity(code,p['quantity'],p['sellable'],side,rule)
        if not qty:
            raise ValueError('设置的数量不足最小申报数量，已跳过')
        price = number((quote or {}).get('price', p.get('price')))
        if price is None or price <= 0:
            raise ValueError('缺少有效价格，请刷新行情或同步持仓')
        # Round a non-aggressive limit to cents. No chase/reprice on an unfilled order.
        limit = Decimal(str(price)).quantize(Decimal('.01'), rounding=ROUND_DOWN)
        value = limit*qty
        return dict(account_id=ident, code=code, side=side, quantity=qty, price=str(limit), value=float(value),sizing_mode=rule[side+'_mode'],lots=rule[side+'_lots'],percent=rule[side+'_percent'],position_shares=p['quantity'],rule_revision=rule['revision'])

    def ingest(self, code, bars, quote, now, continuous):
        if self.settings()['paused'] or not self.store.query("SELECT 1 FROM trading_rules WHERE code=? AND (json_extract(payload,'$.buy_enabled')=1 OR json_extract(payload,'$.sell_enabled')=1) LIMIT 1",(code,)):
            self.frames.pop(code,None)
            return
        from .turning_shapes import signals,liquidity
        observations=[dict(m,liquidity=liquidity(bars,m['time'])) for m in signals(bars)]
        signature=[tuple(b.get(k) for k in ('time','close','volume','average','complete')) for b in bars]
        day=now.date().isoformat()
        with self.lock:
            previous=self.frames.get(code)
            same_day=previous is not None and previous['day']==day
            seen=previous['seen'] if same_day else set()
            fresh=[m for m in observations if m['key'] not in seen]
            revised=bool(same_day and signature[:len(previous['signature'])]!=previous['signature'])
            # Baseline every recovered/revised observation so it cannot turn into a
            # "new" signal one poll later. Includes VWAP revisions affecting labelled chart shapes.
            self.frames[code]=dict(day=day,signature=signature,seen=seen|{m['key'] for m in observations})
            self.observe(code,fresh,quote,now,continuous and same_day and not revised)

    def observe(self, code, observations, quote, now, continuous):
        # Called only by live quote ingestion, never by chart rendering or replay.
        if not continuous or self.settings()['paused']:
            return
        with self.lock:
            for m in observations:
                event_at = datetime.fromisoformat(now.date().isoformat()+'T'+m['time']+':00').replace(tzinfo=now.tzinfo)
                if not 0 <= (now-event_at).total_seconds() <= 45 or event_at.isoformat() <= self.started_at:
                    continue
                side = 'buy' if m['kind'] == 'bottom' else 'sell'
                for row in self.store.query('SELECT * FROM trading_rules WHERE code=?', (code,)):
                    rule = json.loads(row['payload'])
                    if not rule[side+'_enabled'] or event_at.isoformat() <= row['armed_at']:
                        continue
                    key = now.date().isoformat()+'|'+m['key']
                    ident = hashlib.sha256(f"{row['account_id']}|{code}|{side}|{key}".encode()).hexdigest()
                    payload = dict(signal=m,signal_source=SIGNAL, quote=quote, mode=self.settings()['mode'], rule_revision=row['revision'], armed_at=row['armed_at'], run_epoch=self.started_at, reference_price=m['price'])
                    self.store.execute('INSERT OR IGNORE INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)', (ident,row['account_id'],code,side,key,now.date().isoformat(),'pending',json.dumps(payload),now.isoformat(),now.isoformat()))

    def finish(self, run, status, payload):
        self.store.execute('UPDATE trading_runs SET status=?,payload=?,updated_at=? WHERE id=?', (status,json.dumps(payload),now_cn().isoformat(),run['id']))

    def process(self, run):
        payload = json.loads(run['payload'])
        try:
            if self.settings()['paused'] or self.settings()['mode'] != payload['mode'] or payload.get('run_epoch') != self.started_at:
                raise ValueError('自动交易已暂停或模式已改变')
            paused = self.store.query('SELECT paused FROM trading_accounts WHERE account_id=?', (run['account_id'],))
            if paused and paused[0]['paused']:
                raise ValueError('该证券账户已暂停')
            rule = self.rule(run['account_id'],run['code'])
            if not rule[run['side']+'_enabled'] or rule['revision'] != payload['rule_revision'] or rule['armed_at'] != payload.get('armed_at'):
                raise ValueError('交易规则已关闭或修改')
            now = now_cn()
            watch = self.store.query('SELECT enabled FROM watch WHERE code=?',(run['code'],))
            if not watch or not watch[0]['enabled'] or not self.store.config().get('monitor',False):
                raise ValueError('自选监控已停止')
            if not 0 <= stamp_age(run['created_at'],now) <= 45 or not 0 <= stamp_age(payload['quote'].get('timestamp'),now) <= 30:
                raise ValueError('信号或行情已过期，未补下旧单')
            # Re-read and verify account identity before every plan, including trial mode.
            self.sync(run['account_id'])
            state = self.store.query('SELECT * FROM trading_sync WHERE account_id=?', (run['account_id'],))[0]
            if state['status'] != 'complete':
                raise ValueError('持仓同步不完整或代码待确认，暂停执行')
            # Sync may disable a rule after a confirmed clearance.
            current = self.rule(run['account_id'],run['code'])
            if current['revision'] != rule['revision'] or not current[run['side']+'_enabled']:
                raise ValueError('持仓状态已改变，请检查交易规则')
            with self.lock:
                paused = self.store.query('SELECT paused FROM trading_accounts WHERE account_id=?',(run['account_id'],))
                if self.settings()['paused'] or (paused and paused[0]['paused']) or self.rule(run['account_id'],run['code'])['revision']!=rule['revision']:
                    raise ValueError('自动交易已暂停')
                quote = self.app.quotes.get(run['code'],payload['quote'])
                if not 0 <= stamp_age(quote.get('timestamp'),now_cn()) <= 30 or not 0 <= stamp_age(run['created_at'],now_cn()) <= 45:
                    raise ValueError('核验期间信号或行情已过期，已跳过')
                price = number(quote.get('price'))
                if price is None or abs(price/payload['reference_price']-1)*100 > rule['max_deviation_pct']:
                    raise ValueError('价格偏离信号超过允许范围')
                plan = self.plan(run['account_id'],run['code'],run['side'],quote)
                liquidity=payload.get('signal',{}).get('liquidity',{})
                volumes=[number(liquidity.get(k)) for k in ('meanShares','currentShares')]
                if any(v is None or v<=0 or plan['quantity']/v>.01+1e-12 for v in volumes):
                    raise ValueError('实际委托数量超过量能参与上限，或缺少量能依据')
                previous = self.store.query("SELECT * FROM trading_runs WHERE account_id=? AND day=? AND json_extract(payload,'$.mode')=? AND status IN ('trial','sending','accepted','unknown','partial','filled','cancelled','rejected') AND id<>?",(run['account_id'],run['day'],payload['mode'],run['id']))
                same = [r for r in previous if r['code']==run['code']]
                if len(same) >= rule['daily_orders']:
                    raise ValueError('已达到该股每日执行次数上限')
                unresolved = self.store.query("SELECT id FROM trading_runs WHERE account_id=? AND id<>? AND status IN ('sending','accepted','unknown','partial')",(run['account_id'],run['id']))
                if unresolved:
                    raise ValueError('该账户有未完成或待核实委托，请先核对执行记录')
                if run['side']=='buy':
                    available = number(json.loads(state['payload']).get('funds',{}).get('available'))
                    reserved = sum(buy_cash_required(json.loads(r['payload']).get('plan',{}).get('value',0)) for r in previous if r['side']=='buy' and r['status']=='trial')
                    if available is None or buy_cash_required(plan['value']) > available-reserved:
                        raise ValueError('账户可用资金不足或无法读取（已预留费用及试运行占用）')
                elif payload['mode']=='trial':
                    sold = sum(json.loads(r['payload']).get('plan',{}).get('quantity',0) for r in same if r['side']=='sell' and r['status']=='trial')
                    held = self.store.query('SELECT payload FROM trading_positions WHERE account_id=? AND code=?',(run['account_id'],run['code']))[0]
                    if sold+plan['quantity'] > json.loads(held['payload'])['sellable']:
                        raise ValueError('试运行累计卖出已超过可卖股数')
                payload['plan'] = plan
                if payload['mode']=='trial':
                    payload['message'] = '试运行计划已生成，未发送券商委托'
                    self.finish(run,'trial',payload)
                    return
                self.finish(run,'sending',payload)
            # Recheck AFTER device login/preview and immediately before final confirmation.
            def authorize():
                with self.lock:
                    self.account(run['account_id'])
                    current = self.rule(run['account_id'],run['code'])
                    paused = self.store.query('SELECT paused FROM trading_accounts WHERE account_id=?',(run['account_id'],))
                    watch = self.store.query('SELECT enabled FROM watch WHERE code=?',(run['code'],))
                    quote = self.app.quotes.get(run['code'],payload['quote'])
                    price = number(quote.get('price'))
                    if self.settings()['paused'] or self.settings()['mode'] != 'live' or payload.get('run_epoch') != self.started_at or (paused and paused[0]['paused']) or current['revision'] != rule['revision'] or current['armed_at'] != payload.get('armed_at') or not current[run['side']+'_enabled']:
                        raise ValueError('确认前规则或暂停状态已改变，已阻止提交')
                    if not watch or not watch[0]['enabled'] or not self.store.config().get('monitor',False):
                        raise ValueError('自选监控已停止，已阻止提交')
                    if not 0 <= stamp_age(run['created_at'],now_cn()) <= 45 or not 0 <= stamp_age(quote.get('timestamp'),now_cn()) <= 30:
                        raise ValueError('确认前信号或行情已过期，已阻止提交')
                    if price is None or abs(price/payload['reference_price']-1)*100 > rule['max_deviation_pct']:
                        raise ValueError('确认前价格偏离超限，已阻止提交')
            # Existing durable broker gateway owns final account verification and deduplication.
            result = brokers.submit_order(self.store,run['account_id'],run['side'],run['code'][2:],plan['quantity'],plan['price'],None,request_id='auto_'+run['id'],authorize=authorize)
            payload['result'] = result
            payload['message'] = result.get('message') or '请核对券商委托和成交；受理不代表成交'
            self.finish(run,result['status'],payload)
        except Exception as exc:
            payload['message'] = str(exc)
            state = self.store.query('SELECT status FROM trading_runs WHERE id=?',(run['id'],))
            self.finish(run,'unknown' if state and state[0]['status']=='sending' else 'skipped',payload)

    def drain(self):
        # Single worker, no device or broker IO on the monitoring/UI threads.
        for run in self.store.query("SELECT * FROM trading_runs WHERE status='pending' ORDER BY created_at LIMIT 20"):
            changed = self.store.execute("UPDATE trading_runs SET status='processing' WHERE id=? AND status='pending'",(run['id'],))
            if changed:
                self.process(run)
        # Pausing new execution must not stop tracking already submitted orders.
        self.reconciler.poll()
