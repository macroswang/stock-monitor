import {test,expect} from '@playwright/test';
import {dailyPatterns,dailyPatternStatus} from '../../src/dailyPatterns';
import type {DailyPattern} from '../../src/dailyPatterns';

import {candles,flag,bear,triangle,spring} from './fixtures/daily-patterns';
const frozen=(p:DailyPattern)=>({key:p.key,kind:p.kind,start:p.start,detectedOn:p.detectedOn,detectedIndex:p.detectedIndex,anchors:p.anchors,
 lines:p.lines.map(l=>({role:l.role,from:l.from,...(['pole','outline'].includes(l.role)?{to:l.to}:{})}))});

test('flags require a prior pole and retain the actual opposite-sloping parallel boundaries',()=>{
 for(const [rows,kind,status] of [[flag,'falling-flag','up'],[bear,'rising-flag','down']] as const){
  const all=dailyPatterns(rows).filter(p=>p.kind===kind);
  expect(all).toHaveLength(1);const p=all[0];
  expect(p.status).toBe(status);expect(p.detectedOn<p.breakoutOn!).toBe(true);
  expect(p.lines.some(l=>l.role==='pole')).toBe(true);
  const edges=p.lines.filter(l=>l.role==='upper'||l.role==='lower');
  for(const edge of edges)expect(Math.sign(edge.to.price-edge.from.price)).toBe(kind==='falling-flag'?-1:1);
  expect(dailyPatterns(rows.slice(7)).some(p=>p.kind===kind)).toBe(false);
 }
});

test('a triangle has descending highs and ascending lows; either closing breakout is recorded',()=>{
 const up=dailyPatterns(triangle).find(p=>p.kind==='triangle')!;
 expect(up).toBeDefined();expect(up.status).toBe('up');
 const upper=up.lines.find(l=>l.role==='upper')!,lower=up.lines.find(l=>l.role==='lower')!;
 expect(upper.to.price).toBeLessThan(upper.from.price);expect(lower.to.price).toBeGreaterThan(lower.from.price);
 expect(up.anchors.filter(p=>p.price>11).length).toBeGreaterThanOrEqual(2);
 const down=triangle.map(b=>({...b,open:String(22-+b.open),close:String(22-+b.close),high:String(22-+b.low),low:String(22-+b.high)}));
 expect(dailyPatterns(down).find(p=>p.kind==='triangle')?.status).toBe('down');
 expect(dailyPatterns(triangle.slice(0,up.detectedIndex+1)).find(p=>p.key===up.key)?.status).toBe('forming');
});

test('same-direction converging boundaries are a wedge, not a symmetrical triangle',()=>{
 const wedge=candles([[0,7],[3,8],[8,7.2],[13,9],[18,8.6],[23,10],[28,9.8],[30,10]]);
 expect(dailyPatterns(wedge).some(p=>p.kind==='triangle')).toBe(false);
 expect(dailyPatterns(candles([[0,10],[30,13]]))).toEqual([]);
});

test('a false breakdown is first a reclaim, with a separately dated neckline breakout',()=>{
 const early=dailyPatterns(spring.slice(0,11)).find(p=>p.kind==='spring')!;
 expect(early).toBeDefined();expect(early.status).toBe('reclaimed');expect(early.detectedOn).toBe(spring[10].date);
 expect(early.necklineOn).toBeUndefined();expect(early.anchors[0].price).toBeCloseTo(9.96);
 expect(early.anchors[2].price).toBeCloseTo(9.56);
 const full=dailyPatterns(spring).find(p=>p.key===early.key)!;
 expect(full.status).toBe('neckline');expect(full.necklineOn).toBe(spring[12].date);
 expect(frozen(full)).toEqual(frozen(early));
});

test('a same-day undercut and reclaim uses the actual wick; a bounce below support is not a reclaim',()=>{
 const one=spring.slice(0,10).map((b,i)=>i===9?{...b,open:'9.8',low:'9.4',high:'10.5',close:'10.3'}:b);
 expect(dailyPatterns(one).find(p=>p.kind==='spring')?.detectedOn).toBe(one[9].date);
 const weak=spring.slice(0,11).map((b,i)=>i===10?{...b,open:'9.7',close:'9.8',low:'9.65',high:'9.9'}:b);
 expect(dailyPatterns(weak).some(p=>p.kind==='spring')).toBe(false);
});

test('later failure retains the original reversal and its detection date',()=>{
 const rows=[...spring.slice(0,11),{...spring[11],open:'9.8',close:'9.3',low:'9.2',high:'9.9'}];
 const p=dailyPatterns(rows).find(p=>p.kind==='spring')!;
 expect(p.status).toBe('failed');expect(p.failedOn).toBe(rows[11].date);expect(p.detectedOn).toBe(rows[10].date);
 expect(dailyPatternStatus(p)).toBe('后续失效');
});

test('closing back below the reclaimed support is recorded even before another new low',()=>{
 const rows=[...spring.slice(0,11),{...spring[11],open:'9.9',close:'9.7',low:'9.65',high:'10'}];
 const p=dailyPatterns(rows).find(p=>p.kind==='spring')!;
 expect(p.status).toBe('failed');expect(p.failureReason).toBe('support');expect(p.failedOn).toBe(rows[11].date);
});

test('all historical detection dates and anchors are causal and frozen as the input grows',()=>{
 for(const rows of [flag,bear,triangle,spring]){
  const full=dailyPatterns(rows);
  for(let i=0;i<rows.length;i++){
   const prefix=dailyPatterns(rows.slice(0,i+1));
   expect(prefix.map(frozen)).toEqual(full.filter(p=>p.detectedIndex<=i).map(frozen));
   for(const p of prefix){
    expect(p.anchors.every(a=>a.index<=i)).toBe(true);
    expect(p.lines.every(l=>l.from.index<=i&&l.to.index<=i)).toBe(true);
    expect(!p.breakoutOn||p.breakoutOn<=rows[i].date).toBe(true);
    expect(!p.necklineOn||p.necklineOn<=rows[i].date).toBe(true);
   }
  }
 }
});

test('unfinished daily bars cannot confirm either a reclaim or a channel breakout',()=>{
 const unfinished=spring.slice(0,11).map((b,i)=>i===10?{...b,provisional:true}:b);
 expect(dailyPatterns(unfinished).some(p=>p.kind==='spring')).toBe(false);
 const forming=dailyPatterns(flag.slice(0,19)).find(p=>p.kind==='falling-flag')!;
 const provisional=flag.slice(0,20).map((b,i)=>i===19?{...b,provisional:true}:b);
 expect(dailyPatterns(provisional).find(p=>p.key===forming.key)?.breakoutOn).toBeUndefined();
});

test('invalid OHLC and duplicate dates cannot be bridged to manufacture a shape',()=>{
 const malformed=spring.map((b,i)=>i===8?{...b,low:'99'}:b);
 expect(dailyPatterns(malformed).some(p=>p.kind==='spring')).toBe(false);
 expect(dailyPatterns([...spring.slice(0,8),spring[7],...spring.slice(8)]).some(p=>p.kind==='spring')).toBe(false);
 expect(dailyPatterns([])).toEqual([]);
});

test('price geometry does not inherit a volume, profitability or trade-selection gate',()=>{
 for(const rows of [flag,bear,triangle,spring])expect(dailyPatterns(rows.map(b=>({...b,volume:'0'}))).map(frozen)).toEqual(dailyPatterns(rows).map(frozen));
});
