import {test,expect,Locator} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {turningFinal,TURNING_FINAL_MODES,type TurningFinalMode} from '../../src/turningFinal';
import {turningQualityQ1} from '../../src/turningQualityQ1';
import {turningDisplayPoints} from '../../src/turningDisplay';
import type {Bar} from '../../src/models';

// Real 2026-11-12 full-day Tencent minutes (the app's own source) for four stocks:
// sz000981 山子高科, sh600714 金瑞矿业, sz300058 蓝色光标, sz300094 国联水产.
// App-cache copies of sz300058/sz300364 are the Q1-fill fixtures (>3 shapes+Q1 merged).
const cases=JSON.parse(readFileSync('tests/ui/fixtures/turning-final-chart-cases.json','utf8'));
const seed=(c:any):Bar=>({time:'09:30',close:String(c.opening_price),average:String(c.opening_price),volume:0,complete:true});
const chartBars=(c:any):Bar[]=>[seed(c),...c.bars];
const engine=(c:any,mode:TurningFinalMode)=>turningFinal(chartBars(c),TURNING_FINAL_MODES[mode]);
const display=(c:any,mode:TurningFinalMode,capPerKind=3)=>turningDisplayPoints(engine(c,mode),turningQualityQ1(c.bars),true,true,capPerKind);
const kindCount=(events:any[],kind:string)=>events.filter(e=>e.kind===kind).length;
const capText=(events:any[])=>`底 ${kindCount(events,'bottom')}/3 · 顶 ${kindCount(events,'top')}/3`;
const coords=(points:any[])=>points.map(p=>[p.kind==='bottom'?'底':'顶',p.time,p.price]);

async function rendered(chart:Locator){
 return chart.evaluate(async el=>{
  const s=await fetch('/src/Chart.tsx').then(r=>r.text());
  const url=s.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1];
  const e=await import(/* @vite-ignore */url),c=e.getInstanceByDom(el),o=c?.getOption();
  if(!o?.series)return null;
  const marks=o.series[0].markPoint.data.filter((m:any)=>m.observationKey||m.qualityKey);
  return {points:marks.map((m:any)=>[m.turningKind,m.coord[0],m.coord[1]]),
   shapeKeys:marks.filter((m:any)=>m.observationKey).map((m:any)=>m.observationKey),
   q1Keys:marks.filter((m:any)=>m.qualityKey).map((m:any)=>m.qualityKey)};
 });
}
function payloadFor(c:any){
 const payload=JSON.parse(readFileSync('public/preview.json','utf8'));
 const last=String(c.bars.at(-1).close),closes=c.bars.map((b:any)=>Number(b.close));
 const daily={date:c.day,open:String(c.opening_price),close:last,high:String(Math.max(c.opening_price,...closes)),low:String(Math.min(c.opening_price,...closes)),volume:String(c.bars.reduce((n:number,b:any)=>n+b.volume,0)),provisional:true};
 const quote={code:c.code,name:c.name,price:last,previous_close:String(c.previous_close),high:daily.high,low:daily.low,timestamp:c.day+'T15:05:00+08:00',change:String(Number(last)-c.previous_close)};
 const rows=chartBars(c);
 payload.snapshot.watch=[{code:c.code,name:c.name,enabled:1,quote,candidates:[],health:'shape-v2 chart regression'}];
 payload.snapshot.events=[];payload.snapshot.now=c.day+'T15:05:00+08:00';payload.snapshot.config.trading_paused=true;
 payload.minutes[c.code]=[{day:c.day,data:{date:c.day,source:'tencent_public_20261112',bars:rows,previous_close:String(c.previous_close),volume_unit:'shares'}}];
 payload.daily[c.code]=[{day:c.day,data:daily}];
 payload.history[c.code]={...payload.history.sh603002,code:c.code,daily:[daily],days:[{date:c.day,status:'ready',has_minutes:true,signal_count:0,recorded_count:0,matches:[]}],events:[],minute_days:[c.day]};
 return payload;
}
async function openChart(page:any,c:any){
 await page.route('**/preview.json',(route:any)=>route.fulfill({json:payloadFor(c)}));
 await page.goto('/');await page.locator('.stock').filter({hasText:c.name}).click();
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();
 return chart;
}
async function showTip(chart:Locator,time:string){
 await chart.evaluate(async(el,time)=>{
  const s=await fetch('/src/Chart.tsx').then(r=>r.text());
  const e=await import(/* @vite-ignore */s.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]);
  const c=e.getInstanceByDom(el),o=c.getOption();
  c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:o.xAxis[0].data.indexOf(time)});
 },time);
}

