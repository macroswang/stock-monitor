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
        self.research_memo = OrderedDict()
        self.research_lock = threading.RLock()
        self.research_hits, self.research_misses = 0, 0

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

    def research_report(self, code):
        # Separate lazy cache: alert callers of report() never compute E2.
        from .ma250_e2 import analyze, research_spec
        revision = self.revision(code)
        key = (code, *revision, research_spec()['rule_id'])
        with self.research_lock:
            if key in self.research_memo:
                self.research_hits += 1
                self.research_memo.move_to_end(key)
                return self.research_memo[key]
            self.research_misses += 1
            formal = self.report(code)
            rows = [r['data'] for r in self.app.store.getcache(code, 'daily') if r['day'] <= revision[-1]]
            result = analyze(rows, self.app.market_regime.above_map(), formal=formal)
            if revision != self.revision(code):
                return dict(signals=[], **research_spec(), error='日线或指数正在更新，请刷新E2研究参考')
            for old in [item for item in self.research_memo if item[0] == code]:
                del self.research_memo[old]
            self.research_memo[key] = result
            while len(self.research_memo) > self.capacity:
                self.research_memo.popitem(last=False)
            return result
