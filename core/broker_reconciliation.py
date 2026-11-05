"""Read-only reconciliation. A broker acknowledgement is never a fill report.

Only a known contract number plus an account-verified broker report can settle
a request. Missing rows, unsupported readers and errors leave it unresolved.
"""
import json
import re
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation

from . import brokers
from .provider import now_cn, CN

OPEN = ('accepted', 'unknown', 'partial')


def amount(value):
    try:
        if isinstance(value, bool):raise ValueError()
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:raise ValueError()
        return n
    except (InvalidOperation, ValueError):
        raise ValueError('委托金额或数量无法核验') from None


def shares(value):
    n = amount(value)
    if n != int(n):raise ValueError('委托股数不是整数')
    return int(n)


def known_id(result):
    if not isinstance(result, dict):raise ValueError('委托回执格式无效')
    nested=[]
    for key in ('result','verification','order_binding'):
        value=result.get(key)
        if value is None:value={}
        if not isinstance(value,dict):raise ValueError('委托回执格式无效')
        nested.append(value)
    receipt,verification,binding=nested
    ids = {str(x) for x in (result.get('order_id'), receipt.get('order_id'),
                           verification.get('order_id'), binding.get('order_id')) if x}
    # Recover explicit native receipt numbers from older clients. A lookup ID
    # proves no fill by itself; the report still must match the full request.
    from executor.trade import parse_result_message
    if isinstance(receipt.get('message'),str):
        parsed=parse_result_message(receipt['message'])
        if parsed and parsed.kind=='success':
            ident=parsed.as_dict().get('order_id')
            if ident:ids.add(ident)
    if len(ids) > 1:raise ValueError('记录中的委托编号冲突')
    return next(iter(ids), '')


def request_plan(row):
    p = json.loads(row['payload'])
    created = datetime.fromisoformat(row['created_at'])
    if created.tzinfo is None:raise ValueError('缺少明确的委托交易日期')
    if p.get('account_id') != row['account_id'] or p.get('dry_run') is not False:
        raise ValueError('试运行或账户不一致的记录不能核实为实盘成交')
    code = str(p.get('code', ''))
    if code.startswith(('sh', 'sz', 'bj')):code = code[2:]
    if not re.fullmatch(r'\d{6}', code) or p.get('side') not in ('buy', 'sell'):
        raise ValueError('缺少明确的股票或买卖方向')
    qty, price = shares(p.get('quantity')), amount(p.get('price'))
    if qty <= 0 or price <= 0:raise ValueError('缺少原始委托价格或股数')
    return dict(code=code, side=p['side'], quantity=qty, price=str(price)), created.astimezone(CN).date().isoformat()