test('default zhangle mode renders high-coverage marks: <=3/kind and Sanzi 09:37 top / 13:45 bottom',async({page})=>{
 const c=cases.find((x:any)=>x.code==='sz000981');
 const chart=await openChart(page,c);
 await expect(page.getByLabel('顶底模式')).toHaveValue('zhangle');
 const zh=engine(c,'zhangle');
 expect(zh.filter((m:any)=>m.kind==='top').map((m:any)=>m.time)).toContain('09:37');
 expect(zh.filter((m:any)=>m.kind==='bottom').map((m:any)=>m.time)).toContain('13:45');
 for(const kind of ['top','bottom'] as const)expect(kindCount(zh,kind)).toBeLessThanOrEqual(3);
 const expected=display(c,'zhangle');
 await expect.poll(async()=>(await rendered(chart))?.points).toEqual(coords(expected));
 await expect(page.getByTestId('turning-cap-count')).toHaveText(capText(zh));
 // Popover: mode + quality + daily cap rows on a v2 point.
 await showTip(chart,'09:37');
 const tooltip=chart.locator('.quote-tooltip');
 await expect(tooltip).toContainText('模式：');
 await expect(tooltip).toContainText('贴近涨乐通');
 await expect(tooltip).toContainText('质量分：');
 await expect(tooltip).toContainText('当日上限：底 ');
 await chart.screenshot({path:test.info().outputPath('zhangle-sanzi-000981.png')});
});

test('stable mode is opt-in, persisted, and matches the v2.0 events in the real chart',async({page})=>{
 const c=cases.find((x:any)=>x.code==='sz000981');
 const chart=await openChart(page,c);
 const stable=engine(c,'stable'),zhangle=engine(c,'zhangle');
 const zhangleSet=new Set(zhangle.map((m:any)=>[m.kind,m.time,m.candidateTime,m.price].join('|')));
 for(const event of stable)expect(zhangleSet.has([event.kind,event.time,event.candidateTime,event.price].join('|'))).toBe(true);
 for(const kind of ['top','bottom'] as const)expect(kindCount(stable,kind)).toBeLessThanOrEqual(3);
 await page.getByLabel('顶底模式').selectOption('stable');
 await expect(page.getByLabel('顶底模式')).toHaveValue('stable');
 expect(await page.evaluate(()=>localStorage.getItem('stock-monitor-turning-mode-v1'))).toBe('stable');
 await expect.poll(async()=>(await rendered(chart))?.points).toEqual(coords(display(c,'stable')));
 await expect(page.getByTestId('turning-cap-count')).toHaveText(capText(stable));
 await page.reload();
 const reloaded=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(reloaded).toBeVisible();
 await expect(page.getByLabel('顶底模式')).toHaveValue('stable');
 await expect.poll(async()=>(await rendered(reloaded))?.points).toEqual(coords(display(c,'stable')));
 await page.getByLabel('顶底模式').selectOption('zhangle');
 await expect.poll(async()=>(await rendered(reloaded))?.points).toEqual(coords(display(c,'zhangle')));
 await reloaded.screenshot({path:test.info().outputPath('stable-sanzi-000981.png')});
});

