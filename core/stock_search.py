"""Fast local stock lookup by code / Chinese name / pinyin initials.

The A-share name list comes from the same daily universe used by the market radar;
instruments/watch already cached in SQLite are merged in so newly added names resolve offline.
"""
import re
import threading
from .provider import now_cn

_LOCK = threading.Lock()
_CACHE = {}


def _initials(name):
    try:
        from pypinyin import lazy_pinyin, Style
        return ''.join(lazy_pinyin(name, style=Style.FIRST_LETTER)).lower()
    except Exception:
        return ''


def _rows(store):
    day = now_cn().date().isoformat()
    with _LOCK:
        cached = _CACHE.get(day)
    if cached:
        return cached
    names = {}
    try:
        from .market_pulse import name_universe
        names.update(name_universe(store, day))
    except Exception:
        pass
    try:
        for row in store.query('SELECT code,name FROM instruments WHERE name IS NOT NULL'):
            names.setdefault(row['code'], row['name'])
        for row in store.query('SELECT code,name FROM pool WHERE name IS NOT NULL'):
            names.setdefault(row['code'], row['name'])
        for row in store.query('SELECT code,name FROM watch WHERE name IS NOT NULL'):
            names.setdefault(row['code'], row['name'])
    except Exception:
        pass
    rows = [dict(code=code, name=name, initials=_initials(name)) for code, name in names.items()
            if isinstance(code, str) and isinstance(name, str) and name]
    rows.sort(key=lambda item: item['code'])
    with _LOCK:
        _CACHE.clear()
        _CACHE[day] = rows
    return rows


def search(store, query, limit=20):
    text = (query or '').strip()
    if not text:
        return []
    rows = _rows(store)
    lowered = text.lower()
    digits = re.sub(r'\D', '', text)
    scored = []
    for row in rows:
        name = row['name']
        initials = row['initials']
        score = None
        if digits and len(digits) >= 1 and digits in row['code']:
            score = 0 if row['code'].endswith(digits) else 1
        elif lowered and initials == lowered:
            score = 2
        elif lowered and initials.startswith(lowered):
            score = 3
        elif text and name.startswith(text):
            score = 4
        elif text and text in name:
            score = 5
        elif lowered and initials.startswith(lowered[0]):
            score = 6
        elif lowered and lowered in initials:
            score = 7
        if score is not None:
            scored.append((score, len(name), row))
    scored.sort(key=lambda item: (item[0], item[1], item[2]['code']))
    return [dict(code=row['code'], name=row['name'], initials=row['initials'])
            for _, _, row in scored[:max(1, min(30, int(limit or 20)))]]
