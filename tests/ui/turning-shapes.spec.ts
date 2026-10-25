import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import type {Bar} from '../../src/models';
import {turningShapes} from '../../src/turningShapes';
import {turningQualityQ1} from '../../src/turningQualityQ1';
import {turningDisplayPoints} from '../../src/turningDisplay';
const fixtures=JSON.parse(readFileSync('tests/ui/fixtures/turning-shapes.json','utf8'));
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
const geometry=(marks:{kind:string;time:string;price:number;candidateTime:string;candidatePrice:number}[])=>marks.map(m=>[m.kind,m.time,m.price,m.candidateTime,m.candidatePrice]);

test('confirmed shapes recover actual missing sides while frozen Q1 outputs stay exact',()=>{
 for(const c of fixtures){
  const shapes=turningShapes(c.bars),quality=turningQualityQ1(c.bars);
  expect(shapes).toEqual(c.expectedShapes);expect(quality).toEqual(c.expectedQ1);
  expect(new Set(shapes.map(m=>m.kind))).toEqual(new Set(['bottom','top']));
 }
 const shanzi=fixtures.find((c:any)=>c.code==='sz000981');
 expect(shanzi.expectedQ1.every((m:any)=>m.kind==='top')).toBe(true);
 expect(shanzi.expectedShapes.some((m:any)=>m.kind==='bottom')).toBe(true);
});

test('price shapes do not inherit Q1 order-size or cost quality gates',()=>{
 for(const c of fixtures){
  const tiny=c.bars.map((b:Bar)=>({...b,volume:1}));
  expect(geometry(turningShapes(tiny))).toEqual(geometry(turningShapes(c.bars)));
  expect(turningQualityQ1(tiny)).toEqual([]);
 }
});

test('shapes have no daily quota and never manufacture an opposite side',()=>{
 const peaks:Record<number,number>={30:2.34,31:2.33,32:2.33,70:2.40,71:2.39,72:2.39,73:2.38,110:2.46,111:2.45,112:2.44};
 const tops=times.map((time,i)=>({time,close:String(peaks[i]??2.28),average:'2.20',volume:100000,complete:true}));
 const topMarks=turningShapes(tops);
 expect(topMarks.filter(m=>m.kind==='top').length).toBeGreaterThan(2);
 expect(topMarks.some(m=>m.kind==='bottom')).toBe(false);
 const lows=times.map((time,i)=>({time,close:String(i===30?2.12:i===70?2.10:i===110?2.08:2.20),average:'2.30',volume:100000,complete:true}));
 const bottomMarks=turningShapes(lows);
 expect(bottomMarks.filter(m=>m.kind==='bottom').length).toBeGreaterThan(1);
 expect(bottomMarks.some(m=>m.kind==='top')).toBe(false);
});

test('repeated confirmation minutes and small same-run moves do not crowd the chart',()=>{
 for(const c of fixtures){
  const marks=turningShapes(c.bars);
  expect(new Set(marks.map(m=>m.kind+'|'+m.candidateTime+'|'+m.candidatePrice)).size).toBe(marks.length);
  for(const kind of ['bottom','top']){
   const same=marks.filter(m=>m.kind===kind);
   for(let i=1;i<same.length;i++)expect(times.indexOf(same[i].time)-times.indexOf(same[i-1].time)).toBeGreaterThanOrEqual(30);
  }
 }
});

test('shape confirmations stay fixed under prefixes and arbitrary future changes',()=>{
 for(const c of fixtures){
  const bars=c.bars as Bar[],full=turningShapes(bars);
  for(const mark of full){
   const i=bars.findIndex(b=>b.time===mark.time),past=full.filter(m=>m.time<=mark.time);
   expect(turningShapes(bars.slice(0,i+1))).toEqual(past);
   expect(turningShapes(bars.map((b,j)=>j<=i?b:{...b,close:'9999',average:'1',volume:1})).filter(m=>m.time<=mark.time)).toEqual(past);
  }
 }
});

test('unfinished, missing and duplicate context cannot create a confirmed shape',()=>{
 const c=fixtures[0],bars=c.bars as Bar[],mark=c.expectedShapes[0];
 for(const changed of [bars.map(b=>b.time===mark.time?{...b,complete:false}:b),bars.filter(b=>b.time!==mark.time),[...bars,bars.find(b=>b.time===mark.time)!]])
  expect(turningShapes(changed).some(m=>m.time===mark.time)).toBe(false);
 expect(turningShapes([])).toEqual([]);
});

test('display merges exact overlap once and preserves every original Q1 point',()=>{
 for(const c of fixtures){
  const shapes=turningShapes(c.bars),quality=turningQualityQ1(c.bars),points=turningDisplayPoints(shapes,quality,true,true);
  expect(new Set(points.map(p=>p.kind+'|'+p.time)).size).toBe(points.length);
  expect(points.filter(p=>p.q1).map(p=>p.q1)).toEqual(quality);
  expect(points.filter(p=>p.shape).map(p=>p.shape)).toEqual(shapes);
  expect(points.length).toBeLessThanOrEqual(shapes.length+quality.length);
  expect(turningDisplayPoints(shapes,quality,false,false)).toEqual([]);
  expect(turningDisplayPoints(shapes,quality,false,true).map(p=>p.q1)).toEqual(quality);
  expect(turningDisplayPoints(shapes,quality,true,false).map(p=>p.shape)).toEqual(shapes);
 }
});

test('later Q1 acceptance is not moved back onto an earlier shape confirmation',()=>{
 const c=fixtures.find((c:any)=>c.code==='sz000981'),shapes=turningShapes(c.bars),quality=turningQualityQ1(c.bars);
 const points=turningDisplayPoints(shapes,quality,true,true);
 for(const q of quality){
  const p=points.find(p=>p.q1?.key===q.key)!;
  expect(p.time).toBe(q.time);expect(p.price).toBe(q.price);
 }
});
