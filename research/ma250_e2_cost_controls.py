"""Fair matched entry-price stresses, separate from candidate selection."""
import hashlib
import json
import sys
from pathlib import Path

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from research.ma250_e2_diagnostics import OUT,PANEL_NAMES,SOURCE,metrics
from research.ma250_optimization import DATA,Portfolio,digest
from research.ma250_breadth import load_panel


def main():
    plan=json.loads((OUT/'cost-control-plan.json').read_text())
    source=json.loads((OUT/'results.json').read_text())
    assert digest({k:v for k,v in source.items() if k!='elapsed_seconds'})==plan['source_content_digest']
    raw=load_panel(DATA/'tencent');qfq=load_panel(DATA/'baostock-qfq');common=set(raw)&set(qfq)
    panels={'raw415':raw,'raw_matched217':{c:raw[c] for c in common},'qfq217':qfq};result={}
    for name,series in panels.items():
        events=json.loads((SOURCE/(name+'-events.json')).read_text());context=Portfolio(series);rows={}
        for bp in plan['entry_markup_basis_points']:
            rows[str(bp)]={pid:metrics(context.run([dict(e,entry=e['entry']*(1+bp/10000)) for e in events[pid]]))
                           for pid in ('B0','E2')}
        result[name]=rows
    (OUT/'cost-controls.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(result,ensure_ascii=False,indent=1))


if __name__=='__main__':main()
