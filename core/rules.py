"""Streaming implementation of running_max_inclusive_v1, no future-day inputs."""
from decimal import Decimal
from .validated_engine import MINUTES, number

class Session:
    def __init__(self, symbol, day, limit):
        self.symbol, self.day, self.limit = symbol, day, number(limit)
        if self.limit <= 0: raise ValueError('缺少有效涨停价，暂停规则判断')
        self.maximum = 0
        self.index = 0
        self.candidates = []
        self.events = []
        self.gap = False
        self.last = None

    def emit(self, c, label, price, kind):
        c['state'] = 'MATCHED_ONCE'
        c['event_label'] = label
        event = dict(key=c['key'], symbol=self.symbol, trading_date=self.day,
                     candidate_time=c['candidate_time'], confirmation_label=c['confirmation_label'],
                     volumes=c['volumes'][:], event_label=label, kind=kind,
                     reference_price=str(price), branch=c['branch'], manual_sell_only=True)
        self.events.append(event)
        return event

    def bar(self, b):
        t = b['time']
        if t not in MINUTES or b.get('complete') is not True: return []
        if self.last and t <= self.last: raise ValueError('分钟必须严格递增，修订数据需要完整重放')
        idx = MINUTES.index(t)
        if idx != self.index:
            self.gap = True
            for c in self.candidates:
                if c['state'] in ('OBSERVE_TWO','WAIT_FIRST_REOPEN'): c['state']='BLOCKED_COVERAGE_GAP'
        self.index, self.last = idx + 1, t
        v, close = number(b['volume']), number(b['close'])
        if v != v.to_integral_value() or not 0 < close <= self.limit: raise ValueError('非法分钟量或价格')
        high = number(b['high']) if b.get('high') is not None else None
        low = number(b['low']) if b.get('low') is not None else None
        if high is not None and not close <= high <= self.limit: raise ValueError('非法最高价')
        if low is not None and not 0 < low <= close: raise ValueError('非法最低价')
        emitted=[]
        for c in self.candidates:
            if c['state']=='WAIT_FIRST_REOPEN' and ((low is not None and low<self.limit) or close<self.limit):
                emitted.append(self.emit(c,t,close,'FIRST_REOPEN_MINUTE'))
            elif c['state']=='OBSERVE_TWO':
                c['volumes'].append(int(v))
                if v>=c['volumes'][0]: c['state']='INVALID_NOT_STRICTLY_SMALLER'
                elif len(c['volumes'])==3:
                    c['confirmation_label']=t
                    if close==self.limit: c['state']='WAIT_FIRST_REOPEN'
                    else: emitted.append(self.emit(c,t,close,'TWO_MINUTE_CONFIRMATION'))
        prev=self.maximum
        self.maximum=max(prev,int(v))
        if v>0 and v>=prev:
            # Tencent sampled minute prices lack intraminute highs: do not invent them.
            branch=('LIMIT_TOUCHED' if high==self.limit else 'NON_LIMIT') if high is not None else 'TOUCH_UNKNOWN'
            self.candidates.append(dict(key=f'{self.day}|{self.symbol}|{t}',candidate_time=t,
                confirmation_label=None,volumes=[int(v)],branch=branch,
                state='BLOCKED_COVERAGE_GAP' if self.gap else 'OBSERVE_TWO'))
        return emitted

    def tick(self, label, price):
        p=number(price)
        if not 0<p<=self.limit: raise ValueError('非法实时价格')
        if self.gap: return []
        return [self.emit(c,label,p,'FIRST_REOPEN_OBSERVED') for c in self.candidates
                if c['state']=='WAIT_FIRST_REOPEN' and label>(c['confirmation_label'] or '')+':00' and p<self.limit]

    def expire(self):
        for c in self.candidates:
            if c['state'] in ('OBSERVE_TWO','WAIT_FIRST_REOPEN'): c['state']='EXPIRED_AT_CLOSE'
