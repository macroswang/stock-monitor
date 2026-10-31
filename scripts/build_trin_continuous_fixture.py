"""Add fully cross-checked dated history as read-only display fixtures.

Requires the complete 40-day cross-check, retains the existing March dates,
and does not open the user's app database.
"""
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.analyze_trin_crosssections import compute
from scripts.build_breadth_history import build as build_original

RESEARCH=ROOT/'docs/trin-sensitivity-20261028/summary.json'
CHECK=ROOT/'docs/trin-diagnostic-20261028/continuous-crosscheck.json'
INDEX=ROOT/'docs/trin-diagnostic-20261028/index-daily.json'
TARGET=ROOT/'fixtures/breadth-history-verified.json'


def build():
    research=json.loads(RESEARCH.read_text(encoding='utf-8'))
    checks=json.loads(CHECK.read_text(encoding='utf-8'))
    dates=[r['date'] for r in research['results']]
    if research['expected']!=40 or research['failed'] or len(checks)!=40 or [r['date'] for r in checks]!=dates:
        raise ValueError('40 trading days not fully cross-checked')
    indices=json.loads(INDEX.read_text(encoding='utf-8'))
    if any([r['date'] for r in rows]!=dates for rows in indices.values()):
        raise ValueError('index dates do not match the continuous history')
    initial={r['date']:r for r in build_original()}
    for check in checks:
        day=check['date']
        if (check['mismatches'] or check['only_moneytree'] or check['only_baostock'] or
            Decimal(check['max_shares_difference'])!=0 or Decimal(check['max_amount_difference_yuan'])>Decimal('0.5')):
            raise ValueError(f'{day}: provider data not fully reconciled')
        with (ROOT/check['moneytree_path']).open(encoding='utf-8-sig',newline='') as f:
            moneytree=list(csv.DictReader(f))
        independent=compute(moneytree,{'SH','SZ'},False)
        if independent['invalid']:raise ValueError(f'{day}: invalid Money Tree row')
        bao=json.loads((ROOT/check['bao_path']).read_text(encoding='utf-8'))
        rows=[r for r in bao['daily'] if r['code'].startswith(('sh.60','sh.68','sz.00','sz.30')) and not r['code'].startswith('sh.689')]
        groups={k:dict(count=0,volume=0,amount=Decimal(0)) for k in ('advance','decline','flat')}
        suspended=0
        for r in rows:
            volume=int(r['volume'] or 0)
            if r['tradestatus']!='1' or volume==0:
                suspended+=1;continue
            price,previous=Decimal(r['close']),Decimal(r['preclose'])
            amount=Decimal(r['amount'])
            if min(price,previous,amount)<=0:raise ValueError(f'{day}: invalid BaoStock row')
            group='advance' if price>previous else 'decline' if price<previous else 'flat'
            groups[group]['count']+=1;groups[group]['volume']+=volume;groups[group]['amount']+=amount
        a,d,f=(groups[k] for k in ('advance','decline','flat'))
        trin=a['count']*d['volume']/(d['count']*a['volume'])
        trin_amount=float(a['count']*d['amount']/(d['count']*a['amount']))
        if (a['count'],d['count'],f['count'],a['volume'],d['volume']) != (
            independent['counts']['up'],independent['counts']['down'],independent['counts'].get('flat',0),
            int(Decimal(independent['up_volume_shares'])),int(Decimal(independent['down_volume_shares']))):
            raise ValueError(f'{day}: grouped totals disagree')
        if abs(trin-independent['trin_volume'])>1e-12 or abs(trin_amount-independent['trin_amount'])>1e-6:
            raise ValueError(f'{day}: group ratio differs between sources')
        initial[day]=dict(date=day,trin=trin,trin_amount=trin_amount,advance=a['count'],decline=d['count'],flat=f['count'],
                          advance_volume=a['volume'],decline_volume=d['volume'],flat_volume=f['volume'],
                          advance_amount=float(a['amount']),decline_amount=float(d['amount']),
                          advancing_percent=100*a['count']/(a['count']+d['count']+f['count']),
                          advancing_volume_percent=100*a['volume']/(a['volume']+d['volume']),
                          advancing_amount_percent=float(100*a['amount']/(a['amount']+d['amount'])),
                          expected=len(rows),covered=len(rows),suspended=suspended,missing=0,status='closed',historical=True,
                          first_quote=None,last_quote=None,collected_at=bao['fetched_at'],
                          source='BaoStock 收盘日线；Money Tree 逐股交叉核对',
                          universe='沪深当日日线股票，排除689类存托凭证；近似新浪列表')
    return [initial[d] for d in sorted(initial)]


if __name__=='__main__':
    data=build()
    TARGET.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'生成 {len(data)} 天历史，其中连续核验 40 天：{TARGET}')
