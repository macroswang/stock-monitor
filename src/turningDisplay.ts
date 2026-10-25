import type {TurningObservation} from './turningObservations';
import type {TurningQualityQ1} from './turningQualityQ1';

export type TurningDisplayPoint={kind:'bottom'|'top';time:string;price:number;shape?:TurningObservation;q1?:TurningQualityQ1};

// Merge exact coincident points, without changing either engine's decisions,
// confirmation times, spacing or history. Q1-only points remain independently visible.
export function turningDisplayPoints(shapes:TurningObservation[],quality:TurningQualityQ1[],showShapes:boolean,showQuality:boolean):TurningDisplayPoint[]{
 const points=new Map<string,TurningDisplayPoint>();
 if(showShapes)for(const shape of shapes)points.set(`${shape.kind}|${shape.time}`,{kind:shape.kind,time:shape.time,price:shape.price,shape});
 if(showQuality)for(const q1 of quality){
  const key=`${q1.kind}|${q1.time}`,previous=points.get(key);
  points.set(key,{...previous,kind:q1.kind,time:q1.time,price:q1.price,q1});
 }
 return [...points.values()].sort((a,b)=>a.time.localeCompare(b.time));
}
