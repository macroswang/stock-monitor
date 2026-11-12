import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import type {Bar} from '../../src/models';
import {turningShapes} from '../../src/turningShapes';
import {turningQualityQ1} from '../../src/turningQualityQ1';
import {turningDisplayPoints} from '../../src/turningDisplay';
const fixtures=JSON.parse(readFileSync('tests/ui/fixtures/turning-shapes.json','utf8'));
const r1=JSON.parse(readFileSync('tests/fixtures/zhangle-reconstruction.json','utf8'));
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
const seed=(p:number):Bar=>({time:'09:30',close:String(p),average:String(p),volume:0,complete:true});
const bars=(c:any):Bar[]=>[seed(c.opening_price),...c.prices.map((p:number,i:number)=>({time:times[i],close:String(p),average:String(c.averages[i]),volume:c.volumes[i],complete:true}))];
const geometry=(ms:ReturnType<typeof turningShapes>)=>ms.map(m=>[m.kind,m.time,m.price,m.candidateTime,m.candidatePrice]);
const synthetic=(prices:number[],start=0):Bar[]=>[seed(100),...[...Array(start).fill(100),...prices].map((p,i)=>({time:times[i],close:String(p),average:'100',volume:10000,complete:true}))];

test('all 38 stock-days reproduce the frozen R1 positions and backend fields',()=>{
 expect(r1.cases).toHaveLength(38);expect(r1.cases.reduce((n:number,c:any)=>n+c.broker_marks.length,0)).toBe(63);
 for(const c of r1.cases){
  const got=turningShapes(bars(c));expect(geometry(got)).toEqual(c.expected);
  expect(got).toHaveLength(c.expected_full.length);
  for(let i=0;i<got.length;i++)for(const [key,value] of Object.entries(c.expected_full[i])){
   const actual=(got[i] as any)[key];if(typeof value==='number')expect(actual).toBeCloseTo(value,10);else expect(actual).toEqual(value);
  }
 }
});

test('Q1 outputs remain frozen and separate from R1',()=>{
 for(const c of fixtures)expect(turningQualityQ1(c.bars)).toEqual(c.expectedQ1);
 const c=r1.cases[0],rows=bars(c);
 expect(geometry(turningShapes(rows.map(b=>({...b,volume:1}))))).toEqual(c.expected);
});

test('complete opening context is required and truthy flags never count as complete',()=>{
 const rows=bars(r1.cases[0]),mark=turningShapes(rows)[0];expect(mark).toBeTruthy();
 expect(turningShapes(rows.slice(1))).toEqual([]);expect(turningShapes([...rows,rows[0]])).toEqual([]);
 for(const flag of [false,1,'true'])for(const time of ['09:30',mark.time])
  expect(turningShapes(rows.map(b=>b.time===time?{...b,complete:flag as boolean}:b)).some(m=>m.key===mark.key)).toBe(false);
 for(const changed of [rows.filter(b=>b.time!==mark.time),[...rows,rows.find(b=>b.time===mark.time)!]])
  expect(turningShapes(changed).some(m=>m.key===mark.key)).toBe(false);
});

test('every sampled prefix and arbitrary future prices preserve emitted signals',()=>{
 for(const c of r1.cases){
  const rows=bars(c),full=turningShapes(rows);
  for(let cut=1;cut<=rows.length;cut+=7){
   const expected=full.filter(m=>m.time<=rows[cut-1].time);
   expect(turningShapes(rows.slice(0,cut))).toEqual(expected);
   expect(turningShapes(rows.map((b,i)=>i<cut?b:{...b,close:'9999',average:'1'})).filter(m=>m.time<=rows[cut-1].time)).toEqual(expected);
  }
 }
});

test('Sanfu emits the top at 10:32 without any later minute',()=>{
 const c=r1.cases.find((c:any)=>c.code==='sh603938'&&c.day==='2026-11-10'),rows=bars(c),index=rows.findIndex(b=>b.time==='10:32');
 expect(turningShapes(rows.slice(0,index))).toEqual([]);
 expect(turningShapes(rows.slice(0,index+1)).map(m=>[m.kind,m.time])).toEqual([['top','10:32']]);
});

test('one reversal minute suffices, while the original 14:56 cutoff is preserved',()=>{
 for(const start of [0,234]){
  const got=turningShapes(synthetic([98,98.7],start));expect(got).toHaveLength(1);
  expect(got[0]).toMatchObject({candidateTime:times[start],time:times[start+1]});
 }
 expect(turningShapes(synthetic([98,98.7],235))).toEqual([]);
});

