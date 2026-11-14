import type {TurningObservation} from './turningObservations';
import type {TurningQualityQ1} from './turningQualityQ1';
import type {TurningFinalObservation} from './turningFinal';
import {filterTurningSpacing} from './turningCombined';

// A display point merges the v2 shape engine (signals) with the independent Q1 layer.
// The shape event may be a full shape-v2 observation (quality/cap metadata) or a
// legacy TurningObservation in older tests.
export type TurningDisplayShape=TurningObservation&Partial<TurningFinalObservation>;
export type TurningDisplayPoint={kind:'bottom'|'top';time:string;price:number;shape?:TurningDisplayShape;q1?:TurningQualityQ1;
 // 用户规则（2026-11-12）：Q1 顶/底成立时也分别作为一个“顶/底”信号显示。
 // 与同分钟 shape 信号重合时按既有规则合并为一个点（shape 优先，Q1 只补位并受 3/日上限约束）。
 promotedBottom?:boolean;promotedTop?:boolean};

const priceKey=(point:TurningDisplayPoint)=>point.kind+'|'+Math.round(point.price*100);

// Merge exact coincident points, without changing either engine's decisions or history.
// Rules:
//   - shape-v2 events always win a slot (they are already <=cap in production);
//   - Q1-only points fill the remaining slots in time order ("Q1 只补位");
//   - a Q1 point coinciding with a shape event merges into that single point;
//   - Q1 底/顶 both promote to real 底/顶 signals in the display;
//   - the merged display is hard-capped per kind (3/day) and never repeats the same
//     kind at the same price (same 股价不同位置只保留一个；v2 信号优先，否则保留先出现者).
//   - after merging, same-kind emissions need >=10 trading minutes; keep the first.
export function turningDisplayPoints(shapes:TurningDisplayShape[],quality:TurningQualityQ1[],showShapes:boolean,showQuality:boolean,capPerKind=3):TurningDisplayPoint[]{
 const points=new Map<string,TurningDisplayPoint>();
 if(showShapes)for(const shape of shapes)points.set(`${shape.kind}|${shape.time}`,{kind:shape.kind,time:shape.time,price:shape.price,shape});
 if(showQuality)for(const q1 of quality){
  const key=`${q1.kind}|${q1.time}`,previous=points.get(key);
  const clash=!!previous?.shape;
  points.set(key,{...previous,kind:q1.kind,time:q1.time,price:q1.price,q1,
   promotedBottom:q1.kind==='bottom'&&!clash?true:previous?.promotedBottom||false,
   promotedTop:q1.kind==='top'&&!clash?true:previous?.promotedTop||false});
 }
 const finite=Number.isFinite(capPerKind),slots=finite?Math.max(0,Math.floor(capPerKind)):Infinity;
 const kept:TurningDisplayPoint[]=[];
 for(const kind of ['bottom','top'] as const){
  const rows=[...points.values()].filter(p=>p.kind===kind).sort((a,b)=>a.time.localeCompare(b.time));
  const shapeRows=rows.filter(p=>p.shape);
  const qualityOnly=rows.filter(p=>!p.shape);
  kept.push(...(finite?shapeRows.slice(0,slots):shapeRows),...(finite?qualityOnly.slice(0,Math.max(0,slots-shapeRows.length)):qualityOnly));
 }
 // Same kind + same displayed price is one signal only; shapes come first, then Q1 by time.
 const seen=new Set<string>(),unique:TurningDisplayPoint[]=[];
 for(const point of kept){
  const key=priceKey(point);
  if(seen.has(key))continue;
  seen.add(key);unique.push(point);
 }
 return filterTurningSpacing(unique);
}
