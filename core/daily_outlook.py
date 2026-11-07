"""Read dated research separately from the live, validated market snapshot."""
import json
from datetime import datetime, timedelta
from .provider import CN, now_cn
from .breadth import CODE


def view(app, day, batch):
    now = now_cn()
    directory = app.dir / 'daily-outlook'
    # A weekend report may explain the next session, but never silently acts as today's research.
    for offset in range(4):
        date = (now.date() - timedelta(days=offset)).isoformat()
        for path in sorted(directory.glob(date + '_*.json'), reverse=True):
            try:
                issue = json.loads(path.read_text(encoding='utf-8'))
                stamp = datetime.fromisoformat(issue['published_at'])
                if stamp.tzinfo is None or stamp > now or stamp.astimezone(CN).date().isoformat() != date:
                    continue
                codes = {s['code'] for idea in issue['ideas'] for s in idea['stocks']}
            except (OSError, ValueError, KeyError, TypeError):
                continue
            quotes = []
            if date == now.date().isoformat() and isinstance(day, str) and isinstance(batch, str) and codes:
                records = app.store.getcache(CODE, 'breadth_raw_v1', day)
                if records:
                    raw = records[0]['data']
                    if raw['date'] == day and raw['collected_at'] == batch:
                        quotes = [q for q in raw['quotes'] if q['code'] in codes]
            sectors = {}
            if quotes:
                wanted = {idea['sector_code'] for idea in issue['ideas']}
                custom = {t['code']:(t['name'],[(m['code'],m['name'],m['basis'],m['source']) for m in t['members']])
                          for t in issue.get('themes',[]) if t.get('code') in wanted and t.get('members')}
                if custom:
                    member_codes = {m[0] for _,members in custom.values() for m in members}
                    pool_quotes = {q['code']:q for q in raw['quotes'] if q['code'] in member_codes}
                    sectors.update(app.live_theme_flow.view(custom,day,batch,pool_quotes))
                services = [app.sector_flow]
                if any(code.startswith('gn_') for code in wanted):
                    services.append(app.concept_flow)
                for service in services:
                    result = service.view()
                    snapshot = result.get('snapshot') or {}
                    if snapshot.get('date') == day and not result.get('error'):
                        for row in snapshot.get('sectors', []):
                            if row['code'] in wanted:
                                sectors[row['code']] = dict(change=row['change_percent'], net=row['net_yuan'],
                                    time=snapshot.get('quote_time') or snapshot.get('anchor_time'),
                                    inferred=bool(snapshot.get('date_inferred')))
            return dict(issue=issue, quotes=quotes, sectors=sectors, day=day, batch=batch)
    return dict(issue=None, quotes=[], day=day, batch=batch)
