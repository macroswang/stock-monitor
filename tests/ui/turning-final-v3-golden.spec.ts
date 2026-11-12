import {test,expect} from '@playwright/test';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import type {Bar} from '../../src/models';
import {turningFinal,TURNING_FINAL_MODES,turningFinalQualityV2,TURNING_FINAL_RULE} from '../../src/turningFinal';
import {turningFinalV3,turningFinalV3Candidates,TURNING_FINAL_V3_RULE,TURNING_FINAL_V3_VERSION,TURNING_FINAL_V3_KEY_PREFIX} from '../../src/turningFinalV3';

// Golden cross-language fixture for the shape-v3 chart engine (core/turning_final_v3.py).
// Regenerate deliberately with: UPDATE_TURNING_GOLDEN_V3=1 npx playwright test tests/ui/turning-final-v3-golden.spec.ts
const GOLDEN_V3='tests/fixtures/turning-final-golden-v3.json';
const GOLDEN_V2='tests/fixtures/turning-final-golden.json';
const EVAL='tests/fixtures/turning-v3-eval.json';
const reconstruction=JSON.parse(readFileSync('tests/fixtures/zhangle-reconstruction.json','utf8'));
const tencent=JSON.parse(readFileSync('tests/ui/fixtures/turning-final-20261112-cases.json','utf8'));
const v2golden=JSON.parse(readFileSync(GOLDEN_V2,'utf8'));
const evalFixture=JSON.parse(readFileSync(EVAL,'utf8'));
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
const seed=(p:number):Bar=>({time:'09:30',close:String(p),average:String(p),volume:0,complete:true});
const caseBars=(c:any):Bar[]=>[seed(c.opening_price),...c.prices.map((p:number,i:number)=>({time:times[i],close:String(p),average:String(c.averages[i]),volume:c.volumes[i],complete:true}))];
const evalBars=(c:any):Bar[]=>[seed(c.opening_price),...c.bars.map((b:any)=>({time:b.time,close:String(b.close),average:String(b.average),volume:b.volume,complete:b.complete}))];
const timeIndex=(stamp:string)=>times.indexOf(stamp);
const tuple=(e:any)=>[e.kind,e.time,e.price,e.candidateTime,e.quality] as const;
const keyOf=(e:any)=>[e.kind,e.time,e.candidateTime].join('|');

function build(){
 return {
  meta:{generated_by:'tests/ui/turning-final-v3-golden.spec.ts',mode:'v3',version:TURNING_FINAL_V3_VERSION,
   keyPrefix:TURNING_FINAL_V3_KEY_PREFIX,tradingSignal:'shape-v2',chartDefault:false,experimental:true,defaultMode:'zhangle',
   spec:{fixture38:{matched:32,predicted:52,target:63,precision:.6154,recall:.5079,f05:.5904}},
   note:'v3 = v2.4 raw main/fallback streams re-merged by C1 with fallback bottoms suppressed (not a simple filter); stable column is the unchanged v2.0 stream'},
  cases:[
   ...reconstruction.cases.map((c:any)=>({source:'fixture38',code:c.code,day:c.day,
    v3:turningFinalV3(caseBars(c)),stable:turningFinal(caseBars(c),TURNING_FINAL_MODES.stable)})),
   ...tencent.map((c:any)=>({source:'today21',code:c.code,day:c.day,
    v3:turningFinalV3(caseBars(c)),stable:turningFinal(caseBars(c),TURNING_FINAL_MODES.stable)})),
  ],
 };
}

