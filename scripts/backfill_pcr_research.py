"""Collect public SSE option statistics for a longer research comparison.

Uses a temporary database only; does not read or change user accounts or watchlists.
"""
import json
import tempfile
import time
from pathlib import Path

from core.option_pcr import HISTORY, OptionPCR, eligible_sessions, fetch_day, parse_day
from core.provider import now_cn
from core.store import Store


def main():
    now = now_cn()
    dates = eligible_sessions(now, 50)
    if len(dates) != 50:
        raise SystemExit('交易日历不足，未更新历史数据')
    paths={'510050':HISTORY,'510300':HISTORY.with_name('sse300-pcr-verified.json')}
    items={code:{r['date']:r for r in json.loads(path.read_text(encoding='utf-8'))} for code,path in paths.items()}
    needed=[d for d in dates if any(d not in items[c] for c in paths)]
    responses=[]
    for day in needed:
        a,payload=fetch_day(day,now.isoformat())
        b=parse_day(payload,day,now.isoformat(),'510300')
        items['510050'][day]=a;items['510300'][day]=b
        responses.append({'requested_date':day,'response':payload})
        time.sleep(.15)
    for code in paths:
        if not all(d in items[code] for d in dates):raise SystemExit('缺少交易日，未写入')
    out=Path('docs/pcr-comparison-validation-20261029');out.mkdir(parents=True,exist_ok=True)
    (out/'raw.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'report.json').write_text(json.dumps(dict(collected_at=now.isoformat(),requested_dates=needed,
        maintained_dates=dates,source='https://www.sse.com.cn/assortment/options/date/',
        note='两只ETF期权的20日通道分别计算；既非全市场也未证明与作者一致。'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for code,path in paths.items():
        values=[items[code][d] for d in sorted(items[code])]
        path.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with tempfile.TemporaryDirectory() as root:
        store=Store(Path(root)/'preview.sqlite3')
        for code,name in [('510050','pcr-preview.json'),('510300','pcr300-preview.json')]:
            report=OptionPCR(store,code).view(now)
            Path('public',name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            selected=next((x for x in report['days'] if x['date']=='2026-09-30'),None)
            print(code,len(report['days']),'09-30',selected and selected['pcr'],selected and selected['band_lower'],selected and selected['band_upper'])
    print('新取得',len(needed),'个交易日，范围',dates[0],dates[-1])


if __name__=='__main__':main()
