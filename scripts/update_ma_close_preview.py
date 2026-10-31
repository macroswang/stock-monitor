"""Add an already-verified actual close to the local read-only browser preview."""
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from core.breadth import _next_verified_trading_day, add_standard_mcclellan, attach_historical_mcl_reference, summarize
from core.ma_reference import calculate, load_seed
from scripts.research_p250_history import OUT, ROOT


def main():
    day = '2026-10-29'
    evidence = json.loads((OUT / (day + '.closed-validation.json')).read_text())
    raw_path = OUT / (day + '.closed-raw.json')
    if not evidence['replay_models_match'] or hashlib.sha256(raw_path.read_bytes()).hexdigest() != evidence['raw_sha256']:
        raise ValueError('closed sample evidence changed')
    raw = json.loads(raw_path.read_text())
    summary = summarize(raw['quotes'], raw['codes'], raw['date'], raw['collected_at'], raw['suspended'])
    if (raw['date'] != day or summary['status'] != 'closed' or summary['missing']
        or summary['expected'] != evidence['expected'] or summary['covered'] != evidence['covered']):
        raise ValueError('closed sample no longer passes completeness checks')
    seed = load_seed(ROOT / 'fixtures/ma-close-seed-v1.json.gz')
    ma = calculate(seed, [raw], _next_verified_trading_day, summarize,
                   as_of=datetime.now(ZoneInfo('Asia/Shanghai')))
    if len(ma) != 1 or ma[0] != evidence['ma']:
        raise ValueError('MA result no longer matches independently replayed sample')
    summary['ma_daily'] = ma[0]
    summary['anchor_timestamp'] = raw['anchor']
    path = ROOT / 'public/breadth-preview.json'
    report = json.loads(path.read_text())
    rows = [r for r in report['days'] if r['date'] != day] + [summary]
    rows = add_standard_mcclellan(sorted(rows, key=lambda r: r['date']))
    history = json.loads((ROOT / 'fixtures/breadth-history-verified.json').read_text())
    report['days'] = attach_historical_mcl_reference(rows, history)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('preview updated', day, 'as a sampled close; actual user database was not accessed')


if __name__ == '__main__':
    main()
