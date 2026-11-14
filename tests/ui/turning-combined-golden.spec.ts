import {test,expect} from '@playwright/test';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import type {Bar} from '../../src/models';
import {turningFinal,TURNING_FINAL_MODES} from '../../src/turningFinal';
import {turningQualityQ1} from '../../src/turningQualityQ1';
import {turningDisplayPoints} from '../../src/turningDisplay';
import {turningCombinedForBars,turningCombinedSignals,TURNING_COMBINED_SIGNAL,TURNING_COMBINED_VERSION,TURNING_COMBINED_CAP_PER_KIND} from '../../src/turningCombined';

// Golden cross-language fixture for core/turning_combined.py (shape-v2-q1 trading stream).
// Regenerate deliberately with: UPDATE_TURNING_COMBINED_GOLDEN=1 npx playwright test tests/ui/turning-combined-golden.spec.ts
const GOLDEN='tests/fixtures/turning-combined-golden.json';
const reconstruction=JSON.parse(readFileSync('tests/fixtures/zhangle-reconstruction.json','utf8'));
const tencent=JSON.parse(readFileSync('tests/ui/fixtures/turning-final-20261112-cases.json','utf8'));
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
const seed=(p:number):Bar=>({time:'09:30',close:String(p),average:String(p),volume:0,complete:true});
const caseBars=(c:any):Bar[]=>[seed(c.opening_price),...c.prices.map((p:number,i:number)=>({time:times[i],close:String(p),average:String(c.averages[i]),volume:c.volumes[i],complete:true}))];

// Minimal deterministic event stubs for merge-rule parity (same shape as engine events).
const event=(kind:'top'|'bottom',time:string,price:number,key:string)=>({
 key,kind,time,price,candidateTime:time,candidatePrice:price+0.01,vwap:price,deviationPct:1,
 support:price-1,resistance:price+1,movePct:.5,volumeRatio:1,
} as any);
const q1=(kind:'top'|'bottom',time:string,price:number,key:string)=>({
 ...event(kind,time,price,key),quality:{meanShares:10000,currentShares:10000,knownVwap:price,knownSpaceNetPct:.3},
} as any);

function mergeCases(){
 const top=event('top','09:45',10,'v2|top|09:43');
 const fill1=q1('top','09:50',10.5,'q1|top|09:48|09:50');
 const fill2=q1('top','09:55',11,'q1|top|09:53|09:55');
 const fill3=q1('top','10:00',11.5,'q1|top|09:58|10:00');
 const sameMinute=q1('top','09:45',10.2,'q1|top|09:44|09:45');
 const samePrice=q1('top','10:05',10,'q1|top|10:03|10:05');
 const bottomFill=q1('bottom','13:05',9.5,'q1|bottom|13:03|13:05');
 const bottomSamePrice=q1('bottom','13:10',9.5,'q1|bottom|13:08|13:10');
 return [
  {name:'same-minute-v2-wins',final:[top],q1:[sameMinute],expected:turningCombinedSignals([top],[sameMinute])},
  {name:'q1-fills-remaining-slots-in-time-order',final:[top],q1:[fill3,fill1,fill2],expected:turningCombinedSignals([top],[fill3,fill1,fill2])},
  {name:'same-display-price-deduped',final:[top],q1:[samePrice,bottomFill,bottomSamePrice],expected:turningCombinedSignals([top],[samePrice,bottomFill,bottomSamePrice])},
  {name:'spacing-boundaries-and-lunch',final:[event('top','11:25',10,'a'),event('top','13:04',10.1,'b'),event('top','13:05',10.2,'c')],
   q1:[q1('bottom','11:26',9.8,'d'),q1('bottom','13:05',9.7,'e'),q1('bottom','13:06',9.6,'f')],
   expected:turningCombinedSignals([event('top','11:25',10,'a'),event('top','13:04',10.1,'b'),event('top','13:05',10.2,'c')],
    [q1('bottom','11:26',9.8,'d'),q1('bottom','13:05',9.7,'e'),q1('bottom','13:06',9.6,'f')])},
  {name:'cap-and-sort-mixed-kinds',final:[top,event('bottom','10:30',9.8,'v2|bottom|10:28')],
   q1:[fill1,fill2,fill3,bottomFill,bottomSamePrice],expected:turningCombinedSignals([top,event('bottom','10:30',9.8,'v2|bottom|10:28')],[fill1,fill2,fill3,bottomFill,bottomSamePrice])},
 ];
}

