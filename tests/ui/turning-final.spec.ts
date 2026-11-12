import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import type {Bar} from '../../src/models';
import {turningShapes} from '../../src/turningShapes';
import {turningFinal,turningFinalCandidates,turningFinalQualityV2,turningFinalQualityProximity,TURNING_FINAL_RULE,TURNING_FINAL_RULE_ZHANGLE,TURNING_FINAL_MODES,TURNING_FINAL_TIMES} from '../../src/turningFinal';

// Frozen calibration set: 38 stock-days / 63 native Zhangle markers.
const reconstruction=JSON.parse(readFileSync('tests/fixtures/zhangle-reconstruction.json','utf8'));
// Full-day Tencent minutes for 2026-11-12 (21 stocks, 67 verified native marks).
const tencent=JSON.parse(readFileSync('tests/ui/fixtures/turning-final-20261112-cases.json','utf8'));
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
const seed=(p:number):Bar=>({time:'09:30',close:String(p),average:String(p),volume:0,complete:true});
const caseBars=(c:any):Bar[]=>[seed(c.opening_price),...c.prices.map((p:number,i:number)=>({time:times[i],close:String(p),average:String(c.averages[i]),volume:c.volumes[i],complete:true}))];
const timeIndex=(stamp:string)=>times.indexOf(stamp);
const tuple=(m:any)=>[m.kind,m.time,m.price,m.candidateTime,m.candidatePrice] as const;
const geometry=(ms:any[])=>ms.map(tuple);

// Maximum-cardinality one-to-one matching, same kind, |minute delta| <= tol
// (port of the quant study's match_events; frozen evaluation tolerance is +/-1).
function matchEvents(events:any[],marks:any[],tol=1){
 const ev=events.map(e=>({i:timeIndex(e.time),kind:e.kind}));
 const mk=marks.map(m=>({i:timeIndex(m.time),kind:m.kind}));
 const adjacency=ev.map(()=>[] as number[]);
 for(let a=0;a<ev.length;a++)for(let b=0;b<mk.length;b++){
  if(ev[a].kind===mk[b].kind&&(ev[a].i===mk[b].i||Math.abs(ev[a].i-mk[b].i)<=tol))adjacency[a].push(b);
 }
 for(let a=0;a<ev.length;a++)adjacency[a].sort((x,y)=>Math.abs(ev[a].i-mk[x].i)-Math.abs(ev[a].i-mk[y].i));
 const matchB=new Array(mk.length).fill(-1);
 const augment=(a:number,seen:Set<number>):boolean=>{
  for(const b of adjacency[a]){if(seen.has(b))continue;seen.add(b);if(matchB[b]===-1||augment(matchB[b],seen)){matchB[b]=a;return true;}}
  return false;
 };
 let matched=0;for(let a=0;a<ev.length;a++)if(augment(a,new Set()))matched++;
 return matched;
}

function calibration(selector:(bars:Bar[])=>any[]){
 let matched=0,predicted=0,target=0;
 const perCase:any[]=[];
 for(const c of reconstruction.cases){
  const bars=caseBars(c),events=selector(bars),marks=c.broker_marks;
  const m=matchEvents(events,marks,1);
  matched+=m;predicted+=events.length;target+=marks.length;
  perCase.push({code:c.code,day:c.day,events:events.length,marks:marks.length,matched:m,
   maxTop:events.filter(e=>e.kind==='top').length,maxBottom:events.filter(e=>e.kind==='bottom').length});
 }
 return {matched,predicted,target,precision:predicted?matched/predicted:0,recall:target?matched/target:0,
  f05:matched?1.25*(matched/predicted)*(matched/target)/(0.25*(matched/predicted)+matched/target):0,perCase};
}

