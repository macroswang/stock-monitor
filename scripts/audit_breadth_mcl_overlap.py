"""Audit a possible MCL continuity bridge without changing app data or rules."""
import csv
import gzip
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/author-mcl-history-close-20261031'


def evaluate(day):
    quote_path=ROOT/'fixtures'/f'ma-reference-{day}.json.gz'
    daily_path=OUT/'daily'/(day.replace('-','')+'.csv')
    with gzip.open(quote_path,'rt',encoding='utf-8') as f:
        snapshot=json.load(f)
    with daily_path.open(encoding='utf-8-sig',newline='') as f:
        daily=list(csv.DictReader(f))
    if snapshot['date']!=day or any(r['trade_date']!=day.replace('-','') for r in daily):
        raise ValueError(day+': mixed dates')
    quotes={r['code']:r for r in snapshot['quotes'] if int(r['volume'])>0 and not r['code'].startswith('sh689')}
    eligible=[r for r in daily if r['symbol'].endswith(('.SH','.SZ')) and not r['symbol'].startswith('689')]
    records={r['symbol'].split('.')[1].lower()+r['symbol'].split('.')[0]:r for r in eligible}
    if len(quotes)!=sum(int(r['volume'])>0 and not r['code'].startswith('sh689') for r in snapshot['quotes']) or len(records)!=len(eligible):
        raise ValueError(day+': duplicate codes')
    price_mismatch=[];quantity_differences=[];groups={'up':0,'down':0,'flat':0}
    for code in sorted(quotes.keys()&records.keys()):
        q,r=quotes[code],records[code]
        price,previous=Decimal(q['price']),Decimal(q['previous_close'])
        if q['timestamp'][:10]!=day or price!=Decimal(r['close']) or previous!=Decimal(r['pre_close']):
            price_mismatch.append(code)
        group='up' if price>previous else 'down' if price<previous else 'flat'
        groups[group]+=1
        quantity_differences.append(Decimal(q['volume'])-Decimal(r['vol'])*100)
    return {'date':day,'snapshot_collected_at':snapshot['collected_at'],
            'snapshot_sha256':hashlib.sha256(quote_path.read_bytes()).hexdigest(),
            'daily_sha256':hashlib.sha256(daily_path.read_bytes()).hexdigest(),
            'quote_active':len(quotes),'daily_active':len(records),'matched':len(quantity_differences),
            'only_quote':sorted(quotes.keys()-records.keys()),'only_daily':sorted(records.keys()-quotes.keys()),
            'price_mismatch':price_mismatch,'groups':groups,
            'volume_differing_count':sum(x!=0 for x in quantity_differences),
            'max_absolute_volume_difference_shares':str(max(map(abs,quantity_differences),default=0)),
            'total_volume_difference_shares':str(sum(quantity_differences,Decimal(0)))}


def main():
    data={'rows':[evaluate(day) for day in ('2026-10-29','2026-10-30')],
          'limitations':'仅两日的收盘与事后补采，来源可能共享上游；不证明后续数据实时可用或任何作者公式，不改变正式数据源或信号。'}
    (OUT/'tencent-moneytree-overlap.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    for r in data['rows']:
        print(r['date'],'matched',r['matched'],'price mismatches',len(r['price_mismatch']),
              'max share difference',r['max_absolute_volume_difference_shares'])


if __name__=='__main__':
    main()
