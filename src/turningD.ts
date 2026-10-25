import type {Bar} from './models';
import type {TurningObservation} from './turningObservations';
import {turningShapes} from './turningShapes';
import {q1CostSpace} from './turningQualityQ1Costs';
import type {TDirection} from './tCosts';

// Display-only replay of the D reference. Never removes a shape or changes Q1.
export const D_TIMES=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
export const D_REFERENCE=Object.freeze({shares:1000,entryCutoff:233,restoreBy:235,latency:1});
export type DFill={time:string;reference:number};
export type DObservation={direction:TDirection;through:number;gap:boolean;entry:TurningObservation|null;entryFill:DFill|null;exit:TurningObservation|null;exitFill:DFill|null;exitReason:'opposite_signal'|'scheduled_close'|null;
 status:'waiting'|'none'|'entry_pending'|'open'|'exit_pending'|'closed'|'data_gap';netCny:number|null;netPct:number|null;feesCny:number|null;buyFill:number|null;sellFill:number|null};

export function dTopPasses(bars:Bar[],mark:TurningObservation):boolean{
 if(mark.kind!=='top')return true;
 const i=D_TIMES.indexOf(mark.time),c=D_TIMES.indexOf(mark.candidateTime);
 if(i-c!==2)return true;
 const by=new Map(bars.map(b=>[b.time,b]));
 const prior=D_TIMES.slice(Math.max(0,c-19),c+1).map(t=>Number(by.get(t)?.close));
 if(prior.length!==20||prior.some(p=>!Number.isFinite(p)||p<=0))return false;
 const changes=prior.slice(1).map((p,j)=>Math.abs(p-prior[j])).sort((a,b)=>a-b);
 const mid=Math.floor(changes.length/2),median=changes.length%2?changes[mid]:(changes[mid-1]+changes[mid])/2;
 return mark.candidatePrice-mark.price+1e-9>=2*Math.max(.01,median);
}

export function turningD(bars:Bar[],direction:TDirection='sell-buy',shapes=turningShapes(bars)):DObservation{
 const by=new Map<string,Bar>(),duplicates=new Set<string>();
 for(const b of bars){if(by.has(b.time))duplicates.add(b.time);by.set(b.time,b);}
 const valid=(t:string)=>{const b=by.get(t);return !!b&&!duplicates.has(t)&&b.complete&&Number.isFinite(+b.close)&&+b.close>0&&Number.isFinite(b.volume)&&b.volume>=0&&!!b.average&&Number.isFinite(+b.average)&&+b.average>0;};
 let through=-1;while(through+1<D_TIMES.length&&valid(D_TIMES[through+1]))through++;
 const latest=Math.max(-1,...bars.filter(b=>b.complete).map(b=>D_TIMES.indexOf(b.time)));
 const gap=latest>through;
 const result:DObservation={direction,through,gap,entry:null,entryFill:null,exit:null,exitFill:null,exitReason:null,status:gap?'data_gap':through<233?'waiting':'none',netCny:null,netPct:null,feesCny:null,buyFill:null,sellFill:null};
 const known=shapes.filter(m=>D_TIMES.indexOf(m.time)<=through);
 const entry=known.find(m=>D_TIMES.indexOf(m.time)<=233&&(direction==='sell-buy'?m.kind==='top'&&dTopPasses(bars,m):m.kind==='bottom'));
 if(!entry)return result;
 result.entry=entry;
 const entryIndex=D_TIMES.indexOf(entry.time)+1;
 if(entryIndex>through){result.status=gap?'data_gap':'entry_pending';return result;}
 result.entryFill={time:D_TIMES[entryIndex],reference:+by.get(D_TIMES[entryIndex])!.close};
 result.status=gap?'data_gap':'open';
 // Original opposite shape is retained even when C1 would reject that top.
 const opposite=known.find(m=>m.kind!==entry.kind&&D_TIMES.indexOf(m.time)>=entryIndex);
 let exitIndex:number|null=null;
 if(opposite&&D_TIMES.indexOf(opposite.time)+1<=235){
  result.exit=opposite;result.exitReason='opposite_signal';exitIndex=D_TIMES.indexOf(opposite.time)+1;
  result.status=gap?'data_gap':'exit_pending';
 }else if(through>=235){result.exitReason='scheduled_close';exitIndex=235;}
 if(exitIndex===null||exitIndex>through)return result;
 result.exitFill={time:D_TIMES[exitIndex],reference:+by.get(D_TIMES[exitIndex])!.close};result.status='closed';
 const money=direction==='sell-buy'?q1CostSpace(result.exitFill.reference,result.entryFill.reference):q1CostSpace(result.entryFill.reference,result.exitFill.reference);
 if(money){result.netCny=money.netCny;result.netPct=money.netCny/(result.entryFill.reference*1000)*100;result.feesCny=money.feesCny;result.buyFill=money.buyFill;result.sellFill=money.sellFill;}
 return result;
}

export function dShapeRole(observation:DObservation,shape:TurningObservation):'entry'|'exit'|null{
 if(observation.entry?.key===shape.key)return 'entry';
 if(observation.exit?.key===shape.key)return 'exit';
 return null;
}

export function dRoleLabel(observation:DObservation,shape:TurningObservation):string{
 const role=dShapeRole(observation,shape);
 if(!role)return shape.kind==='bottom'?'底':'顶';
 if(observation.direction==='sell-buy')return role==='entry'?'顶·D':'底·回';
 return role==='entry'?'底·T':'顶·退';
}

export function dRoleDescription(observation:DObservation,shape:TurningObservation):string{
 const role=dShapeRole(observation,shape);
 if(!role)return '形态观察，不是本轮D的独立买卖指令';
 if(observation.direction==='sell-buy')return role==='entry'?'D候选卖点：假设已有可卖持仓，先卖后买':'卖出后的原形态底回补观察，不是独立开仓买点';
 return role==='entry'?'先买后卖的原形态底观察，需有原有可卖持仓':'买底后的原形态顶退出，未套用D入场过滤';
}
