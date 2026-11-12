import {test,expect} from '@playwright/test';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import type {Bar} from '../../src/models';
import {turningFinal,TURNING_FINAL_MODES} from '../../src/turningFinal';

// Golden cross-language fixture for core/turning_final.py (trading engine parity).
// Regenerate deliberately with: UPDATE_TURNING_GOLDEN=1 npx playwright test tests/ui/turning-final-golden.spec.ts
const GOLDEN='tests/fixtures/turning-final-golden.json';
const reconstruction=JSON.parse(readFileSync('tests/fixtures/zhangle-reconstruction.json','utf8'));
const tencent=JSON.parse(readFileSync('tests/ui/fixtures/turning-final-20261112-cases.json','utf8'));
const times=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
const seed=(p:number):Bar=>({time:'09:30',close:String(p),average:String(p),volume:0,complete:true});
const bars=(c:any):Bar[]=>[seed(c.opening_price),...c.prices.map((p:number,i:number)=>({time:times[i],close:String(p),average:String(c.averages[i]),volume:c.volumes[i],complete:true}))];
function build(){
 return {
  meta:{generated_by:'tests/ui/turning-final-golden.spec.ts',mode:'zhangle',version:'shape-v2.4',signal:'shape-v2',
   sameSessionOnly:false,dailyCapPerKind:3,qualityTauEmit:4.5,mergeRule:'causal-chronological',fallback:{enabled:true,rsiArm:false,qualityTauEmit:4.5,dedupeMinutes:2,minimumDeviationPct:.7,reversalMinPct:.15}},
  cases:[
   ...reconstruction.cases.map((c:any)=>({source:'fixture38',code:c.code,day:c.day,
    zhangle:turningFinal(bars(c),TURNING_FINAL_MODES.zhangle),stable:turningFinal(bars(c),TURNING_FINAL_MODES.stable)})),
   ...tencent.map((c:any)=>({source:'today21',code:c.code,day:c.day,
    zhangle:turningFinal(bars(c),TURNING_FINAL_MODES.zhangle),stable:turningFinal(bars(c),TURNING_FINAL_MODES.stable)})),
  ],
 };
}
test('shape-v2 golden fixture is in sync with src/turningFinal.ts',()=>{
 const current=build();
 if(process.env.UPDATE_TURNING_GOLDEN==='1')writeFileSync(GOLDEN,JSON.stringify(current));
 expect(existsSync(GOLDEN)).toBe(true);
 expect(JSON.parse(readFileSync(GOLDEN,'utf8'))).toEqual(current);
 expect(current.cases).toHaveLength(59);
 for(const c of current.cases)for(const mode of ['zhangle','stable'] as const){
  const events=(c as any)[mode];
  for(const kind of ['top','bottom'] as const)expect(events.filter((e:any)=>e.kind===kind).length).toBeLessThanOrEqual(3);
  for(const e of events)expect(e.key.startsWith('shape-v2|')).toBe(true);
 }
});