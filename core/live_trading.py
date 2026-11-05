"""Account-scoped holdings and chart top/bottom automation. Paused by default.

No credentials in this module. All device operations go through brokers, which
verifies the selected account under the shared device lock.
"""
import hashlib
import json
import math
import threading
import time
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

from . import brokers
from .provider import now_cn, symbol
from .turning_shapes import SIGNAL, LABEL
from .trading_quantity import order_quantity,quantity as sized_quantity,migrate_rule
from .trading_price import PRICE_POLICY, price_guard, rejection_message
from .trading_quantity import BUY_CASH_RESERVE_RATE, BUY_CASH_RESERVE_FIXED, buy_cash_required
from executor.runtime import DeviceBusy, OperationInterrupted, budget


DEFAULT_RULE = dict(buy_enabled=False,sell_enabled=False,buy_mode='lots',sell_mode='lots',
                    buy_lots=1,sell_lots=1,buy_percent=50,sell_percent=50,signal=SIGNAL)

# Bound each native operation so one broker cannot hang the app. Queue waiting
# is not measured against the chart's minute label; latest-signal checks own it.
DEVICE_OPERATION_SECONDS=90


class QuoteNotReady(ValueError):
    pass


def signal_identity(signal):
    candidate=signal.get('candidateTime')
    return f"{SIGNAL}|{signal['kind']}|{candidate}" if candidate else signal['key']


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


def milliseconds(age):
    return round(max(0,age)*1000,1) if math.isfinite(age) else None