test('v2 stream: R1 kernel subset, frozen key/quality/cap contract',()=>{
 const r1=calibration(turningShapes),v2=calibration(turningFinal);
 console.log('[metrics] R1',JSON.stringify({matched:r1.matched,predicted:r1.predicted,target:r1.target,p:r1.precision,r:r1.recall,f05:r1.f05}));
 console.log('[metrics] v2',JSON.stringify({matched:v2.matched,predicted:v2.predicted,target:v2.target,p:v2.precision,r:v2.recall,f05:v2.f05}));
 for(const c of reconstruction.cases){
  const bars=caseBars(c),r1Events=turningShapes(bars),v2Events=turningFinal(bars);
  const r1Set=new Set(r1Events.map(geometryOne));
  for(const event of v2Events){
   expect(r1Set.has(JSON.stringify(tuple(event)))).toBe(true);
   expect(event.key).toBe(`shape-v2|${event.kind}|${event.candidateTime}`);
   expect(event.ruleVersion).toBe('shape-v2.0');
   expect(event.capIndex).toBeGreaterThanOrEqual(1);
   expect(event.capIndex).toBeLessThanOrEqual(3);
   expect(event.quality).toBeGreaterThanOrEqual(TURNING_FINAL_RULE.qualityTauEmit);
   expect(event.quality).toBeLessThanOrEqual(10);
   expect(timeIndex(event.time)).toBeGreaterThanOrEqual(0);
   expect(timeIndex(event.time)).toBeLessThanOrEqual(235); // 14:56 emission cutoff
   expect(TURNING_FINAL_TIMES).toContain(event.candidateTime);
   expect(TURNING_FINAL_TIMES).toContain(event.time);
  }
  expect(new Set(v2Events.map(e=>e.key)).size).toBe(v2Events.length);
  for(const kind of ['top','bottom'] as const)expect(v2Events.filter(e=>e.kind===kind).length).toBeLessThanOrEqual(3);
 }
 // Frozen spec §8.1 calibration numbers (shape-v2.0).
 expect(v2.predicted).toBe(37);expect(v2.target).toBe(63);expect(v2.matched).toBe(27);
 expect(r1.predicted).toBe(44);expect(r1.matched).toBe(29);
 expect(v2.precision).toBeCloseTo(.730,3);expect(v2.recall).toBeCloseTo(.429,3);expect(v2.f05).toBeCloseTo(.640,3);
});

function geometryOne(m:any){return JSON.stringify(tuple(m));}

test('cap layer: the 4th same-kind candidate is suppressed, never replaced',()=>{
 // Four meaningful bottom waves with fixed VWAP=100: R1 emits all four (no quota).
 const rows=synthetic([98,98.7,96,97.5,94,96,90,92]);
 const uncapped=turningFinalCandidates(rows);
 const bottoms=uncapped.filter(m=>m.kind==='bottom');
 expect(bottoms.length).toBe(4);
 const capped=turningFinal(rows,{...TURNING_FINAL_RULE,qualityTauEmit:-Infinity});
 expect(capped.map(m=>m.kind)).toEqual(['bottom','bottom','bottom']);
 expect(capped.map(m=>m.capIndex)).toEqual([1,2,3]);
 expect(capped.map(m=>m.candidateTime)).toEqual(bottoms.slice(0,3).map(m=>m.candidateTime));
 expect(capped.some(m=>m.candidateTime===bottoms[3].candidateTime)).toBe(false);
 // The suppressed candidate still carries a quality score for the diagnostic view.
 expect(Number.isFinite(bottoms[3].quality)).toBe(true);
});

test('quality gate: weak candidates are dropped and cap never exceeds 3',()=>{
 for(const c of reconstruction.cases){
  const bars=caseBars(c),raw=turningFinalCandidates(bars),final=turningFinal(bars);
  const weak=raw.filter(m=>m.quality<TURNING_FINAL_RULE.qualityTauEmit);
  expect(final.some(m=>m.quality<TURNING_FINAL_RULE.qualityTauEmit)).toBe(false);
  for(const kind of ['top','bottom'] as const)expect(final.filter(m=>m.kind===kind).length).toBeLessThanOrEqual(3);
  // A candidate passing the quality gate can only be absent because of the cap.
  const pass=raw.filter(m=>m.quality>=TURNING_FINAL_RULE.qualityTauEmit);
  expect(pass.length-final.length).toBeGreaterThanOrEqual(0);
  expect(pass.length-final.length).toBeLessThanOrEqual(weak.length>=0?pass.length:0);
 }
});

test('14:56 emission cutoff is retained',()=>{
 for(const start of [0,234]){
  const got=turningFinal(synthetic([96,97.5],start));
  expect(got).toHaveLength(1);
  expect(got[0]).toMatchObject({candidateTime:times[start],time:times[start+1]});
 }
 expect(turningFinal(synthetic([98,98.7],235))).toEqual([]);
 expect(times[235]).toBe('14:56');expect(times[236]).toBe('14:57');
});

