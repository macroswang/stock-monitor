import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';

// shape-v2 chart/trading top/bottom stream: the frozen R1 kernel (identical parameters
// and candidate/confirmation order), a quality gate, an optional all-day fallback pass,
// then a hard daily cap per kind. This single module feeds BOTH the chart display and
// the auto-trading engine (trading always uses the zhangle/v2.4 rule). The legacy R1
// (turningShapes.ts) and Q1 stay untouched as frozen references; historical shape-v1
// execution records still render through autoTradeMarks().
//
// Frozen spec: outputs/turning-improve-20261112/spec.md (shape-v2.0, final). Parameters
// live only here; the display layer consumes this single source of truth.
//
// Implementation notes (spec ambiguities resolved literally, reported to Lead):
// 1. Q = rsi_term + rev_term + dev_term + 2*amp_term. spec labels it "0..8" but its
//    own clamps allow 0..10; the quant calibration script (09_final_eval.py) uses the
//    formula with max 10, so this module follows the formula, not the comment.
// 2. rsi_term uses the RSI at the CANDIDATE (arming) minute = spec "rsiCandidate",
//    stored on the candidate; the confirmation-minute RSI is emitted separately.
// 3. dev_term uses the signed VWAP deviation at the candidate minute.
// 4. amp_term uses (high-low)/low*100 over bars known at the confirmation minute.
// 5. quality compares unrounded (spec: "过滤用未舍入值"); display rounds to 2 dp.
// 6. same_session_only defaults to FALSE (allowed to straddle lunch): the 2026-11-12
//    Zhangle marks sh600714 top 13:01 and sz300094 top 13:01 both confirm an 11:30
//    candidate across the lunch break, and the production R1 also allows it. The
//    option stays configurable so spec §9's old same-session variant can still be
//    exercised (a test covers the true branch).
// 7. event key = shape-v2|kind|candidateTime; the plan's guanliang-v2 alias is not
//    used because spec §1/§9.3 freezes the shape-v2 prefix.
// 8. Quality gate then cap are applied INSIDE this module (never by the chart). The
//    kernel stream is computed causally; events that fail Q<5.0 are dropped before the
//    cap counter, so daily counts only ever contain emitted signals.
// 9. daily cap key is (code, trade_day, kind). This pure function receives one day's
//    bars, so counting is rebuilt deterministically from the same prefix on every call
//    (chart refresh included); no cross-day state can leak in.
// 10. C1 merge (causal chronological): both branches are computed causally, then scanned
//    in (time, main-before-fallback) order. A main event is accepted whenever its kind is
//    below the daily cap; a fallback event is accepted only if its kind is below the cap
//    and no same-kind event ALREADY ACCEPTED is within +/-dedupeMinutes. Nothing looks at
//    future main events, so any prefix output is exactly the final full-day output cut at
//    that prefix (signals never appear and later disappear), and per-kind daily orders can
//    never exceed 3.
//
// Parameterised without touching the v2.0 kernel:
//  - rule.quality is a replaceable Q function (Q' can be swapped in);
//  - rule.fallback is an optional all-day second pass (earlyLimit Infinity; earlyLimit
//    can still restrict it to the first N candidate minutes). It reuses the causal kernel
//    with rsiArm/rsiConfirm switches, its own quality function/tau, deviation floor and
//    reversal floor, then participates in the C1 causal merge above. The v2.3-only knobs
//    (onlyWhenMainKindEmpty/maxPerKind/minSameGap) stay on the type for compatibility but
//    the C1 merge ignores them. Default disabled -> exact v2.0 output.

export type TurningFinalKind = 'top' | 'bottom';

// All inputs below are known at the confirmation minute; rsiCandidate/deviation
// came from the candidate minute and are still known then (no future data).
export type TurningFinalQualityInput = {
  kind: TurningFinalKind;
  sign: 1 | -1;
  price: number;
  average: number;
  high: number;
  low: number;
  movePct: number;
  deviationPct: number;
  candidate: {index: number; time: string; price: number; vwap: number; rsi: number; deviationPct: number};
};

