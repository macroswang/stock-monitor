"""Resumable Baostock qfq archive for the MA250 study.

Samples the 415 Tencent codes for a paired comparison plus a deterministic
sample of the historical tradable universe (including later-delisted names) to
reduce survivorship. Never opens the client database or emits signals.
"""
import argparse, json, re, sys, time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from core.provider import now_cn

DATES = ('2018-08-01', '2020-01-02', '2022-01-04', '2024-01-02', '2026-11-13')
FIELDS = 'date,open,high,low,close,volume,amount,tradestatus,isST'
EXISTING = BASE / 'docs' / 'ma250-pullback' / 'data' / 'tencent'
OUT = BASE / 'docs' / 'ma250-pullback' / 'data' / 'baostock-qfq'


def valid_code(code):
    return bool(re.fullmatch(r'(sh\.6\d{5}|sz\.(?:0|3)\d{5})', code)) and not code.startswith('sh.689')


def bs_code(code):
    return code[:2] + '.' + code[2:]


def universe(bs):
    codes = set()
    for day in DATES:
        result = bs.query_all_stock(day=day)
        if result.error_code != '0':
            raise RuntimeError(f'all_stock {day}: {result.error_msg}')
        while result.next():
            code = result.get_row_data()[0]
            if valid_code(code):
                codes.add(code)
    return sorted(codes)


def sample(bs, target):
    existing = sorted(path.stem for path in EXISTING.glob('*.json'))
    chosen = [bs_code(code) for code in existing]
    pool = [code for code in universe(bs) if code not in set(chosen)]
    need = max(0, target - len(chosen))
    if need and pool:
        step = max(1, len(pool) // need)
        chosen += pool[::step][:need]
    return chosen


def fetch(bs, code):
    result = bs.query_history_k_data_plus(code, FIELDS, start_date='2018-08-01', end_date='2026-11-13',
                                          frequency='d', adjustflag='2')
    if result.error_code != '0':
        raise RuntimeError(result.error_msg)
    rows = []
    while result.next():
        fields = result.get_row_data()
        if len(fields) < 9 or fields[7] != '1':
            continue
        try:
            day, open_, high, low, close, volume = fields[0], float(fields[1]), float(fields[2]), float(fields[3]), float(fields[4]), float(fields[5])
        except (TypeError, ValueError):
            continue
        if min(open_, high, low, close) <= 0 or high < max(open_, close) or low > min(open_, close) or volume < 0:
            continue
        rows.append([day, round(open_, 4), round(close, 4), round(high, 4), round(low, 4), round(volume, 0), int(fields[8] or 0)])
    rows.sort(key=lambda item: item[0])
    unique, seen = [], set()
    for row in rows:
        if row[0] not in seen:
            seen.add(row[0])
            unique.append(row)
    return unique


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description='Baostock 前复权日线归档')
    parser.add_argument('--target', type=int, default=1000)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    import baostock as bs
    login = bs.login()
    if login.error_code != '0':
        raise SystemExit('baostock login failed: ' + login.error_msg)
    try:
        codes = sample(bs, args.target)[:args.limit or None]
        manifest = dict(source='baostock', adjustment='qfq', dates=list(DATES), target=args.target,
                        codes=len(codes), collected_at=now_cn().isoformat(), failures={}, progress=0)
        failures = 0
        for index, code in enumerate(codes, 1):
            path = OUT / f'{code.replace(".", "")}.json'
            if path.exists() and path.stat().st_size > 2:
                continue
            for attempt in range(3):
                try:
                    rows = fetch(bs, code)
                    if len(rows) < 320:
                        raise ValueError(f'only {len(rows)} tradable bars')
                    save(path, dict(code=code.replace('.', ''), source='baostock', adjustment='qfq',
                                    fetched_at=now_cn().isoformat(), rows=rows))
                    break
                except Exception as error:
                    if attempt == 2:
                        failures += 1
                        manifest['failures'][code] = type(error).__name__
                    else:
                        time.sleep(2 ** attempt)
            manifest['progress'] = index
            if index % 25 == 0 or index == len(codes):
                save(OUT / 'manifest.json', manifest)
                print(f'{index}/{len(codes)} codes, failures {failures}', flush=True)
            time.sleep(0.1)
        manifest['finished_at'] = now_cn().isoformat()
        save(OUT / 'manifest.json', manifest)
        print('done', manifest['progress'], 'failures', failures)
    finally:
        bs.logout()


if __name__ == '__main__':
    main()
