"""Build dated MA breadth references from reconciled daily constituent bars."""
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.build_mcl_history_fixture import build as check_earlier
from scripts.build_trin_continuous_fixture import build as check_later
from scripts.research_author_p_hypothesis import load_history
from scripts.analyze_trin_crosssections import reconcile

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'fixtures/breadth-history-verified.json'


def main():
    earlier=check_earlier()
    later=check_later()
    checked={r['date']:r for r in earlier}
    if any(day not in checked or checked[day]['advance']!=r['advance'] or checked[day]['decline']!=r['decline'] for r in later for day in [r['date']]):
        raise ValueError('history changed since cross-check')
    # Recheck individual price bars, not just grouped totals: moving averages
    # depend on every stock's close even when its daily direction is unchanged.
    for check in json.loads((ROOT/'docs/trin-diagnostic-20261028/continuous-crosscheck.json').read_text()):
        with (ROOT/check['moneytree_path']).open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        bao=json.loads((ROOT/check['bao_path']).read_text())
        actual=reconcile(rows,bao)
        for key in ('compared','mismatches','only_moneytree','only_baostock','max_shares_difference','max_amount_difference_yuan'):
            if actual[key]!=check[key]:raise ValueError(check['date']+': raw historical cross-check changed')
    data=load_history()
    if len(data)!=100 or any(r['date'] not in checked for r in data):raise ValueError('missing reconciled input date')
    rows=json.loads(TARGET.read_text())
    by_date={r['date']:r for r in rows}
    generated=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    for item in data:
        for window in ('20','60','250'):
            c=item['windows'][window]
            if not 0<=c['above']<=c['eligible']<=item['active']:raise ValueError('invalid coverage')
        by_date[item['date']]['ma_breadth']=dict(date=item['date'],active=item['active'],windows=item['windows'],
            source='Money Tree 未复权日线；BaoStock 逐日逐股核对',computed_at=generated)
    TARGET.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print('wrote historical MA references:',len(data))


if __name__=='__main__':main()
