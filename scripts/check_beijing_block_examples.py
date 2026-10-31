"""Compare observed BJ turnover gaps against cited public block-trade cases."""
import json
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/trin-author-table-comparison-20261029'


def compare(examples, crosscheck):
    by_date={r['date']:r for r in crosscheck['rows']}
    result=[]
    for event in examples:
        detail=by_date[event['date']]['bar_mismatches'][event['code']]
        shares=Decimal(str(detail['tdx_shares']))-Decimal(detail['money_shares'])
        amount=Decimal(detail['tdx_amount_yuan'])-Decimal(detail['money_amount_yuan'])
        # Public table amounts are rounded; TDX stores cash as float32.
        amount_error=abs(amount-Decimal(event['amount']))
        result.append({'date':event['date'],'code':event['code'],'url':event['url'],
                       'volume_difference':str(shares),'disclosed_block_volume':event['volume'],
                       'volume_matches':shares==event['volume'],
                       'amount_difference_yuan':str(amount),'disclosed_block_amount_yuan':event['amount'],
                       'amount_absolute_difference_yuan':str(amount_error),'amount_matches_within_32_yuan':amount_error<=32})
    return result


def main():
    examples=json.loads((ROOT/'fixtures/beijing-block-trade-examples.json').read_text())
    base=json.loads((OUT/'march-beijing-tdx-crosscheck.json').read_text())
    rows=compare(examples,base)
    report={'rows':rows,'warning':'公开大宗成交表金额经舍入；通达信金额为 float32。五个示例的差额吻合不证明所有日期、所有来源或作者采用何种口径。'}
    (OUT/'beijing-block-trade-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False))


if __name__=='__main__':main()