test('missing, duplicated and unfinished minutes truncate the causal prefix',()=>{
 const c=reconstruction.cases[0],rows=caseBars(c),full=turningFinal(rows);
 expect(full.length).toBeGreaterThan(0);
 const mark=full[0],at=rows.findIndex(b=>b.time===mark.time);
 const expected=full.filter(m=>m.time<=rows[at].time);
 // Prefix without the emitting minute loses that signal and everything after it.
 expect(turningFinal(rows.slice(0,at))).toEqual(full.filter(m=>m.time<mark.time));
 const dup=[...rows];dup.splice(dup.findIndex(b=>b.time===mark.time),0,{...dup[findIndexTime(dup,mark.time)]});
 expect(turningFinal(dup).some(m=>m.key===mark.key)).toBe(false);
 expect(turningFinal(tamper(rows,mark.time,{complete:false}))).toEqual(full.filter(m=>m.time<mark.time));
 expect(turningFinal(tamper(rows,mark.time,{close:'0'}))).toEqual(full.filter(m=>m.time<mark.time));
 expect(turningFinal(tamper(rows,mark.time,{average:'0'}))).toEqual(full.filter(m=>m.time<mark.time));
 // Past signals keep their exact fields after the break (no rewrite, no bridging).
 expect(turningFinal(tamper(rows,mark.time,{complete:false}))).toEqual(expected.filter(m=>m.time<mark.time));
});

test('09:30 opening quote contract: missing, duplicated, unfinished or non-positive means no signals',()=>{
 const c=reconstruction.cases[0],rows=caseBars(c);
 expect(turningFinal(rows).length).toBeGreaterThan(0);
 expect(turningFinal(rows.slice(1))).toEqual([]);
 expect(turningFinal([...rows,rows[0]])).toEqual([]);
 for(const flag of [false,1,'true'])expect(turningFinal([{...rows[0],complete:flag as boolean},...rows.slice(1)])).toEqual([]);
 for(const price of ['0','-1','NaN'])expect(turningFinal([{...rows[0],close:price,average:price},...rows.slice(1)])).toEqual([]);
});

test('appending future minutes never changes already emitted signals',()=>{
 for(const c of reconstruction.cases){
  const rows=caseBars(c),full=turningFinal(rows);
  for(let cut=1;cut<=rows.length;cut+=7){
   const prefix=rows.slice(0,cut),expected=full.filter(m=>m.time<=rows[cut-1].time);
   expect(turningFinal(prefix)).toEqual(expected);
   expect(turningFinal(rows.map((b,i)=>i<cut?b:{...b,close:'9999',average:'1',volume:1})).filter(m=>m.time<=rows[cut-1].time)).toEqual(expected);
  }
 }
});



test('quality formula and tau boundary are frozen',()=>{
 const base={kind:'top' as const,sign:1 as const,price:101,average:100,high:102,low:99,movePct:.45,deviationPct:1,
  candidate:{index:0,time:'09:31',price:102,vwap:100,rsi:80,deviationPct:2}};
 // rsi_term=1.2 (candidate RSI 80), rev_term=1 (0.45/0.45), dev_term=2/1.5,
 // amp_term=clamp((102-99)/99*100/1.5,0,2)=2 -> 2*amp_term=4.
 expect(turningFinalQualityV2(base)).toBeCloseTo(1.2+1+2/1.5+4,10);
 const low={...base,candidate:{...base.candidate,rsi:50,deviationPct:0},movePct:0,deviationPct:0,high:100,low:100};
 expect(turningFinalQualityV2(low)).toBe(0);
 expect(TURNING_FINAL_RULE.qualityTauEmit).toBe(5);
 expect(TURNING_FINAL_RULE.dailyCapPerKind).toBe(3);
 expect(TURNING_FINAL_RULE.fallback).toBeNull();
 expect(TURNING_FINAL_RULE.version).toBe('shape-v2.0');
});

