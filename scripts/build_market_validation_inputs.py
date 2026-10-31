"""保存交叉核对的行情输入；研究用途，不访问模拟或真实账户。"""
import hashlib
import json
from pathlib import Path
from scripts.research_market_regime_extended import load_index
from scripts.research_etf_position import load_etf, OUT

ROOT = Path(__file__).resolve().parents[1]


def main():
    index = load_index()
    etf = load_etf(index)
    names = ['tencent-index-2025-2026.json', 'sina-index-2025-2026.json',
             'tencent-etf-raw.json', 'tencent-etf-qfq.json', 'sina-etf.json']
    result = {'version': 1, 'symbol': '510300',
              'provenance': '腾讯及新浪日线开收盘对照；上游独立性未知；行情事后采集',
              'input_sha256': {n: hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in names},
              'days': [{'date': r['date'], 'index_close': str(r['close']),
                        'etf_open': etf[r['date']][1], 'etf_close': etf[r['date']][2],
                        'etf_high': etf[r['date']][3], 'etf_low': etf[r['date']][4]}
                       for r in index]}
    target = ROOT/'fixtures/market-validation-inputs.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(f'{target}: {len(result["days"])} 条')


if __name__ == '__main__':
    main()