test('zero-volume context does not block but the emitting minute needs volume',()=>{
 const rows=synthetic([98,98.7]);rows[1].volume=0;expect(turningShapes(rows)).toHaveLength(1);
 rows[2].volume=0;expect(turningShapes(rows)).toEqual([]);
 for(const volume of [-1,NaN,Infinity])expect(turningShapes(synthetic([98,98.7]).map((b,i)=>i===1?{...b,volume}:b))).toEqual([]);
});

test('small same-wave moves are suppressed and meaningful new waves have no daily quota',()=>{
 expect(turningShapes(synthetic([98,98.7,97.8,98.5,96,97.5])).map(m=>m.candidatePrice)).toEqual([98,96]);
 for(const side of ['bottom','top']){
  const prices=[98,98.7,96,97.5,94,96].map(p=>side==='bottom'?p:200-p),got=turningShapes(synthetic(prices));
  expect(got).toHaveLength(3);expect(got.every(m=>m.kind===side)).toBe(true);
  expect(new Set(got.map(m=>m.key)).size).toBe(got.length);
 }
});

test('expired candidates are discarded and quote inputs are not mutated',()=>{
 expect(turningShapes(synthetic([98,98.05,98.1,98.15,99]))).toEqual([]);
 const rows=bars(r1.cases[0]),copy=structuredClone(rows);expect(turningShapes(rows)).toEqual(turningShapes(rows));expect(rows).toEqual(copy);
 expect(turningShapes([])).toEqual([]);expect(turningShapes(synthetic(Array(240).fill(100)))).toEqual([]);
});

test('display merges overlaps, keeps one point per kind+price, and preserves uncapped Q1/shape points',()=>{
 const dedupe=(rows:any[])=>{const seen=new Set<string>();return rows.filter(p=>{const key=p.kind+'|'+Math.round(p.price*100);if(seen.has(key))return false;seen.add(key);return true;});};
 for(const c of r1.cases){
  const rows=bars(c),shapes=turningShapes(rows),quality=turningQualityQ1(rows),points=turningDisplayPoints(shapes,quality,true,true,Infinity);
  expect(new Set(points.map(p=>p.kind+'|'+p.time)).size).toBe(points.length);
  expect(new Set(points.map(p=>p.kind+'|'+Math.round(p.price*100))).size).toBe(points.length);
  const shapePoints=turningDisplayPoints(shapes,quality,true,false,Infinity);
  expect(shapePoints.map(p=>p.shape)).toEqual(dedupe(shapes));
  const q1Only=turningDisplayPoints(shapes,quality,false,true,Infinity);
  expect(q1Only.map(p=>p.q1)).toEqual(dedupe(quality));
  // Uncapped shape+Q1 merge: shapes win a same-price clash, Q1 points otherwise preserved.
  expect(points.filter(p=>p.shape).map(p=>p.shape)).toEqual(dedupe(shapes));
  const shapeKeys=new Set(shapes.map((s:any)=>s.kind+'|'+Math.round(s.price*100)));
  expect(points.filter(p=>p.q1&&!p.shape).map(p=>p.q1)).toEqual(dedupe(quality).filter((q:any)=>!shapeKeys.has(q.kind+'|'+Math.round(q.price*100))));
  expect(turningDisplayPoints(shapes,quality,false,false,Infinity)).toEqual([]);
 }
});

test('display hard-caps 3/kind/day: shapes win the slots and Q1 only fills the rest',()=>{
 const shape=(kind:'top'|'bottom',time:string,price=10)=>({key:'shape-v2|'+kind+'|'+time,kind,time,price,candidateTime:time,candidatePrice:price,vwap:10,
  deviationPct:1,support:9,resistance:11,movePct:1,volumeRatio:1,quality:6,capIndex:1,ruleVersion:'shape-v2.0'});
 const q1=(kind:'top'|'bottom',time:string,price=10)=>({key:'quality-first-Q|'+kind+'|'+time,kind,time,price,candidateTime:time,candidatePrice:price,vwap:10,
  deviationPct:1,support:9,resistance:11,movePct:1,volumeRatio:1,quality:{meanShares:1,currentShares:1,knownVwap:10,knownSpaceNetPct:1}});
 const shapes=[shape('top','09:31',10),shape('top','09:40',10.1)];
 const quality=[q1('top','09:32',10.2),q1('top','09:33',10.3),q1('top','09:35',10.4),q1('top','09:50',10.5)];
 expect(turningDisplayPoints(shapes,quality,true,true,3).map(p=>p.time)).toEqual(['09:31','09:32','09:40']);
 // Even if a future engine produced more shapes, display still stops at the cap.
 const many=Array.from({length:5},(_,i)=>shape('bottom',String(9+i).padStart(2,'0')+':00',10+i/100));
 expect(turningDisplayPoints(many,[],true,false,3).map(p=>p.time)).toEqual(['09:00','10:00','11:00']);
 // Hidden shapes never let Q1 exceed the cap either.
 expect(turningDisplayPoints(shapes,quality,false,true,3).map(p=>p.time)).toEqual(['09:32','09:33','09:35']);
 for(const kind of ['top','bottom'] as const)expect(turningDisplayPoints(many,quality,true,true).filter(p=>p.kind===kind).length).toBeLessThanOrEqual(3);
});