class LiveTrading:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.lock = threading.RLock()
        self.started_at = now_cn().isoformat()
        self.frames = {}
        self.verified_sync = {}
        self.control_revision = 0
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
            CREATE INDEX IF NOT EXISTS trading_runs_code_created ON trading_runs(code,created_at DESC);
            ''')
            # The gateway commits BOTH journals to sending before touching a
            # submit button. Prepared + processing proves no submit boundary
            # was crossed; it must not leave an account permanently blocked.
            for row in self.store.db.execute("SELECT b.request_id FROM broker_requests b JOIN trading_runs t ON b.request_id='auto_'||t.id AND b.account_id=t.account_id WHERE b.status='prepared' AND t.status IN ('pending','processing')").fetchall():
                result=dict(status='failed',submitted=False,request_id=row['request_id'],message='上次委托准备已中断，未进入提交阶段；不重放旧信号')
                self.store.db.execute("UPDATE broker_requests SET status='failed',result=?,updated_at=? WHERE request_id=?",(json.dumps(result),self.started_at,row['request_id']))
            # Interrupted work is never automatically replayed after a process restart.
            self.store.db.execute("UPDATE trading_runs SET status='unknown' WHERE status='sending'")
            self.store.db.execute("UPDATE trading_runs SET status='skipped' WHERE status IN ('pending','processing')")
            # Quantity semantics changed: preserve prior whole-lot intentions and
            # switches, remove obsolete quotas, then require a fresh activation.
            changed=False
            for row in self.store.db.execute('SELECT r.*,p.payload AS position FROM trading_rules r LEFT JOIN trading_positions p ON p.account_id=r.account_id AND p.code=r.code').fetchall():
                old=json.loads(row['payload'])
                if set(old)==set(DEFAULT_RULE) and old.get('signal')==SIGNAL:continue
                if set(old)-{'daily_orders','max_deviation_pct'}==set(DEFAULT_RULE) and old.get('signal')==SIGNAL:
                    self.store.db.execute('UPDATE trading_rules SET payload=?,revision=revision+1 WHERE account_id=? AND code=?',
                                          (json.dumps({k:old[k] for k in DEFAULT_RULE}),row['account_id'],row['code']))
                    continue
                new=migrate_rule(row['code'],old,json.loads(row['position'] or '{}'),DEFAULT_RULE)
                new['signal']=SIGNAL
                self.store.db.execute('UPDATE trading_rules SET payload=?,revision=revision+1,armed_at=? WHERE account_id=? AND code=?',
                                      (json.dumps(new),self.started_at,row['account_id'],row['code']))
                changed=True
            if changed:
                self.store.db.execute("INSERT OR REPLACE INTO config VALUES('trading_paused','true')")
                self.store.db.execute("INSERT OR REPLACE INTO config VALUES('trading_signal_notice',?)",(json.dumps('数量规则已简化为固定手数或当前持仓百分比；金额上限已移除，原买卖开关已保留，自动执行已暂停。'),))
            self.store.db.execute("INSERT OR REPLACE INTO config VALUES('trading_price_policy',?)",(json.dumps(PRICE_POLICY),))
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
                if not args['paused'] and self.settings()['mode']=='live':
                    enabled=self.enabled_accounts()
                    if any(not a['supports_order'] for a in brokers.list_accounts(self.store) if a['id'] in enabled):
                        raise ValueError('已开启规则的账户尚不支持本机下单，请使用试运行')
                self.store.setconfig('trading_paused', args['paused'])
                if not args['paused']:self.store.setconfig('trading_signal_notice','')
                self.started_at = now_cn().isoformat()
            if 'mode' in args or 'paused' in args:self.control_revision+=1
            return self.view()

    def pause_account(self, ident, paused):
        self.account(ident)
        if type(paused) is not bool:
            raise ValueError('暂停状态必须为开或关')
        with self.lock:
            self.control_revision+=1
            self.store.execute('INSERT OR REPLACE INTO trading_accounts VALUES(?,?)', (ident, int(paused)))
            self.store.execute('UPDATE trading_rules SET armed_at=? WHERE account_id=?', (now_cn().isoformat(), ident))
        return self.view()

    def prepare(self):
        """Warm up accounts before admitting NEW signals; a pause cancels startup."""
        with self.lock:
            epoch=self.control_revision
            if not self.settings()['paused']:raise ValueError('自动执行已在运行')
            accounts=self.enabled_accounts()
            if not accounts:raise ValueError('请先开启股票的自动买卖规则')
        for ident in sorted(accounts):
            if self.sync(ident)['status']!='complete':
                codes=self.store.query("SELECT code FROM trading_rules WHERE account_id=? AND (json_extract(payload,'$.buy_enabled')=1 OR json_extract(payload,'$.sell_enabled')=1)",(ident,))
                if any(self.execution_sync(ident,r['code'])['status']!='complete' for r in codes):
                    raise ValueError('配置股票的持仓无法核验，自动执行保持暂停')
            with self.lock:
                if epoch!=self.control_revision:raise ValueError('启动已取消，自动执行保持暂停')
        with self.lock:
            if epoch!=self.control_revision:raise ValueError('启动已取消，自动执行保持暂停')
            return self.configure(dict(paused=False))

    def enabled_accounts(self):
        return {r['account_id'] for r in self.store.query("SELECT DISTINCT r.account_id FROM trading_rules r LEFT JOIN trading_accounts a ON a.account_id=r.account_id WHERE COALESCE(a.paused,0)=0 AND (json_extract(r.payload,'$.buy_enabled')=1 OR json_extract(r.payload,'$.sell_enabled')=1)")}

    def rule(self, ident, code):
        rows = self.store.query('SELECT * FROM trading_rules WHERE account_id=? AND code=?', (ident, code))
        return dict(json.loads(rows[0]['payload']), revision=rows[0]['revision'], armed_at=rows[0]['armed_at']) if rows else dict(DEFAULT_RULE, revision=0, armed_at=self.started_at)

    def save_rule(self, ident, code, changes, revision):
        code = symbol(code)
        with self.lock:
            self.account(ident)
            positions = self.store.query('SELECT * FROM trading_positions WHERE account_id=? AND code=?', (ident, code))
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
            if new['signal'] != SIGNAL:
                raise ValueError('自动交易使用图中已确认的顶／底信号')
            self.store.execute('INSERT OR REPLACE INTO trading_rules VALUES(?,?,?,?,?)',
                               (ident, code, json.dumps(new), old['revision']+1, now_cn().isoformat()))
            self.control_revision+=1
            return self.rule(ident, code)

    def sync(self, ident, reuse_seconds=0):
        self.account(ident)
        if reuse_seconds and 0 <= stamp_age(self.verified_sync.get(ident), now_cn()) <= reuse_seconds:
            state = self.store.query('SELECT status FROM trading_sync WHERE account_id=?',(ident,))
            if state and state[0]['status']=='complete':return dict(status='complete',cached=True)
        try:
            snapshot = brokers.holdings(self.store, ident)
            with self.lock:
                result = self.apply_snapshot(ident, snapshot)
                if result['status']=='complete':
                    self.verified_sync[ident]=snapshot['observed_at']
                else:self.verified_sync.pop(ident,None)
                return result
        except (DeviceBusy,OperationInterrupted):raise
        except Exception as exc:
            self.verified_sync.pop(ident,None)
            self.store.execute("INSERT INTO trading_sync(account_id,status,error,updated_at) VALUES(?,'failed',?,?) ON CONFLICT(account_id) DO UPDATE SET status='failed',error=excluded.error,updated_at=excluded.updated_at",
                               (ident, str(exc), now_cn().isoformat()))
            raise

    def execution_sync(self,ident,code):
        if 0 <= stamp_age(self.verified_sync.get(ident),now_cn()) <= 30:return self.sync(ident,reuse_seconds=30)
        states=self.store.query('SELECT * FROM trading_sync WHERE account_id=?',(ident,))
        if not states or states[0]['status'] not in ('complete','partial'):return self.sync(ident)
        baseline=states[0]
        # A persisted account-verified baseline can route a targeted recheck after
        # restart. The native gateway still verifies the account before/after
        # reading, and both actual target quantities are reread, never inferred.
        data=json.loads(baseline['payload'])
        known=self.store.query('SELECT 1 FROM trading_positions WHERE account_id=? AND code=?',(ident,code))
        if not known or data.get('account_id')!=ident or data.get('account_verified') is not True:
            return self.sync(ident)
        snapshot=brokers.holdings(self.store,ident,target_code=code)
        if snapshot.get('position_only') is not True:
            with self.lock:
                result=self.apply_snapshot(ident,snapshot)
                # Unresolved OTHER stocks do not invalidate a freshly verified
                # explicit target code in this account's native snapshot.
                targets=[p for p in snapshot.get('positions',[]) if p.get('code') in (code,code[2:])]
                qty=number(targets[0].get('quantity')) if len(targets)==1 else None
                sellable=number(targets[0].get('sellable')) if len(targets)==1 else None
                if result['status']=='partial' and qty is not None and sellable is not None and 0<=sellable<=qty and qty==int(qty) and sellable==int(sellable):
                    fresh=self.store.query('SELECT updated_at FROM trading_positions WHERE account_id=? AND code=?',(ident,code))
                    if fresh and fresh[0]['updated_at']==snapshot['observed_at']:return dict(status='complete',position_only=True)
                return result
        if snapshot.get('account_id')!=ident or snapshot.get('account_verified') is not True or not 0<=stamp_age(snapshot.get('observed_at'),now_cn())<=30:
            raise ValueError('目标持仓的账户或时间无法核验')
        positions=snapshot.get('positions',[])
        if len(positions)!=1 or symbol(positions[0].get('code',''))!=code:raise ValueError('目标持仓代码不一致')
        row=dict(positions[0]);qty=number(row.get('quantity'));sellable=number(row.get('sellable'))
        if qty is None or sellable is None or not 0<=sellable<=qty or qty!=int(qty) or sellable!=int(sellable):raise ValueError('目标持仓数量无法核验')
        row.update(code=code,quantity=int(qty),sellable=int(sellable))
        with self.lock,self.store.lock,self.store.db:
            current=self.store.db.execute('SELECT token,status FROM trading_sync WHERE account_id=?',(ident,)).fetchone()
            if not current or current['token']!=baseline['token'] or current['status']!=baseline['status']:raise ValueError('持仓快照已改变，请重新核验')
            data=json.loads(baseline['payload']);data.update(funds=snapshot.get('funds',{}),observed_at=snapshot['observed_at'])
            data['positions']=[row if p.get('code') in (code,code[2:]) or (not p.get('code') and p.get('name')==row.get('name')) else p for p in data.get('positions',[])]
            self.store.db.execute('UPDATE trading_positions SET payload=?,active=?,updated_at=? WHERE account_id=? AND code=?',(json.dumps(row),int(qty>0),snapshot['observed_at'],ident,code))
            self.store.db.execute('UPDATE trading_sync SET payload=?,updated_at=? WHERE account_id=?',(json.dumps(data),snapshot['observed_at'],ident))
        return dict(status='complete',position_only=True)

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
                        stored = self.store.db.execute('SELECT payload FROM trading_positions WHERE account_id=? AND code=?',(ident,old['code'])).fetchone()
                        zero = dict(json.loads(stored['payload']),quantity=0,sellable=0)
                        self.store.db.execute('UPDATE trading_positions SET active=0,payload=?,updated_at=? WHERE account_id=? AND code=?', (json.dumps(zero),stamp, ident, old['code']))
            # A cleared position keeps its strategy. Fixed lots can enter again;
            # a percentage of zero remains zero and cannot produce an order.
            status = 'complete' if complete else 'partial'
            payload = dict(snapshot, unresolved=unresolved)
            self.store.db.execute('INSERT INTO trading_sync VALUES(?,?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET token=excluded.token,payload=excluded.payload,status=excluded.status,error=excluded.error,updated_at=excluded.updated_at,last_success=COALESCE(excluded.last_success,trading_sync.last_success)',
                                 (ident, token, json.dumps(payload), status, '' if complete else snapshot.get('warning') or '部分持仓代码待确认；已核验股票可独立执行', stamp, stamp if complete else None))
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
        from .trading_chart import legacy_receipt_id,receipt_status
        from .broker_reconciliation import known_id
        runs=[]
        for row in self.store.query('''SELECT r.*,b.result AS broker_result,b.payload AS request_payload,
            b.status AS request_status,b.created_at AS request_at FROM trading_runs r
            LEFT JOIN broker_requests b ON b.request_id='auto_'||r.id AND b.account_id=r.account_id
            ORDER BY r.created_at DESC,r.rowid DESC LIMIT 200'''):
            payload=json.loads(row['payload']);ack=json.loads(row['broker_result'] or '{}')
            try:ident=known_id(ack)
            except ValueError:ident=''
            receipt_id=legacy_receipt_id(row,payload,ack)
            runs.append(dict(**{k:v for k,v in row.items() if k not in ('payload','broker_result','request_payload','request_status','request_at')},
                             payload=payload,order_id=ident or receipt_id,receipt_accepted=bool(receipt_id)))
            runs[-1]['status']=receipt_status(row,payload,ack)
        return dict(settings=self.settings(), accounts=accounts, positions=positions, runs=runs,
                    cash_reserve=dict(rate=BUY_CASH_RESERVE_RATE,fixed=BUY_CASH_RESERVE_FIXED))

    def plan(self, ident, code, side, quote=None, now=None):
        now = now or now_cn()
        self.account(ident)
        rule = self.rule(ident, code)
        rows = self.store.query('SELECT * FROM trading_positions WHERE account_id=? AND code=?', (ident, code))
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

    def ingest(self, code, bars, quote, now, continuous, admission_reason=''):
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
            tail=max((b['time'] for b in bars),default='')
            prior_tail=max((b[0] for b in previous['signature']),default='') if same_day else ''
            if same_day and (tail<prior_tail or len(signature)<len(previous['signature'])):
                previous['ready']=False
                return
            latest=max(observations,key=lambda m:m['time'],default=None)
            live_minute=str(quote.get('timestamp') or now.isoformat())[11:16]
            self.frames[code]=dict(day=day,signature=signature,seen=seen|{m['key'] for m in observations},
                                   latest=signal_identity(latest) if latest else None,ready=tail==live_minute,observed_at=now.isoformat())
            for m in fresh:
                historical=(not same_day and m['time']<=self.started_at[11:16]) or m['time']<prior_tail or m['time']!=tail or m['time']!=live_minute or m is not latest
                self.observe(code,[m],quote,now,continuous,admission_reason='历史信号或启动采样基线，未补单' if historical else '',
                             baseline_at=previous.get('observed_at') if same_day else None)

    def observe(self, code, observations, quote, now, continuous, admission_reason='',baseline_at=None):
        # Called only by live quote ingestion, never by chart rendering or replay.
        if self.settings()['paused']:
            return
        with self.lock:
            for m in observations:
                event_at = datetime.fromisoformat(now.date().isoformat()+'T'+m['time']+':00').replace(tzinfo=now.tzinfo)
                age=(now-event_at).total_seconds()
                if age<0 or (event_at.isoformat()<=self.started_at and (not baseline_at or baseline_at<self.started_at)):continue
                reason=admission_reason
                side = 'buy' if m['kind'] == 'bottom' else 'sell'
                for row in self.store.query('SELECT * FROM trading_rules WHERE code=?', (code,)):
                    rule = json.loads(row['payload'])
                    if not rule[side+'_enabled'] or (event_at.isoformat()<=row['armed_at'] and (not baseline_at or baseline_at<row['armed_at'])):
                        continue
                    if m.get('candidateTime') and self.store.query("SELECT 1 FROM trading_runs WHERE account_id=? AND code=? AND side=? AND day=? AND json_extract(payload,'$.signal.candidateTime')=? AND json_extract(payload,'$.mode')=? AND status NOT IN ('skipped','failed','not_sent') LIMIT 1",
                            (row['account_id'],code,side,now.date().isoformat(),m['candidateTime'],self.settings()['mode'])):
                        continue
                    key = now.date().isoformat()+'|'+m['key']
                    ident = hashlib.sha256(f"{row['account_id']}|{code}|{side}|{key}".encode()).hexdigest()
                    payload = dict(signal=m,signal_at=event_at.isoformat(),signal_source=SIGNAL, quote=quote, mode=self.settings()['mode'], rule_revision=row['revision'], armed_at=row['armed_at'], run_epoch=self.started_at, reference_price=m['price'])
                    payload['admission']=dict(allowed=not bool(reason),continuous=continuous,observed_at=now.isoformat(),baseline_at=baseline_at,signal_age_ms=milliseconds(age),reason=reason)
                    if reason:payload['message']=reason
                    self.store.execute('INSERT OR IGNORE INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)', (ident,row['account_id'],code,side,key,now.date().isoformat(),'skipped' if reason else 'pending',json.dumps(payload),now.isoformat(),now.isoformat()))

    def persist_progress(self, run, payload):
        self.store.execute('UPDATE trading_runs SET payload=?,updated_at=? WHERE id=?',(json.dumps(payload),now_cn().isoformat(),run['id']))

    def check_price(self, run, payload, quote, rule, stage):
        stamp=now_cn()
        checks=payload.setdefault('price_checks',{})
        try:
            check=price_guard(run['side'],payload['reference_price'],quote.get('price'))
            plan=payload.get('plan')
            if quote.get('code') not in (None,run['code']):
                check.update(allowed=False,error='行情代码与委托股票不一致')
            # Favorable movement is allowed only for valid same-stock prices;
            # market-provided daily bounds remain independent protections.
            prices=[number(quote.get('price')),number(payload['reference_price'])]+([number(plan['price'])] if plan else [])
            for key,label,upper in (('limit_up','涨停价',True),('limit_down','跌停价',False)):
                if key not in quote:continue
                bound=number(quote[key])
                if bound is None or bound<=0 or any(v is None or (v>bound if upper else v<bound) for v in prices):
                    check.update(allowed=False,error='价格超出有效'+label+'范围，已阻止提交')
            if plan:
                ordered=price_guard(run['side'],payload['reference_price'],plan['price'])
                check.update(order_price=plan['price'],order_allowed=ordered['allowed'],order_adverse_deviation_pct=ordered['adverse_deviation_pct'])
                if not ordered['allowed']:
                    check['allowed']=False
                    check['error']='委托限价超出不利价格保护范围'
        except ValueError as exc:
            check=dict(policy=PRICE_POLICY,allowed=False,error=str(exc),reference_price=payload.get('reference_price'),quote_price=quote.get('price'))
        quote_age=stamp_age(quote.get('timestamp'),stamp);signal_age=self.execution_age(run,stamp)
        check.update(checked_at=stamp.isoformat(),quote_at=quote.get('timestamp'),stage=stage,quote_age_ms=milliseconds(quote_age),signal_age_ms=milliseconds(signal_age))
        if not 0<=quote_age<=30:
            check.update(allowed=False,error='行情尚未更新，等待新报价')
        checks[stage]=check
        payload.setdefault('timings',{})['elapsed_ms']=milliseconds(signal_age)
        self.persist_progress(run,payload)
        if not check['allowed']:
            if check.get('error')=='行情尚未更新，等待新报价':raise QuoteNotReady(check['error'])
            raise ValueError(check.get('error') or rejection_message(check))

    def finish(self, run, status, payload):
        payload.setdefault('timings',{})['elapsed_ms']=milliseconds(self.execution_age(run,now_cn()))
        self.store.execute('UPDATE trading_runs SET status=?,payload=?,updated_at=? WHERE id=?', (status,json.dumps(payload),now_cn().isoformat(),run['id']))

    def process(self, run):
        with budget(DEVICE_OPERATION_SECONDS):
            self._process(run)

    def check_current(self,run,payload):
        now=now_cn()
        if run['day']!=now.date().isoformat() or now.strftime('%H:%M:%S')>'15:00:00':
            raise ValueError('交易日或交易时段已结束，未补发旧委托')
        frame=self.frames.get(run['code'])
        if frame and frame['day']==run['day'] and not frame.get('ready',True):
            raise QuoteNotReady('分钟数据尚未更新，等待实时信号核验')
        if frame and frame['day']==run['day'] and frame.get('latest')!=signal_identity(payload['signal']):
            raise ValueError('信号已变化，原委托已取消')
        newer=self.store.query("SELECT id FROM trading_runs WHERE account_id=? AND code=? AND day=? AND COALESCE(json_extract(payload,'$.admission.allowed'),1)=1 ORDER BY created_at DESC,rowid DESC LIMIT 1",
                               (run['account_id'],run['code'],run['day']))
        if newer and newer[0]['id']!=run['id']:raise ValueError('已有更新信号，原委托已取消')

    def execution_age(self,run,now):
        return stamp_age(json.loads(run['payload']).get('signal_at',run['created_at']),now)

    def _process(self, run):
        payload = json.loads(run['payload'])
        payload.setdefault('timings',{})['queue_ms']=milliseconds(stamp_age(run['created_at'],now_cn()))
        try:
            self.check_current(run,payload)
            if self.settings()['paused'] or self.settings()['mode'] != payload['mode'] or payload.get('run_epoch') != self.started_at:
                raise ValueError('自动交易已暂停或模式已改变')
            paused = self.store.query('SELECT paused FROM trading_accounts WHERE account_id=?', (run['account_id'],))
            if paused and paused[0]['paused']:
                raise ValueError('该证券账户已暂停')
            rule = self.rule(run['account_id'],run['code'])
            if not rule[run['side']+'_enabled'] or rule['revision'] != payload['rule_revision'] or rule['armed_at'] != payload.get('armed_at'):
                raise ValueError('交易规则已关闭或修改')
            watch = self.store.query('SELECT enabled FROM watch WHERE code=?',(run['code'],))
            if not watch or not watch[0]['enabled'] or not self.store.config().get('monitor',False):
                raise ValueError('自选监控已停止')
            quote = self.app.quotes.get(run['code'],payload['quote'])
            # Re-read and verify account identity before every plan, including trial mode.
            # Each distinct signal gets fresh broker funds/positions. Old
            # acknowledgement/fill states never block today's new requests.
            self.verified_sync.pop(run['account_id'],None)
            self.check_price(run,payload,quote,rule,'before_holdings')
            sync_started=time.monotonic()
            try:
                synced=self.execution_sync(run['account_id'],run['code'])
                payload['timings']['holdings_scope']='cached' if synced.get('cached') else 'target' if synced.get('position_only') else 'complete'
            finally:
                payload['timings']['holdings_ms']=round((time.monotonic()-sync_started)*1000,1)
                self.persist_progress(run,payload)
            state = self.store.query('SELECT * FROM trading_sync WHERE account_id=?', (run['account_id'],))[0]
            if synced['status'] != 'complete':
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
                self.check_price(run,payload,quote,rule,'after_holdings')
                plan = self.plan(run['account_id'],run['code'],run['side'],quote)
                # Quantity comes from the account's explicit lots/position rule.
                # Minute liquidity is diagnostic evidence, not a hidden order cap;
                # a live minute's partial volume must not veto that configured size.
                payload['plan'] = plan
                previous = self.store.query("SELECT * FROM trading_runs WHERE account_id=? AND day=? AND json_extract(payload,'$.mode')=? AND status IN ('trial','sending','accepted','unknown','partial','filled','cancelled','rejected') AND id<>?",(run['account_id'],run['day'],payload['mode'],run['id']))
                same = [r for r in previous if r['code']==run['code']]
                if run['side']=='buy':
                    available = number(json.loads(state['payload']).get('funds',{}).get('available'))
                    reserved = sum(buy_cash_required(json.loads(r['payload']).get('plan',{}).get('value',0)) for r in previous if r['side']=='buy' and r['status']=='trial')
                    if available is None or buy_cash_required(plan['value']) > available-reserved:
                        raise ValueError('账户可用资金不足或无法读取')
                elif payload['mode']=='trial':
                    sold = sum(json.loads(r['payload']).get('plan',{}).get('quantity',0) for r in same if r['side']=='sell' and r['status']=='trial')
                    held = self.store.query('SELECT payload FROM trading_positions WHERE account_id=? AND code=?',(run['account_id'],run['code']))[0]
                    if sold+plan['quantity'] > json.loads(held['payload'])['sellable']:
                        raise ValueError('试运行累计卖出已超过可卖股数')
                if payload['mode']=='trial':
                    payload['message'] = '试运行计划已生成，未发送券商委托'
                    self.finish(run,'trial',payload)
                    return
                self.finish(run,'processing',payload)
            # Recheck AFTER device login/preview and immediately before final confirmation.
            def authorize():
                with self.lock:
                    self.check_current(run,payload)
                    self.account(run['account_id'])
                    current = self.rule(run['account_id'],run['code'])
                    paused = self.store.query('SELECT paused FROM trading_accounts WHERE account_id=?',(run['account_id'],))
                    watch = self.store.query('SELECT enabled FROM watch WHERE code=?',(run['code'],))
                    quote = self.app.quotes.get(run['code'],payload['quote'])
                    if self.settings()['paused'] or self.settings()['mode'] != 'live' or payload.get('run_epoch') != self.started_at or (paused and paused[0]['paused']) or current['revision'] != rule['revision'] or current['armed_at'] != payload.get('armed_at') or not current[run['side']+'_enabled']:
                        raise ValueError('确认前规则或暂停状态已改变，已阻止提交')
                    if not watch or not watch[0]['enabled'] or not self.store.config().get('monitor',False):
                        raise ValueError('自选监控已停止，已阻止提交')
                    self.check_price(run,payload,quote,rule,'before_submit')
            # Existing durable broker gateway owns final account verification and deduplication.
            gateway_started=time.monotonic()
            try:
                result = brokers.submit_order(self.store,run['account_id'],run['side'],run['code'][2:],plan['quantity'],plan['price'],None,request_id='auto_'+run['id'],authorize=authorize)
            finally:
                payload['timings']['gateway_ms']=round((time.monotonic()-gateway_started)*1000,1)
            self.verified_sync.pop(run['account_id'],None)
            payload['result'] = result
            payload['message'] = result.get('message') or (result.get('result') or {}).get('message') or {'accepted':'券商已受理','rejected':'券商已拒绝','unknown':'未收到明确回执；本请求不自动重发'}.get(result['status'],'委托结果已记录')
            self.finish(run,result['status'],payload)
        except (DeviceBusy,QuoteNotReady,TimeoutError) as exc:
            payload['message'] = str(exc)+'；等待后重新核验最新信号，不重复发送委托'
            state=self.store.query('SELECT status FROM trading_runs WHERE id=?',(run['id'],))
            status='unknown' if state and state[0]['status']=='sending' else 'pending'
            if isinstance(exc,QuoteNotReady):payload['retry_after']=time.time()+3
            self.finish(run,status,payload)
        except Exception as exc:
            payload['message'] = str(exc)
            state = self.store.query('SELECT status FROM trading_runs WHERE id=?',(run['id'],))
            self.finish(run,'unknown' if state and state[0]['status']=='sending' else 'skipped',payload)

    def drain(self, reports=True):
        # Single worker, no device or broker IO on the monitoring/UI threads.
        for run in self.store.query("SELECT * FROM trading_runs WHERE status='pending' ORDER BY created_at LIMIT 20"):
            if json.loads(run['payload']).get('retry_after',0)>time.time():continue
            changed = self.store.execute("UPDATE trading_runs SET status='processing' WHERE id=? AND status='pending'",(run['id'],))
            if changed:
                self.process(run)
        # Pausing new execution must not stop tracking already submitted orders.
        if reports:self.poll_reports()

    def poll_reports(self):
        with budget(120,cancelled=lambda:bool(self.store.query("SELECT 1 FROM trading_runs WHERE status='pending' LIMIT 1"))):
            self.reconciler.poll()
