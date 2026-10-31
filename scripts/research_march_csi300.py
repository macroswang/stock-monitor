"""Read-only March 23 CSI 300 membership and historical turnover comparison."""
import hashlib
import json
import re
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DAY = '2026-03-23'
RAW = ROOT / 'docs/trin-reconstruction-20261028/baostock/2026-03-23.json'
MONEY = ROOT / 'docs/trin-reconstruction-20261028/money-tree/20260323.csv'
OUT = ROOT / 'docs/author-trading-system-20261028/march-csi300-research-20261031.json'


def calculate(members, market):
    codes = [r['code'] for r in members]
    if len(codes) != 300 or len(set(codes)) != 300 or any(not re.fullmatch(r'(sh|sz)\.\d{6}', c) for c in codes):
        raise ValueError('沪深300成分名单缺失或重复')
    if any(r['updateDate'] != DAY for r in members):
        raise ValueError('成分名单日期不一致')
    stocks = {r['code']:r for r in market if r['code'].startswith(('sh.','sz.')) and not r['code'].startswith('sh.689') and r['tradestatus']=='1' and Decimal(r['volume'])>0}
    missing = sorted(set(codes)-set(stocks))
    if missing:
        raise ValueError('名单中存在无当日有效行情的股票：'+','.join(missing))
    def group(r):
        diff = Decimal(r['close'])-Decimal(r['preclose'])
        return 'up' if diff>0 else 'down' if diff<0 else 'flat'
    grouped = {key:[r for r in stocks.values() if group(r)==key] for key in ('up','down','flat')}
    core = {key:[r for r in grouped[key] if r['code'] in codes] for key in grouped}
    totals = {key:sum((Decimal(r['amount']) for r in grouped[key]), Decimal(0)) for key in grouped}
    core_totals = {key:sum((Decimal(r['amount']) for r in core[key]), Decimal(0)) for key in core}
    return {'market_count':{key:len(value) for key,value in grouped.items()},
            'member_count':{key:len(value) for key,value in core.items()},
            'market_turnover':{key:str(value) for key,value in totals.items()},
            'member_turnover':{key:str(value) for key,value in core_totals.items()},
            'member_share_percent':{key:float(core_totals[key]*100/totals[key]) if totals[key] else None for key in grouped}}


def check_market(market, money):
    bao = {r['code']:r for r in market if r['code'].startswith(('sh.','sz.')) and not r['code'].startswith('sh.689') and r['tradestatus']=='1' and Decimal(r['volume'])>0}
    other = {}
    for row in money:
        symbol = row['symbol']
        if not re.fullmatch(r'\d{6}\.(SH|SZ)', symbol) or symbol.startswith('689') or Decimal(row['vol'])<=0:
            continue
        if row['trade_date'] != DAY.replace('-',''):
            raise ValueError('Money Tree 日期不一致')
        code = symbol[-2:].lower()+'.'+symbol[:6]
        if code in other:
            raise ValueError('Money Tree 股票重复')
        other[code] = row
    if set(bao) != set(other):
        raise ValueError('两来源的活跃股票名单不一致')
    max_amount_diff = Decimal(0)
    for code,row in bao.items():
        peer = other[code]
        if Decimal(row['close']) != Decimal(peer['close']) or Decimal(row['preclose']) != Decimal(peer['pre_close']) or Decimal(row['volume']) != Decimal(peer['vol'])*100:
            raise ValueError('两来源价格、昨收或成交股数不一致：'+code)
        delta = abs(Decimal(row['amount'])-Decimal(peer['amount'])*1000)
        max_amount_diff = max(max_amount_diff,delta)
        if delta>Decimal('0.5'):
            raise ValueError('两来源成交额不一致：'+code)
    return {'stocks':len(bao),'max_turnover_difference_yuan':str(max_amount_diff)}


def main():
    import baostock as bs
    login = bs.login()
    if login.error_code != '0':
        raise ValueError('BaoStock 登录失败：'+login.error_msg)
    try:
        result = bs.query_hs300_stocks(DAY)
        members = []
        while result.error_code == '0' and result.next():
            members.append(dict(zip(result.fields,result.get_row_data())))
        if result.error_code != '0':
            raise ValueError('成分查询失败：'+result.error_msg)
    finally:
        bs.logout()
    source = RAW.read_bytes()
    payload = json.loads(source)
    money_source = MONEY.read_bytes()
    with MONEY.open(encoding='utf-8-sig',newline='') as stream:
        crosscheck = check_market(payload['daily'], list(csv.DictReader(stream)))
    report = {'date':DAY,'member_observed_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'member_source':'BaoStock query_hs300_stocks', 'price_source':'BaoStock 日线',
              'price_captured_at':payload['fetched_at'],'price_sha256':hashlib.sha256(source).hexdigest(),
              'money_tree_sha256':hashlib.sha256(money_source).hexdigest(), 'market_crosscheck':crosscheck,
              'members':members,'result':calculate(members,payload['daily']),
              'limitations':'历史成分是第三方事后查询结果，尚未与交易所当日完整名单交叉核对；成交额不能识别买卖方向或投资者。'}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['result'],ensure_ascii=False))


if __name__ == '__main__':
    main()
