"""Compare predefined point-in-time SH/SZ scopes with video TRIN readings.

Uses saved BaoStock daily files only; never opens the application database.
Matches are descriptive, not proof of the speaker's undisclosed method.
"""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'docs/trin-reconstruction-20261028/baostock'
OUTPUT = ROOT / 'docs/trin-diagnostic-20261028/scope-results.json'
VIDEO = {'2026-03-23': .31, '2026-03-24': None, '2026-03-25': 1.4,
         '2026-10-22': .51, '2026-10-23': .93}


def contains(code, scope):
    if not code.startswith(('sh.60','sh.68','sz.00','sz.30')) or code.startswith('sh.689'):
        return False
    if scope == 'sh': return code.startswith('sh.')
    if scope == 'sz': return code.startswith('sz.')
    if scope == 'main': return code.startswith(('sh.60', 'sz.00'))
    if scope == 'growth': return code.startswith(('sh.68', 'sz.30'))
    return scope in ('all', 'exclude_st')


def compute(rows, scope, unit):
    groups = {'up': {'count':0, 'total':Decimal(0)}, 'down': {'count':0,'total':Decimal(0)}, 'flat': {'count':0,'total':Decimal(0)}}
    for row in rows:
        if not contains(row['code'],scope) or (scope == 'exclude_st' and row['isST'] == '1'):
            continue
        if row['tradestatus'] != '1' or Decimal(row['volume'] or '0') <= 0:
            continue
        close, previous = Decimal(row['close']),Decimal(row['preclose'])
        if min(close,previous) <= 0: raise ValueError('invalid price')
        group = 'up' if close>previous else 'down' if close<previous else 'flat'
        value = Decimal(row['volume' if unit=='shares' else 'amount'])
        if not value.is_finite() or value <= 0: raise ValueError('invalid total')
        groups[group]['count'] += 1
        groups[group]['total'] += value
    u,d = groups['up'],groups['down']
    return dict(advance=u['count'],decline=d['count'],flat=groups['flat']['count'],
                advance_total=str(u['total']),decline_total=str(d['total']),
                trin=float(u['count']*d['total']/(d['count']*u['total'])) if u['count'] and d['count'] and u['total'] else None)


def main():
    report=[]
    for day,target in VIDEO.items():
        payload=json.loads((INPUT/f'{day}.json').read_text(encoding='utf-8'))
        if payload['date'] != day or any(r['date'] != day for r in payload['daily']):
            raise ValueError('source date mismatch')
        for scope in ('all','exclude_st','sh','sz','main','growth'):
            for unit in ('shares','amount'):
                result=compute(payload['daily'],scope,unit)
                report.append(dict(date=day,video=target,scope=scope,unit=unit,**result))
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for scope in ('all','exclude_st','sh','sz','main','growth'):
        for unit in ('shares','amount'):
            x=[r for r in report if r['scope']==scope and r['unit']==unit]
            print(scope,unit,' '.join(f"{r['date'][5:]}:{r['trin']:.3f}" for r in x))


if __name__ == '__main__': main()