// Per-stock +/-1 one-to-one matching (spec §1.2). The Lead's full_compare.py headline
// numbers (40/61, 25/33) were matched GLOBALLY across different stocks, which inflates
// them; per-stock, R1 is 21/33 and stable v2.0 is 21/31. The v2.4 number moved from
// 29/61 (old main-first daily merge) to 28/61 after the C1 causal merge: sz300094's
// late 13:01 main top now yields its already-accepted earlier fallback top, and two
// more stock-days swap a later main event for an earlier fallback event (0.02 cal
// F0.5 budget; see the calibration assertion below).
// Both modes allow lunch-crossing confirmations by default (sh600714 top 13:01
// confirms an 11:30 candidate, matching the legacy R1 and the 2026-11-12 marks).
test('2026-11-12 per-stock metrics: R1 and both modes match the spec-conformant reference',()=>{
 const r1=calibrationOn(tencent,turningShapes),stable=calibrationOn(tencent,c=>turningFinal(c,TURNING_FINAL_RULE)),
  zhangle=calibrationOn(tencent,c=>turningFinal(c,TURNING_FINAL_RULE_ZHANGLE));
 console.log('[11-12] R1',JSON.stringify({m:r1.matched,p:r1.predicted,t:r1.target,P:r1.precision,R:r1.recall,F:r1.f05}));
 console.log('[11-12] stable',JSON.stringify({m:stable.matched,p:stable.predicted,t:stable.target,P:stable.precision,R:stable.recall,F:stable.f05}));
 console.log('[11-12] zhangle',JSON.stringify({m:zhangle.matched,p:zhangle.predicted,t:zhangle.target,P:zhangle.precision,R:zhangle.recall,F:zhangle.f05}));
 expect([r1.matched,r1.predicted,r1.target]).toEqual([21,33,67]);
 expect([stable.matched,stable.predicted,stable.target]).toEqual([21,31,67]);
 expect([zhangle.matched,zhangle.predicted,zhangle.target]).toEqual([28,61,67]);
 expect(zhangle.precision).toBeCloseTo(.459,3);expect(zhangle.recall).toBeCloseTo(.4179,3);expect(zhangle.f05).toBeCloseTo(.4502,3);
 expect(zhangle.predicted).toBeGreaterThan(stable.predicted);
 expect(zhangle.matched).toBeGreaterThan(stable.matched);
});

test('zhangle (v2.4) on the frozen 38 stock-days: signal count and 3/3 cap compliance',()=>{
 const metrics=calibration(c=>turningFinal(c,TURNING_FINAL_RULE_ZHANGLE));
 let maxPerKind=0;
 for(const c of reconstruction.cases){
  const events=turningFinal(caseBars(c),TURNING_FINAL_RULE_ZHANGLE);
  for(const kind of ['top','bottom'] as const){
   const count=events.filter(e=>e.kind===kind).length;
   maxPerKind=Math.max(maxPerKind,count);
   expect(count).toBeLessThanOrEqual(3);
  }
 }
 console.log('[fixture38] zhangle',JSON.stringify({m:metrics.matched,p:metrics.predicted,t:metrics.target,P:metrics.precision,R:metrics.recall,F:metrics.f05,maxPerKind}));
 expect(maxPerKind).toBe(3);
 expect([metrics.matched,metrics.predicted,metrics.target]).toEqual([36,69,63]);
 expect(metrics.precision).toBeCloseTo(.5217,3);expect(metrics.recall).toBeCloseTo(.5714,3);expect(metrics.f05).toBeCloseTo(.5310,3);
});

test('verifier cross-check: C1 zhangle is 28/61/67; legacy same-session branch is 27/60/67',()=>{
 // outputs/qa-20261112/expected-events-today21.json (old main-first merge, per-stock)
 // is 29/61. C1 changes only the three documented stock-days, net -1 match at
 // sz300094 (13:01 main top replaced by the earlier 09:52 fallback top).
 const metrics=calibrationOn(tencent,c=>turningFinal(c,TURNING_FINAL_RULE_ZHANGLE));
 expect([metrics.matched,metrics.predicted,metrics.target]).toEqual([28,61,67]);
 // The superseded spec §9 same-session branch is still available and configurable.
 const legacy={...TURNING_FINAL_RULE_ZHANGLE,sameSessionOnly:true};
 const legacyMetrics=calibrationOn(tencent,c=>turningFinal(c,legacy));
 expect([legacyMetrics.matched,legacyMetrics.predicted,legacyMetrics.target]).toEqual([27,60,67]);
});

