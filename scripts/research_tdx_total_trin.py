"""Compare auction-like Money Tree and TDX day totals on author screenshot dates.

TRIN grouping uses Money Tree close vs its reference price for both sources;
TDX .day records lack an explicit adjusted previous close. Membership is only
the Money Tree universe; the archive's full listing completeness is not proven.
This script does not modify application data or production indicators.
"""
import csv
import hashlib
import json
import math
import struct
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path, PurePosixPath

from scripts.compare_author_trin_scopes import DIRECTORIES

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'docs/p250-research-20261029/tdx-hsjday-20261028.zip'
OUT=ROOT/'docs/trin-author-table-comparison-20261029/tdx-total-trin-sensitivity.json'
BAR=struct.Struct('<IIIIIfII');D=Decimal


def valid_tdx(bar, row):
    _,op,hi,lo,close,amount,vol,_=bar
    if min(op,hi,lo,close,vol)<=0 or not math.isfinite(amount) or amount<=0:return False
    return all(D(row[key])==D(value)/100 for key,value in [('open',op),('high',hi),('low',lo),('close',close)])


def aggregate(rows,tdx,allowed):
    chosen={k:r for k,r in rows.items() if k[-2:] in allowed and not (k.endswith('SH') and k.startswith('689'))}
    missing=sorted(chosen.keys()-tdx.keys()); mismatched=sorted(k for k in chosen.keys()&tdx.keys() if not valid_tdx(tdx[k],chosen[k]))
    volume_diff=[];amount_diff=[];totals={k:D(0) for k in ('up_money','down_money','up_tdx','down_tdx')};counts=Counter()
    for code in chosen.keys()&tdx.keys()-set(mismatched):
        row,bar=chosen[code],tdx[code];close,pre=D(row['close']),D(row['pre_close'])
        group='up' if close>pre else 'down' if close<pre else 'flat';counts[group]+=1
        money_amount=D(row['amount'])*1000;tdx_amount=D(str(bar[5]));money_volume=D(row['vol'])*100
        amount_delta=tdx_amount-money_amount;volume_delta=D(bar[6])-money_volume
        tolerance=max(D(1),abs(tdx_amount)*D(2)**-23)
        if abs(amount_delta)>tolerance:amount_diff.append({'symbol':code,'amount_delta_yuan':str(amount_delta)})
        if volume_delta:volume_diff.append({'symbol':code,'volume_delta_shares':str(volume_delta)})
        if group!='flat':totals[group+'_money']+=money_amount;totals[group+'_tdx']+=tdx_amount
    def trin(source):
        if missing or mismatched or not counts['up'] or not counts['down'] or min(totals.values())<=0:return None
        return float(D(counts['up'])*totals['down_'+source]/(D(counts['down'])*totals['up_'+source]))
    return {'expected':len(chosen),'matched':len(chosen)-len(missing)-len(mismatched),'missing':missing,
            'ohlc_or_tdx_invalid':mismatched,'counts':dict(counts),'money_trin_amount':trin('money'),'tdx_trin_amount':trin('tdx'),
            'amount_difference_count':len(amount_diff),'volume_difference_count':len(volume_diff),
            'amount_differences':amount_diff,'volume_differences':volume_diff}


def main():
    references=json.loads((ROOT/'fixtures/author-trin-reference.json').read_text())+json.loads((ROOT/'fixtures/author-trin-march-reference.json').read_text())
    data={};hashes={}
    for item in references:
        day=item['date'].replace('-','')
        path=next((d/(day+'.csv') for d in DIRECTORIES if (d/(day+'.csv')).exists()),None)
        if not path:raise ValueError('缺少底表 '+day)
        hashes[day]=hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        if not rows or any(r['trade_date']!=day for r in rows) or len({r['symbol'] for r in rows})!=len(rows):raise ValueError('重复或日期不符 '+day)
        data[day]={r['symbol'].replace('.',''):r for r in rows}
    target={int(day) for day in data};found={day:{} for day in data};wanted={k for d in data.values() for k in d}
    with zipfile.ZipFile(ARCHIVE) as z:
        seen=set()
        for info in z.infolist():
            name=PurePosixPath(info.filename.replace('\\','/')).name.lower()
            if not name.endswith('.day') or len(name)!=12:continue
            code=(name[2:8]+name[:2]).upper()
            if code not in wanted:continue
            if code in seen:raise ValueError('重复 TDX 文件 '+code)
            seen.add(code);raw=z.read(info)
            if len(raw)%BAR.size:raise ValueError('截断 '+code)
            prev=0
            for bar in BAR.iter_unpack(raw):
                date=bar[0]
                if date<=prev:raise ValueError('日期乱序 '+code)
                prev=date
                if date in target and code in data[str(date)]:found[str(date)][code]=bar
    digest=hashlib.sha256()
    with ARCHIVE.open('rb') as f:
        while chunk:=f.read(1024*1024):digest.update(chunk)
    results=[]
    for ref in sorted(references,key=lambda x:x['date']):
        day=ref['date'].replace('-','')
        for label,allowed in [('shsz',{'SH','SZ'}),('shszbj',{'SH','SZ','BJ'})]:
            results.append({'date':ref['date'],'author_trin':ref['trin'],'scope':label,**aggregate(data[day],found[day],allowed)})
    report={'tdx_archive_sha256':digest.hexdigest(),'money_sha256':hashes,'rows':results,
            'warning':'TDX 与 Money Tree 使用同一 Money Tree 名单、收盘价和昨收分组；不证明名单完整或数据来源独立。含大宗等各类差异只作敏感性比较，不据此确定作者方法。'}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('date','scope','author_trin','expected','matched','money_trin_amount','tdx_trin_amount','amount_difference_count','volume_difference_count')} for r in results],ensure_ascii=False))


if __name__=='__main__':main()
