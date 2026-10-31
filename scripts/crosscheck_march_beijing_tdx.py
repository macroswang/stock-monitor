"""Cross-check March BJ daily bars; does not infer historic stock membership.

TDX .day layout and amount float units are hypotheses checked against the
other source. Previous raw close is compared separately: it may differ from
Money Tree's adjusted reference on corporate-action days.
"""
import csv
import hashlib
import json
import struct
import zipfile
from decimal import Decimal
from pathlib import Path, PurePosixPath
from scripts.analyze_trin_crosssections import compute

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'docs/p250-research-20261029/tdx-hsjday-20261028.zip'
MONEY=ROOT/'docs/trin-reconstruction-20261028/money-tree'
OUTPUT=ROOT/'docs/trin-author-table-comparison-20261029/march-beijing-tdx-crosscheck.json'
BAR=struct.Struct('<IIIIIfII')
DAYS=('20260323','20260324','20260325')
D=Decimal


def compare(money, bar, prior):
    _,op,hi,lo,close,amount,volume,_=bar
    changes=[]
    for key,value in [('open',op),('high',hi),('low',lo),('close',close)]:
        if D(money[key])!=D(value)/100:changes.append(key)
    shares=D(money['vol'])*100
    if shares!=D(volume):changes.append('volume')
    expected=D(money['amount'])*1000
    # TDX stores amount as binary float32; allow one relative ULP (or 1 yuan).
    amount_delta=abs(expected-D(str(amount)))
    tolerance=max(D(1),abs(D(str(amount)))*D(2)**-23)
    if amount_delta>tolerance:changes.append('amount')
    previous_diff=prior is None or D(money['pre_close'])!=D(prior)/100
    return {'fields':changes,'amount_difference_yuan':str(amount_delta),
            'money_shares':str(shares),'tdx_shares':volume,
            'money_amount_yuan':str(expected),'tdx_amount_yuan':str(amount),
            'previous_raw_close_differs':previous_diff,
            'previous_raw_close':str(D(prior)/100) if prior is not None else None,
            'money_previous_close':money['pre_close']}


def main():
    expected={};all_rows={};hashes={}
    for day in DAYS:
        path=MONEY/(day+'.csv');hashes[day]=hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding='utf-8-sig',newline='') as stream:
            data=list(csv.DictReader(stream))
        all_rows[day]=data
        rows=[r for r in data if r['symbol'].endswith('.BJ')]
        if not rows or any(r['trade_date']!=day for r in rows) or len({r['symbol'] for r in rows})!=len(rows):
            raise ValueError(day+' 北交所数据缺失、重复或日期错误')
        expected[day]={r['symbol'][:6]:r for r in rows}
    wanted={code for rows in expected.values() for code in rows}
    found={day:{} for day in DAYS};duplicates=[]
    with zipfile.ZipFile(ARCHIVE) as z:
        for item in z.infolist():
            name=PurePosixPath(item.filename.replace('\\','/')).name.lower()
            if not name.startswith('bj') or not name.endswith('.day') or name[2:-4] not in wanted:continue
            code=name[2:-4]
            data=z.read(item)
            if len(data)%BAR.size:raise ValueError('截断 '+name)
            last_date=0;last_close=None
            for bar in BAR.iter_unpack(data):
                date=bar[0]
                if date<=last_date:raise ValueError('日期乱序 '+name)
                last_date=date;day=str(date)
                if day in found and bar[6]>0:
                    if code in found[day]:duplicates.append((day,code))
                    found[day][code]=(bar,last_close)
                if bar[6]>0 and bar[4]>0:last_close=bar[4]
    if duplicates:raise ValueError('重复北交所证券 '+str(duplicates[:3]))
    summaries=[]
    for day in DAYS:
        exp=expected[day];got=found[day];common=exp.keys()&got.keys()
        checks={code:compare(exp[code],*got[code]) for code in sorted(common)}
        mixed_trin=None;mixed_invalid=[]
        if len(common)==len(exp) and not any(v['previous_raw_close_differs'] or
                any(k in v['fields'] for k in ('open','high','low','close')) for v in checks.values()):
            mixed=[]
            for row in all_rows[day]:
                copy=dict(row)
                if row['symbol'].endswith('.BJ'):
                    bar=got[row['symbol'][:6]][0]
                    copy['vol']=str(D(bar[6])/100)
                    copy['amount']=str(D(str(bar[5]))/1000)
                mixed.append(copy)
            computed=compute(mixed,{'SH','SZ','BJ'},True)
            mixed_trin=computed['trin_amount'];mixed_invalid=computed['invalid']
        summaries.append({'date':day,'money_tree_bj':len(exp),'tdx_matched':len(common),
                          'missing_in_tdx':sorted(exp.keys()-got.keys()),
                          'bar_mismatches':{k:v for k,v in checks.items() if v['fields']},
                          'previous_close_disagreements':{k:v for k,v in checks.items() if v['previous_raw_close_differs']},
                          'max_amount_difference_yuan':str(max((D(v['amount_difference_yuan']) for v in checks.values()),default=D(0))),
                          'research_mixed_source_trin_amount':mixed_trin,'research_mixed_source_invalid':mixed_invalid})
    digest=hashlib.sha256()
    with ARCHIVE.open('rb') as f:
        while chunk:=f.read(1024*1024):digest.update(chunk)
    report={'tdx_archive_sha256':digest.hexdigest(),'money_tree_sha256':hashes,'rows':summaries,
            'limitations':['比较 Money Tree 北交所名单内可匹配证券；未核验 TDX 全部上市/退市覆盖',
                           'TDX 前一成交日原始收盘不等于除权后的官方昨收',
                           '成交额 float32 容差按一 ULP 估算；上游数据血缘未知']}
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{'date':r['date'],'expected':r['money_tree_bj'],'matched':r['tdx_matched'],
                       'missing':len(r['missing_in_tdx']),'bar_mismatches':len(r['bar_mismatches']),
                       'previous_close_disagreements':len(r['previous_close_disagreements']),
                       'max_amount_difference_yuan':r['max_amount_difference_yuan'],
                       'research_mixed_source_trin_amount':r['research_mixed_source_trin_amount'],
                       'research_mixed_source_invalid':r['research_mixed_source_invalid']} for r in summaries],ensure_ascii=False))


if __name__=='__main__':main()
