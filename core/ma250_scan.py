"""Read-only MA250 pullback scan for the dedicated annual-line page.

It scans the local daily cache for the selected universe, labels the strong
subset with the same core rule as the chart/alert, and never writes events,
notifications or pool records.
"""
import threading, time

from .provider import now_cn


class Ma250Scan:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.memo = {}
        self.memo_at = {}

    def _universe(self, mode):
        watch = {row['code']: row['name'] for row in self.app.store.query(
            'SELECT code,name FROM watch WHERE enabled=1')}
        if mode == 'watch':
            return watch
        pool = {row['code']: row['name'] for row in self.app.store.query(
            'SELECT code,name FROM pool WHERE archived=0')}
        if mode == 'watch_pool':
            return {**pool, **watch}
        cached = {row['code']: row['code'] for row in self.app.store.query(
            "SELECT code FROM cache_revision r WHERE kind='daily' AND EXISTS "
            "(SELECT 1 FROM cache c WHERE c.code=r.code AND c.kind='daily')")}
        names = {row['code']: row['name'] for row in self.app.store.query('SELECT code,name FROM instruments')}
        return {code: names.get(code, watch.get(code, pool.get(code, code))) for code in cached}

    def _recent_days(self, recent):
        # Union with completed stock observations: a stale index must not hide
        # the latest stock session. Intraday/live rows are never in this query.
        from .ma250_sessions import eligible_sessions
        from datetime import timedelta
        now=now_cn();verified=eligible_sessions(now,recent)
        if len(verified)>=recent:return verified[-recent:]
        completed=eligible_sessions(now,1)
        end=completed[-1] if completed else (now.date()-timedelta(days=int(now.strftime('%H:%M')<'15:20'))).isoformat()
        dates=list(self.app.market_regime.above_map())+verified
        dates += [r['day'] for r in self.app.store.query(
            "SELECT DISTINCT day FROM cache WHERE kind='daily' AND day<=? ORDER BY day DESC LIMIT ?",(end,recent))]
        return sorted(d for d in set(dates) if d<=end)[-recent:]

    def view(self,args=None):
        from .ma250_pullback import rule_spec
        from .market_regime import CODE,KIND
        args=args or {}
        mode=args.get('universe') if args.get('universe') in ('watch','watch_pool','all') else 'watch_pool'
        recent=max(1,min(1000,int(args.get('recent') or 5)))
        names=self._universe(mode);now=now_cn();days=self._recent_days(recent)
        revisions={r['code']:r['revision'] for r in self.app.store.query(
            "SELECT code,revision FROM cache_revision WHERE kind='daily'")}
        key=(mode,recent,tuple(sorted(names.items())),tuple((c,revisions.get(c,0)) for c in sorted(names)),
             self.app.store.cache_revision(CODE,KIND),tuple(days),rule_spec()['rule_id'])
        with self.lock:
            cached=self.memo.get(key)
        if cached is None or args.get('force'):
            allowed=set(days);rows=[];coverage=dict(ready=0,insufficient=0,quality_blocked=0,invalid=0);latest=None
            for code,name in names.items():
                report=self.app.annual_signals.report(code)
                last=report['latest']
                if report['error']:
                    coverage['invalid']+=1;continue
                if last:latest=max(latest or last['date'],last['date'])
                state=last.get('readiness','ready' if last.get('ready') else 'insufficient') if last else 'insufficient'
                coverage[state]+=1
                for signal in report['signals']:
                    if signal['date'] not in allowed:continue
                    rows.append(dict(signal,code=code,name=name,kind='pullback',quality=signal['strong'],
                                     slope60_pct=None,volume_ratio=None,margin_pct=signal['distance_pct']))
                for item in report['breakouts']:
                    if item['date'] not in allowed:continue
                    rows.append(dict(item,code=code,name=name,strong=False,strong_reasons=[],
                                     distance_pct=item['margin_pct'],pullback_pct=None,touch_date=None,
                                     touch_low=None,atr20_pct=None))
            # Stable priority, newest first within each quality tier.
            rows.sort(key=lambda r:r['code'])
            rows.sort(key=lambda r:r['date'],reverse=True)
            rows.sort(key=lambda r:(not r['strong'],not r.get('quality')))
            cached=dict(rows=rows,coverage=coverage,latest=latest)
            with self.lock:
                self.memo={key:cached}  # bounded; annual service retains stock-level work
        all_rows=cached['rows'];kind=args.get('kind','all');query=str(args.get('query') or '').strip().lower()
        selected=[r for r in all_rows if (kind=='all' or r['kind']==kind)
                  and (not args.get('strong_only') or r['kind']=='pullback' and r['strong'])
                  and (not query or query in r['code'].lower() or query in r['name'].lower())]
        size=max(1,min(300,int(args.get('page_size') or 100)));page=max(1,int(args.get('page') or 1))
        pages=max(1,(len(selected)+size-1)//size);page=min(page,pages)
        return dict(generated_at=now.isoformat(),universe=mode,recent=recent,trading_days=days,
            scanned=cached['coverage']['ready'],processed=len(names),codes=len(names),latest_day=cached['latest'],
            market=self.app.market_regime.view(),rows=selected[(page-1)*size:page*size],total=len(all_rows),
            filtered_total=len(selected),strong_count=sum(r['strong'] for r in all_rows),
            breakout_count=sum(r['kind']=='breakout' for r in all_rows),coverage=cached['coverage'],
            page=page,page_size=size,pages=pages,rule=rule_spec())
