"""shape-v2-q1 combined trading signal stream (v2.4 chart signals + backend Q1 fill).

User requirement (task-21): the Q1 top/bottom points shown on the chart must trigger auto
trading exactly like the original top/bottom signals, without changing any other trading
logic. This module mirrors the chart display merge semantics:
  1) v2 = turning_final.signals(bars, ZHANGLE)  (v2.4, already C1 cap 3/kind/day);
  2) q1 = turning_q1.signals(bars)              (backend Q1, frozen engine);
  3) same kind + same minute: keep the v2 event, drop the Q1 duplicate;
  4) per-kind cap 3: v2 events take the slots, Q1 events fill the remaining slots in time
     order, skipping candidates whose display price (0.01) duplicates an already selected
     same-kind event;
  5) return the merged list sorted by time; every event keeps its original key/fields
     (Q1 keys look like quality-first-Q|kind|candidateTime|time).
The merge is a deterministic function of the current bars; because later v2 events can push
an earlier Q1 signal out of the merge, live_trading adds an order-level daily cap as a
safety net (see SPEC).
"""
import math

from . import turning_final, turning_q1
from .turning_q1 import TIMES

SIGNAL = 'shape-v2-q1'
LABEL = '观量底／顶信号'
VERSION = 'shape-v2-q1.0'
DAILY_CAP_PER_KIND = 3


def _cents(price):
    """Match JS Math.round(price*100) for the positive prices used here."""
    return math.floor(float(price) * 100 + 0.5)


def merge_signals(final_signals, q1_signals, cap_per_kind=DAILY_CAP_PER_KIND):
    """Chart-display semantic merge of v2.4 signals and Q1 signals (see module doc)."""
    selected = list(final_signals)
    counts = {'top': 0, 'bottom': 0}
    minutes = set()
    prices = {'top': set(), 'bottom': set()}
    for event in selected:
        kind = event['kind']
        counts[kind] += 1
        minutes.add((kind, event['time']))
        prices[kind].add(_cents(event['price']))
    ordered = sorted(enumerate(q1_signals), key=lambda item: (TIMES.index(item[1]['time']), item[0]))
    for _, event in ordered:
        kind = event['kind']
        if counts[kind] >= cap_per_kind:
            continue
        if (kind, event['time']) in minutes:
            continue
        cents = _cents(event['price'])
        if cents in prices[kind]:
            continue
        selected.append(event)
        counts[kind] += 1
        minutes.add((kind, event['time']))
        prices[kind].add(cents)
    selected.sort(key=lambda event: TIMES.index(event['time']))
    return selected


def signals(bars):
    """Combined trading signal stream for one trading day."""
    final = turning_final.signals(bars, turning_final.ZHANGLE)
    quality = turning_q1.signals(bars)
    return merge_signals(final, quality)
