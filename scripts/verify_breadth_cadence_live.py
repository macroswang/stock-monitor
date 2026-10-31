"""Record two real breadth scheduler scans in an isolated temporary database.

Public quotes only; never opens the user's watchlist, accounts or notifications.
The report is evidence for these scans, not a general real-time guarantee.
"""
import json
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from core.app import App, now_cn
from core.breadth import Breadth, CODE, KIND, BREADTH_INTERVAL_SECONDS
from core.store import Store

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/market-regime-research-20261029/live-cadence-20261030.json'


def main():
    current = now_cn()
    if current.date().isoformat() != '2026-10-30' or not ('13:00' <= current.strftime('%H:%M') < '14:50'):
        raise RuntimeError('仅在 2026-10-30 下午连续竞价时段启动，且应留出两轮采样时间')
    stop = threading.Event()
    samples = []
    with tempfile.TemporaryDirectory(prefix='breadth-cadence-') as directory:
        store = Store(Path(directory) / 'isolated.sqlite3')
        service = Breadth(store)

        class Recorder:
            @property
            def last_attempt(self):
                return service.last_attempt

            def refresh(self):
                start, tick = now_cn(), time.monotonic()
                service.refresh()
                finish = now_cn()
                rows = store.getcache(CODE, KIND, finish.date().isoformat())
                data = rows[0]['data'] if rows else {}
                first = data.get('first_quote')
                age = (finish - datetime.fromisoformat(first)).total_seconds() if first else None
                sample = {'start': start.isoformat(), 'finish': finish.isoformat(),
                          'duration_seconds': round(time.monotonic()-tick, 2),
                          'error': service.error, 'status': data.get('status'),
                          'collected_at': data.get('collected_at'), 'first_quote': first,
                          'last_quote': data.get('last_quote'), 'first_age_at_finish_seconds': age,
                          'covered': data.get('covered'), 'expected': data.get('expected')}
                samples.append(sample)
                print(json.dumps(sample, ensure_ascii=False), flush=True)
                if len(samples) >= 2:
                    stop.set()

        try:
            App.breadth_loop(SimpleNamespace(store=store, breadth=Recorder(), stop=stop))
            result = {'interval_seconds': BREADTH_INTERVAL_SECONDS, 'samples': samples,
                      'warning': '仅两次独立临时数据库采样；不证明长期可用、交易信号有效或安装包稳定。'}
            OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        finally:
            store.db.close()


if __name__ == '__main__':
    main()