test('Q1 top/bottom are both promoted to signals in the display merge',()=>{
 const shape=(kind:'top'|'bottom',time:string,price=10)=>({key:'shape-v2|'+kind+'|'+time,kind,time,price,candidateTime:time,candidatePrice:price,vwap:10,
  deviationPct:1,support:9,resistance:11,movePct:1,volumeRatio:1,quality:6,capIndex:1,ruleVersion:'shape-v2.0'});
 const q1=(kind:'top'|'bottom',time:string,price=10)=>({key:'quality-first-Q|'+kind+'|'+time,kind,time,price,candidateTime:time,candidatePrice:price,vwap:10,
  deviationPct:1,support:9,resistance:11,movePct:1,volumeRatio:1,quality:{meanShares:1,currentShares:1,knownVwap:10,knownSpaceNetPct:1}});
 // Q1-only points on both sides are promoted.
 const only=turningDisplayPoints([],[q1('bottom','10:00',10),q1('top','10:01',10.2)],true,true,Infinity);
 expect(only.find(p=>p.kind==='bottom')!.promotedBottom).toBe(true);
 expect(only.find(p=>p.kind==='top')!.promotedTop).toBe(true);
 // Same-minute v2 + Q1 bottom merge into one point (existing rule, shape wins).
 const merged=turningDisplayPoints([shape('bottom','10:00')],[q1('bottom','10:00')],true,true,Infinity);
 expect(merged).toHaveLength(1);
 expect(merged[0].shape).toBeTruthy();
 expect(merged[0].q1).toBeTruthy();
 expect(merged[0].promotedBottom).toBe(false);
 // The 3/day cap still applies: three shapes win all slots, a Q1 bottom is not shown.
 const capped=turningDisplayPoints([shape('bottom','09:31',10),shape('bottom','09:40',10.1),shape('bottom','09:50',10.2)],[q1('bottom','10:00',10.3)],true,true,3);
 expect(capped.map(p=>p.time)).toEqual(['09:31','09:40','09:50']);
});

test('Display never repeats the same kind at the same price (v2 wins over Q1, earlier otherwise)',()=>{
 const shape=(kind:'top'|'bottom',time:string,price:number)=>({key:'shape-v2|'+kind+'|'+time,kind,time,price,candidateTime:time,candidatePrice:price,vwap:price,
  deviationPct:1,support:price-1,resistance:price+1,movePct:1,volumeRatio:1,quality:6,capIndex:1,ruleVersion:'shape-v2.0'});
 const q1=(kind:'top'|'bottom',time:string,price:number)=>({key:'quality-first-Q|'+kind+'|'+time,kind,time,price,candidateTime:time,candidatePrice:price,vwap:price,
  deviationPct:1,support:price-1,resistance:price+1,movePct:1,volumeRatio:1,quality:{meanShares:1,currentShares:1,knownVwap:price,knownSpaceNetPct:1}});
 // 利欧股份复现：同一价格 4.28 的两个 Q1 底，只保留先出现的 13:56。
 const leo=turningDisplayPoints([],[q1('bottom','13:56',4.28),q1('bottom','14:33',4.28)],true,true,3);
 expect(leo.map(p=>p.time)).toEqual(['13:56']);
 // 同类同价：v2 优先；若都是 Q1 保留更早；不同价格正常保留。
 const mixed=turningDisplayPoints([shape('top','10:30',4.45)],[q1('top','10:11',4.45),q1('top','11:00',4.50)],true,true,3);
 expect(mixed.map(p=>p.time)).toEqual(['10:30','11:00']);
 expect(mixed[0].shape).toBeTruthy();
 // 底/顶不同 kind 同价互不影响。
 const both=turningDisplayPoints([],[q1('bottom','10:00',10),q1('top','10:05',10)],true,true,3);
 expect(both).toHaveLength(2);
});
