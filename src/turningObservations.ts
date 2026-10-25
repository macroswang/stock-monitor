import type {Bar} from './models';

// Guanliang's independent display-only heuristic; not the formula of a third-party product.
export const TURNING_OBSERVATION_RULE=Object.freeze({window:20,confirmation:2,vwapDeviation:.005,reversal:.003,tick:.01,cooldown:10});
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
export type TurningObservation={key:string;kind:'bottom'|'top';time:string;price:number;candidateTime:string;candidatePrice:number;vwap:number;deviationPct:number;support:number;resistance:number;movePct:number;volumeRatio:number|null};

export function turningObservations(bars:Bar[]):TurningObservation[]{
 const byTime=new Map<string,Bar>(),duplicates=new Set<string>();
 for(const b of bars){if(byTime.has(b.time))duplicates.add(b.time);byTime.set(b.time,b);}
 const all=times.map(t=>byTime.get(t)),result:TurningObservation[]=[];
 const rule=TURNING_OBSERVATION_RULE,last={bottom:-Infinity,top:-Infinity};
 const valid=(b:Bar|undefined):b is Bar=>!!b&&!duplicates.has(b.time)&&b.complete&&Number.isFinite(+b.close)&&+b.close>0&&Number.isFinite(b.volume)&&b.volume>=0&&!!b.average&&Number.isFinite(+b.average)&&+b.average>0;
 for(let i=0;i<236;i++){
  const start=i<120?0:120,c=i-rule.confirmation,lo=c-rule.window+1;
  if(lo<start)continue;
  const window=all.slice(lo,i+1);
  if(!window.every(valid))continue;
  const pivot=all[c]!,one=all[c+1]!,two=all[i]!;
  if(one.volume<=0||two.volume<=0)continue;
  const p=+pivot.close,p1=+one.close,p2=+two.close,vwap=+pivot.average!;
  const prior=all.slice(lo,c+1).map(b=>+b!.close),support=Math.min(...prior),resistance=Math.max(...prior);
  const deviation=p/vwap-1,required=Math.max(rule.tick,p*rule.reversal),epsilon=1e-9;
  const bottom=p<=support+epsilon&&deviation<=-rule.vwapDeviation&&p1>=p&&p2>=p1&&p2-p+epsilon>=required;
  const top=p>=resistance-epsilon&&deviation>=rule.vwapDeviation&&p1<=p&&p2<=p1&&p-p2+epsilon>=required;
  const kind=bottom?'bottom':top?'top':null;
  if(!kind||i-last[kind]<rule.cooldown)continue;
  last[kind]=i;
  const before=all.slice(c-5,c).reduce((sum,b)=>sum+b!.volume,0)/5;
  result.push({key:`turning-v1|${kind}|${times[c]}|${times[i]}`,kind,time:times[i],price:p2,
   candidateTime:times[c],candidatePrice:p,vwap,deviationPct:deviation*100,support,resistance,
   movePct:Math.abs(p2/p-1)*100,volumeRatio:before>0?(one.volume+two.volume)/2/before:null});
 }
 return result;
}