test('frozen 27/37 uses the neutral-50 candidate-RSI=0 convention; strict-0 would predict 38',()=>{
 // The quant reference (09_final_eval.py: "rsiCandidate or 50.0") treats a zero RSI as
 // missing. Keeping that convention reproduces frozen spec §8.1 (27/37/63); the strict
 // formula (RSI 0 stays 0, i.e. maximally extreme) predicts 38 events on the same bars.
 const strict=(input:any)=>{const {sign,candidate,high,low,movePct}=input;const clamp=(v:number,lo:number,hi:number)=>Math.min(hi,Math.max(lo,v));
  const amp=low>0?(high-low)/low*100:0;
  return clamp(sign*(candidate.rsi-50)/25,0,2)+clamp(movePct/0.45,0,2)+clamp(Math.abs(candidate.deviationPct)/1.5,0,2)+2*clamp(amp/1.5,0,2);};
 const compat=calibration(turningFinal),strictMetrics=calibration(c=>turningFinal(c,{...TURNING_FINAL_RULE,quality:strict}));
 expect([compat.matched,compat.predicted,compat.target]).toEqual([27,37,63]);
 expect([strictMetrics.matched,strictMetrics.predicted,strictMetrics.target]).toEqual([27,38,63]);
});

test('lunch-crossing confirmation is allowed and reproduces the 13:01 Zhangle marks',()=>{
 expect(TURNING_FINAL_RULE.sameSessionOnly).toBe(false);
 expect(TURNING_FINAL_RULE_ZHANGLE.sameSessionOnly).toBe(false);
 const c600714=tencent.find((x:any)=>x.code==='sh600714');
 const lunch=turningFinal(tencentBars(c600714),TURNING_FINAL_RULE_ZHANGLE)
  .filter(e=>e.kind==='top'&&e.time==='13:01'&&e.candidateTime==='11:30');
 expect(lunch).toHaveLength(1);expect(lunch[0].price).toBeCloseTo(14.64,2);
 // sz300094 has the same cross-lunch candidate, but C1's causal cap fills its three top
 // slots earlier (09:36/09:47/09:52 fallbacks), so 13:01 is correctly dropped for good.
 const c300094=tencent.find((x:any)=>x.code==='sz300094');
 const events300094=turningFinal(tencentBars(c300094),TURNING_FINAL_RULE_ZHANGLE);
 expect(events300094.filter((e:any)=>e.kind==='top')).toHaveLength(3);
 expect(events300094.some((e:any)=>e.time==='13:01')).toBe(false);
 // Synthetic: a bottom candidate armed at 11:30 confirms at 13:01 when the rule allows it.
 const rows=flatSynthetic(240);
 rows[119]={...rows[119],close:'98'};rows[120]={...rows[120],close:'98.7'};
 expect(turningFinal([seed(100),...rows]).map(m=>[m.kind,m.time])).toEqual([['bottom','13:01']]);
 expect(turningFinal([seed(100),...rows],{...TURNING_FINAL_RULE,sameSessionOnly:true})).toEqual([]);
});

test('zhangle default: Sanzi (sz000981) shows top 09:37 and bottom 13:45, each kind <= 3',()=>{
 const c=tencent.find((x:any)=>x.code==='sz000981'),bars=tencentBars(c);
 const zhangle=turningFinal(bars,TURNING_FINAL_RULE_ZHANGLE);
 expect(zhangle.filter(m=>m.kind==='top').map(m=>m.time)).toContain('09:37');
 expect(zhangle.filter(m=>m.kind==='bottom').map(m=>m.time)).toContain('13:45');
 for(const kind of ['top','bottom'] as const)expect(zhangle.filter(m=>m.kind===kind).length).toBeLessThanOrEqual(3);
 // C1: every prefix of this day is a truncation of the final set (no disappearing signal).
 for(let cut=0;cut<bars.length;cut++)expect(turningFinal(bars.slice(0,cut+1),TURNING_FINAL_RULE_ZHANGLE))
  .toEqual(zhangle.filter(e=>timeIndex(e.time)<=timeIndex(bars[cut].time)));
});

