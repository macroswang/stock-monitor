"""Research-only BaoStock / TDX close comparison, with no archive extraction.

TDX archive record layout is a hypothesis to be tested against dated bars;
coverage and every mismatch are reported, not silently repaired.
"""
import hashlib
import json
import re
import struct
import zipfile
from decimal import Decimal
from pathlib import PurePosixPath

from scripts.research_p250_history import OUT, ROOT

BAR = struct.Struct('<IIIIIfII')
SYMBOL = re.compile(r'^(sh(?:60|68)\d{4}|sz(?:00|30)\d{4})\.day$', re.I)


def bars_for_dates(data, wanted):
    if len(data) % BAR.size:
        raise ValueError('truncated day file')
    result = {}
    previous = 0
    for day, _open, _high, _low, close, _amount, volume, _ in BAR.iter_unpack(data):
        if day <= previous:
            raise ValueError('non-increasing or repeated date')
        previous = day
        if day in wanted and volume > 0:
            if close <= 0:
                raise ValueError('nonpositive active close')
            result[day] = close
    return result


def main():
    collection = json.loads((OUT / 'baostock-collection.json').read_text())
    days = collection['expected']
    if (len(days) != 171 or collection['failures']
        or set(days) != set(collection['records'])):
        raise ValueError('BaoStock history incomplete')
    target = {int(day.replace('-', '')): day for day in days}
    expected = {}
    for day in days:
        rec = collection['records'][day]
        data = (ROOT / rec['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != rec['sha256']:
            raise ValueError(day + ': BaoStock bytes changed')
        payload = json.loads(data)
        if payload['date'] != day or any(r['date'] != day for r in payload['daily']):
            raise ValueError(day + ': mixed dates')
        current = {}
        for row in payload['daily']:
            if row['tradestatus'] != '1' or int(row['volume'] or 0) <= 0:
                continue
            exchange, number = row['code'].split('.')
            symbol = exchange + number
            if not SYMBOL.fullmatch(symbol + '.day') or symbol.startswith('sh689'):
                continue
            price = Decimal(row['close'])
            if not price.is_finite() or price <= 0 or symbol in current:
                raise ValueError(day + ': invalid or duplicate BaoStock price')
            current[symbol] = price
        expected[day] = current
    found = {d: {} for d in days}
    path = OUT / 'tdx-hsjday-20261028.zip'
    digest = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    count = 0
    seen = set()
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            basename = PurePosixPath(info.filename.replace('\\', '/')).name.lower()
            match = SYMBOL.fullmatch(basename)
            if not match or basename.startswith('sh689'):
                continue
            symbol = match.group(1).lower()
            if symbol in seen:
                raise ValueError('duplicate archive stock file ' + symbol)
            seen.add(symbol)
            if info.file_size > 10_000_000:
                raise ValueError('unexpectedly large day file')
            for date_number, close in bars_for_dates(z.read(info), target).items():
                found[target[date_number]][symbol] = Decimal(close) / 100
            count += 1
            if count % 500 == 0:
                print('stock files', count, flush=True)
    if count < 4000:
        raise ValueError('archive stock files incomplete')
    results = []
    for day in days:
        bao, tdx = expected[day], found[day]
        common = bao.keys() & tdx.keys()
        differences = [{'symbol': code, 'baostock': str(bao[code]), 'tdx': str(tdx[code])}
                       for code in sorted(common) if bao[code] != tdx[code]]
        results.append({'date': day, 'baostock': len(bao), 'tdx': len(tdx), 'matched': len(common),
                        'only_baostock': sorted(bao.keys() - tdx.keys()),
                        'only_tdx': sorted(tdx.keys() - bao.keys()), 'close_mismatches': differences})
    report = {'source': 'TDX public hsjday.zip / BaoStock daily', 'archive_sha256': digest.hexdigest(),
              'archive_bytes': path.stat().st_size, 'stock_files': count, 'rows': results,
              'limitation': 'Only close prices and active membership checked; historical data lineage may overlap. TDX record layout requires independent validation.'}
    (OUT / 'tdx-close-crosscheck.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    issues = [r for r in results if r['only_baostock'] or r['only_tdx'] or r['close_mismatches']]
    print('dates', len(results), 'matched', sum(r['matched'] for r in results), 'issue days', len(issues), flush=True)


if __name__ == '__main__':
    main()
