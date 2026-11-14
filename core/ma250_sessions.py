"""Annual-line close gate; independent of the later option-statistics release."""
from datetime import timedelta
from .paper_session import calendar
from .provider import CN


def eligible_sessions(now, limit=1):
    now = now.astimezone(CN)
    day = now.date() - (timedelta(days=1) if now.strftime('%H:%M') < '15:20' else timedelta())
    out = []
    for _ in range(max(100, limit * 3)):
        closed = calendar(day.year)
        if closed is None:
            break
        stamp = day.isoformat()
        if day.weekday() < 5 and not any(a <= stamp <= b for a, b in closed):
            out.append(stamp)
            if len(out) >= limit:
                break
        day -= timedelta(days=1)
    return list(reversed(out))
