import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';
import {TURNING_V2_RULE} from './turningObservationsV2';

// Price geometry only. Q1's volume, liquidity and cost acceptance stays separate.
export const TURNING_SHAPE_RULE=Object.freeze({version:'shape-v1',bottomDeviation:.008,topDeviation:.015,
 minSeparation:30,minSameRunTicks:2,minSameRunPct:.008});
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

export function turningShapes(bars:Bar[]):TurningObservation[]{
 const byTime=new Map<string,Bar>(),duplicates=new Set<string>();
 for(const bar of bars){if(byTime.has(bar.time))duplicates.add(bar.time);byTime.set(bar.time,bar);}
 const all=times.map(t=>byTime.get(t));
 const valid=(b:Bar|undefined):b is Bar=>!!b&&!duplicates.has(b.time)&&b.complete&&Number.isFinite(+b.close)&&+b.close>0&&Number.isFinite(b.volume)&&b.volume>=0&&!!b.average&&Number.isFinite(+b.average)&&+b.average>0;
 const result:TurningObservation[]=[],last:Partial<Record<'bottom'|'top',TurningObservation>>={},rule=TURNING_SHAPE_RULE,epsilon=1e-9;
 // The current complete minute is the candidate. Never inspect later bars to
 // decide whether it may emit; Q1 keeps its separate confirmation algorithm.
 for(let i=TURNING_V2_RULE.window-1;i<236;i++){
  const window=all.slice(i-TURNING_V2_RULE.window+1,i+1),bar=all[i];
  if(!window.every(valid)||!valid(bar)||bar.volume<=0)continue;
  const p=+bar.close,vwap=+bar.average!,prices=window.map(b=>+b!.close),support=Math.min(...prices),resistance=Math.max(...prices),deviation=p/vwap-1;
  const kind=p<=support+epsilon&&-deviation*100+epsilon>=rule.bottomDeviation*100?'bottom':p>=resistance-epsilon&&deviation*100+epsilon>=rule.topDeviation*100?'top':null;
  if(!kind)continue;
  const before=all.slice(i-5,i).reduce((sum,b)=>sum+b!.volume,0)/5;
  const m:TurningObservation={key:`candidate-shape-v1|${kind}|${bar.time}`,kind,time:bar.time,price:p,
   candidateTime:bar.time,candidatePrice:p,vwap,deviationPct:deviation*100,support,resistance,
   movePct:0,volumeRatio:before>0?bar.volume/before:null};
  const previous=last[m.kind];
  if(previous&&times.indexOf(m.time)-times.indexOf(previous.time)<rule.minSeparation)continue;
  // A continuing run needs a meaningful new extreme. An intervening opposite
  // shape starts a new swing; it does not require a new daily high/low.
  if(previous&&result.at(-1)?.kind===m.kind){
   const advance=m.kind==='top'?m.candidatePrice-previous.candidatePrice:previous.candidatePrice-m.candidatePrice;
   if(advance+epsilon<Math.max(.01*rule.minSameRunTicks,previous.candidatePrice*rule.minSameRunPct))continue;
  }
  result.push(m);last[m.kind]=m;
 }
 return result;
}
