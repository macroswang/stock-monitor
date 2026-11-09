"""Read dated research separately from the live, validated market snapshot.

The RPC payload is slim: heavy constituents/themes members and internal scoring maps stay on disk,
and only the current verified quote batch plus a minimal breadth day are attached for live gating.
"""
import json
import threading
import time
from datetime import datetime, timedelta
from .provider import CN, now_cn
from .breadth import CODE

_CACHE = {}
_LOCK = threading.Lock()
_SLIM_KEYS = ('screen_version', 'horizon', 'verdict', 'bias', 'position', 'quote_date', 'published_at',
              'native_slot', 'focus', 'top_picks', 'directions', 'radar', 'radar_summary', 'playbooks',
              'timetable', 'risk', 'warnings', 'coverage', 'discovery', 'pulse')
_DAY_KEYS = ('date', 'status', 'advance', 'decline', 'flat', 'expected', 'covered', 'missing',
             'first_quote', 'last_quote', 'collected_at')


def _latest_batch(store, now):
    """The quote batch belongs to the app's current expected session, not to the issue's date."""
    from .sector_flow import expected_day
    day = expected_day(now)
    if not day:
        return None, None
    rows = store.getcache(CODE, 'breadth_day_v1', day)
    if not rows:
        return None, None
    summary = rows[0]['data']
    if summary.get('date') != day or summary.get('status') not in ('closed', 'provisional'):
        return None, None
    return day, summary.get('collected_at')


def _trade_codes(issue):
    """Only codes the UI's live gates can actually read: direction stocks/peers, picks and radar."""
    codes = set()
    for direction in issue.get('directions') or []:
        candidate = direction.get('candidate') or {}
        if candidate.get('code'):
            codes.add(candidate['code'])
        for item in (direction.get('peers') or []) + (direction.get('stocks') or []):
            if item.get('code'):
                codes.add(item['code'])
    for pick in issue.get('top_picks') or []:
        if pick.get('code'):
            codes.add(pick['code'])
    for item in issue.get('radar') or []:
        for stock in item.get('stocks') or []:
            if stock.get('code'):
                codes.add(stock['code'])
    if not codes:
        codes = {s['code'] for idea in issue.get('ideas') or [] for s in ((idea.get('stocks') or []) + (idea.get('core_members') or []))}
    return codes


def _trim_quote(row):
    return {key: row.get(key) for key in ('code', 'price', 'previous_close', 'day_low', 'day_high', 'timestamp')}


def _slim_issue(issue):
    slim = {key: issue[key] for key in _SLIM_KEYS if key in issue}
    themes = []
    for theme in issue.get('themes') or []:
        if not isinstance(theme, dict):
            continue
        themes.append({key: theme.get(key) for key in ('code', 'name', 'change', 'net', 'advance', 'matched_count')})
    slim['themes'] = themes
    slim['directory'] = issue.get('directory') or {}
    slim['exclusions'] = issue.get('exclusions') or {}
    pulse = slim.get('pulse')
    if isinstance(pulse, dict):
        for block, key in (('sentiment', '_days'), ('sentiment', 'by_code'), ('capital', 'by_code')):
            value = pulse.get(block)
            if isinstance(value, dict):
                value.pop(key, None)
    return slim


def _day_info(store, day):
    rows = store.getcache(CODE, 'breadth_day_v1', day)
    if not rows:
        return None
    summary = rows[0]['data']
    if summary.get('date') != day:
        return None
    return {key: summary.get(key) for key in _DAY_KEYS}


def view(app, day, batch):
    now = now_cn()
    directory = app.dir / 'daily-outlook'
    live_day, live_batch = (day, batch) if day and batch else _latest_batch(app.store, now)
    for offset in range(4):
        date = (now.date() - timedelta(days=offset)).isoformat()
        for path in sorted(directory.glob(date + '_*.json'), reverse=True):
            try:
                key = (str(path), path.stat().st_mtime_ns, live_day, live_batch)
                with _LOCK:
                    cached = _CACHE.get(key)
                if cached is not None:
                    report, stamp, covered = cached
                    # Sector snapshots fill in asynchronously after the first call; retry soon
                    # instead of serving an incomplete map until the next breadth batch.
                    if covered or time.monotonic() - stamp < 8:
                        return report
                issue = json.loads(path.read_text(encoding='utf-8'))
                stamp = datetime.fromisoformat(issue['published_at'])
                if stamp.tzinfo is None or stamp > now or stamp.astimezone(CN).date().isoformat() != date:
                    continue
                codes = _trade_codes(issue)
                wanted = {direction['sector_code'] for direction in issue.get('directions') or []}
                if not wanted:
                    wanted = {idea['sector_code'] for idea in issue.get('ideas') or []}
            except (OSError, ValueError, KeyError, TypeError):
                continue
            quotes = []
            if date == now.date().isoformat() and isinstance(live_day, str) and isinstance(live_batch, str) and codes:
                records = app.store.getcache(CODE, 'breadth_raw_v1', live_day)
                if records:
                    raw = records[0]['data']
                    if raw['date'] == live_day and raw['collected_at'] == live_batch:
                        quotes = [_trim_quote(q) for q in raw['quotes'] if q['code'] in codes]
            sectors = {}
            if quotes:
                custom = {t['code']:(t['name'],[(m['code'],m['name'],m['basis'],m['source']) for m in t['members']])
                          for t in issue.get('themes',[]) if t.get('code') in wanted and t.get('members')}
                if custom:
                    member_codes = {m[0] for _,members in custom.values() for m in members}
                    pool_quotes = {q['code']:q for q in raw['quotes'] if q['code'] in member_codes}
                    sectors.update(app.live_theme_flow.view(custom,live_day,live_batch,pool_quotes))
                for service in (app.sector_flow, app.concept_flow):
                    result = service.view()
                    snapshot = result.get('snapshot') or {}
                    if snapshot.get('date') == live_day and not result.get('error'):
                        for row in snapshot.get('sectors', []):
                            if row['code'] in wanted:
                                sectors[row['code']] = dict(change=row['change_percent'], net=row['net_yuan'],
                                    time=snapshot.get('quote_time') or snapshot.get('anchor_time'),
                                    inferred=bool(snapshot.get('date_inferred')))
            report = dict(issue=_slim_issue(issue), quotes=quotes, sectors=sectors, day=live_day,
                          batch=live_batch, day_info=_day_info(app.store, live_day) if live_day else None)
            with _LOCK:
                if len(_CACHE) >= 8:
                    _CACHE.clear()
                covered = len(sectors) >= len(wanted) if wanted else True
                _CACHE[key] = (report, time.monotonic(), covered)
            return report
    return dict(issue=None, quotes=[], sectors={}, day=live_day, batch=live_batch,
                day_info=_day_info(app.store, live_day) if live_day else None)