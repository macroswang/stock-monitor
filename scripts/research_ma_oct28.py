"""Compare a separately reconciled close with the author's dated MA table."""
import csv
import hashlib
import json

from scripts.analyze_trin_crosssections import reconcile
from scripts.build_mcl_history_fixture import build as verify_earlier
from scripts.research_author_p_hypothesis import ROOT, analyze, load_history


def main():
    source = ROOT / 'docs/ma-quote-bridge-20261029'
    day = '2026-10-28'
    raw = (source / '20261028.csv').read_bytes()
    check = json.loads((source / (day + '.crosscheck.json')).read_text())
    bao = json.loads((source / (day + '.baostock.json')).read_text())
    if check['date'] != day or hashlib.sha256(raw).hexdigest() != check['sha256']:
        raise ValueError('incorrect or changed Money Tree close')
    if bao['date'] != day or any(r['date'] != day for r in bao['daily']):
        raise ValueError('incorrect BaoStock close')
    with (source / '20261028.csv').open(encoding='utf-8-sig', newline='') as f:
        extra = list(csv.DictReader(f))
    if len(extra) < 4000 or len({r['symbol'] for r in extra}) != len(extra) or any(r['trade_date'] != '20261028' for r in extra):
        raise ValueError('invalid dated constituent data')
    actual = reconcile(extra, bao)
    for key in ('compared', 'mismatches', 'only_moneytree', 'only_baostock',
                'max_shares_difference', 'max_amount_difference_yuan'):
        if actual[key] != check[key]:
            raise ValueError('current raw files do not match the prior cross-check')
    if actual['mismatches'] or actual['only_moneytree'] or actual['only_baostock']:
        raise ValueError('cross-check has differences')
    verify_earlier()
    for entry in json.loads((ROOT / 'docs/trin-diagnostic-20261028/continuous-crosscheck.json').read_text()):
        with (ROOT / entry['moneytree_path']).open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        rechecked = reconcile(rows, json.loads((ROOT / entry['bao_path']).read_text()))
        for key in ('compared', 'mismatches', 'only_moneytree', 'only_baostock',
                    'max_shares_difference', 'max_amount_difference_yuan'):
            if rechecked[key] != entry[key]:
                raise ValueError(entry['date'] + ': prior constituent cross-check changed')
    history = load_history(lambda days, reader: analyze(
        days + [day], lambda d: extra if d == day else reader(d)))
    result = history[-1]
    author = next(r for r in json.loads((ROOT / 'fixtures/author-p-reference.json').read_text()) if r['date'] == day)
    output = {'date': day, 'author': author, 'reference': result, 'source_check': actual,
              'note': '独立历史收盘参照；非作者已确认公式，不是盘中结果或交易信号。'}
    (source / '2026-10-28.ma-comparison.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
