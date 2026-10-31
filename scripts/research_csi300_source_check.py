"""Check dated BaoStock constituent snapshots against the archived CSI file."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.csi300 import REFERENCE_MEMBERS, REFERENCE_MEMBERS_SHA256, parse_members

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/csi300-source-check-20261031.json'
MARCH = ROOT / 'docs/author-trading-system-20261028/march-csi300-research-20261031.json'
DAYS = ('2026-03-23', '2026-06-16', '2026-10-30')


def check(snapshots, official, march):
    codes = {}
    for day in DAYS:
        rows = snapshots[day]
        if len(rows)!=300 or any(not re.fullmatch(r'(sh|sz)\.\d{6}',r['code']) or r['updateDate']>day for r in rows):
            raise ValueError('第三方成分格式或日期异常')
        current = {r['code'].replace('.','') for r in rows}
        if len(current)!=300:
            raise ValueError('第三方成分重复')
        codes[day]=current
    original = {r['code'].replace('.','') for r in march['members']}
    official_codes = set(official['codes'])
    if official['date']!='2026-10-30' or len(official_codes)!=300:
        raise ValueError('官方快照日期或数量异常')
    return {'march_matches_archived':codes[DAYS[0]]==original,
            'oct_matches_official':codes[DAYS[2]]==official_codes,
            'march_to_june_removed':sorted(codes[DAYS[0]]-codes[DAYS[1]]),
            'march_to_june_added':sorted(codes[DAYS[1]]-codes[DAYS[0]]),
            'oct_only_baostock':sorted(codes[DAYS[2]]-official_codes),
            'oct_only_official':sorted(official_codes-codes[DAYS[2]])}


def main():
    import baostock as bs
    conn=bs.login()
    if conn.error_code!='0':
        raise ValueError(conn.error_msg)
    snapshots={}
    try:
        for day in DAYS:
            response=bs.query_hs300_stocks(day)
            rows=[]
            while response.error_code=='0' and response.next():
                rows.append(dict(zip(response.fields,response.get_row_data())))
            if response.error_code!='0':
                raise ValueError(response.error_msg)
            snapshots[day]=rows
    finally:
        bs.logout()
    raw=REFERENCE_MEMBERS.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=REFERENCE_MEMBERS_SHA256:
        raise ValueError('官方文件哈希不符')
    official=parse_members(raw,datetime(2026,10,31,4,tzinfo=ZoneInfo('Asia/Shanghai')))
    march=json.loads(MARCH.read_text())
    result=check(snapshots,official,march)
    report={'observed_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'source':'BaoStock query_hs300_stocks', 'official_date':official['date'],
            'official_sha256':official['sha256'], 'snapshots':snapshots, 'result':result,
            'limitations':'只有10月30日有同日官方名单；3月和6月的变化证明接口返回不同日期的列表，不证明历史列表完全正确。'}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'march_matches_archived':result['march_matches_archived'],
                      'oct_matches_official':result['oct_matches_official'],
                      'march_to_june_removed':len(result['march_to_june_removed']),
                      'march_to_june_added':len(result['march_to_june_added'])},ensure_ascii=False))


if __name__=='__main__':
    main()
