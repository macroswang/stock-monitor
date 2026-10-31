"""Rebuild the browser preview from checked history and its existing live snapshots."""
import json
from pathlib import Path
from core.breadth import add_standard_mcclellan, attach_historical_mcl_reference, add_advance_decline, attach_historical_ad_reference

ROOT=Path(__file__).resolve().parents[1]


def main():
    path=ROOT/'public/breadth-preview.json'
    report=json.loads(path.read_text())
    history=json.loads((ROOT/'fixtures/breadth-history-verified.json').read_text())
    days={r['date']:r for r in history}
    for item in report['days']:
        if item.get('historical'):continue
        if item['date'] not in days or item.get('status')=='closed':days[item['date']]=item
    result=add_standard_mcclellan([days[d] for d in sorted(days)])
    report['days']=attach_historical_ad_reference(add_advance_decline(attach_historical_mcl_reference(result,history)),history)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('preview records:',len(report['days']))


if __name__=='__main__':main()