export type TurningFinalQualityFn = (input: TurningFinalQualityInput) => number;

// Optional fallback pass (v2.3 first-hour / v2.4 all-day direction). The default
// rule has it disabled; enabling it may only ADD signals the main branch did not
// emit, never replace or reorder main signals, and the total stays within the cap.
export type TurningFinalFallbackRule = {
  enabled: boolean;
  // false = do not require the RSI extreme to arm a fallback candidate.
  rsiArm: boolean;
  // false = do not require RSI to have crossed back before confirming.
  rsiConfirm: boolean;
  // Quality function for fallback signals (Q' e.g. extreme proximity instead of the
  // RSI term); independent from the main rule quality function.
  quality: TurningFinalQualityFn;
  qualityTauEmit: number;
  // Candidate minute index (0 = 09:31) strictly below this counts as early session.
  // Infinity (default) makes the fallback branch apply to the whole trading day.
  earlyLimit: number;
  // true = only fill a kind that the main branch produced nothing for.
  onlyWhenMainKindEmpty: boolean;
  // Fallback-only daily cap per kind; Infinity lets the merged total cap decide.
  maxPerKind: number;
  // Reject fallback candidates within this many minutes of a main event of the same kind.
  dedupeMinutes: number;
  // Minimum minutes between same-kind accepted signals (main included); 0 disables.
  minSameGap: number;
  // shape-v3 flag (v3 module only; the v2 engine ignores it): false = fallback emits
  // tops only, true/absent = the full v2.4 fallback (tops and bottoms).
  fallbackBottomEnabled?: boolean;
  // Candidate arming deviation floor (v2.4: 0.7% instead of the R1 1.0%).
  minimumDeviationPct: number;
  // Absolute reversal floor in percent of the candidate price (v2.4: 0.15%).
  reversalMinPct: number;
};

export type TurningFinalRule = {
  version: string;
  rsiPeriod: number;
  topRsi: number;
  bottomRsi: number;
  minimumDeviationPct: number;
  reversalFraction: number;
  sameKindAdvancePct: number;
  candidateExpiryMinutes: number;
  sameSessionOnly: boolean;
  emissionCutoffIndex: number;
  dailyCapPerKind: number;
  qualityTauEmit: number;
  quality: TurningFinalQualityFn;
  fallback: TurningFinalFallbackRule | null;
};

// Superset of the shared chart observation; field names follow the frozen spec.
export type TurningFinalObservation = TurningObservation & {
  candidateVwap: number;
  rsi: number;
  rsiCandidate: number;
  deviationCandidatePct: number;
  quality: number;
  capIndex: number;
  ruleVersion: string;
};

type Candidate = {index: number; time: string; price: number; vwap: number; rsi: number; deviationPct: number};
type Parsed = {byTime: Map<string, Bar>; duplicates: Set<string>; openingPrice: number; prefixEnd: number};

