import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';

export type TurningV2Rules={window:number;minConfirmation:number;maxConfirmation:number;vwapDeviation:number;reversal:number;tick:number;cooldown:number;topTicks:number;bottomTicks:number;dedupeEqualCandidate:boolean;carryWindowAcrossLunch:boolean;newLowerBottomBypassesCooldown:boolean};
// Engineering trial selected before examining its returns. Not a validated trading strategy.
export const TURNING_V2_RULE:Readonly<TurningV2Rules>=Object.freeze({window:20,minConfirmation:2,maxConfirmation:5,vwapDeviation:.005,reversal:.003,tick:.01,cooldown:10,topTicks:2,bottomTicks:1,dedupeEqualCandidate:true,carryWindowAcrossLunch:true,newLowerBottomBypassesCooldown:true});
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

export function turningObservationsV2(bars:Bar[],rule:Readonly<TurningV2Rules>=TURNING_V2_RULE):TurningObservation[]{
 const byTime=new Map<string,Bar>(),duplicates=new Set<string>();
 for(const bar of bars){if(byTime.has(bar.time))duplicates.add(bar.time);byTime.set(bar.time,bar);}
 const all=times.map(t=>byTime.get(t)),result:TurningObservation[]=[];
 const valid=(b:Bar|undefined):b is Bar=>!!b&&!duplicates.has(b.time)&&b.complete&&Number.isFinite(+b.close)&&+b.close>0&&Number.isFinite(b.volume)&&b.volume>=0&&!!b.average&&Number.isFinite(+b.average)&&+b.average>0;
 const last:Partial<Record<'bottom'|'top',{index:number;candidatePrice:number}>>={};
 const epsilon=1e-9;
 for(let i=0;i<236;i++){
  const sessionStart=i<120?0:120;
  if(!valid(all[i])||!valid(all[i-1])||all[i]!.volume<=0||all[i-1]!.volume<=0)continue;
  let emitted=false;
  for(let lag=rule.maxConfirmation;lag>=rule.minConfirmation&&!emitted;lag--){
   const c=i-lag,lo=c-rule.window+1;
   // Prior context may span lunch. A reversal confirmation never spans lunch.
   if(c<sessionStart||lo<0||(!rule.carryWindowAcrossLunch&&lo<sessionStart))continue;
   const window=all.slice(lo,i+1);
   if(!window.every(valid))continue;
   const pivot=all[c]!,p=+pivot.close,vwap=+pivot.average!;
   const prior=all.slice(lo,c+1).map(b=>+b!.close),support=Math.min(...prior),resistance=Math.max(...prior);
   const deviation=p/vwap-1,path=all.slice(c,i+1).map(b=>+b!.close),current=+all[i]!.close;
   const bottom=p<=support+epsilon&&deviation<=-rule.vwapDeviation&&path.every((x,j)=>j===0||x>=path[j-1])&&current-p+epsilon>=Math.max(rule.tick*rule.bottomTicks,p*rule.reversal);
   const top=p>=resistance-epsilon&&deviation>=rule.vwapDeviation&&path.every((x,j)=>j===0||x<=path[j-1])&&p-current+epsilon>=Math.max(rule.tick*rule.topTicks,p*rule.reversal);
   const kind=bottom?'bottom':top?'top':null;
   if(!kind)continue;
   const previous=last[kind],newLower=kind==='bottom'&&rule.newLowerBottomBypassesCooldown&&previous&&p<=previous.candidatePrice-rule.tick+epsilon;
   if(previous&&i-previous.index<rule.cooldown&&!newLower)continue;
   if(rule.dedupeEqualCandidate&&result.at(-1)?.kind===kind&&previous&&Math.abs(p-previous.candidatePrice)<epsilon)continue;
   const before=all.slice(c-5,c).reduce((sum,b)=>sum+b!.volume,0)/5;
   result.push({key:`turning-v2|${kind}|${times[c]}|${times[i]}`,kind,time:times[i],price:current,
    candidateTime:times[c],candidatePrice:p,vwap,deviationPct:deviation*100,support,resistance,
    movePct:Math.abs(current/p-1)*100,volumeRatio:before>0?(all[i-1]!.volume+all[i]!.volume)/2/before:null});
   last[kind]={index:i,candidatePrice:p};emitted=true;
  }
 }
 return result;
}
