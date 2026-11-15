import {test,expect} from '@playwright/test';
import {candleChangeText} from '../../src/candleTooltip';
import {weeklyBars} from '../../src/candleData';
import type {Daily} from '../../src/models';
const b=(date:string,close:string,provisional=false):Daily=>({date,close,open:close,high:close,low:close,volume:'100',provisional});

test('returns are prefix invariant, independent of future daily candles or future weeks',()=>{
 const rows=[b('2026-10-09','10'),b('2026-10-12','11'),b('2026-10-13','12'),b('2026-10-16','13'),b('2026-10-19','14',true)];
 for(let length=2;length<=rows.length;length++){
  const prefix=rows.slice(0,length),mutated=[...prefix,...rows.slice(length).map(row=>({...row,close:'999'}))];
  for(let i=0;i<prefix.length;i++)expect(candleChangeText(mutated,i)).toBe(candleChangeText(prefix,i));
  const weeks=weeklyBars(prefix),later=weeklyBars([...prefix,b('2026-10-26','888')]);
  for(let i=0;i<weeks.length;i++)expect(candleChangeText(later,i)).toBe(candleChangeText(weeks,i));
 }
});

test('unfinished week changes only with observed prices in that week; previous week stays fixed',()=>{
 const rows=[b('2026-10-02','8'),b('2026-10-09','10'),b('2026-10-12','11')];
 const monday=weeklyBars(rows),tuesday=weeklyBars([...rows,b('2026-10-13','12',true)]);
 expect(candleChangeText(monday,2)).toBe('+10.00%');expect(candleChangeText(tuesday,2)).toBe('+20.00%');
 expect(candleChangeText(monday,1)).toBe('+25.00%');expect(candleChangeText(tuesday,1)).toBe('+25.00%');
 expect(tuesday[2].provisional).toBe(true);expect(rows).toHaveLength(3);
});

test('missing, nonpositive or unfinished previous close never falls back to an older candle',()=>{
 for(const close of ['', ' ', '0','-1','NaN','Infinity']){
  expect(candleChangeText([b('2026-10-08','8'),b('2026-10-09',close),b('2026-10-12','11')],2)).toBe('—（缺少前收盘）');
  expect(candleChangeText(weeklyBars([b('2026-10-02','8'),b('2026-10-09',close),b('2026-10-12','11')]),2)).toBe('—（缺少前收盘）');
 }
 expect(candleChangeText(weeklyBars([b('2026-10-12','11')]),0)).toBe('—（缺少前收盘）');
 expect(candleChangeText([b('2026-10-09','10',true),b('2026-10-12','11')],1)).toBe('—（前收盘未确认）');
 expect(candleChangeText([b('2026-10-09','10'),b('2026-10-09','11')],1)).toBe('—（缺少前收盘）');
 expect(candleChangeText([b('2026-10-12','10'),b('2026-10-09','11')],1)).toBe('—（缺少前收盘）');
 for(const close of ['9.999999','10','10.000001'])expect(candleChangeText([b('2026-10-09','10'),b('2026-10-12',close)],1)).toBe('0.00%');
});

test('hover calculation reads just two candles even for a long immutable history',()=>{
 const rows=Object.freeze(Array.from({length:100000},(_,i)=>Object.freeze(b(i===99999?'2026-10-12':'2026-10-09',i===99999?'11':'10'))));
 const reads:string[]=[];
 const guarded=new Proxy(rows,{get(target,key,receiver){reads.push(String(key));if(key!=='99998'&&key!=='99999')throw Error('Unexpected history traversal: '+String(key));return Reflect.get(target,key,receiver);}});
 expect(candleChangeText(guarded,99999)).toBe('+10.00%');expect(reads).toEqual(['99999','99998']);
});