function matchEvents(events:any[],marks:any[],tol=1){
 const ev=events.map(e=>({i:timeIndex(e.time),kind:e.kind}));
 const mk=marks.map(m=>({i:timeIndex(m.time),kind:m.kind}));
 const adjacency=ev.map(()=>[] as number[]);
 for(let a=0;a<ev.length;a++)for(let b=0;b<mk.length;b++){
  if(ev[a].kind===mk[b].kind&&Math.abs(ev[a].i-mk[b].i)<=tol)adjacency[a].push(b);
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

test('shape-v3 golden fixture is in sync with src/turningFinalV3.ts',()=>{
 const current=build();
 if(process.env.UPDATE_TURNING_GOLDEN_V3==='1')writeFileSync(GOLDEN_V3,JSON.stringify(current));
 expect(existsSync(GOLDEN_V3)).toBe(true);
 expect(JSON.parse(readFileSync(GOLDEN_V3,'utf8'))).toEqual(current);
 expect(current.cases).toHaveLength(59);
 for(const c of current.cases){
  for(const kind of ['top','bottom'] as const)expect(c.v3.filter((e:any)=>e.kind===kind).length).toBeLessThanOrEqual(3);
  for(const event of c.v3){
   expect(event.key).toBe(`shape-v3|${event.kind}|${event.candidateTime}`);
   expect(event.ruleVersion).toBe('shape-v3.0');
   expect(event.capIndex).toBeGreaterThanOrEqual(1);
   expect(timeIndex(event.time)).toBeLessThanOrEqual(235);
  }
  expect(new Set(c.v3.map((e:any)=>e.key)).size).toBe(c.v3.length);
 }
});

test('v3 stable column still equals the frozen v2.0 golden column',()=>{
 for(let i=0;i<v2golden.cases.length;i++){
  const v2case=v2golden.cases[i],v3case=build().cases[i];
  expect(v3case.source).toBe(v2case.source);
  expect(v3case.code).toBe(v2case.code);
  expect(v3case.stable).toEqual(v2case.stable);
 }
});

test('v3 fallback_bottom_enabled=true reproduces the v2.4 event set event-for-event',()=>{
 const legacyRule:any={...TURNING_FINAL_V3_RULE,version:'shape-v2.4',keyPrefix:'shape-v2',
  fallback:{...TURNING_FINAL_V3_RULE.fallback,fallbackBottomEnabled:true}};
 const allCases=[...reconstruction.cases.map((c:any)=>({source:'fixture38',c})),
  ...tencent.map((c:any)=>({source:'today21',c}))];
 let checked=0;
 for(let i=0;i<v2golden.cases.length;i++){
  const v2case=v2golden.cases[i],{source,c}=allCases[i];
  expect(v2case.source).toBe(source);expect(v2case.code).toBe(c.code);
  expect(turningFinalV3(caseBars(c),legacyRule)).toEqual(v2case.zhangle);
  checked++;
 }
 expect(checked).toBe(59);
});

test('v3 eval fixture (quant research copy, C1-corrected) matches the engine',()=>{
 let checked=0;
 for(const c of evalFixture.cases){
  const got=turningFinalV3(evalBars(c));
  const expected=c.expected.map((e:any)=>({...e,key:`shape-v3|${e.kind}|${e.candidateTime}`}));
  expect(got.map(tuple),c.code).toEqual(expected.map(tuple));
  expect(got.map((e:any)=>e.key)).toEqual(expected.map((e:any)=>e.key));
  const capIndex:any={top:0,bottom:0};
  for(const event of got){capIndex[event.kind]++;expect(event.capIndex).toBe(capIndex[event.kind]);}
  checked++;
 }
 expect(checked).toBe(4);
});

test('v3 fixture38 metrics match the frozen spec (32/52/63, P.615/R.508/F0.5 .590)',()=>{
 let matched=0,predicted=0,target=0;
 for(const c of reconstruction.cases){
  const events=turningFinalV3(caseBars(c));
  matched+=matchEvents(events,c.broker_marks,1);predicted+=events.length;target+=c.broker_marks.length;
 }
 const precision=matched/predicted,recall=matched/target,f05=1.25*precision*recall/(0.25*precision+recall);
 expect([matched,predicted,target]).toEqual([32,52,63]);
 expect(precision).toBeCloseTo(.6154,3);expect(recall).toBeCloseTo(.5079,3);expect(f05).toBeCloseTo(.5904,3);
});

test('v3 is a C1 re-merge, not a v2.4 simple filter: freed cap slots admit earlier-dropped main events',()=>{
 // sz300364 2026-11-12: v2.4 drops the main bottom 13:31 because three fallback bottoms
 // already consumed the cap; v3 removes those fallback bottoms and the main bottom returns.
 const c=tencent.find((x:any)=>x.code==='sz300364');
 const v24=turningFinal(caseBars(c),TURNING_FINAL_MODES.zhangle);
 const v3=turningFinalV3(caseBars(c));
 expect(v24.some((e:any)=>e.kind==='bottom'&&e.time==='13:31')).toBe(false);
 expect(v3.some((e:any)=>e.kind==='bottom'&&e.time==='13:31')).toBe(true);
 for(const event of v3.filter((e:any)=>e.kind==='top'))expect(v24.some((e:any)=>keyOf(e)===keyOf(event))).toBe(true);
});