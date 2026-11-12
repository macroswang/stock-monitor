import type {TurningObservation} from './turningObservations';
import type {TurningQualityQ1} from './turningQualityQ1';
import type {TurningFinalObservation} from './turningFinal';

// A display point merges the v2 shape engine (labels) with the independent Q1 layer
// (small circles). The shape event may be a full shape-v2 observation (quality/cap
// metadata) or a legacy TurningObservation in older tests.
export type TurningDisplayShape=TurningObservation&Partial<TurningFinalObservation>;
export type TurningDisplayPoint={kind:'bottom'|'top';time:string;price:number;shape?:TurningDisplayShape;q1?:TurningQualityQ1};

// Merge exact coincident points, without changing either engine's decisions,
// confirmation times, spacing or history. Q1-only points remain independently visible,
// but the merged display is hard-capped per kind (default 3/day if the engine produced
// more, e.g. with a different engine or after a future parameter change):
//   - shape-v2 events always win a slot (they are already <=cap in production);
//   - Q1-only points fill the remaining slots in time order ("Q1 只补位");
//   - a Q1 point coinciding with a shape event merges into that single point.
export function turningDisplayPoints(shapes:TurningDisplayShape[],quality:TurningQualityQ1[],showShapes:boolean,showQuality:boolean,capPerKind=3):TurningDisplayPoint[]{
 const points=new Map<string,TurningDisplayPoint>();
 if(showShapes)for(const shape of shapes)points.set(`${shape.kind}|${shape.time}`,{kind:shape.kind,time:shape.time,price:shape.price,shape});
 if(showQuality)for(const q1 of quality){
  const key=`${q1.kind}|${q1.time}`,previous=points.get(key);
  points.set(key,{...previous,kind:q1.kind,time:q1.time,price:q1.price,q1});
 }
 if(!Number.isFinite(capPerKind))return [...points.values()].sort((a,b)=>a.time.localeCompare(b.time));
 const kept:TurningDisplayPoint[]=[];
 for(const kind of ['bottom','top'] as const){
  const rows=[...points.values()].filter(p=>p.kind===kind).sort((a,b)=>a.time.localeCompare(b.time));
  const shapes=rows.filter(p=>p.shape);
  const qualityOnly=rows.filter(p=>!p.shape);
  const slots=Math.max(0,Math.floor(capPerKind));
  kept.push(...shapes.slice(0,slots),...qualityOnly.slice(0,Math.max(0,slots-shapes.length)));
 }
 return kept.sort((a,b)=>a.time.localeCompare(b.time));
}
