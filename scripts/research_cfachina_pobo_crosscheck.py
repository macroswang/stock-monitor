"""Compare saved CFA delayed snapshots with dated third-party close tables."""
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from core.provider import CN
from .research_cfachina_option_crosscheck import OUT as CFA_OUT, parse
from .research_cffex_coverage import OUTPUT as IO_OUT, fetch, parse_close

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/author-trading-system-20261028/cfachina-pobo-20261031'
URLS = {'HO': 'https://webnewslt1.pobo.net.cn/DATA/STOCK/6806309.HTML',
        'MO': 'https://webnewslt1.pobo.net.cn/DATA/STOCK/6806311.HTML'}


def compare(prefix, payload, cfa_payload):
    close = parse_close(payload, prefix)
    volume = parse(cfa_payload, prefix, '2026-10-30')
    if set(close) != set(volume):
        raise ValueError('收盘表与协会合约集合不一致')
    cfa = {row['tradeCode']: row for row in cfa_payload['data']['delayList']}
    missing, wrong_volume, wrong_price = [], [], []
    for code, row in close.items():
        if row['volume'] is None:
            missing.append({'code': code, 'association_volume': volume[code]})
            continue
        if row['volume'] != volume[code]:
            wrong_volume.append(code)
        try:
            if Decimal(row['close'].replace(',', '')) != Decimal(cfa[code]['close']):
                wrong_price.append(code)
        except (InvalidOperation, TypeError):
            raise ValueError('收盘价无效') from None
    return {'contracts': len(close), 'missing_close_volume': missing,
            'volume_mismatch': wrong_volume, 'close_mismatch_on_nonblank_volume': wrong_price}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'observed_at': datetime.now(CN).isoformat(), 'date': '2026-10-30', 'groups': {}}
    for prefix in ('IO', 'HO', 'MO'):
        raw = (IO_OUT / 'pobo-20261030.html').read_bytes() if prefix == 'IO' else fetch(URLS[prefix])
        cfa_raw = (CFA_OUT / f'{prefix}.json').read_bytes()
        result = compare(prefix, raw, json.loads(cfa_raw))
        result.update(close_sha256=hashlib.sha256(raw).hexdigest(), cfa_sha256=hashlib.sha256(cfa_raw).hexdigest())
        (OUT / f'{prefix}.html').write_bytes(raw)
        report['groups'][prefix] = result
    report['note'] = '第三方收盘表与协会延时行情可能共享上游，均非本次取得的交易所结算原始文件。'
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k: {'contracts':v['contracts'],'blank':len(v['missing_close_volume']),
                          'volume_mismatch':len(v['volume_mismatch']),
                          'price_mismatch':len(v['close_mismatch_on_nonblank_volume'])}
                      for k,v in report['groups'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
