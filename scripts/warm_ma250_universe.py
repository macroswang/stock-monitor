"""Warm daily history for the annual-line scan across watch + active pool.

One-off/background maintenance: it only reads watch/pool membership and fills the
daily cache via the same DailyCache.ensure_history path the client uses. It does
not change signals, alerts, watch, pool or trading state.
"""
import argparse, os, sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.app import App


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default=os.path.expanduser('~/Library/Application Support/com.xreddot.stockmonitor'))
    parser.add_argument('--universe', choices=('watch', 'pool', 'watch_pool', 'all'), default='watch_pool')
    parser.add_argument('--minimum', type=int, default=310)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    app = App(args.data_dir, False)
    try:
        watch = {row['code']: row['name'] for row in app.store.query('SELECT code,name FROM watch')}
        pool = {row['code']: row['name'] for row in app.store.query("SELECT code,name FROM pool WHERE archived=0")}
        if args.universe == 'watch':
            names = watch
        elif args.universe == 'pool':
            names = pool
        elif args.universe == 'watch_pool':
            names = {**pool, **watch}
        else:
            names = {row['code']: row['code'] for row in app.store.query("SELECT DISTINCT code FROM cache WHERE kind='daily'")}
        items = list(names.items())
        if args.limit:
            items = items[:args.limit]
        ready = skipped = failed = 0
        for index, (code, name) in enumerate(items, 1):
            count = app.store.query("SELECT count(*) AS n FROM cache WHERE code=? AND kind='daily'", (code,))[0]['n']
            if count >= args.minimum:
                ready += 1
                skipped += 1
                print(f'[{index}/{len(items)}] {code} {name}: {count} bars, skip', flush=True)
                continue
            try:
                end = app.daily_cache.completed_day()
                app.daily_cache.fetch(code, end - timedelta(days=600), end)
                now = app.store.query("SELECT count(*) AS n FROM cache WHERE code=? AND kind='daily'", (code,))[0]['n']
                if now >= args.minimum:
                    ready += 1
                print(f'[{index}/{len(items)}] {code} {name}: {count} -> {now} bars', flush=True)
            except Exception as exc:
                failed += 1
                print(f'[{index}/{len(items)}] {code} {name}: failed {type(exc).__name__}: {exc}', flush=True)
        print(f'done: ready={ready} skipped={skipped} failed={failed} total={len(items)}', flush=True)
    finally:
        app.store.db.close()


if __name__ == '__main__':
    main()