def validate_report(report, row, order_id, expected, day, previous, now):
    if report.get('account_id') != row['account_id'] or report.get('account_verified') is not True:
        raise ValueError('回报与原委托的证券账户不一致')
    try:
        observed = datetime.fromisoformat(report['observed_at'])
        age = (now-observed).total_seconds()
    except (KeyError, ValueError, TypeError):raise ValueError('回报时间无法核验') from None
    if not 0 <= age <= 180:raise ValueError('券商回报已过期')
    if report.get('found') is not True:
        raise ValueError('未找到一致的委托编号；仍待核实，不能据此认定未发出')
    for key, value in dict(order_id=order_id, date=day, code=expected['code'], side=expected['side']).items():
        if report.get(key) != value:raise ValueError('回报的委托编号、日期、股票或方向不一致')
    try:
        broker_at = datetime.fromisoformat(day+'T'+report['time']).replace(tzinfo=CN)
        created = datetime.fromisoformat(row['created_at'])
        lag = (broker_at-created).total_seconds()
    except (KeyError, ValueError, TypeError):raise ValueError('券商委托时间无法核验') from None
    fills_report=report.get('kind')=='contract_fills'
    native_order=report.get('kind')=='native_order'
    if lag < -30 or (not (fills_report or native_order) and lag>180) or broker_at > observed:raise ValueError('券商委托时间与原始请求不一致')
    if report.get('date_source') == 'broker_today_query' and observed.astimezone(CN).date().isoformat() != day:
        raise ValueError('当日查询跨越交易日期，稍后重新核验')
    if fills_report:
        # Execution average is NOT the original limit price. Verify the immutable
        # limit/quantity against the captured, account-checked submission receipt.
        ack=previous.get('acknowledgement',previous)
        confirm=ack.get('confirm',{})
        recovery=report.get('receipt_recovery')
        recovered=False
        if recovery and previous.get('receipt_recovery')==recovery:
            submitted=datetime.fromisoformat(recovery['submitted_at'])
            recovered=(submitted.tzinfo is not None and submitted.date().isoformat()==day and
                       created<=submitted<=observed and -2<=(broker_at-submitted).total_seconds()<=15 and
                       shares(report.get('filled'))==expected['quantity'])
        acknowledged=ack.get('status')=='accepted' and ack.get('submitted') is True and known_id(ack)==order_id
        if (report.get('source')!='ths_native_contract_group' or not (acknowledged or recovered) or
            confirm.get('code')!=expected['code'] or confirm.get('side')!=expected['side'] or
            shares(confirm.get('quantity'))!=expected['quantity'] or amount(confirm.get('price'))!=amount(expected['price'])):
            raise ValueError('合同成交回报缺少与原始委托一致的已核验受理凭据')
        average=amount(report.get('average'));money=amount(report.get('amount'));executed=shares(report.get('filled'))
        limit=amount(expected['price'])
        if average<=0 or abs(average*executed-money)>Decimal('.0005')*executed+Decimal('.01'):
            raise ValueError('合同成交金额与累计成交量、均价不一致')
        if (expected['side']=='buy' and average>limit) or (expected['side']=='sell' and average<limit):
            raise ValueError('合同成交均价超出原始委托限价')
        report=dict(report,status='filled' if executed==expected['quantity'] else 'partial')
    elif shares(report.get('quantity')) != expected['quantity'] or amount(report.get('price')) != amount(expected['price']):
        raise ValueError('回报的价格或委托股数不一致')
    if native_order:
        from executor.ths_orders import order_key
        ack=previous.get('acknowledgement',previous);confirm=ack.get('confirm') or {}
        recovery=report.get('receipt_recovery') or {}
        try:submitted=datetime.fromisoformat(recovery['submitted_at'])
        except (ValueError,TypeError,KeyError):raise ValueError('缺少当日委托关联的原始提交时间') from None
        if (report.get('source')!='ths_native_today_order' or report.get('order_id') or
            recovery.get('method')!='native_order_list' or recovery!=previous.get('receipt_recovery') or
            submitted.tzinfo is None or submitted.date().isoformat()!=day or not created<=submitted<=observed or
            not -2<=(broker_at-submitted).total_seconds()<=15 or not isinstance(confirm,dict) or
            not confirm.get('name') or confirm.get('name')!=report.get('name') or
            confirm.get('code')!=expected['code'] or confirm.get('side')!=expected['side'] or
            shares(confirm.get('quantity'))!=expected['quantity'] or amount(confirm.get('price'))!=amount(expected['price']) or
            report.get('native_order_key')!=order_key(report)):
            raise ValueError('当日委托与原始券商确认无法唯一核对')
    filled = shares(report.get('filled'))
    old_filled = shares(previous.get('verification', {}).get('filled', 0))
    status = report.get('status')
    if status not in ('accepted', 'partial', 'filled', 'cancelled', 'rejected') or not old_filled <= filled <= expected['quantity']:
        raise ValueError('回报状态或累计成交股数不一致')
    if ((status == 'filled' and filled != expected['quantity']) or
        (status in ('accepted', 'rejected') and filled != 0) or
        (status == 'partial' and not 0 < filled < expected['quantity']) or
        (status == 'cancelled' and filled >= expected['quantity'])):
        raise ValueError('成交股数与券商委托状态不一致')
    if not report.get('source') or not re.fullmatch(r'[a-f0-9]{64}', report.get('evidence_hash', '')):
        raise ValueError('缺少完整的券商回报证据')
    execution={}
    if fills_report:execution=dict(average=str(average),amount=str(money))
    if native_order and filled:
        average=amount(report.get('average'));limit=amount(expected['price'])
        if average<=0 or (expected['side']=='buy' and average>limit) or (expected['side']=='sell' and average<limit):raise ValueError('当日委托成交均价与限价不一致')
        execution['average']=str(average)
    if native_order:execution['native_order_key']=report['native_order_key']
    return dict(**execution,origin='broker_auto', status=status, order_id=order_id, filled=filled,
                at=now.isoformat(), observed_at=report['observed_at'], source=report['source'],
                evidence_hash=report['evidence_hash'], note='已按账户、交易日、原始确认及唯一当日委托核对' if native_order else '已按账户、交易日及唯一委托号核对券商回报')


