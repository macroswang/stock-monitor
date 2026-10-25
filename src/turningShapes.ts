import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';
import {turningObservationsV2,TURNING_V2_RULE} from './turningObservationsV2';

// Price geometry only. Q1's volume, liquidity and cost acceptance stays separate.
export const TURNING_SHAPE_RULE=Object.freeze({version:'shape-v1',bottomDeviation:.008,topDeviation:.015,
 minSeparation:30,minSameRunTicks:2,minSameRunPct:.008});
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

export function turningShapes(bars:Bar[]):TurningObservation[]{
 const raw=turningObservationsV2(bars,{...TURNING_V2_RULE,cooldown:0,topTicks:1,bottomTicks:1,
  dedupeEqualCandidate:false,newLowerBottomBypassesCooldown:false});
 const result:TurningObservation[]=[],last:Partial<Record<'bottom'|'top',TurningObservation>>={},rule=TURNING_SHAPE_RULE,epsilon=1e-9;
 for(const m of raw){
  if((m.kind==='bottom'?-m.deviationPct:m.deviationPct)+epsilon<100*(m.kind==='bottom'?rule.bottomDeviation:rule.topDeviation))continue;
  const previous=last[m.kind];
  if(previous&&times.indexOf(m.time)-times.indexOf(previous.time)<rule.minSeparation)continue;
  // A continuing run needs a meaningful new extreme. An intervening opposite
  // shape starts a new swing; it does not require a new daily high/low.
  if(previous&&result.at(-1)?.kind===m.kind){
   const advance=m.kind==='top'?m.candidatePrice-previous.candidatePrice:previous.candidatePrice-m.candidatePrice;
   if(advance+epsilon<Math.max(.01*rule.minSameRunTicks,previous.candidatePrice*rule.minSameRunPct))continue;
  }
  const accepted={...m,key:`confirmed-shape-v1|${m.kind}|${m.candidateTime}|${m.time}`};
  result.push(accepted);last[m.kind]=accepted;
 }
 return result;
}
