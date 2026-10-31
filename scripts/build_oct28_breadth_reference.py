"""Add a cross-checked historical close; never touch user databases or orders."""
import csv
import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from scripts.analyze_trin_crosssections import compute
from scripts.research_author_p_hypothesis import ROOT
from scripts.research_ma_oct28 import main as verify_ma


def build():
    verify_ma()
    source = ROOT / 'docs/ma-quote-bridge-20261029'
    bao = json.loads((source / '2026-10-28.baostock.json').read_text())
    ma = json.loads((source / '2026-10-28.ma-comparison.json').read_text())
    with (source / '20261028.csv').open(encoding='utf-8-sig', newline='') as f:
        other = compute(list(csv.DictReader(f)), {'SH', 'SZ'}, False)
    if other['invalid']:
        raise ValueError('invalid independent market data')
    stock = [r for r in bao['daily'] if r['code'].startswith(('sh.60', 'sh.68', 'sz.00', 'sz.30'))
             and not r['code'].startswith('sh.689')]
    groups = {k: {'count': 0, 'volume': 0, 'amount': Decimal(0)} for k in ('advance', 'decline', 'flat')}
    suspended = 0
    for r in stock:
        volume = int(r['volume'] or 0)
        if r['tradestatus'] != '1' or volume == 0:
            suspended += 1
            continue
        price, previous, amount = Decimal(r['close']), Decimal(r['preclose']), Decimal(r['amount'])
        if min(price, previous, amount) <= 0:
            raise ValueError('invalid active BaoStock row')
        group = 'advance' if price > previous else 'decline' if price < previous else 'flat'
        groups[group]['count'] += 1
        groups[group]['volume'] += volume
        groups[group]['amount'] += amount
    a, d, f = (groups[k] for k in ('advance', 'decline', 'flat'))
    if (a['count'], d['count'], f['count'], a['volume'], d['volume']) != (
        other['counts']['up'], other['counts']['down'], other['counts'].get('flat', 0),
        int(Decimal(other['up_volume_shares'])), int(Decimal(other['down_volume_shares']))):
        raise ValueError('grouped values differ from independent source')
    trin = a['count'] * d['volume'] / (d['count'] * a['volume'])
    amount_trin = float(a['count'] * d['amount'] / (d['count'] * a['amount']))
    if abs(trin - other['trin_volume']) > 1e-12 or abs(amount_trin - other['trin_amount']) > 1e-6:
        raise ValueError('ratio differs from independent source')
    data = ma['reference']
    if data['date'] != '2026-10-28' or data['active'] != a['count'] + d['count'] + f['count']:
        raise ValueError('MA and cross-checked stock lists differ')
    return dict(date='2026-10-28', trin=trin, trin_amount=amount_trin, advance=a['count'], decline=d['count'],
        flat=f['count'], advance_volume=a['volume'], decline_volume=d['volume'], flat_volume=f['volume'],
        advance_amount=float(a['amount']), decline_amount=float(d['amount']),
        advancing_percent=100*a['count']/(a['count']+d['count']+f['count']),
        advancing_volume_percent=100*a['volume']/(a['volume']+d['volume']),
        advancing_amount_percent=float(100*a['amount']/(a['amount']+d['amount'])),
        expected=len(stock), covered=len(stock), suspended=suspended, missing=0, status='closed', historical=True,
        first_quote=None, last_quote=None, collected_at=bao['fetched_at'],
        source='BaoStock 收盘日线；Money Tree 逐股交叉核对',
        universe='沪深当日日线股票，排除689类存托凭证；近似新浪列表',
        ma_breadth=dict(date=data['date'], active=data['active'], windows=data['windows'],
            source='Money Tree 未复权日线；BaoStock 逐日逐股核对',
            computed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    row = build()
    path = ROOT / 'fixtures/breadth-history-verified.json'
    rows = json.loads(path.read_text())
    if args.write:
        rows = [r for r in rows if r['date'] != row['date']] + [row]
        rows.sort(key=lambda r: r['date'])
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'date': row['date'], 'advance': row['advance'], 'decline': row['decline'],
        'ma': row['ma_breadth']['windows'], 'written': args.write}, ensure_ascii=False))