test('both modes stay within the 3/3 cap on every 2026-11-12 stock-day',()=>{
 for(const c of tencent){
  const bars=tencentBars(c);
  for(const rule of [TURNING_FINAL_RULE,TURNING_FINAL_RULE_ZHANGLE]){
   const events=turningFinal(bars,rule);
   for(const kind of ['top','bottom'] as const)expect(events.filter(e=>e.kind===kind).length).toBeLessThanOrEqual(3);
   expect(new Set(events.map(e=>e.key)).size).toBe(events.length);
   expect(events.every(e=>e.time<='14:56')).toBe(true);
   for(const e of events)expect(e.ruleVersion).toBe(rule.version);
  }
 }
});

test('C1 causal merge: every prefix of all 59 stock-days is a truncation of the final set',()=>{
 const cases=[...reconstruction.cases.map((c:any)=>({c,bars:caseBars(c)})),
  ...tencent.map((c:any)=>({c,bars:tencentBars(c)}))];
 for(const {c,bars} of cases){
  const full=turningFinal(bars,TURNING_FINAL_RULE_ZHANGLE);
  const lastBar=full.length?timeIndex(full.at(-1)!.time)+1:0;
  for(let cut=0;cut<=lastBar;cut++){
   const prefix=turningFinal(bars.slice(0,cut+1),TURNING_FINAL_RULE_ZHANGLE);
   const expected=full.filter(e=>timeIndex(e.time)<=timeIndex(bars[cut].time));
   if(JSON.stringify(prefix)!==JSON.stringify(expected))
    throw new Error('prefix changed later: '+c.code+' '+c.day+' cut '+cut);
   for(const kind of ['top','bottom'] as const)expect(prefix.filter(e=>e.kind===kind).length).toBeLessThanOrEqual(3);
  }
  // After the last emission minute the signature is stable too.
  for(let cut=Math.max(1,lastBar);cut<bars.length;cut+=31)
   expect(turningFinal(bars.slice(0,cut+1),TURNING_FINAL_RULE_ZHANGLE)).toEqual(full);
  expect(turningFinal(bars,TURNING_FINAL_RULE_ZHANGLE)).toEqual(full);
 }
});

test('C1 causal merge on a five-candidate synthetic day: 3 signals, no disappearance',()=>{
 const rows=synthetic([98,98.7,96,97.5,94,96,90,92,88,90]);
 const full=turningFinal(rows,TURNING_FINAL_RULE_ZHANGLE);
 expect(full.map(e=>e.kind)).toEqual(['bottom','bottom','bottom']);
 const union=new Map<string,any>();
 for(let cut=1;cut<=rows.length;cut++){
  const prefix=turningFinal(rows.slice(0,cut),TURNING_FINAL_RULE_ZHANGLE);
  for(const event of prefix)union.set(event.key,event);
  expect(prefix).toEqual(full.filter(e=>timeIndex(e.time)<=timeIndex(rows[cut-1].time)));
 }
 expect([...union.keys()].sort()).toEqual(full.map(e=>e.key).sort());
});

// --- helpers -----------------------------------------------------------------
function tencentBars(c:any):Bar[]{
 return [seed(c.opening_price),...c.prices.map((p:number,i:number)=>({time:times[i],close:String(p),average:String(c.averages[i]),volume:c.volumes[i],complete:true}))];
}
function calibrationOn(cases:any[],selector:(bars:Bar[])=>any[]){
 let matched=0,predicted=0,target=0;
 for(const c of cases){
  const bars=tencentBars(c),events=selector(bars),marks=c.broker_marks;
  matched+=matchEvents(events,marks,1);predicted+=events.length;target+=marks.length;
 }
 const precision=predicted?matched/predicted:0,recall=target?matched/target:0;
 return {matched,predicted,target,precision,recall,f05:matched?1.25*precision*recall/(0.25*precision+recall):0};
}
function synthetic(prices:number[],start=0):Bar[]{
 return [seed(100),...[...Array(start).fill(100),...prices].map((p,i)=>({time:times[i],close:String(p),average:'100',volume:10000,complete:true}))];
}
function flatSynthetic(count:number):Bar[]{
 return Array.from({length:count},(_,i)=>({time:times[i],close:'100',average:'100',volume:10000,complete:true}));
}
function findIndexTime(rows:Bar[],stamp:string){return rows.findIndex(b=>b.time===stamp);}
function tamper(rows:Bar[],stamp:string,change:Partial<Bar>):Bar[]{
 return rows.map(b=>b.time===stamp?{...b,...change}:b);
}