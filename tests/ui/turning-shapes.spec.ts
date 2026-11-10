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

test('display merges overlaps and preserves independent Q1 points',()=>{
 for(const c of r1.cases){
  const rows=bars(c),shapes=turningShapes(rows),quality=turningQualityQ1(rows),points=turningDisplayPoints(shapes,quality,true,true);
  expect(new Set(points.map(p=>p.kind+'|'+p.time)).size).toBe(points.length);
  expect(points.filter(p=>p.q1).map(p=>p.q1)).toEqual(quality);
  expect(points.filter(p=>p.shape).map(p=>p.shape)).toEqual(shapes);
  expect(turningDisplayPoints(shapes,quality,false,true).map(p=>p.q1)).toEqual(quality);
  expect(turningDisplayPoints(shapes,quality,true,false).map(p=>p.shape)).toEqual(shapes);
  expect(turningDisplayPoints(shapes,quality,false,false)).toEqual([]);
 }
});
