"""Refresh public-data research previews in isolated, disposable databases.

No application account, watchlist, notification or production cache is accessed.
An unavailable source never replaces an existing preview with a partial result.
"""
import argparse
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.equity_bond import EquityBond
from core.index_technical import IndexTechnical
from core.option_pcr import OptionPCR, eligible_sessions
from core.provider import now_cn
from core.store import Store

ROOT = Path(__file__).resolve().parents[1]


def collect_one(name, factory, filename, expected, now, directory):
    store = Store(str(Path(directory) / (name + '.sqlite3')))
    try:
        service = factory(store)
        service.refresh(now=now)
        report = service.view(now=now)
        if service.error:
            return name, False, service.error
        entries = report.get('daily', report.get('days', []))
        if not entries or entries[-1]['date'] != expected or report.get('latest_eligible') != expected:
            return name, False, '未取得并校验指定日期的完整收盘数据'
        path = ROOT / 'public' / filename
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
        return name, True, f'{expected} · {len(entries)} 条 · {filename}'
    finally:
        store.db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-date', required=True)
    args = parser.parse_args()
    now = now_cn()
    dates = eligible_sessions(now, 1)
    if not dates or dates[-1] != args.expected_date:
        raise SystemExit('指定日期不是本次可采集的最近已结束交易日')
    jobs = [
        ('pcr50', lambda store: OptionPCR(store, '510050'), 'pcr-preview.json'),
        ('pcr300', lambda store: OptionPCR(store, '510300'), 'pcr300-preview.json'),
        ('equity_bond', EquityBond, 'equity-bond-preview.json'),
        ('index', IndexTechnical, 'index-technical-preview.json'),
    ]
    failed = False
    with tempfile.TemporaryDirectory(prefix='stock-observation-preview-') as directory:
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = [pool.submit(collect_one, name, factory, filename, args.expected_date, now, directory)
                       for name, factory, filename in jobs]
            for future in as_completed(pending):
                try:
                    name, ok, detail = future.result()
                    print(name, 'OK' if ok else 'FAILED', detail, flush=True)
                    failed |= not ok
                except Exception as exc:
                    print('FAILED', type(exc).__name__, str(exc), flush=True)
                    failed = True
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
