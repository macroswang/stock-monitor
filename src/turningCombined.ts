import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';
import {turningFinal,TURNING_FINAL_MODES} from './turningFinal';
import {turningQualityQ1,type TurningQualityQ1} from './turningQualityQ1';

// shape-v2-q1 combined signal list, mirroring core/turning_combined.py and the chart
// display merge. v2.4 events take the slots first; Q1 signals fill the remaining per-kind
// slots in time order (same kind+minute v2 wins; same kind+display price deduped), so the
// list is exactly what the chart shows as 底/顶 and what auto-trading must follow.
// Finally suppress same-kind emissions less than 10 trading minutes apart, keeping the first.
export const TURNING_COMBINED_SIGNAL='shape-v2-q1';
export const TURNING_COMBINED_VERSION='shape-v2-q1.0';
export const TURNING_COMBINED_CAP_PER_KIND=3;
export const TURNING_MIN_SEPARATION=10;

export type TurningCombinedSignal=TurningObservation;

const cents=(price:number)=>Math.round(price*100);

// Compare emission times on the trading clock; lunch contributes zero minutes.
export function filterTurningSpacing<T extends {kind:'top'|'bottom';time:string}>(events:ReadonlyArray<T>):T[]{
 const last:Partial<Record<'top'|'bottom',number>>={},kept:T[]=[];
 for(const event of [...events].sort((a,b)=>a.time.localeCompare(b.time))){
  const [h,m]=event.time.split(':').map(Number),clock=h*60+m,at=clock-(clock>=780?90:0);
  const previous=last[event.kind];
  if(previous!==undefined&&at-previous<TURNING_MIN_SEPARATION)continue;
  last[event.kind]=at;kept.push(event);
 }
 return kept;
}

export function turningCombinedSignals(finalSignals:ReadonlyArray<TurningObservation>,
 qualitySignals:ReadonlyArray<TurningQualityQ1>,capPerKind=TURNING_COMBINED_CAP_PER_KIND):TurningCombinedSignal[]{
 const selected:TurningObservation[]=[...finalSignals];
 const counts:{top:number;bottom:number}={top:0,bottom:0};
 const minutes=new Set<string>(),prices:{top:Set<number>;bottom:Set<number>}={top:new Set(),bottom:new Set()};
 for(const event of selected){counts[event.kind]++;minutes.add(event.kind+'|'+event.time);prices[event.kind].add(cents(event.price));}
 const ordered=[...qualitySignals].map((event,index)=>({event,index}))
  .sort((a,b)=>a.event.time.localeCompare(b.event.time)||a.index-b.index);
 for(const {event} of ordered){
  if(counts[event.kind]>=capPerKind)continue;
  if(minutes.has(event.kind+'|'+event.time))continue;
  const value=cents(event.price);
  if(prices[event.kind].has(value))continue;
  selected.push(event);counts[event.kind]++;minutes.add(event.kind+'|'+event.time);prices[event.kind].add(value);
 }
 return filterTurningSpacing(selected);
}

// Convenience wrapper for the chart/trading parity path (Q1 is computed on the same bars;
// the extra 09:30 row is ignored by both engines).
export function turningCombinedForBars(bars:Bar[],capPerKind=TURNING_COMBINED_CAP_PER_KIND):TurningCombinedSignal[]{
 const final=turningFinal(bars,TURNING_FINAL_MODES.zhangle);
 const quality=turningQualityQ1(bars);
 return turningCombinedSignals(final,quality,capPerKind);
}
