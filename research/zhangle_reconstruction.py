"""Offline runner for the production R1 reconstruction; no broker connection."""
import argparse
import json
from pathlib import Path
from core.turning_shapes import PARAMETERS, TIMES, VERSION, _number, signals as production_signals


def signals(bars, opening_price):
    opening_price = _number(opening_price)
    if opening_price <= 0:
        raise ValueError('A positive same-day opening price is required')
    opening = dict(time='09:30',close=opening_price,average=opening_price,volume=0,complete=True)
    if any(b.get('time') == '09:30' for b in bars):
        raise ValueError('Supply the opening quote separately, not twice')
    return production_signals([opening, *bars])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path,
                        help='JSON object containing bars and opening_price; never a broker connection')
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    print(json.dumps(dict(version=VERSION, parameters=PARAMETERS,
                          signals=signals(data['bars'], data['opening_price'])),
                     ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