test('Q1 circles fill only leftover slots, so the displayed stream never exceeds 3/kind',async({page})=>{
 // App-cache copies (2026-11-12 蓝色光标/中文在线) are the fixtures where the uncapped
 // shape+Q1 merge really exceeds 3; the chart must still render at most 3 per kind.
 for(const [code,source] of [['sz300058','app-cache-copy'],['sz300364','app-cache-copy'],['sz300058','tencent'],['sh600714','tencent']] as const){
  const c=cases.find((x:any)=>x.code===code&&x.source===source);
  const chart=await openChart(page,c);
  const uncapped=display(c,'zhangle',Infinity),capped=display(c,'zhangle',3);
  for(const kind of ['top','bottom'] as const)expect(capped.filter((p:any)=>p.kind===kind).length).toBeLessThanOrEqual(3);
  if(source==='app-cache-copy')expect(['top','bottom'].some(kind=>uncapped.filter((p:any)=>p.kind===kind).length>3)).toBe(true);
  await expect.poll(async()=>(await rendered(chart))?.points).toEqual(coords(capped));
  const shown=await rendered(chart);
  for(const kind of ['top','bottom'] as const)expect(shown!.points.filter((p:any)=>p[0]===(kind==='bottom'?'底':'顶')).length).toBeLessThanOrEqual(3);
  await chart.screenshot({path:test.info().outputPath('display-cap-'+(source)+'-'+code+'.png')});
 }
});

test('sz300094 keeps only its three causal tops: the late 13:01 main top yields the earlier fallback',async({page})=>{
 // C1 causal merge: sz300094 already accepted three top signals in the morning, so the
 // later 13:01 main top is dropped for good (the old main-first merge showed 13:01 and
 // hid an earlier fallback — signals could "disappear" later). Both the engine and the
 // rendered chart must agree on the causal three.
 const c=cases.find((x:any)=>x.code==='sz300094'&&x.source==='tencent');
 const chart=await openChart(page,c);
 const zh=engine(c,'zhangle');
 const tops=zh.filter((e:any)=>e.kind==='top');
 expect(tops).toHaveLength(3);
 expect(tops.some((e:any)=>e.time==='13:01')).toBe(false);
 await expect.poll(async()=>(await rendered(chart))?.points).toEqual(coords(display(c,'zhangle')));
 for(const event of tops)expect((await rendered(chart))!.points).toContainEqual(['顶',event.time,event.price]);
});

test('cross-view: the linked K-line minute chart shows the same mode, marks and cap indicator',async({page})=>{
 const c=cases.find((x:any)=>x.code==='sh600714');
 const chart=await openChart(page,c);
 const zh=engine(c,'zhangle');
 const lunchTop=zh.find((e:any)=>e.kind==='top'&&e.time==='13:01'&&e.candidateTime==='11:30');
 expect(lunchTop).toBeTruthy();expect(lunchTop.price).toBeCloseTo(14.64,2);
 const expected=coords(display(c,'zhangle'));
 expect(expected).toContainEqual(['顶','13:01',lunchTop.price]);
 await expect.poll(async()=>(await rendered(chart))?.points).toEqual(expected);
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const linked=page.locator('.linked-minute').getByLabel('分时价格及分钟成交量',{exact:true});
 await expect(linked).toBeVisible();
 await expect.poll(async()=>(await rendered(linked))?.points).toEqual(expected);
 await expect(page.locator('.linked-minute').getByTestId('turning-cap-count')).toHaveText(capText(engine(c,'zhangle')));
 await page.locator('.linked-minute').getByLabel('顶底模式').selectOption('stable');
 await expect.poll(async()=>(await rendered(linked))?.points).toEqual(coords(display(c,'stable')));
 await page.getByRole('button',{name:'分时',exact:true}).click();
 await expect.poll(async()=>(await rendered(page.getByLabel('分时价格及分钟成交量',{exact:true})))?.points).toEqual(coords(display(c,'stable')));
});