"""Local-only historical paper ledger. No broker, network or notification access."""
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from datetime import date, time, timedelta
from .provider import now_cn
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR


def cents(value):
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('金额必须是有限数字')
    return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def quantity(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9]\d*', str(value)):
        raise ValueError('股数必须是正整数')
    n = int(value)
    if n > 100000000:
        raise ValueError('模拟股数过大')
    return n


class Paper:
    def __init__(self, path, store):
        self.store = store
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,name TEXT,state TEXT);
        CREATE TABLE IF NOT EXISTS orders(account TEXT,id TEXT,payload TEXT,request TEXT,
            PRIMARY KEY(account,id));
        CREATE TABLE IF NOT EXISTS pending(account TEXT,id TEXT,payload TEXT,request TEXT,
            PRIMARY KEY(account,id));
        CREATE TABLE IF NOT EXISTS fill_index(account TEXT,id TEXT,code TEXT,stamp TEXT,side TEXT,shares INTEGER,amount INTEGER,price INTEGER,fees INTEGER,PRIMARY KEY(account,id));
        CREATE INDEX IF NOT EXISTS fills_chart ON fill_index(account,code,stamp,side);
        CREATE INDEX IF NOT EXISTS fills_time ON fill_index(account,stamp);
        CREATE INDEX IF NOT EXISTS pending_status ON pending(account,json_extract(payload,'$.status'));
        CREATE INDEX IF NOT EXISTS orders_parent ON orders(account,json_extract(payload,'$.parent_id'));
        CREATE TABLE IF NOT EXISTS paper_meta(key TEXT PRIMARY KEY,value TEXT);''')
        # One-time, transactional backfill preserves old execution records.
        with self.db:
            if not self.db.execute("SELECT 1 FROM paper_meta WHERE key='fill_index_v1'").fetchone():
                for row in self.db.execute('SELECT payload FROM orders'):
                    self.index_fill(json.loads(row[0]))
                self.db.execute("INSERT INTO paper_meta VALUES('fill_index_v1','ready')")

    def index_fill(self,o):
        if o['status']=='filled':
            self.db.execute('INSERT OR IGNORE INTO fill_index VALUES(?,?,?,?,?,?,?,?,?)',
                (o['account'],o['id'],o['code'],o['stamp'],o['side'],o['shares'],o['amount'],o['price'],o['fees']))

    def used_shares(self,account,code,stamp):
        return self.db.execute('SELECT COALESCE(SUM(shares),0) FROM fill_index WHERE account=? AND code=? AND stamp=?',(account,code,stamp)).fetchone()[0]

    def load(self, account):
        row = self.db.execute('SELECT state FROM accounts WHERE id=?', (account,)).fetchone()
        if not row:
            raise ValueError('请先创建模拟账户')
        return json.loads(row['state'])

    def save(self, state):
        state['revision']=state.get('revision',0)+1
        self.db.execute('UPDATE accounts SET state=? WHERE id=?',
                        (json.dumps(state, ensure_ascii=False), state['id']))

    def account(self, args):
        cash = cents(args['cash'])
        if cash <= 0 or cash > 100000000000:
            raise ValueError('初始资金应大于0且不超过10亿元')
        commission = Decimal(str(args.get('commission_wan', 2)))
        minimum = cents(args.get('minimum', 5))
        slip = Decimal(str(args.get('slippage_bps', 0)))
        if not commission.is_finite() or not slip.is_finite() or not 0 <= commission <= 100 or not 0 <= slip <= 100 or not 0 <= minimum <= 1000000:
            raise ValueError('请检查佣金、最低佣金及滑点参数')
        key = uuid.uuid4().hex
        state = dict(id=key, name=str(args.get('name') or '回放账户')[:40], initial=cash,
                     cash=cash, clock='', lots=[], realized=0,
                     fees=dict(commission_wan=str(commission), minimum=minimum, slippage_bps=str(slip)))
        self.db.execute('INSERT INTO accounts VALUES(?,?,?)', (key,state['name'],json.dumps(state)))
        return state

    def clock(self, state, stamp):
        if not isinstance(stamp,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', stamp):
            raise ValueError('回放日期或分钟无效')
        date.fromisoformat(stamp[:10])
        t = stamp[11:]
        time.fromisoformat(t)
        if not ('09:30' <= t <= '11:30' or '13:00' <= t <= '15:00'):
            raise ValueError('请选择交易时段分钟')
        if state['clock'] and stamp < state['clock']:
            raise ValueError('账户时间不能倒退，请选择更晚分钟或新建回放账户')

    def quote(self, args, payload=None):
        code = str(args.get('code','')).lower()
        if not re.fullmatch(r'(sh60\d{4}|sz00\d{4}|sz30[01]\d{3})', code):
            raise ValueError('当前模拟支持沪深主板及创业板股票')
        stamp = str(args.get('stamp',''))
        self.clock(dict(clock=''), stamp)
        if payload is None:
            rows = self.store.getcache(code,'minute',stamp[:10])
            if not rows:raise ValueError('所选日期没有本地分钟数据')
            payload = rows[0]['data']
        if payload.get('volume_unit','shares') != 'shares':
            raise ValueError('分钟成交量单位无法确认')
        bars = [b for b in payload.get('bars',[]) if b.get('time') == stamp[11:]]
        if len(bars) != 1 or not bars[0].get('complete'):
            raise ValueError('所选分钟不存在、重复或尚未结束')
        b = bars[0]
        p = cents(b['close'])
        v = Decimal(str(b.get('volume',0)))
        if p <= 0 or not v.is_finite() or v < 0:
            raise ValueError('该分钟价格或成交量无效，无法核对委托')
        names = self.store.query('SELECT name FROM instruments WHERE code=?',(code,))
        result = dict(code=code, name=names[0]['name'] if names else code, stamp=stamp,
                      price=p, volume=int(v), source=str(payload.get('source','unknown')))
        result['token'] = hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
        return result

    def seed(self, s, args):
        if s['clock'] or self.db.execute('SELECT 1 FROM orders WHERE account=?',(s['id'],)).fetchone():
            raise ValueError('期初持仓仅能在开始回放前设置')
        code = str(args['code']).lower()
        if not re.fullmatch(r'(sh60\d{4}|sz00\d{4}|sz30[01]\d{3})',code):
            raise ValueError('请输入沪深主板或创业板代码（含sh/sz）')
        n,p = quantity(args['shares']),cents(args['cost'])
        if p <= 0 or p*n > s['cash']:
            raise ValueError('成本必须大于0，且不得超过可用初始资金')
        s['cash'] -= p*n
        names=self.store.query('SELECT name FROM instruments WHERE code=?',(code,))
        s['lots'].append(dict(code=code,name=str(args.get('name') or (names[0]['name'] if names else code))[:40],shares=n,cost=p*n,day='',seed=True))
        self.save(s)

    def fill(self, s, args, execution=None):
        request = json.dumps(args,sort_keys=True,ensure_ascii=False)
        key = str(args.get('id',''))
        if not re.fullmatch(r'[\w-]{8,80}',key):
            raise ValueError('缺少有效订单编号')
        old = self.db.execute('SELECT * FROM orders WHERE account=? AND id=?',(s['id'],key)).fetchone()
        if old:
            if old['request'] != request:
                raise ValueError('订单编号已用于不同交易，请勿重复使用')
            return json.loads(old['payload'])
        q = execution['quote'] if execution else self.quote(args)
        if not execution and q['token'] != args.get('token'):
            raise ValueError('行情数据已修订，请重新核对后提交')
        self.clock(s,q['stamp'])
        n,side = quantity(args['shares']),args.get('side')
        if side not in ('buy','sell'):
            raise ValueError('买卖方向无效')
        fee = s['fees']
        slip = Decimal(fee['slippage_bps'])/10000
        raw = Decimal(q['price'])*(1+slip if side=='buy' else 1-slip)
        p = int(raw.quantize(Decimal('1'),rounding=ROUND_CEILING if side=='buy' else ROUND_FLOOR))
        if execution:p=execution['price']
        gross = p*n
        commission = max(int((Decimal(gross)*Decimal(fee['commission_wan'])/10000).quantize(Decimal('1'),rounding=ROUND_HALF_UP)),fee['minimum'])
        transfer = int((Decimal(gross)*Decimal('.00001')).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        stamp = int((Decimal(gross)*Decimal('.0005')).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if side=='sell' else 0
        if execution:
            commission,transfer,stamp=execution['commission'],execution['transfer'],execution['stamp_tax']
        fees = commission+transfer+stamp
        lots = [l for l in s['lots'] if l['code']==q['code'] and l['shares']>0]
        eligible = [l for l in lots if not l['day'] or l['day']<q['stamp'][:10]]
        available = sum(l['shares'] for l in eligible)
        used = self.used_shares(s['id'],q['code'],q['stamp'])
        spendable = (execution['spendable'] if 'spendable' in execution else s['cash']-self.frozen(s,exclude=execution['parent_id'])[0]) if execution else s['cash']
        reason = ''
        if not execution and side=='buy' and n%100: reason='买入股数需为100股的整数倍'
        elif p<=0: reason='滑点后价格无效'
        elif used+n>q['volume']: reason='同一分钟累计模拟股数超过该分钟成交量'
        elif side=='buy' and gross+fees>spendable: reason='可用资金不足（含费用）'
        elif side=='sell' and gross+spendable<fees: reason='卖出所得及可用现金不足以支付费用'
        elif side=='sell' and n>available: reason='可卖持仓不足；当日买入需下一交易日期才能卖出'
        elif not execution and side=='sell' and n%100 and n!=available: reason='零股仅支持一次性卖出全部可卖数量'
        realized = 0
        if not reason:
            if side=='buy':
                s['cash']-=gross+fees
                s['lots'].append(dict(code=q['code'],name=q['name'],shares=n,cost=gross+fees,day=q['stamp'][:10],seed=False))
            else:
                remaining,allocated=n,0
                for lot in eligible:
                    take=min(remaining,lot['shares'])
                    cost=lot['cost'] if take==lot['shares'] else int((Decimal(lot['cost'])*take/lot['shares']).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                    lot['shares']-=take;lot['cost']-=cost;allocated+=cost;remaining-=take
                    if not remaining: break
                s['cash']+=gross-fees
                realized=gross-fees-allocated;s['realized']+=realized
            s['clock']=q['stamp'];self.save(s)
        order=dict(id=key,account=s['id'],code=q['code'],name=q['name'],stamp=q['stamp'],side=side,shares=n,
                   price=p,reference_price=q['price'],amount=gross,fees=fees,commission=commission,transfer=transfer,
                   stamp_tax=stamp,realized=realized,status='rejected' if reason else 'filled',reason=reason,
                   source=q['source'],origin=str(args.get('origin','手动'))[:40],fee_settings=fee,
                   quote_token=q['token'],recorded_at=now_cn().isoformat(timespec='seconds'),model='next_minute_limit_proxy' if execution else 'historical_minute_close_proxy',parent_id=execution['parent_id'] if execution else None)
        self.db.execute('INSERT INTO orders VALUES(?,?,?,?)',(s['id'],key,json.dumps(order,ensure_ascii=False),request))
        self.index_fill(order)
        return order

    def pending(self, account, active_only=False, limit=None):
        sql='SELECT payload FROM pending WHERE account=?';args=[account]
        if active_only:sql+=" AND json_extract(payload,'$.status') IN ('open','partial')"
        sql+=' ORDER BY rowid DESC' if limit else ' ORDER BY rowid'
        if limit:sql+=' LIMIT ?';args.append(limit)
        return [json.loads(r[0]) for r in self.db.execute(sql,args)]

    def update_pending(self, o):
        self.db.execute('UPDATE pending SET payload=? WHERE account=? AND id=?',(json.dumps(o,ensure_ascii=False),o['account'],o['id']))

    def fee_total(self,s,amount,side):
        round_int=lambda x:int(Decimal(x).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        return dict(commission=max(round_int(Decimal(amount)*Decimal(s['fees']['commission_wan'])/10000),s['fees']['minimum']) if amount else 0,
                    transfer=round_int(Decimal(amount)*Decimal('.00001')),
                    stamp_tax=round_int(Decimal(amount)*Decimal('.0005')) if side=='sell' else 0)

    def cash_reserve(self,s,o):
        if o['status'] not in ('open','partial'):return 0
        remaining=o['shares']-o['filled']
        if o['side']=='buy':
            gross=remaining*o['price']
            fees=self.fee_total(s,o['amount']+gross,'buy')
            return gross+max(0,sum(fees.values())-o['fees'])
        # The first partial sale may pay the minimum commission before the
        # remaining shares execute. Reserve that shortfall, even for a large order.
        gross=min(remaining,100)*o['price']
        fees=self.fee_total(s,o['amount']+gross,'sell')
        return max(0,sum(fees.values())-o['fees']-gross)

    def frozen(self,s,exclude=None):
        cash,stocks=0,{}
        for o in self.pending(s['id'],active_only=True):
            if o['id']==exclude or o['status'] not in ('open','partial'):continue
            remaining=o['shares']-o['filled']
            cash+=self.cash_reserve(s,o)
            if o['side']=='sell':stocks[o['code']]=stocks.get(o['code'],0)+remaining
        return cash,stocks

    def place(self,s,args):
        key=str(args.get('id',''));request=json.dumps(args,sort_keys=True,ensure_ascii=False)
        if not re.fullmatch(r'[\w-]{8,80}',key):raise ValueError('缺少有效委托编号')
        old=self.db.execute('SELECT * FROM pending WHERE account=? AND id=?',(s['id'],key)).fetchone()
        if old:
            if old['request']!=request:raise ValueError('委托编号已用于不同请求')
            return json.loads(old['payload'])
        q=self.quote(args);self.clock(s,q['stamp'])
        if q['stamp'][11:]>'14:56':raise ValueError('当前撮合仅支持连续竞价阶段，尾盘集合竞价不模拟新委托')
        if q['token']!=args.get('token'):raise ValueError('参考行情已修订，请重新核对')
        # Process earlier outstanding orders before reserving resources at this time.
        self.advance(s,q['stamp'])
        n,p,side=quantity(args['shares']),cents(args['limit_price']),args.get('side')
        if Decimal(str(args['limit_price']))*100!=p:raise ValueError('委托价最多保留两位小数')
        if side not in ('buy','sell') or p<=0:raise ValueError('委托方向或限价无效')
        frozen,stocks=self.frozen(s)
        available=sum(l['shares'] for l in s['lots'] if l['code']==q['code'] and (not l['day'] or l['day']<q['stamp'][:10]))-stocks.get(q['code'],0)
        reserve=n*p+sum(self.fee_total(s,n*p,'buy').values())
        reason=''
        payload=self.store.getcache(q['code'],'minute',q['stamp'][:10])[0]['data']
        upper,lower=payload.get('limit_up'),payload.get('limit_down')
        if (upper and p>cents(upper)) or (lower and p<cents(lower)):reason='委托价超过已知涨跌停范围'
        elif side=='buy' and n%100:reason='买入委托需为100股整数倍'
        elif side=='buy' and reserve>s['cash']-frozen:reason='可用资金不足（已扣除其他委托冻结资金及费用）'
        elif side=='sell' and n>available:reason='可卖数量不足（已扣除委托冻结及当日买入）'
        elif side=='sell' and n%100 and n!=available:reason='零股仅支持全部可卖数量一次委托'
        elif side=='sell' and max(0,sum(self.fee_total(s,min(n,100)*p,'sell').values())-min(n,100)*p)>s['cash']-frozen:reason='卖出所得及可用现金不足以支付费用（已扣除其他委托冻结）'
        o=dict(id=key,account=s['id'],code=q['code'],name=q['name'],stamp=q['stamp'],last_checked=q['stamp'],
               side=side,shares=n,filled=0,price=p,reference_price=q['price'],amount=0,fees=0,commission=0,
               transfer=0,stamp_tax=0,realized=0,status='rejected' if reason else 'open',reason=reason,
               origin=str(args.get('origin','分时委托'))[:40],source=q['source'],recorded_at=now_cn().isoformat(),
               fee_settings=s['fees'],participation_percent=1,model='next_minute_limit_proxy')
        self.db.execute('INSERT INTO pending VALUES(?,?,?,?)',(s['id'],key,json.dumps(o,ensure_ascii=False),request))
        return o

    def cancel(self,s,args):
        rows=[o for o in self.pending(s['id']) if o['id']==args.get('id')]
        if not rows:raise ValueError('委托不存在')
        o=rows[0]
        if o['status'] in ('open','partial'):
            if '14:57'<=s['clock'][11:]<'15:00':raise ValueError('收盘集合竞价阶段不接受撤单')
            o['status']='cancelled';o['reason']='已撤销剩余委托';o['cancel_time']=s['clock'];self.update_pending(o);self.save(s)
        return o

    def advance(self,s,target):
        self.clock(s,target)
        active=self.pending(s['id'],active_only=True)
        reserves={o['id']:self.cash_reserve(s,o) for o in active}
        reserved_cash=sum(reserves.values())
        candidates={}
        for code in {o['code'] for o in active}:
            for row in self.store.query("SELECT day,payload FROM cache WHERE code=? AND kind='minute' AND day>=? AND day<=? ORDER BY day",(code,s['clock'][:10],target[:10])):
                payload=json.loads(row['payload'])
                for b in payload.get('bars',[]):
                    stamp=row['day']+' '+str(b.get('time',''))
                    if s['clock']<stamp<=target and b.get('complete') and stamp[11:]<='14:56':
                        candidates[stamp,code]=payload
        for (stamp,code),payload in sorted(candidates.items()):
            orders=[o for o in active if o['code']==code and o['status'] in ('open','partial') and o['last_checked']<stamp and o['stamp'][:10]==stamp[:10]]
            if not orders:continue
            try:q=self.quote(dict(code=code,stamp=stamp),payload)
            except (ValueError,ArithmeticError,TypeError):continue
            # No order-book queue data: conservative, explicitly limited participation.
            capacity=int(Decimal(q['volume'])*Decimal('.01'))
            previous=self.used_shares(s['id'],code,stamp)
            capacity=max(0,capacity-previous)
            for o in sorted(orders,key=lambda x:(0 if x['side']=='buy' else 1,(-x['price'] if x['side']=='buy' else x['price']),x['stamp'],x['recorded_at'])):
                o['last_checked']=stamp
                slip=Decimal(s['fees']['slippage_bps'])/10000
                price=int((Decimal(q['price'])*(1+slip if o['side']=='buy' else 1-slip)).quantize(Decimal('1'),rounding=ROUND_CEILING if o['side']=='buy' else ROUND_FLOOR))
                # Close-only model: no invented intraminute crossing, no better-than-limit fills.
                match=price<=o['price'] if o['side']=='buy' else price>=o['price']
                if not match or price<=0:self.update_pending(o);continue
                # At a known price limit, queues cannot be resolved from minute data.
                limit=payload.get('limit_up' if o['side']=='buy' else 'limit_down')
                if limit and ((o['side']=='buy' and q['price']>=cents(limit)) or (o['side']=='sell' and q['price']<=cents(limit))):
                    o['reason']='涨跌停排队不可验证，保持未成交';self.update_pending(o);continue
                n=min(o['shares']-o['filled'],capacity)
                if n<o['shares']-o['filled'] or o['side']=='buy':n=n//100*100
                if n<=0:self.update_pending(o);continue
                totals=self.fee_total(s,o['amount']+price*n,o['side'])
                delta={k:totals[k]-o[k] for k in totals}
                execution=dict(quote=q,price=price,parent_id=o['id'],spendable=s['cash']-reserved_cash+reserves[o['id']],**delta)
                args=dict(id=o['id']+'-'+stamp.replace(' ','T').replace(':',''),code=code,stamp=stamp,side=o['side'],shares=n,origin=o['origin'])
                # Tick IDs are compact even for a maximum length external order ID.
                args['id']=hashlib.sha256(args['id'].encode()).hexdigest()
                fill=self.fill(s,args,execution)
                if fill['status']=='filled':
                    o['filled']+=n;o['amount']+=fill['amount'];o['fees']+=fill['fees'];o['realized']+=fill['realized']
                    for k in totals:o[k]=totals[k]
                    o['status']='filled' if o['filled']==o['shares'] else 'partial';o['reason']='';capacity-=n
                else:o['reason']=fill['reason']
                reserve=self.cash_reserve(s,o)
                reserved_cash+=reserve-reserves[o['id']];reserves[o['id']]=reserve
                self.update_pending(o)
        # DAY orders expire at the close, or before crossing into a later date.
        for o in active:
            if o['status'] in ('open','partial') and (o['stamp'][:10]<target[:10] or (o['stamp'][:10]==target[:10] and target[11:]=='15:00')):
                o['status']='expired';o['reason']='当日有效委托已到期';self.update_pending(o)
        s['clock']=target;self.save(s)

    def day_profit(self,s,positions,equity):
        day=s['clock'][:10]
        unknown=lambda reason:dict(date=day or None,profit=None,opening_equity=None,reason=reason)
        if not day:return unknown('开始回放后计算当日盈亏')
        # Reconstruct start-of-day shares and cash without replaying all history.
        opening={p['code']:p['shares'] for p in positions}
        cash=s['cash']
        rows=self.db.execute("SELECT code,SUM(CASE WHEN side='buy' THEN shares ELSE -shares END) shares_delta,SUM(CASE WHEN side='buy' THEN amount+fees ELSE -amount+fees END) reverse_cash FROM fill_index WHERE account=? AND stamp>=? AND stamp<=? GROUP BY code",(s['id'],day+' 00:00',s['clock']))
        for r in rows:
            opening[r['code']]=opening.get(r['code'],0)-r['shares_delta'];cash+=r['reverse_cash']
        baseline=cash
        for code,n in opening.items():
            if n<0:return unknown('成交记录与持仓不一致，无法确定期初资产')
            if not n:continue
            rows=self.store.query("SELECT payload FROM cache WHERE code=? AND kind='minute' AND day=?",(code,day))
            try:
                raw=json.loads(rows[0]['payload']).get('previous_close') if rows else None
                previous=cents(raw) if raw is not None else 0
            except (ValueError,TypeError,ArithmeticError):previous=0
            if previous<=0:return unknown('缺少期初持仓 '+code.upper()+' 在回放当日的可靠昨收价')
            baseline+=n*previous
        for p in positions:
            if p['valuation']!='minute_close' or not p['price_time'].startswith(day):
                return unknown('缺少持仓 '+p['code'].upper()+' 截至回放时点的当日价格')
        return dict(date=day,profit=equity-baseline,opening_equity=baseline,reason='',
                    basis='期初现金＋期初持仓按当日昨收估值；当日成交费用已计入')

    def snapshot(self, account=None, history_limit=200):
        accounts=[dict(id=r['id'],name=r['name']) for r in self.db.execute('SELECT id,name FROM accounts ORDER BY rowid')]
        if not accounts: return dict(accounts=[],account=None,positions=[],orders=[])
        s=self.load(account or accounts[-1]['id']);positions=[]
        for code in sorted({l['code'] for l in s['lots'] if l['shares']>0}):
            lots=[l for l in s['lots'] if l['code']==code and l['shares']>0]
            n=sum(l['shares'] for l in lots);basis=sum(l['cost'] for l in lots)
            mark=None
            # Fetch only the latest eligible day, falling back only when no valid bar exists.
            before=s['clock'][:10] if s['clock'] else ''
            while before:
                rows=self.store.query("SELECT day,payload FROM cache WHERE code=? AND kind='minute' AND day<=? ORDER BY day DESC LIMIT 1",(code,before))
                if not rows:break
                row=rows[0];candidates=[]
                for b in json.loads(row['payload']).get('bars',[]):
                    stamp=row['day']+' '+b.get('time','')
                    if stamp<=s['clock'] and b.get('complete'):
                        try:
                            price=cents(b['close'])
                            if price>0:candidates.append((stamp,price))
                        except (ValueError,TypeError,ArithmeticError):pass
                if candidates:mark=max(candidates);break
                # Exclude this day while preserving the indexed date bound.
                before=(date.fromisoformat(row['day'])-timedelta(days=1)).isoformat()
            value=mark[1]*n if mark else basis
            positions.append(dict(code=code,name=lots[-1]['name'],shares=n,cost=basis,market_value=value,
                price=mark[1] if mark else None,price_time=mark[0] if mark else '',unrealized=value-basis,
                available=sum(l['shares'] for l in lots if not l['day'] or (s['clock'] and l['day']<s['clock'][:10])),
                valuation='minute_close' if mark else 'cost_fallback'))
        history_limit=max(1,min(int(history_limit),5000))
        orders=[json.loads(r[0]) for r in self.db.execute('SELECT o.payload FROM orders o JOIN fill_index f ON f.account=o.account AND f.id=o.id WHERE o.account=? ORDER BY o.rowid DESC LIMIT ?',(s['id'],history_limit))]
        legacy=[json.loads(r[0]) for r in self.db.execute("SELECT payload FROM orders WHERE account=? AND json_extract(payload,'$.parent_id') IS NULL ORDER BY rowid DESC LIMIT ?",(s['id'],history_limit))]
        pending=self.pending(s['id'],limit=history_limit)
        order_count=self.db.execute('SELECT COUNT(*) FROM pending WHERE account=?',(s['id'],)).fetchone()[0]+self.db.execute("SELECT COUNT(*) FROM orders WHERE account=? AND json_extract(payload,'$.parent_id') IS NULL",(s['id'],)).fetchone()[0]
        fill_count=self.db.execute('SELECT COUNT(*) FROM fill_index WHERE account=?',(s['id'],)).fetchone()[0]
        frozen_cash,frozen_stocks=self.frozen(s)
        for p in positions:
            p['frozen']=frozen_stocks.get(p['code'],0);p['available']-=p['frozen']
        value=sum(p['market_value'] for p in positions);equity=s['cash']+value
        return dict(accounts=accounts,account={k:v for k,v in s.items() if k!='lots'},positions=positions,orders=sorted(pending+legacy,key=lambda o:o['recorded_at'] if 'recorded_at' in o else o['stamp'],reverse=True)[:history_limit],fills=orders,order_count=order_count,fill_count=fill_count,history_limit=history_limit,available_cash=s['cash']-frozen_cash,frozen_cash=frozen_cash,
                    day_pnl=self.day_profit(s,positions,equity),market_value=value,equity=equity,profit=equity-s['initial'],unrealized=sum(p['unrealized'] for p in positions),
                    total_fees=self.db.execute('SELECT COALESCE(SUM(fees),0) FROM fill_index WHERE account=?',(s['id'],)).fetchone()[0])

    def chart(self,args):
        s=self.load(args['account']);start=str(args['start']);end=str(args['end'])
        date.fromisoformat(start);date.fromisoformat(end)
        if start>end:raise ValueError('图表日期区间无效')
        # Aggregation bounds the minute chart to at most two points per minute.
        def query(first,last,daily=False):
            stamp="substr(stamp,1,10)||' 00:00'" if daily else 'stamp'
            rows=self.db.execute('SELECT '+stamp+' stamp,side,SUM(shares) shares,SUM(amount) amount,COUNT(*) fills FROM fill_index WHERE account=? AND code=? AND stamp>=? AND stamp<=? GROUP BY '+stamp+',side ORDER BY stamp,side',
                (s['id'],str(args['code']).lower(),first+' 00:00',last+' 23:59'))
            return [dict(r) for r in rows]
        daily=args.get('daily') is True
        result=dict(account=s['id'],revision=s.get('revision',0),points=query(start,end,daily))
        if daily and args.get('day'):
            day=str(args['day']);date.fromisoformat(day)
            result['minute_points']=query(day,day)
        return result

    def call(self, method, args):
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if method=='paper_create':return self.account(args)
            if method=='paper_snapshot':return self.snapshot(args.get('account'),args.get('history_limit',200))
            if method=='paper_chart':return self.chart(args)
            if method=='paper_export':
                self.load(args['account'])
                if args.get('kind')=='fills':
                    return [json.loads(r[0]) for r in self.db.execute('SELECT o.payload FROM orders o JOIN fill_index f ON o.account=f.account AND o.id=f.id WHERE o.account=? ORDER BY o.rowid',(args['account'],))]
                legacy=[json.loads(r[0]) for r in self.db.execute("SELECT payload FROM orders WHERE account=? AND json_extract(payload,'$.parent_id') IS NULL ORDER BY rowid",(args['account'],))]
                return self.pending(args['account'])+legacy
            if method=='paper_quote':return self.quote(args)
            s=self.load(args.get('account'))
            if method=='paper_seed':self.seed(s,args);return self.snapshot(s['id'])
            if method=='paper_order':return self.place(s,args)
            if method=='paper_cancel':return self.cancel(s,args)
            if method=='paper_advance':
                q=self.quote(args);self.clock(s,q['stamp']);self.advance(s,q['stamp']);return self.snapshot(s['id'])
            raise ValueError('未知模拟操作')
