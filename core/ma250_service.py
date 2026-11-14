"""Bounded, revision-aware annual-line computations shared by all client views."""
from collections import OrderedDict
import threading

from .ma250_pullback import analyze, rule_spec
from .market_regime import CODE, KIND


class AnnualSignals:
    def __init__(self, app, capacity=512):
        self.app, self.capacity = app, capacity
        self.memo, self.lock = OrderedDict(), threading.RLock()
        self.hits, self.misses = 0, 0

    def revision(self, code):
        from .ma250_sessions import eligible_sessions
        from .provider import now_cn
        from datetime import timedelta
        now=now_cn();days=eligible_sessions(now,1)
        end=days[-1] if days else (now.date()-timedelta(days=int(now.strftime('%H:%M')<'15:20'))).isoformat()
        return (self.app.store.cache_revision(code, 'daily'),
                self.app.store.cache_revision(CODE, KIND), rule_spec()['rule_id'],end)

    def report(self, code):
        key = (code, *self.revision(code))
        with self.lock:
            if key in self.memo:
                self.hits += 1
                self.memo.move_to_end(key)
                return self.memo[key]
            self.misses += 1
            rows = self.app.store.getcache(code, 'daily')
            result = analyze([row['data'] for row in rows if row['day']<=key[-1]], market=self.app.market_regime.above_map())
            # Keep just the newest revision per stock, with a hard upper bound.
            for old in [item for item in self.memo if item[0] == code]:
                del self.memo[old]
            self.memo[key] = result
            while len(self.memo) > self.capacity:
                self.memo.popitem(last=False)
            return result