function build(){
 const cases=[
  ...reconstruction.cases.map((c:any)=>({source:'fixture38',code:c.code,day:c.day,events:turningCombinedForBars(caseBars(c))})),
  ...tencent.map((c:any)=>({source:'today21',code:c.code,day:c.day,events:turningCombinedForBars(caseBars(c))})),
 ];
 return {meta:{generated_by:'tests/ui/turning-combined-golden.spec.ts',signal:TURNING_COMBINED_SIGNAL,
  version:TURNING_COMBINED_VERSION,capPerKind:TURNING_COMBINED_CAP_PER_KIND},
  cases,mergeCases:mergeCases()};
}

test('combined golden fixture is in sync with src/turningCombined.ts',()=>{
 const current=build();
 if(process.env.UPDATE_TURNING_COMBINED_GOLDEN==='1')writeFileSync(GOLDEN,JSON.stringify(current));
 expect(existsSync(GOLDEN)).toBe(true);
 expect(JSON.parse(readFileSync(GOLDEN,'utf8'))).toEqual(current);
 expect(current.meta.signal).toBe('shape-v2-q1');
 expect(current.cases).toHaveLength(59);
 for(const c of current.cases){
  const events=c.events;
  expect(events.map((e:any)=>e.time)).toEqual([...events.map((e:any)=>e.time)].sort());
  for(const kind of ['top','bottom'] as const)expect(events.filter((e:any)=>e.kind===kind).length).toBeLessThanOrEqual(3);
  // Spacing applies to the merged chart/trading stream, including v2 events.
  const v2=turningFinal(caseBars(tencent.find((x:any)=>x.code===c.code&&x.day===c.day)||reconstruction.cases.find((x:any)=>x.code===c.code&&x.day===c.day)),TURNING_FINAL_MODES.zhangle);
  const source=tencent.find((x:any)=>x.code===c.code&&x.day===c.day)||reconstruction.cases.find((x:any)=>x.code===c.code&&x.day===c.day);
  expect(events.map((e:any)=>[e.kind,e.time,e.price])).toEqual(turningDisplayPoints(v2,turningQualityQ1(caseBars(source)),true,true).map(e=>[e.kind,e.time,e.price]));
 }
});

test('combined merge rules: same-minute v2 priority, time-ordered Q1 fill, price dedupe, cap 3',()=>{
 const cases=build().mergeCases;
 for(const c of cases){
  expect(c.expected.some((e:any)=>e.key==='q1|top|09:44|09:45')).toBe(false); // same minute
  for(const kind of ['top','bottom'] as const)expect(c.expected.filter((e:any)=>e.kind===kind).length).toBeLessThanOrEqual(3);
 }
 const fill=build().mergeCases.find(c=>c.name==='q1-fills-remaining-slots-in-time-order')!;
 expect(fill.expected.map((e:any)=>e.key)).toEqual(['v2|top|09:43','q1|top|09:53|09:55']);
 const dedupe=build().mergeCases.find(c=>c.name==='same-display-price-deduped')!;
 expect(dedupe.expected.map((e:any)=>e.key)).toEqual(['v2|top|09:43','q1|bottom|13:03|13:05']);
 expect(cases.find(c=>c.name==='spacing-boundaries-and-lunch')!.expected.map((e:any)=>e.key)).toEqual(['a','d','c','f']);
});

test('中文在线 filters the nearby 09:41 top in both chart and trading',()=>{
 const {bars}=JSON.parse(readFileSync('tests/ui/fixtures/turning-spacing-20261113.json','utf8'));
 const main=turningFinal(bars,TURNING_FINAL_MODES.zhangle),quality=turningQualityQ1(bars);
 expect(main.filter((p:any)=>p.kind==='top').map((p:any)=>p.time)).toEqual(['09:34','09:41','10:34']);
 const trading=turningCombinedSignals(main,quality),display=turningDisplayPoints(main,quality,true,true);
 expect(trading.filter(p=>p.kind==='top').map(p=>p.time)).toEqual(['09:34','10:34']);
 expect(display.map(p=>[p.kind,p.time,p.price])).toEqual(trading.map(p=>[p.kind,p.time,p.price]));
});
