import type {Bar} from './models';
import type {TurningFinalFallbackRule, TurningFinalKind, TurningFinalObservation, TurningFinalRule} from './turningFinal';
import {TURNING_FINAL_RULE_ZHANGLE, turningFinalStreams} from './turningFinal';

// shape-v3.0 chart engine (frozen spec: outputs/turning-similarity-20261113/research/spec-v3.md).
// Detection kernel is byte-for-byte the proven v2.4 engine; the ONLY rule change is that
// the fallback branch may not emit bottom signals (fallback_bottom_enabled=false).
// Because the C1 merge is causal, removing the fallback-bottom candidates can free daily
// cap slots and +/-2min dedupe room, so v3 is NOT "v2.4 events filtered": it is the v2.4
// raw main/fallback streams re-merged by C1 with fallback bottoms suppressed.
// Fallback bottoms stay available for rollback/comparison via fallbackBottomEnabled=true,
// which reproduces the v2.4 event set event-for-event (locked by the v2 golden).
//
// Product decision (Lead, after 36-stock/95-marker re-validation): v2.4 stays the default;
// v3 is an OPTIONAL experimental chart mode (default off) because it loses fallback bottom
// signals and bottom quality/coverage. Auto-trading and autoTradeMarks keep using v2.4.
// Event fields stay v2-compatible; version = shape-v3.0 and key prefix = shape-v3|.

export const TURNING_FINAL_V3_VERSION = 'shape-v3.0';
export const TURNING_FINAL_V3_KEY_PREFIX = 'shape-v3';
export const TURNING_FINAL_V3_SIGNAL = 'shape-v2'; // trading stays shape-v2 by product decision
export const TURNING_FINAL_V3_LABEL = '观量底／顶信号';

export type TurningFinalV3FallbackRule = TurningFinalFallbackRule & {
  // false (v3 default) = fallback emits tops only; true = full v2.4 fallback (rollback).
  fallbackBottomEnabled?: boolean;
};

export type TurningFinalV3Rule = Omit<TurningFinalRule, 'fallback'> & {
  // Key/version are rule fields so the v2.4-equivalence test can switch them back.
  keyPrefix: string;
  version: string;
  fallback: TurningFinalV3FallbackRule | null;
};

export type TurningFinalV3Observation = TurningFinalObservation;

export const TURNING_FINAL_V3_RULE: Readonly<TurningFinalV3Rule> = Object.freeze({
  ...TURNING_FINAL_RULE_ZHANGLE,
  version: TURNING_FINAL_V3_VERSION,
  keyPrefix: TURNING_FINAL_V3_KEY_PREFIX,
  fallback: Object.freeze({
    ...(TURNING_FINAL_RULE_ZHANGLE.fallback as TurningFinalFallbackRule),
    fallbackBottomEnabled: false,
  }),
});

const TIMES = [...Array.from({length: 120}, (_, i) => 571 + i), ...Array.from({length: 120}, (_, i) => 781 + i)]
  .map(m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`);
export const TURNING_V3_TIMES: ReadonlyArray<string> = Object.freeze([...TIMES]);
const timeIndex = (stamp: string) => TIMES.indexOf(stamp);

type Candidate = {event: TurningFinalObservation; isMain: boolean};

function tagEvent(event: TurningFinalObservation, rule: Readonly<TurningFinalV3Rule>, capIndex: number): TurningFinalV3Observation {
  return {...event, key: `${rule.keyPrefix}|${event.kind}|${event.candidateTime}`, ruleVersion: rule.version, capIndex};
}

// v2.4 raw streams -> v3 candidate queue: main kept as-is (already Q-gated/capped among
// itself), fallback quality/early-limit filtered and (unless fallbackBottomEnabled=true)
// restricted to tops. Sorted by (time, main-before-fallback) for the causal C1 scan.
function buildQueue(bars: Bar[], rule: Readonly<TurningFinalV3Rule>): Candidate[] {
  const streams = turningFinalStreams(bars, rule as Readonly<TurningFinalRule>);
  const fallback = rule.fallback;
  const queue: Candidate[] = streams.main.map(event => ({event, isMain: true}));
  if (fallback && fallback.enabled) {
    for (const event of streams.fallback) {
      if (event.quality < fallback.qualityTauEmit) continue;
      if (timeIndex(event.candidateTime) >= fallback.earlyLimit) continue;
      if (fallback.fallbackBottomEnabled !== true && event.kind !== 'top') continue;
      queue.push({event, isMain: false});
    }
  }
  queue.sort((a, b) => timeIndex(a.event.time) - timeIndex(b.event.time)
    || (a.isMain === b.isMain ? 0 : a.isMain ? -1 : 1));
  return queue;
}

// Candidate stream BEFORE the C1 cap/dedupe scan (diagnostics + cap tests).
export function turningFinalV3Candidates(bars: Bar[], rule: Readonly<TurningFinalV3Rule> = TURNING_FINAL_V3_RULE): TurningFinalV3Observation[] {
  return buildQueue(bars, rule).map(({event}) => tagEvent(event, rule, 0));
}

// Final v3 events: causal C1 (cap 3/kind/day; main branch never deduped; fallback dropped
// when a same-kind accepted event is within +/-dedupeMinutes) -> capIndex/key/ruleVersion.
export function turningFinalV3(bars: Bar[], rule: Readonly<TurningFinalV3Rule> = TURNING_FINAL_V3_RULE): TurningFinalV3Observation[] {
  const queue = buildQueue(bars, rule);
  const fallbackDedupe = rule.fallback?.dedupeMinutes ?? 0;
  const accepted: Partial<Record<TurningFinalKind, number[]>> = {top: [], bottom: []};
  const out: TurningFinalV3Observation[] = [];
  for (const {event, isMain} of queue) {
    const times = accepted[event.kind]!;
    if (times.length >= rule.dailyCapPerKind) continue;
    const at = timeIndex(event.time);
    if (!isMain && times.some(t => Math.abs(t - at) <= fallbackDedupe)) continue;
    times.push(at);
    out.push(tagEvent(event, rule, times.length));
  }
  return out;
}

// Re-exported for tests and for the chart's "当日上限" row.
export const TURNING_FINAL_V3_TIMES: ReadonlyArray<string> = TURNING_V3_TIMES;
