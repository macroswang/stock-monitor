import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';
// Empirical R1 proxy; identical parameters and event semantics to the backend.
// Q1 remains independent; account, fee and execution rules are unchanged.
export const TURNING_SHAPE_RULE=Object.freeze({version:'zhangle-proxy-r1',rsiPeriod:9,topRsi:75,bottomRsi:25,
 minimumDeviationPct:1,reversalFraction:.2,sameKindAdvancePct:1,candidateExpiryMinutes:3});
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

type Candidate={index:number;time:string;price:number;vwap:number};
type R1Observation=TurningObservation&{candidateVwap:number;rsi:number};
const finite=(n:unknown)=>(typeof n==='number'||typeof n==='string'&&n.trim()!=='')&&Number.isFinite(Number(n));

export function turningShapes(bars:Bar[]):R1Observation[]{
 const byTime=new Map<string,Bar>(),duplicates=new Set<string>();
 for(const b of bars){if(byTime.has(b.time))duplicates.add(b.time);byTime.set(b.time,b);}
 const opening=byTime.get('09:30');
 if(!opening||duplicates.has('09:30')||opening.complete!==true||!finite(opening.close)||+opening.close<=0)return [];
 const rule=TURNING_SHAPE_RULE,result:R1Observation[]=[],armed:Partial<Record<'bottom'|'top',Candidate>>={},last:Partial<Record<'bottom'|'top',R1Observation>>={};
 const epsilon=1e-9,alpha=1/rule.rsiPeriod;let previousPrice=+opening.close,gain=0,loss=0,high=-Infinity,low=Infinity;
 for(let index=0;index<236;index++){
  const stamp=times[index],bar=byTime.get(stamp);
  if(!bar||duplicates.has(stamp)||bar.complete!==true||!finite(bar.close)||+bar.close<=0||!finite(bar.average)||Number(bar.average)<=0||!finite(bar.volume)||bar.volume<0)break;
  const price=+bar.close,average=Number(bar.average),volume=Number(bar.volume),delta=price-previousPrice;
  gain=(1-alpha)*gain+alpha*Math.max(delta,0);loss=(1-alpha)*loss+alpha*Math.max(-delta,0);
  const rsi=gain+loss?100*gain/(gain+loss):50;previousPrice=price;high=Math.max(high,price);low=Math.min(low,price);
  for(const kind of ['top','bottom'] as const){
   const sign=kind==='top'?1:-1,edge=kind==='top'?rule.topRsi:rule.bottomRsi,record=kind==='top'?high:low;
   if(sign*(price-average)<=0){delete armed[kind];continue;}
   const deviation=sign*(price/average-1)*100;
   if(sign*(rsi-edge)>0&&deviation+epsilon>=rule.minimumDeviationPct&&Math.abs(price-record)<epsilon){
    const old=armed[kind];if(!old||sign*(price-old.price)>=0)armed[kind]={index,time:stamp,price,vwap:average};
   }
   const candidate=armed[kind];if(!candidate)continue;
   const age=index-candidate.index;if(age>rule.candidateExpiryMinutes){delete armed[kind];continue;}
   if(!age||sign*(rsi-edge)>0||volume<=0)continue;
   const reverse=sign*(candidate.price-price),distance=sign*(candidate.price-candidate.vwap);
   if(reverse+epsilon<Math.max(.01,distance*rule.reversalFraction))continue;
   const previous=last[kind];
   if(previous&&result.at(-1)?.kind===kind&&sign*(candidate.price-previous.candidatePrice)+epsilon<Math.max(.01,previous.candidatePrice*rule.sameKindAdvancePct/100))continue;
   const prior=times.slice(Math.max(0,index-5),index).map(t=>Number(byTime.get(t)!.volume)),before=prior.length?prior.reduce((a,b)=>a+b,0)/prior.length:0;
   const event:R1Observation={key:`${rule.version}|${kind}|${candidate.time}`,kind,time:stamp,price,
    candidateTime:candidate.time,candidatePrice:candidate.price,candidateVwap:candidate.vwap,vwap:average,rsi,
    deviationPct:(price/average-1)*100,support:low,resistance:high,movePct:reverse/candidate.price*100,volumeRatio:before>0?volume/before:null};
   result.push(event);last[kind]=event;delete armed[kind];
  }
 }
 return result;
}
