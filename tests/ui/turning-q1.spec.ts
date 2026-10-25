import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import type {Bar} from '../../src/models';
import {turningQualityQ1} from '../../src/turningQualityQ1';
import {q1CostSpace} from '../../src/turningQualityQ1Costs';
const cases=JSON.parse(readFileSync('tests/ui/fixtures/turning-q1.json','utf8'));
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

test('Q1 exact frozen outputs and dependency hashes match the selected historical candidate',()=>{
 const freeze=JSON.parse(readFileSync('docs/turning-quality-q1/freeze.json','utf8'));
 for(const [file,hash] of Object.entries(freeze.sourceHashes))expect(createHash('sha256').update(readFileSync(file)).digest('hex')).toBe(hash);
 for(const c of cases)expect(turningQualityQ1(c.bars)).toEqual(c.expected);
});

test('Q1 has no daily bottom or top quota',()=>{
 const values:Record<number,number>={30:2.34,31:2.33,32:2.33,70:2.40,71:2.39,72:2.39,73:2.38,110:2.46,111:2.45,112:2.44};
 const tops=times.map((time,i)=>({time,close:String(values[i]??2.28),average:'2.20',volume:100000,complete:true}));
 expect(turningQualityQ1(tops).filter(m=>m.kind==='top').length).toBeGreaterThan(2);
 const bottoms=times.map((time,i)=>({time,close:String(i===30?2.12:i===70?2.10:i===110?2.08:2.20),average:'2.30',volume:100000,complete:true}));
 expect(turningQualityQ1(bottoms).filter(m=>m.kind==='bottom').length).toBeGreaterThan(1);
});

test('Q1 known liquidity gates reject insufficient volumes and invalid or unfinished inputs',()=>{
 const c=cases[1],bars=c.bars as Bar[],time=c.expected[0].time;
 expect(turningQualityQ1(bars.map(b=>({...b,volume:99999})))).toEqual([]);
 for(const changed of [bars.map(b=>b.time===time?{...b,complete:false}:b),bars.filter(b=>b.time!==time),
  [...bars,bars.find(b=>b.time===time)!],bars.map(b=>b.time===time?{...b,average:null}:b),bars.map(b=>({...b,average:null}))])
  expect(turningQualityQ1(changed).some(m=>m.time===time)).toBe(false);
 expect(turningQualityQ1([])).toEqual([]);
});

test('Q1 accepted signals do not change when future data changes or arrives',()=>{
 const bars=cases[1].bars as Bar[],all=turningQualityQ1(bars);
 for(let i=0;i<bars.length;i++){
  const expected=all.filter(m=>m.time<=bars[i].time);
  expect(turningQualityQ1(bars.slice(0,i+1))).toEqual(expected);
  expect(turningQualityQ1(bars.map((b,j)=>j<=i?b:{...b,close:'999',average:'1',volume:1})).filter(m=>m.time<=bars[i].time)).toEqual(expected);
 }
});

test('Q1 frozen cost rounding includes cent slippage, minimum commissions and side-specific fees',()=>{
 expect(q1CostSpace(5.44,5.49)).toEqual({netCny:17.16,feesCny:12.84,buyFill:5.45,sellFill:5.48});
 expect(q1CostSpace(10,10)).toEqual({netCny:-35.2,feesCny:15.2,buyFill:10.01,sellFill:9.99});
 for(const p of [0,-1,NaN,Infinity])expect(q1CostSpace(p,10)).toBeNull();
});
