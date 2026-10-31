"""Research P250 with BaoStock, and disclose overlap with another source."""
import csv
import hashlib
import json
from pathlib import Path

from scripts.analyze_p250_history import next_research_day
from scripts.analyze_trin_crosssections import reconcile
from scripts.build_mcl_history_fixture import build as verify_earlier
from scripts.build_trin_continuous_fixture import build as verify_later
from scripts.research_author_p_hypothesis import analyze
from scripts.research_ma_oct28 import main as verify_oct28
from scripts.research_ma_quote_bridge import ROOT, rows_for_day
from scripts.research_p250_history import OUT


def main():
    source = json.loads((OUT / 'baostock-collection.json').read_text())
    earlier = json.loads((ROOT / 'docs/author-mcl-history-20261029/collection.json').read_text())
    later = json.loads((ROOT / 'docs/trin-sensitivity-20261028/summary.json').read_text())
    if (source['failures'] or len(source['records']) != 171 or len(source['expected']) != 171
        or set(source['records']) != set(source['expected'])):
        raise ValueError('BaoStock history incomplete')
    if earlier['failures'] or later['failed']:
        raise ValueError('existing history incomplete')
    days = source['expected'] + earlier['expected'] + [r['date'] for r in later['results']] + ['2026-10-28']
    if len(days) != 272:
        raise ValueError('expected 272 consecutive dates')
    # Recheck the actual previously reconciled bars, including close prices:
    # grouped TRIN totals alone cannot establish an MA input is unchanged.
    verify_earlier()
    verify_later()
    verify_oct28()
    checks = json.loads((ROOT / 'docs/trin-diagnostic-20261028/continuous-crosscheck.json').read_text())
    for check in checks:
        with (ROOT / check['moneytree_path']).open(encoding='utf-8-sig', newline='') as f:
            original = list(csv.DictReader(f))
        other = json.loads((ROOT / check['bao_path']).read_text())
        actual = reconcile(original, other)
        for key in ('compared', 'mismatches', 'only_moneytree', 'only_baostock',
                    'max_shares_difference', 'max_amount_difference_yuan'):
            if actual[key] != check[key]:
                raise ValueError(check['date'] + ': prior constituent cross-check changed')
    overlap = []

    def read_rows(day):
        record = source['records'].get(day)
        if record is None:
            return rows_for_day(day)
        path = ROOT / record['path']
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError(day + ': source file changed')
        bao = json.loads(data)
        rows = bao['daily']
        if bao['date'] != day or any(r['date'] != day for r in rows):
            raise ValueError(day + ': mixed dates')
        csv_path = OUT / 'daily' / (day.replace('-', '') + '.csv')
        if csv_path.exists():
            with csv_path.open(encoding='utf-8-sig', newline='') as f:
                other = list(csv.DictReader(f))
            if any(r.get('trade_date') != day.replace('-', '') for r in other):
                raise ValueError(day + ': second source mixed dates')
            overlap.append({'date': day, **reconcile(other, bao)})
        result = []
        for row in rows:
            if row['tradestatus'] != '1' or int(row['volume'] or 0) == 0:
                continue
            exchange, code = row['code'].split('.')
            if exchange not in ('sh', 'sz'):
                continue
            result.append({'symbol': code + '.' + exchange.upper(), 'close': row['close']})
        return result

    history = analyze(days, read_rows, windows=(250,), next_day=next_research_day)
    by_date = {r['date']: r for r in history}
    author = json.loads((ROOT / 'fixtures/author-p-reference.json').read_text())
    out = []
    for item in author:
        row = by_date.get(item['date'])
        if row:
            out.append({'date': item['date'], 'author_p250': item['p250'], **row['windows']['250']})
    if len(out) != 10 or any(r['percent'] is None for r in out):
        raise ValueError('screenshot comparison incomplete')
    (OUT / 'baostock-overlap.json').write_text(json.dumps(overlap, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'baostock-comparison.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    eligible = [{'date': r['date'], **r['windows']['250']} for r in history
                if r['windows']['250']['percent'] is not None]
    (OUT / 'baostock-daily-research.json').write_text(json.dumps(eligible, ensure_ascii=False, indent=2) + '\n')
    mismatch_days = [r['date'] for r in overlap if r['mismatches'] or r['only_moneytree'] or r['only_baostock']]
    error = sum(abs(r['author_p250'] - r['percent']) for r in out) / len(out)
    lines = ['# 作者 P250 与 250 日均线宽度假设', '',
             '研究假设：当日收盘高于该股最近 250 个连续交易日（含当日）未复权简单均线的沪深活跃股票占比，排除 689。窗口中缺日的股票不计入分母。2025 年日历依据[上交所休市安排](https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20241223_10767110.shtml)。', '',
             f'较早 171 日使用 BaoStock，后 101 日使用已比对的 Money Tree。较早 171 日中 {len(overlap)} 日有 Money Tree 重叠数据，逐股核对出现价格、成交量或名单差异的日期：{", ".join(mismatch_days) if mismatch_days else "无"}；上游血缘未知。其他来源的收盘价核对见 [通达信逐日结果](tdx-close-crosscheck.json)。本表仅为研究，作者口径尚未确认。', '',
             '| 日期 | 作者 P250 | 本机 250 日参照 | 有效样本数 |', '|---|---:|---:|---:|']
    for r in out:
        lines.append(f"| {r['date']} | {r['author_p250']:.1f}% | {r['percent']:.2f}% | {r['eligible']} |")
    lines.extend(['', f'以上 {len(out)} 个日期平均绝对差为 {error:.2f} 个百分点；截图不是随机样本。',
                  '作者数值来自[视频截图 9 月](../author-trading-system-20261028/source-samples/chart-score-0218.png)与[10 月](../author-trading-system-20261028/source-samples/october-score-0017.png)。作者股票池、复权和停牌处理未知；未复权价格可能受除权影响。接近不等于已确认作者公式，也不能作为盈利或交易信号。'])
    (OUT / 'P250假设对照.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('overlap', len(overlap), 'mismatch days', mismatch_days, 'mean absolute difference', error, flush=True)
    print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
