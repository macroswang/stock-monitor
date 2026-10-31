"""Build the checked historical fixture from the retained dated research inputs."""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / 'docs/trin-reconstruction-20261028'
DAYS = ('2026-03-23', '2026-03-24', '2026-03-25', '2026-10-22', '2026-10-23')


def build():
    analysis = {x['date']: x for x in json.loads((RESEARCH / 'money-tree-analysis.json').read_text())}
    output = []
    for day in DAYS:
        research = analysis[day]
        checks = research['bao_reconciliation']
        if checks['mismatches'] or checks['only_moneytree'] or checks['only_baostock'] or research['shsz_no_cdr']['invalid']:
            raise ValueError(f'{day}: incomplete reconciliation')
        raw = json.loads((RESEARCH / 'baostock' / f'{day}.json').read_text())
        rows = [r for r in raw['daily'] if r['code'].startswith(('sh.60', 'sh.68', 'sz.00', 'sz.30')) and not r['code'].startswith('sh.689')]
        groups = {key: {'count': 0, 'volume': 0, 'amount': Decimal(0)} for key in ('advance', 'decline', 'flat')}
        suspended = 0
        for r in rows:
            volume = int(r['volume'] or 0)
            if r['tradestatus'] != '1' or volume == 0:
                suspended += 1
                continue
            price, previous = Decimal(r['close']), Decimal(r['preclose'])
            group = 'advance' if price > previous else 'decline' if price < previous else 'flat'
            groups[group]['count'] += 1
            groups[group]['volume'] += volume
            amount = Decimal(r['amount'])
            if not amount.is_finite() or amount <= 0:
                raise ValueError(f'{day}: invalid turnover')
            groups[group]['amount'] += amount
        a, d, f = (groups[k] for k in ('advance', 'decline', 'flat'))
        trin = a['count'] * d['volume'] / (d['count'] * a['volume'])
        check = research['shsz_no_cdr']
        if (a['count'], d['count'], f['count'], a['volume'], d['volume']) != (check['counts']['up'], check['counts']['down'], check['counts'].get('flat', 0), int(Decimal(check['up_volume_shares'])), int(Decimal(check['down_volume_shares']))) or abs(trin - check['trin_volume']) > 1e-12:
            raise ValueError(f'{day}: calculated totals disagree')
        if abs(float(a['count'] * d['amount'] / (d['count'] * a['amount'])) - check['trin_amount']) > 1e-6:
            raise ValueError(f'{day}: turnover ratio disagrees')
        output.append(dict(date=day, trin=trin, advance=a['count'], decline=d['count'], flat=f['count'],
                           advance_volume=a['volume'], decline_volume=d['volume'], flat_volume=f['volume'],
                           trin_amount=float(a['count'] * d['amount'] / (d['count'] * a['amount'])),
                           advance_amount=float(a['amount']), decline_amount=float(d['amount']),
                           advancing_amount_percent=float(100 * a['amount'] / (a['amount'] + d['amount'])),
                           advancing_percent=100 * a['count'] / (a['count'] + d['count'] + f['count']),
                           advancing_volume_percent=100 * a['volume'] / (a['volume'] + d['volume']),
                           expected=len(rows), covered=len(rows), suspended=suspended, missing=0,
                           status='closed', historical=True, first_quote=None, last_quote=None,
                           collected_at=raw['fetched_at'], source='BaoStock 收盘日线；Money Tree 逐股交叉核对',
                           universe='沪深当日日线股票，排除689类存托凭证；近似新浪列表'))
    return output


if __name__ == '__main__':
    target = ROOT / 'fixtures/breadth-history-verified.json'
    result = build()
    if target.exists() and len(json.loads(target.read_text(encoding='utf-8'))) > len(result):
        raise ValueError('现有历史数据更多，拒绝覆盖；请使用连续历史构建脚本')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'生成 {len(DAYS)} 个已复核日期：{target}')
