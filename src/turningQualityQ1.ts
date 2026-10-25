import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';
import {turningObservationsV2,TURNING_V2_RULE} from './turningObservationsV2';
import {q1CostSpace} from './turningQualityQ1Costs';

// Exact Q candidate from quality-first-20261025. Freeze geometry AND acceptance order.
// Chart observations only; historical positive expectancy has not proved stable profit.
export const TURNING_Q1_RULE=Object.freeze({version:'Q1',bottomDeviation:.008,topDeviation:.015,minVolumeRatio:1,
 minSeparation:30,bottomTicks:1,firstTopTicks:1,laterTopTicks:2,minNewTopTicks:2,minNewTopPct:.008,
 shares:1000,volumeWindow:5,maxParticipation:.01,minNetSpacePct:.2});
export type TurningQualityQ1=TurningObservation&{quality:{meanShares:number;currentShares:number;knownVwap:number;knownSpaceNetPct:number}};
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

export function turningQualityQ1(bars:Bar[]):TurningQualityQ1[]{
 const raw=turningObservationsV2(bars,{...TURNING_V2_RULE,cooldown:0,topTicks:1,bottomTicks:1,dedupeEqualCandidate:false,newLowerBottomBypassesCooldown:false});
 const rule=TURNING_Q1_RULE,by=new Map(bars.map(b=>[b.time,b]));
 const last:Partial<Record<'bottom'|'top',TurningQualityQ1>>={},count={top:0,bottom:0},result:TurningQualityQ1[]=[],epsilon=1e-9;
 for(const m of raw){
  const kind=m.kind,previous=last[kind],i=times.indexOf(m.time);
  if((kind==='bottom'?-m.deviationPct:m.deviationPct)+epsilon<100*(kind==='bottom'?rule.bottomDeviation:rule.topDeviation))continue;
  if(m.volumeRatio===null||m.volumeRatio+epsilon<rule.minVolumeRatio)continue;
  const ticks=kind==='bottom'?rule.bottomTicks:count.top?rule.laterTopTicks:rule.firstTopTicks;
  if(Math.abs(m.price-m.candidatePrice)+epsilon<Math.max(.01*ticks,m.candidatePrice*.003))continue;
  if(previous&&i-times.indexOf(previous.time)<rule.minSeparation)continue;
  if(kind==='top'&&previous&&m.candidatePrice-previous.candidatePrice+epsilon<Math.max(.01*rule.minNewTopTicks,previous.candidatePrice*rule.minNewTopPct))continue;
  const volumes=times.slice(i-4,i+1).map(t=>by.get(t)?.volume),current=by.get(m.time);
  if(!current||volumes.length!==5||volumes.some(v=>v===undefined||!Number.isFinite(v)||v<=0))continue;
  const mean=volumes.reduce<number>((n,v)=>n+v!,0)/5;
  if(1000/mean>.01+1e-12||1000/current.volume>.01+1e-12)continue;
  const price=+current.close,target=+current.average!,flow=kind==='bottom'?q1CostSpace(price,target):q1CostSpace(target,price);
  const space=flow?flow.netCny/(price*1000)*100:null;
  if(space===null||space+epsilon<.2)continue;
  const accepted:TurningQualityQ1={...m,key:`quality-first-Q|${kind}|${m.candidateTime}|${m.time}`,
   quality:{meanShares:mean,currentShares:current.volume,knownVwap:target,knownSpaceNetPct:space}};
  // Rejected raw candidates do not consume spacing or affect subsequent top thresholds.
  result.push(accepted);last[kind]=accepted;count[kind]++;
 }
 return result;
}
