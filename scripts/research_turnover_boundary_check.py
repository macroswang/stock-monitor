"""Compare dated BaoStock close rows with saved Sina/Tencent boundary cases."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/author-trading-system-20261028'


def compare_cases(snapshot, history, quote_snapshot):
    cases = snapshot['boundary_disagreements']
    dated = {item['code'].replace('.', ''): item for item in history['rows']}
    result = []
    for item in cases:
        code = item['code']
        match = dated.get(code, {})
        rows = match.get('rows', [])
        if len(rows) != 1 or rows[0].get('date') != snapshot['anchor_timestamp'][:10] or rows[0].get('tradestatus') != '1':
            raise ValueError(f'{code} 缺少同日交易日线')
        quote = quote_snapshot.get('quotes', {}).get(code, {})
        try:
            aligned = (quote['timestamp'] == item['tencent_timestamp']
                       and Decimal(quote['price']) == Decimal(rows[0]['close'])
                       and Decimal(quote['previous_close']) == Decimal(rows[0]['preclose'])
                       and abs(int(quote['volume'])-int(rows[0]['volume'])) <= 50)
        except (KeyError, TypeError, ValueError):
            aligned = False
        if not aligned:
            raise ValueError(f'{code} 腾讯报价与历史日线日期、价格或成交量不一致')
        bao, sina, tencent = (Decimal(str(v)) for v in (rows[0]['turn'],item['sina_turn'],item['tencent_turn']))
        if not all(v.is_finite() and v>=0 for v in (bao,sina,tencent)):
            raise ValueError(f'{code} 换手率无效')
        result.append({'code':code, 'date':rows[0]['date'], 'bao_turn':str(bao),
                       'sina_turn':str(sina), 'tencent_turn':str(tencent),
                       'bao_sina_difference':str(abs(bao-sina)),
                       'bao_tencent_difference':str(abs(bao-tencent)),
                       'bao_above_or_equal_5':bao>=5,
                       'close_and_previous_close_match':True,
                       'volume_difference_shares':abs(int(quote['volume'])-int(rows[0]['volume']))})
    return result


def main():
    paths = [DOCS/'turnover-close-crosscheck-20261031.json', DOCS/'turnover-boundary-baostock-20261031.json',
             DOCS/'turnover-boundary-tencent-20261031.json']
    raw = [path.read_bytes() for path in paths]
    snapshot, history, quotes = [json.loads(value) for value in raw]
    report = {'rows':compare_cases(snapshot,history,quotes),
              'inputs_sha256':{path.name:hashlib.sha256(value).hexdigest() for path,value in zip(paths,raw)},
              'warning':'3只边界案例的事后对照；新浪列表未自带日期、各来源上游血缘未知，不能推广为全市场核验或确定作者口径。'}
    (DOCS/'turnover-boundary-comparison-20261031.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__': main()
