"""Resumable, rate-limited Tencent daily archive for the MA250 study.

Reads a fixed, return-independent sample of the checked seed universe and
fetches Tencent unadjusted bars, the same basis as the client. Data is written
under an ignored docs folder; the production database is never opened.
"""
import argparse, gzip, json, re, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from core.provider import Tencent, now_cn

SAMPLE_STEP = 12
START = '2018-08-01'


def clean(rows):
    """Sort, deduplicate and validate one unadjusted daily series."""
    out, seen = [], set()
    for row in rows:
        day = str(row.get('date'))
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or day in seen:
            continue
        try:
            o, c, h, l = (float(row[key]) for key in ('open', 'close', 'high', 'low'))
            v = float(row.get('volume') or 0)
        except (TypeError, ValueError):
            continue
        if min(o, c, h, l) <= 0 or h < max(o, c) or l > min(o, c) or v < 0:
            continue
        seen.add(day)
        out.append(dict(date=day, open=o, close=c, high=h, low=l, volume=v))
    return sorted(out, key=lambda item: item['date'])


def seed_codes():
    with gzip.open(BASE / 'fixtures' / 'ma-close-seed-v1.json.gz', 'rt', encoding='utf-8') as stream:
        seed = json.load(stream)
    codes = sorted(code for code in seed['stocks']
                   if re.fullmatch(r'(sh(?:60|68)|sz(?:00|30))\d{4}', code) and not code.startswith('sh689'))
    return codes[::SAMPLE_STEP]


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description='年线回踩大样本日线归档')
    parser.add_argument('--out', default=str(BASE / 'docs' / 'ma250-pullback' / 'data'))
    parser.add_argument('--interval', type=float, default=0.7)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    out = Path(args.out)
    end = now_cn().date().isoformat()
    codes = seed_codes()[:args.limit or None]
    manifest = dict(sample='seed universe sorted, every 12th code; not selected by returns',
                    sample_step=SAMPLE_STEP, codes=len(codes), start=START, end=end,
                    interval=args.interval, collected_at=now_cn().isoformat(), failures={}, progress=0)
    failures = 0
    for index, code in enumerate(codes, 1):
        path = out / 'tencent' / f'{code}.json'
        if path.exists() and path.stat().st_size > 2:
            continue
        attempts = 0
        while True:
            try:
                rows = clean(Tencent().daily(code, START, end))
                if len(rows) < 400:
                    raise ValueError(f'returned only {len(rows)} bars')
                save(path, dict(code=code, source='tencent', adjustment='none',
                                fetched_at=now_cn().isoformat(), rows=rows))
                break
            except Exception as error:
                attempts += 1
                if attempts >= 3:
                    failures += 1
                    manifest['failures'][code] = type(error).__name__
                    break
                time.sleep(2 ** attempts)
            finally:
                time.sleep(args.interval)
        if failures >= 12:
            manifest['aborted'] = 'too many failures'
            break
        if index % 25 == 0 or index == len(codes):
            manifest['progress'] = index
            save(out / 'manifest.json', manifest)
            print(f'{index}/{len(codes)} codes, failures {failures}', flush=True)
    manifest['finished_at'] = now_cn().isoformat()
    save(out / 'manifest.json', manifest)
    print('done', manifest['progress'], 'failures', failures)


if __name__ == '__main__':
    main()
