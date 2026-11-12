"""shape-v3.0 bottom/top engine, mirroring src/turningFinalV3.ts.

Frozen spec: outputs/turning-similarity-20261113/research/spec-v3.md.
shape-v3.0 = the proven shape-v2.4 detection kernel unchanged; the ONLY rule change is
that the fallback branch may not emit bottom signals (fallback_bottom_enabled=False).
Because C1 is causal, removing fallback-bottom candidates can free daily cap slots and
+/-2min dedupe room, so v3 is NOT a simple filter of the v2.4 event list: the v2.4 raw
main/fallback streams are re-merged (C1) with fallback bottoms suppressed.
fallback_bottom_enabled=True reproduces the v2.4 event set event-for-event (locked against
the v2 golden).

Product decision (Lead, after 36-stock/95-marker re-validation): v2.4 stays the default;
v3 is an OPTIONAL experimental chart mode (default off) because it loses fallback bottom
signals and bottom quality/coverage. Auto-trading and autoTradeMarks keep using v2.4
(shape-v2). This module is not wired into live_trading; SIGNAL below documents that
trading stays shape-v2. Event fields are v2-compatible; key prefix is shape-v3| and ruleVersion is
shape-v3.0.
"""
import math

from .turning_final import ZHANGLE, liquidity, turning_final_streams
from .turning_q1 import TIMES

SIGNAL = 'shape-v2'  # trading stays shape-v2 by product decision (v3 is chart-only)
LABEL = '观量底／顶信号'
VERSION = 'shape-v3.0'
KEY_PREFIX = 'shape-v3'

RULE = dict(
    ZHANGLE,
    version=VERSION,
    key_prefix=KEY_PREFIX,
    fallback=dict(ZHANGLE['fallback'], fallback_bottom_enabled=False),
)


def _time_index(stamp):
    return TIMES.index(stamp)


def _tag(event, rule, cap_index):
    return dict(event,
                key=f"{rule.get('key_prefix', KEY_PREFIX)}|{event['kind']}|{event['candidateTime']}",
                ruleVersion=rule.get('version', VERSION),
                capIndex=cap_index)


def _build_queue(bars, rule):
    """v2.4 raw streams -> v3 candidate queue (main as-is; fallback quality/early-limit
    filtered and, unless fallback_bottom_enabled=True, restricted to tops)."""
    streams = turning_final_streams(bars, rule)
    fallback = rule.get('fallback')
    queue = [(event, True) for event in streams['main']]
    if fallback and fallback.get('enabled'):
        for event in streams['fallback']:
            if event['quality'] < fallback['quality_tau_emit']:
                continue
            if _time_index(event['candidateTime']) >= fallback['early_limit']:
                continue
            if fallback.get('fallback_bottom_enabled') is not True and event['kind'] != 'top':
                continue
            queue.append((event, False))
    queue.sort(key=lambda item: (_time_index(item[0]['time']), 0 if item[1] else 1))
    return queue


def candidates(bars, rule=None):
    """Candidate queue BEFORE the C1 cap/dedupe scan (diagnostics + cap tests)."""
    rule = rule or RULE
    return [_tag(event, rule, 0) for event, _ in _build_queue(bars, rule)]


def signals(bars, rule=None):
    """Confirmed v3 chart events: C1 cap 3/kind/day, fallback-only +/-2min same-kind
    dedupe, main branch never deduped, capIndex = acceptance order."""
    rule = rule or RULE
    fallback = rule.get('fallback') or {}
    dedupe = fallback.get('dedupe_minutes', 0)
    accepted = {'top': [], 'bottom': []}
    out = []
    for event, is_main in _build_queue(bars, rule):
        same_kind = accepted[event['kind']]
        if len(same_kind) >= rule['daily_cap_per_kind']:
            continue
        at = _time_index(event['time'])
        if not is_main and any(abs(previous - at) <= dedupe for previous in same_kind):
            continue
        same_kind.append(at)
        out.append(_tag(event, rule, len(same_kind)))
    return out
