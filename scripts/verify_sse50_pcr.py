"""Fetch and preserve public SSE daily option statistics for a local preview.

No user database, brokerage access, orders or monitoring settings are touched.
"""
import json
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from core.option_pcr import eligible_sessions, fetch_day, parse_day, HISTORY, _valid_record
from core.provider import now_cn


def main():
    now = now_cn()
    sessions = eligible_sessions(now, 30)
    if len(sessions) < 30:
        raise SystemExit('缺少完整的已核验交易日历，不生成预览数据')
    observed, observed_300, raw = [], [], []
    for day in sessions:
        data, response = fetch_day(day, now.isoformat())
        observed.append(data)
        observed_300.append(parse_day(response, day, now.isoformat(), '510300'))
        raw.append({'requested_date':day, 'response':response})
        time.sleep(.15)
    # Independent public presentation of the same SSE figures, rounded to 0.01 万张.
    check = next((x['response']['result'] for x in raw if x['requested_date'] == '2026-09-22'), None)
    checks = {}
    if check:
        for field, printed in [('CALL_VOLUME','381.84'),('PUT_VOLUME','264.88')]:
            count = sum(int(str(x[field]).replace(',','')) for x in check)
            rounded = (Decimal(count)/10000).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            if rounded != Decimal(printed):
                raise SystemExit(f'上交所 9 月月报与日统计的 {field} 不一致')
            checks[field] = {'daily_sum_contracts':count, 'monthly_wan_rounded':str(rounded)}
    out = Path('docs/sse50-pcr-validation-20261028')
    out.mkdir(parents=True, exist_ok=True)
    (out/'raw.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out/'report.json').write_text(json.dumps({'retrieved_at':now.isoformat(),'dates':sessions,
        'products':['上证50ETF华夏期权（510050）','沪深300ETF华泰柏瑞期权（510300）'],'monthly_crosscheck':checks,
        'monthly_source':'https://www.sse.com.cn/aboutus/publication/monthly/report/',
        'daily_source':'https://www.sse.com.cn/assortment/options/date/'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for path, code, new in [(HISTORY,'510050',observed),(HISTORY.with_name('sse300-pcr-verified.json'),'510300',observed_300)]:
        old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        merged = {r['date']:r for r in old if _valid_record(r,code)}
        merged.update({r['date']:r for r in new})
        path.write_text(json.dumps([merged[d] for d in sorted(merged)],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'成功核对并保存两个标的各 {len(observed)} 个交易日：{sessions[0]} 至 {sessions[-1]}；月报复核 {checks}')


if __name__ == '__main__':
    main()