class Reconciler:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()

    def reconcile(self, account_id, request_id, order_id='', secrets=None):
        # A busy read is skipped, never turned into a second device operation.
        if not self.lock.acquire(blocking=False):return dict(status='busy', message='正在核实其他委托，请稍后刷新')
        try:return self._reconcile(account_id, request_id, order_id, secrets)
        finally:self.lock.release()

    def _reconcile(self, account_id, request_id, binding, secrets):
        rows = self.store.query('SELECT * FROM broker_requests WHERE request_id=? AND account_id=?', (request_id, account_id))
        if len(rows) != 1:raise ValueError('所选账户没有此委托请求')
        original = rows[0]
        if original['status'] not in OPEN:raise ValueError('该委托已结束或仍在提交，不能自动核实')
        result = json.loads(original['result'] or '{}')
        run = None
        if request_id.startswith('auto_'):
            found = self.store.query('SELECT * FROM trading_runs WHERE id=? AND account_id=?', (request_id[5:], account_id))
            if len(found) != 1 or found[0]['status'] not in OPEN:raise ValueError('自动执行记录与委托不一致')
            run = found[0]
        checked = now_cn().isoformat()
        try:
            expected, day = request_plan(original)
            ident = known_id(result)
            if binding:
                if not isinstance(binding, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', binding):raise ValueError('委托编号格式无效')
                if ident and ident != binding:
                    old_binding=result.get('order_binding', {})
                    if old_binding.get('order_id')!=ident or result.get('verification') or result.get('order_id') or result.get('result',{}).get('order_id'):
                        raise ValueError('不能更换已有的唯一委托编号')
                    result.setdefault('binding_history', []).append(old_binding)
                ident = binding
            if run:
                p = json.loads(run['payload']).get('plan', {})
                if (p.get('account_id') != account_id or p.get('code') != run['code'] or
                    p.get('code', '')[2:] != expected['code'] or p.get('side') != expected['side'] or
                    run['side'] != expected['side'] or run['day'] != day or
                    shares(p.get('quantity')) != expected['quantity'] or amount(p.get('price')) != amount(expected['price'])):
                    raise ValueError('自动执行计划与原始券商请求不一致')
            recovered_report=None
            if not ident:
                if not run:raise ValueError('缺少可核验的自动委托记录')
                accounts=self.store.query('SELECT broker FROM broker_accounts WHERE id=?',(account_id,))
                if not accounts or accounts[0]['broker']!='ths':raise ValueError('该券商缺少委托号时暂不能自动关联')
                submitted=json.loads(run['payload']).get('price_checks',{}).get('before_submit',{}).get('checked_at')
                if not submitted:raise ValueError('缺少原始提交时间，不能自动关联成交')
                confirm=result.get('acknowledgement',result).get('confirm') or {}
                if isinstance(confirm,dict) and confirm.get('name'):
                    if (confirm.get('code')!=expected['code'] or confirm.get('side')!=expected['side'] or
                        shares(confirm.get('quantity'))!=expected['quantity'] or amount(confirm.get('price'))!=amount(expected['price'])):
                        raise ValueError('原始券商确认与委托计划不一致')
                    expected=dict(expected,name=confirm['name'])
                recovered_report=brokers.discover_order_report(self.store,account_id,day,expected,submitted,secrets=secrets)
                if recovered_report.get('receipt_recovery',{}).get('submitted_at')!=submitted:raise ValueError('成交关联的提交时间与原记录不一致')
                ident=recovered_report.get('order_id','')
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',ident) and not (ident=='' and recovered_report.get('kind')=='native_order'):
                    raise ValueError('回报缺少唯一委托依据')
                result['receipt_recovery']=recovered_report.get('receipt_recovery')
            if binding:
                # Binding is only a lookup target; it never proves acceptance/fill.
                result['order_binding'] = dict(order_id=ident, origin='user', at=checked)
            for other in self.store.query('''SELECT b.*,t.payload AS run_payload FROM broker_requests b
                LEFT JOIN trading_runs t ON b.request_id='auto_'||t.id AND b.account_id=t.account_id
                WHERE b.account_id=? AND b.request_id<>?''', (account_id,request_id)):
                try:
                    other_plan,other_day=request_plan(other)
                    other_id=known_id(json.loads(other['result'] or '{}'))
                except ValueError:continue
                native_key=(recovered_report or {}).get('native_order_key')
                other_key=json.loads(other['result'] or '{}').get('verification',{}).get('native_order_key')
                if other_day==day and ((ident and other_id==ident) or (native_key and native_key==other_key)):
                    raise ValueError('同一账户交易日的券商委托已属于另一请求，需人工核对')
                if (native_key and other_day==day and other['status'] in ('accepted','partial','filled','cancelled','unknown','sending') and
                    all(other_plan[k]==expected[k] for k in ('code','side','quantity')) and amount(other_plan['price'])==amount(expected['price'])):
                    other_submit=json.loads(other['run_payload'] or '{}').get('price_checks',{}).get('before_submit',{}).get('checked_at')
                    broker_at=datetime.fromisoformat(day+'T'+recovered_report['time']).replace(tzinfo=CN)
                    at=datetime.fromisoformat(other_submit or other['created_at'])
                    # A second indistinguishable local submission cannot claim
                    # this native row, even when that request already has an ID.
                    if -2<=(broker_at-at).total_seconds()<=15:
                        raise ValueError('该当日委托也可能属于另一原始请求，不能唯一关联')
            report = recovered_report if recovered_report is not None else brokers.order_report(self.store, account_id, ident, day, expected, secrets=secrets)
            verification = validate_report(report, original, ident, expected, day, result, now_cn())
            if run:
                old = json.loads(run['payload']).get('verification', {})
                if shares(old.get('filled', 0)) > verification['filled']:raise ValueError('累计成交股数不能回退')
            result['verification'] = verification
            result['order_id']=ident
            result.setdefault('acknowledgement',json.loads(original['result'] or '{}'))
            result.update(status=verification['status'],submitted=True)
            message = '券商回报已自动核实：'+{'filled':'全部成交','partial':'部分成交，继续跟踪','accepted':'已受理，继续跟踪','cancelled':'委托已撤销','rejected':'已拒绝'}[verification['status']]
            status = verification['status']
            check = dict(at=checked, ok=True, message=message)
        except Exception as exc:
            # No-match is not evidence for not_sent; no automatic retries of orders.
            status = original['status']
            check = dict(at=checked, ok=False, message=str(exc))
        result['reconciliation'] = check
        with self.store.lock, self.store.db:
            current = self.store.db.execute('SELECT status,result FROM broker_requests WHERE request_id=?', (request_id,)).fetchone()
            if not current or current['status'] != original['status'] or current['result'] != original['result']:
                return dict(status='changed', message='记录已由其他操作更新，请刷新查看')
            if run:
                current_run = self.store.db.execute('SELECT status,payload FROM trading_runs WHERE id=?', (run['id'],)).fetchone()
                if not current_run or current_run['status'] != run['status'] or current_run['payload'] != run['payload']:
                    return dict(status='changed', message='执行记录已更新，请刷新查看')
                payload = json.loads(run['payload'])
                payload['reconciliation'] = check
                if binding and result.get('order_binding'):payload['order_binding'] = result['order_binding']
                if check['ok']:
                    payload['verification'] = result['verification']
                    payload['message'] = check['message']
                self.store.db.execute('UPDATE trading_runs SET status=?,payload=?,updated_at=? WHERE id=?',
                                      (status, json.dumps(payload), checked, run['id']))
            self.store.db.execute('UPDATE broker_requests SET status=?,result=?,updated_at=? WHERE request_id=?',
                                  (status, json.dumps(result), checked, request_id))
        return dict(status=status, **check)

    def poll(self):
        now = now_cn()
        rows = self.store.query("SELECT * FROM broker_requests WHERE status IN ('accepted','unknown','partial') ORDER BY updated_at,request_id")
        for row in rows:
            result = json.loads(row['result'] or '{}')
            try:
                _,day=request_plan(row)
                historical=day!=now.date().isoformat()
                if historical:
                    # Only unfinished real paired-T legs need historical
                    # reads. Independent historical orders keep their policy.
                    if not self.store.query("SELECT name FROM sqlite_master WHERE type='table' AND name='trading_cycles'"):continue
                    if not self.store.query("""SELECT 1 FROM trading_cycles c JOIN trading_runs t ON t.id=c.first_run_id
                        WHERE c.account_id=? AND c.state IN ('sell_pending','waiting_buy','buy_pending','needs_review')
                        AND (?='auto_'||c.first_run_id OR ?='auto_'||c.second_run_id)
                        AND json_extract(t.payload,'$.mode')='live' LIMIT 1""",(row['account_id'],row['request_id'],row['request_id'])):continue
                ident = known_id(result)
                if not ident:
                    accounts=self.store.query('SELECT broker FROM broker_accounts WHERE id=?',(row['account_id'],))
                    if not accounts or accounts[0]['broker']!='ths' or not row['request_id'].startswith('auto_'):continue
                last = datetime.fromisoformat(result.get('reconciliation', {}).get('at', row['created_at']))
                if (now-last).total_seconds() < (300 if historical else 60):continue
            except (ValueError, TypeError):continue
            return self.reconcile(row['account_id'], row['request_id'])
