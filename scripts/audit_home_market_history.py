"""Audit dates and arithmetic for the local 90-session market preview."""
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'public/breadth-csi300-preview.json'
CALENDAR = ROOT / 'fixtures/exchange-calendar-2026.json'


def audit(rows, calendar, now, count=90):
    if not rows or not isinstance(count, int) or count < 1:
        raise ValueError('缺少历史数据或日期范围无效')
    end = date.fromisoformat(rows[-1]['date'])
    wanted = []
    while len(wanted) < count and end.year == calendar['year']:
        day = end.isoformat()
        if end.weekday() < 5 and not any(a <= day <= b for a, b in calendar['closed_ranges']):
            wanted.append(day)
        end -= timedelta(days=1)
    if len(wanted) != count:
        raise ValueError('交易日历覆盖不足')
    selected = [row for row in rows if row['date'] in set(wanted)]
    days = [row['date'] for row in selected]
    missing = sorted(set(wanted) - set(days))
    invalid = []
    for row in selected:
        try:
            observed = datetime.fromisoformat(row['collected_at'])
            if observed.tzinfo is None:
                raise ValueError('缺少采集时区')
            local = observed.astimezone(ZoneInfo('Asia/Shanghai'))
            day = date.fromisoformat(row['date'])
            if (row['status'] != 'closed' or observed > now or local.date() < day
                or (local.date() == day and local.strftime('%H:%M') < '15:00')
                or row['missing'] != 0 or row['covered'] != row['expected']
                or sum(row[k] for k in ('advance', 'decline', 'flat', 'suspended')) != row['covered']):
                raise ValueError('日期或股票覆盖异常')
            for basis, field in (('volume', 'trin'), ('amount', 'trin_amount')):
                up, down = row['advance_' + basis], row['decline_' + basis]
                trin, share = row[field], row['advancing_' + basis + '_percent']
                numbers = (up, down, trin, share, row['advance'], row['decline'])
                if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in numbers):
                    raise ValueError('缺少有效成交量或家数')
                calculated = row['advance'] * down / (row['decline'] * up)
                if abs(trin - calculated) > 1e-9 * max(1, abs(calculated)) or abs(share - 100 * up / (up + down)) > 1e-7:
                    raise ValueError('成交占比或 TRIN 无法复算')
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            invalid.append(row.get('date'))
    transitions = [{'from': a['date'], 'to': b['date']} for a, b in zip(selected, selected[1:])
                   if a.get('source') != b.get('source') or a.get('universe') != b.get('universe')]
    return {'start': wanted[-1], 'end': wanted[0], 'expected_sessions': count,
            'records': len(selected), 'duplicate_dates': sorted(day for day, n in Counter(days).items() if n > 1),
            'missing_dates': missing, 'invalid_dates': invalid,
            'source_counts': dict(Counter(row['source'] for row in selected)), 'source_transitions': transitions}


def main():
    data = json.loads(DATA.read_text())
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    result = audit(data['days'], json.loads(CALENDAR.read_text()), now)
    result.update(checked_at=now.isoformat(), input_sha256=hashlib.sha256(DATA.read_bytes()).hexdigest(),
                  limitation='只核对日期、覆盖及汇总算术；不证明原始逐股数据独立或与视频口径一致。')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['duplicate_dates'] or result['missing_dates'] or result['invalid_dates']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