// Frozen key prefix (§1/§9.3): independent of the rule's display version string.
export const TURNING_FINAL_KEY_PREFIX = 'shape-v2';
const TIMES = [...Array.from({length: 120}, (_, i) => 571 + i), ...Array.from({length: 120}, (_, i) => 781 + i)]
  .map(m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`);
const EPSILON = 1e-9;
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
const finite = (n: unknown) => (typeof n === 'number' || typeof n === 'string' && n.trim() !== '') && Number.isFinite(Number(n));
const indexOfTime = (stamp: string) => TIMES.indexOf(stamp);

// Frozen §4 formula: 0..10 (spec's "0..8" comment contradicts its own clamps).
// NOTE: the candidate RSI is exactly 0 only while the zero-initialized Wilder RSI has
// never seen a gain (typically the first down minute). The quant reference used for the
// frozen §8.1 calibration treats a zero/absent candidate RSI as neutral 50
// (09_final_eval.py: `e.get('rsiCandidate') or 50.0`), which is required to reproduce
// the frozen 27/37/63 numbers; without that compatibility the same bars predict 38.
export function turningFinalQualityV2(input: TurningFinalQualityInput): number {
  const {sign, candidate, high, low, movePct} = input;
  const candidateRsi = Number.isFinite(candidate.rsi) && candidate.rsi !== 0 ? candidate.rsi : 50;
  const rsiTerm = clamp(sign * (candidateRsi - 50) / 25, 0, 2);
  const revTerm = clamp(movePct / 0.45, 0, 2);
  const devTerm = clamp(Math.abs(candidate.deviationPct) / 1.5, 0, 2);
  const amplitudePct = low > 0 ? (high - low) / low * 100 : 0;
  const ampTerm = clamp(amplitudePct / 1.5, 0, 2);
  return rsiTerm + revTerm + devTerm + 2 * ampTerm;
}

// v2.4 fallback quality Q' = prox + rev + dev + 2*amp (tau 4.5, unrounded compare).
// prox replaces the main branch's RSI term: how close the candidate extreme still is
// to the day's known extreme at the confirmation minute.
export function turningFinalQualityProximity(input: TurningFinalQualityInput): number {
  const {sign, candidate, high, low, movePct} = input;
  const distancePct = sign > 0
    ? high > 0 ? (high - candidate.price) / high * 100 : 0
    : low > 0 ? (candidate.price - low) / low * 100 : 0;
  const proxTerm = clamp((1 - distancePct) / 0.5, 0, 2);
  const revTerm = clamp(movePct / 0.45, 0, 2);
  const devTerm = clamp(Math.abs(candidate.deviationPct) / 1.5, 0, 2);
  const amplitudePct = low > 0 ? (high - low) / low * 100 : 0;
  const ampTerm = clamp(amplitudePct / 1.5, 0, 2);
  return proxTerm + revTerm + devTerm + 2 * ampTerm;
}

export const TURNING_FINAL_RULE: Readonly<TurningFinalRule> = Object.freeze({
  version: 'shape-v2.0',
  rsiPeriod: 9,
  topRsi: 75,
  bottomRsi: 25,
  minimumDeviationPct: 1,
  reversalFraction: .2,
  sameKindAdvancePct: 1,
  candidateExpiryMinutes: 3,
  // Lunch-crossing confirmation is allowed (matches Zhangle 2026-11-12 600714/300094
  // top 13:01 marks and the legacy R1); set true to restore spec §9's old behaviour.
  sameSessionOnly: false,
  emissionCutoffIndex: 236, // TIMES[:236] -> last emission minute is 14:56
  dailyCapPerKind: 3,
  qualityTauEmit: 5,
  quality: turningFinalQualityV2,
  fallback: null,
});

// v2.4 high-coverage rule: stable main branch untouched, plus an all-day fallback
// pass (rsi_arm=False, 0.7% deviation floor, max(0.01, 0.15%, 0.2*distance) reversal,
// Q' proximity quality with tau 4.5, main-first merge, +/-2 minute dedupe, total cap 3).
export const TURNING_FINAL_RULE_ZHANGLE: Readonly<TurningFinalRule> = Object.freeze({
  ...TURNING_FINAL_RULE,
  version: 'shape-v2.4',
  fallback: Object.freeze({
    enabled: true,
    rsiArm: false,
    rsiConfirm: true,
    quality: turningFinalQualityProximity,
    qualityTauEmit: 4.5,
    earlyLimit: Infinity,
    onlyWhenMainKindEmpty: false,
    maxPerKind: Infinity,
    dedupeMinutes: 2,
    minSameGap: 0,
    minimumDeviationPct: .7,
    reversalMinPct: .15,
  } satisfies TurningFinalFallbackRule),
} satisfies TurningFinalRule);

export type TurningFinalMode = 'zhangle' | 'stable';
export const TURNING_FINAL_MODES: Readonly<Record<TurningFinalMode, Readonly<TurningFinalRule>>> = Object.freeze({
  zhangle: TURNING_FINAL_RULE_ZHANGLE,
  stable: TURNING_FINAL_RULE,
});

function parseInput(bars: Bar[], rule: Readonly<TurningFinalRule>): Parsed | null {
  const byTime = new Map<string, Bar>(), duplicates = new Set<string>();
  for (const bar of bars) {
    if (byTime.has(bar.time)) duplicates.add(bar.time);
    byTime.set(bar.time, bar);
  }
  const opening = byTime.get('09:30');
  if (!opening || duplicates.has('09:30') || opening.complete !== true || !finite(opening.close) || +opening.close <= 0) return null;
  const limit = Math.min(rule.emissionCutoffIndex, TIMES.length);
  let prefixEnd = 0;
  for (; prefixEnd < limit; prefixEnd++) {
    const stamp = TIMES[prefixEnd], bar = byTime.get(stamp);
    if (!bar || duplicates.has(stamp) || bar.complete !== true) break;
    if (!finite(bar.close) || +bar.close <= 0 || !finite(bar.average) || Number(bar.average) <= 0) break;
    if (!finite(bar.volume) || Number(bar.volume) < 0) break;
  }
  return {byTime, duplicates, openingPrice: +opening.close, prefixEnd};
}

type KernelOptions = {
  armRsi: (candidateIndex: number) => boolean;
  rsiConfirm: boolean;
  quality: TurningFinalQualityFn;
  minimumDeviationPct?: number;
  reversalMinPct?: number;
};

// Causal R1 kernel (plus the optional same-session rule, default off). Quality is attached to each raw
// event; the Q gate and cap are applied by the selectors below, never by the chart.
function kernel(parsed: Parsed, rule: Readonly<TurningFinalRule>, options: KernelOptions): TurningFinalObservation[] {
  const {byTime, openingPrice, prefixEnd} = parsed;
  const result: TurningFinalObservation[] = [];
  const armed: Partial<Record<TurningFinalKind, Candidate>> = {};
  const last: Partial<Record<TurningFinalKind, TurningFinalObservation>> = {};
  const minimumDeviationPct = options.minimumDeviationPct ?? rule.minimumDeviationPct;
  const reversalMinPct = options.reversalMinPct ?? 0;
  const alpha = 1 / rule.rsiPeriod;
  let previousPrice = openingPrice, gain = 0, loss = 0, high = -Infinity, low = Infinity;
  for (let index = 0; index < prefixEnd; index++) {
    const stamp = TIMES[index], bar = byTime.get(stamp)!;
    const price = +bar.close, average = Number(bar.average), volume = Number(bar.volume);
    const delta = price - previousPrice;
    gain = (1 - alpha) * gain + alpha * Math.max(delta, 0);
    loss = (1 - alpha) * loss + alpha * Math.max(-delta, 0);
    const rsi = gain + loss ? 100 * gain / (gain + loss) : 50;
    previousPrice = price;
    high = Math.max(high, price);
    low = Math.min(low, price);
    for (const kind of ['top', 'bottom'] as const) {
      const sign = kind === 'top' ? 1 : -1;
      const edge = kind === 'top' ? rule.topRsi : rule.bottomRsi;
      const record = kind === 'top' ? high : low;
      if (sign * (price - average) <= 0) { delete armed[kind]; continue; }
      const deviation = sign * (price / average - 1) * 100;
      // R1 arming gate; armRsi lets the fallback pass drop only the RSI condition.
      const rsiArmed = options.armRsi(index) ? sign * (rsi - edge) > 0 : true;
      if (rsiArmed && deviation + EPSILON >= minimumDeviationPct && Math.abs(price - record) < EPSILON) {
        const old = armed[kind];
        if (!old || sign * (price - old.price) >= 0) {
          armed[kind] = {index, time: stamp, price, vwap: average, rsi, deviationPct: deviation};
        }
      }
      const candidate = armed[kind];
      if (!candidate) continue;
      const age = index - candidate.index;
      // expiry, same-bar, (optional) session boundary, RSI cross-back, volume, reversal,
      // same-kind advance: exactly the R1 order (the session rule defaults off).
      if (age > rule.candidateExpiryMinutes) { delete armed[kind]; continue; }
      if (!age) continue;
      if (rule.sameSessionOnly && (candidate.index < 120) !== (index < 120)) { delete armed[kind]; continue; }
      if (options.rsiConfirm && sign * (rsi - edge) > 0) continue;
      if (volume <= 0) continue;
      const distance = sign * (candidate.price - candidate.vwap);
      const reverse = sign * (candidate.price - price);
      // R1 needs max(0.01, 20% of the candidate-to-VWAP distance); the v2.4 fallback
      // additionally requires max(..., 0.15% of the candidate price).
      const required = Math.max(.01, distance * rule.reversalFraction, candidate.price * reversalMinPct / 100);
      if (reverse + EPSILON < required) continue;
      const previous = last[kind];
      if (previous && result.at(-1)?.kind === kind
          && sign * (candidate.price - previous.candidatePrice) + EPSILON
             < Math.max(.01, previous.candidatePrice * rule.sameKindAdvancePct / 100)) continue;
      const movePct = reverse / candidate.price * 100;
      const quality = options.quality({kind, sign, price, average, high, low, movePct,
        deviationPct: (price / average - 1) * 100, candidate});
      const prior = TIMES.slice(Math.max(0, index - 5), index).map(t => Number(byTime.get(t)!.volume));
      const before = prior.length ? prior.reduce((a, b) => a + b, 0) / prior.length : 0;
      const event: TurningFinalObservation = {
        key: `${TURNING_FINAL_KEY_PREFIX}|${kind}|${candidate.time}`,
        kind, time: stamp, price,
        candidateTime: candidate.time,
        candidatePrice: candidate.price,
        candidateVwap: candidate.vwap,
        vwap: average,
        rsi,
        rsiCandidate: candidate.rsi,
        deviationPct: (price / average - 1) * 100,
        deviationCandidatePct: candidate.deviationPct,
        support: low,
        resistance: high,
        movePct,
        volumeRatio: before > 0 ? volume / before : null,
        quality,
        capIndex: 0, // assigned by the selectors below, never by the chart
        ruleVersion: rule.version,
      };
      result.push(event);
      last[kind] = event;
      delete armed[kind];
    }
  }
  return result;
}

// Q >= tau first, then the hard per-kind cap in emission order (spec §2.2/§6),
// assigning capIndex 1..cap. Never replaces an already accepted event.
function select(events: TurningFinalObservation[], tau: number, cap: number): TurningFinalObservation[] {
  const emitted: Record<TurningFinalKind, number> = {top: 0, bottom: 0};
  const out: TurningFinalObservation[] = [];
  for (const event of events) {
    if (event.quality < tau) continue;
    const next = emitted[event.kind] + 1;
    if (next > cap) continue;
    emitted[event.kind] = next;
    out.push(event.capIndex === next ? event : {...event, capIndex: next});
  }
  return out;
}

// Confirmed chart events for one trading day, with the frozen quality gate and the
// hard per-kind cap already applied (cap is inside the engine, never a display filter).
export function turningFinal(bars: Bar[], rule: Readonly<TurningFinalRule> = TURNING_FINAL_RULE): TurningFinalObservation[] {
  const parsed = parseInput(bars, rule);
  if (!parsed) return [];
  const raw = kernel(parsed, rule, {armRsi: () => true, rsiConfirm: true, quality: rule.quality});
  const main = select(raw, rule.qualityTauEmit, rule.dailyCapPerKind);
  const fallback = rule.fallback;
  if (!fallback || !fallback.enabled) return main;
  const rawFallback = kernel(parsed, rule, {
    armRsi: index => fallback.rsiArm || index >= fallback.earlyLimit,
    rsiConfirm: fallback.rsiConfirm,
    quality: fallback.quality,
    minimumDeviationPct: fallback.minimumDeviationPct,
    reversalMinPct: fallback.reversalMinPct,
  });
  // C1 causal merge: scan (time, main-before-fallback) once, never looking ahead.
  const queue: {event: TurningFinalObservation; isMain: boolean}[] = [
    ...main.map(event => ({event, isMain: true})),
    ...rawFallback
      .filter(event => event.quality >= fallback.qualityTauEmit)
      .filter(event => indexOfTime(event.candidateTime) < fallback.earlyLimit)
      .map(event => ({event, isMain: false})),
  ];
  queue.sort((a, b) => indexOfTime(a.event.time) - indexOfTime(b.event.time)
    || (a.isMain === b.isMain ? 0 : a.isMain ? -1 : 1));
  const accepted: Record<TurningFinalKind, TurningFinalObservation[]> = {top: [], bottom: []};
  const out: TurningFinalObservation[] = [];
  for (const {event, isMain} of queue) {
    const sameKind = accepted[event.kind];
    if (sameKind.length >= rule.dailyCapPerKind) continue;
    if (!isMain) {
      const at = indexOfTime(event.time);
      if (sameKind.some(m => Math.abs(indexOfTime(m.time) - at) <= fallback.dedupeMinutes)) continue;
    }
    sameKind.push(event);
    out.push(event);
  }
  const emitted: Record<TurningFinalKind, number> = {top: 0, bottom: 0};
  return out.map(event => {
    emitted[event.kind] += 1;
    return {...event, capIndex: emitted[event.kind]};
  });
}

// Shared raw streams for the shape-v3 module (additive; the v2 entry points above are
// unchanged and the v2 golden still locks their behaviour). main is already Q-gated and
// cap-selected among itself; fallback is the raw causal fallback stream (quality attached)
// so a caller can apply extra filters before its own C1 merge.
export type TurningFinalStreams = {main: TurningFinalObservation[]; fallback: TurningFinalObservation[]};

export function turningFinalStreams(bars: Bar[], rule: Readonly<TurningFinalRule> = TURNING_FINAL_RULE): TurningFinalStreams {
  const parsed = parseInput(bars, rule);
  if (!parsed) return {main: [], fallback: []};
  const main = select(kernel(parsed, rule, {armRsi: () => true, rsiConfirm: true, quality: rule.quality}),
    rule.qualityTauEmit, rule.dailyCapPerKind);
  const fallback = rule.fallback;
  if (!fallback || !fallback.enabled) return {main, fallback: []};
  return {
    main,
    fallback: kernel(parsed, rule, {
      armRsi: index => fallback.rsiArm || index >= fallback.earlyLimit,
      rsiConfirm: fallback.rsiConfirm,
      quality: fallback.quality,
      minimumDeviationPct: fallback.minimumDeviationPct,
      reversalMinPct: fallback.reversalMinPct,
    }),
  };
}

// Diagnostic only: the kernel stream BEFORE the quality gate and cap, with quality
// attached to every candidate. The chart never renders this; tests use it to prove
// which candidates the gate/cap suppressed.
export function turningFinalCandidates(bars: Bar[], rule: Readonly<TurningFinalRule> = TURNING_FINAL_RULE): TurningFinalObservation[] {
  const parsed = parseInput(bars, rule);
  if (!parsed) return [];
  return kernel(parsed, rule, {armRsi: () => true, rsiConfirm: true, quality: rule.quality});
}

// Re-exported for tests and for the popover's "当日上限" row.
export const TURNING_FINAL_TIMES: ReadonlyArray<string> = Object.freeze([...TIMES]);