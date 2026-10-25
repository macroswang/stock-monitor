import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {turningD,dTopPasses,D_TIMES} from '../../src/turningD';
import {turningShapes} from '../../src/turningShapes';
import type {Bar} from '../../src/models';
import {researchMarkers,researchScenarios,tradeStage,validateResearchBundle} from '../../src/dResearchModel';
import type {ResearchBundle,ResearchScenario} from '../../src/dResearchModel';
const body=readFileSync('src/research/d-reserved-20261025.json','utf8');
const bundle=JSON.parse(body) as ResearchBundle;
const metal=bundle.cases.find(c=>c.id==='sh600560|2026-10-15')!;

test('exported historical supplementary results reconcile for all six cost scenarios',()=>{
 validateResearchBundle(bundle);
 for(const slot of ['S','S_L1','S_LQ'] as const)for(const scenario of Object.keys(researchScenarios) as ResearchScenario[]){
  const trades=bundle.cases.map(c=>c.trades[slot][scenario]).filter(t=>t?.status==='price_proxy');const metric=bundle.metrics[slot][scenario];
  expect(trades).toHaveLength(metric.n);
  expect(trades.reduce((n,t)=>n+t!.net_pct!,0)/trades.length).toBeCloseTo(metric.mean_net_pct!,10);
  expect(trades.filter(t=>t!.net_pct!>0).length/trades.length).toBe(metric.win_rate);
  expect(trades.reduce((n,t)=>n+t!.net_cny!,0)).toBeCloseTo(metric.net_cny,6);
 }
 expect(bundle.metrics.D.primary.n).toBe(612);expect(bundle.meta.newDates).toBe(0);expect(bundle.meta.frozen).toBe(false);
});

test('replay markers cannot reveal later confirmations, fills or future cover profits',()=>{
 const times=bundle.times;const s=metal.trades.S.primary!,d=metal.trades.D.primary!;
 expect(tradeStage(null,0,times)).toBe('future');expect(tradeStage(null,233,times)).toBe('none');
 expect(tradeStage(s,times.indexOf('10:16'),times)).toBe('future');
 expect(tradeStage(s,times.indexOf('10:17'),times)).toBe('pending');
 expect(tradeStage(s,times.indexOf('10:18'),times)).toBe('open');
 expect(tradeStage(d,times.indexOf('11:08'),times)).toBe('future');
 expect(tradeStage(d,times.indexOf('14:56'),times)).toBe('closed');
 for(const c of bundle.cases)for(const scenario of Object.keys(researchScenarios) as ResearchScenario[])for(const cursor of [0,45,46,47,97,98,119,120,234,239]){
  for(const mode of ['P','I','U'] as const){
   const marks=researchMarkers(c,scenario,mode,'S',cursor,times,true,true,true);
   expect(marks.every(m=>times.indexOf(m.time)<=cursor)).toBe(true);
   expect(new Set(marks.map(m=>m.time+'|'+m.price+'|'+m.kind)).size).toBe(marks.length);
   expect(marks.filter(m=>m.kind==='signal').every(m=>m.price===c.price[times.indexOf(m.time)])).toBe(true);
  }
 }
 const before=researchMarkers(metal,'primary','I','S',97,times);expect(before.some(m=>m.label==='D顶确认')).toBe(false);
 const after=researchMarkers(metal,'primary','I','S',98,times);expect(after.some(m=>m.label==='D顶确认'&&m.time==='11:09')).toBe(true);
});

test('same-inventory shadow and dedicated-inventory trades remain distinct with T+1 bookkeeping',()=>{
 for(const c of bundle.cases)for(const scenario of Object.keys(researchScenarios) as ResearchScenario[])for(const key of ['P','I','I_L1','I_LQ','U']){
  const account=c.accounts[key][scenario];let sold=0,cash=0,held=account.initial_qty;
  for(const a of account.actions){
   if(a.side==='sell'){sold+=a.qty;held-=a.qty;}else held+=a.qty;
   cash+=a.cash_delta;
   expect(a.sellable).toBe(account.initial_qty-sold);expect(a.sellable).toBeGreaterThanOrEqual(0);expect(a.holdings).toBe(held);
  }
  expect(held).toBe(account.initial_qty);expect(cash).toBeCloseTo(account.net_cny!,6);
  if(key==='P')expect(account.actions.every(a=>a.slot==='D')).toBe(true);
  if(key.startsWith('I'))expect(account.initial_qty).toBe(2000);
 }
 expect(metal.accounts.P.primary.net_cny).toBe(283.41);
 expect(metal.accounts.U.primary.net_cny).toBe(103.5);
 expect(metal.accounts.I.primary.net_cny).toBe(386.91);
 expect(metal.accounts.I.primary.actions.filter(a=>a.side==='sell').map(a=>a.time)).toEqual(['10:18','11:10']);
});

const barsOf=(c:typeof metal):Bar[]=>bundle.times.map((time,i)=>({time,close:String(c.price[i]),average:String(c.average[i]),volume:c.volume[i],complete:true}));

test('current-chart D observations reproduce every focused historical D entry and primary cost',()=>{
 for(const c of bundle.cases){
  const bars=barsOf(c),shapes=turningShapes(bars),d=turningD(bars),expected=c.trades.D.primary;
  for(const shape of shapes.filter(m=>m.kind==='top'))expect(dTopPasses(bars,shape)).toBe(c.decisions.find(x=>x.key===shape.key&&x.lag===0)!.c1);
  if(!expected){expect(d.entry).toBeNull();continue;}
  expect(d.entry?.time).toBe(expected.signal_time);expect(d.entryFill?.time).toBe(expected.entry_time);expect(d.exitFill?.time).toBe(expected.exit_time);
  expect(d.exitReason).toBe(expected.exit_reason);expect(d.netCny).toBeCloseTo(expected.net_cny!,7);expect(d.netPct).toBeCloseTo(expected.net_pct!,9);
 }
 const d=turningD(barsOf(metal));expect(d.entry?.time).toBe('11:09');expect(d.exit).toBeNull();expect(d.exitReason).toBe('scheduled_close');expect(d.netCny).toBe(283.41);
});

test('current-chart D has no future confirmation/fill, does not skip missing data, and retains original buy-first exits',()=>{
 const bars=barsOf(metal),full=turningD(bars);
 for(const cursor of [0,45,46,47,97,98,99,119,120,234,235,239]){
  const d=turningD(bars.slice(0,cursor+1));
  if(d.entry)expect(D_TIMES.indexOf(d.entry.time)).toBeLessThanOrEqual(cursor);
  if(d.entryFill)expect(D_TIMES.indexOf(d.entryFill.time)).toBeLessThanOrEqual(cursor);
  if(d.exitFill)expect(D_TIMES.indexOf(d.exitFill.time)).toBeLessThanOrEqual(cursor);else expect(d.netCny).toBeNull();
 }
 expect(turningD(bars.slice(0,98)).entry).toBeNull();expect(turningD(bars.slice(0,99)).status).toBe('entry_pending');
 const missing=turningD(bars.filter(b=>b.time!=='11:10'));expect(missing.entry?.time).toBe(full.entry?.time);expect(missing.entryFill).toBeNull();expect(missing.status).toBe('data_gap');
 expect(turningD(bars.filter(b=>b.time!=='09:32')).entry).toBeNull();
 expect(turningD([...bars,bars[2]]).entry).toBeNull();
 for(const c of bundle.cases){
  const bs=barsOf(c),all=turningShapes(bs),d=turningD(bs,'buy-sell');const first=all.find(m=>m.kind==='bottom'&&D_TIMES.indexOf(m.time)<=233);
  expect(d.entry?.key??null).toBe(first?.key??null);
  if(!first)continue;
  const entryIndex=D_TIMES.indexOf(first.time)+1,opposite=all.find(m=>m.kind==='top'&&D_TIMES.indexOf(m.time)>=entryIndex);
  if(opposite&&D_TIMES.indexOf(opposite.time)+1<=235)expect(d.exit?.key).toBe(opposite.key);
 }
});

async function fixture(page:Page){
 const p=JSON.parse(readFileSync('public/preview.json','utf8')),code=metal.code,day=metal.day,bars=barsOf(metal),h=p.history.sh603002;
 const daily={date:day,open:String(metal.price[0]),close:String(metal.price.at(-1)),high:String(Math.max(...metal.price)),low:String(Math.min(...metal.price)),volume:String(metal.volume.reduce((a,b)=>a+b,0)),source:'test'};
 p.snapshot.watch=[{code,name:metal.name,enabled:1,quote:null,health:'只读测试缓存',cache_health:null,candidates:[]}];p.snapshot.events=[];
 p.minutes[code]=[{day,data:{bars,source:'test'}}];p.daily[code]=[{day,data:daily}];p.history[code]={...h,code,daily:[daily],events:[],days:[{date:day,status:'ready',has_minutes:true,matches:[],signal_count:0,recorded_count:0}],minute_days:[day]};
 await page.route('**/preview.json',route=>route.fulfill({json:p}));
 await page.goto('/#research');await expect(page.getByRole('heading',{name:'自选监控',exact:true})).toBeVisible();await expect(page.getByLabel('交易日期')).toHaveValue(day);
 await expect(page.getByRole('button',{name:'研究验证',exact:true})).toHaveCount(0);
 await expect(page).not.toHaveURL(/#research/);
}
async function option(page:Page){return page.getByLabel('分时价格及分钟成交量').evaluate(async el=>{
 const source=await fetch('/src/Chart.tsx').then(r=>r.text());const match=source.match(/from "([^"]*echarts\.js[^"]*)"/)!;
 const echarts=await import(match[1]);return echarts.getInstanceByDom(el).getOption();
});}

test('D roles are merged into the actual watchlist chart, with a separate non-bottom scheduled cover',async({page})=>{
 await fixture(page);const o=await option(page),marks=o.series[0].markPoint.data;
 const d=marks.find((m:any)=>m.dRole==='entry');expect(d.coord[0]).toBe('11:09');expect(d.label.formatter).toBe('顶·D');
 expect(marks.filter((m:any)=>m.observationKey).map((m:any)=>m.coord)).toEqual(turningShapes(barsOf(metal)).map(m=>[m.time,m.price]));
 const plan=marks.filter((m:any)=>m.dPlannedReturn);expect(plan).toHaveLength(1);expect(plan[0].value).toBe('回补');expect(plan[0].coord[0]).toBe('14:56');expect(plan[0].turningKind).toBeUndefined();
 await page.locator('.d-purpose-panel>summary').click();await expect(page.locator('.d-purpose-panel')).toContainText('283.41元');await expect(page.locator('.d-purpose-panel')).toContainText('不是底点或独立开仓买点');
 const chart=page.getByLabel('分时价格及分钟成交量');await chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const echarts=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=echarts.getInstanceByDom(el),o=c.getOption();c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:o.xAxis[0].data.indexOf('14:56')});});
 await expect(chart.locator('.quote-tooltip')).toContainText('计划回补对照');await expect(chart.locator('.quote-tooltip')).toContainText('不是独立底点或开仓买点');
 await page.getByRole('checkbox',{name:'显示Q1质量',exact:true}).uncheck();expect((await option(page)).series[0].markPoint.data.some((m:any)=>m.dRole==='entry')).toBe(true);
 await page.getByRole('checkbox',{name:'显示形态底/顶',exact:true}).uncheck();expect((await option(page)).series[0].markPoint.data.some((m:any)=>m.dRole||m.dPlannedReturn)).toBe(false);
});

test('historical costs and daily results open beneath the watchlist chart without a new menu',async({page})=>{
 await fixture(page);await page.locator('.d-purpose-panel>summary').click();await page.locator('.d-history-details>summary').click();
 await expect(page.getByLabel('D历史全样本成本对照')).toContainText('-0.8083%');await expect(page.getByLabel('D历史全样本成本对照')).toContainText('-0.7997%');
 await page.getByLabel('历史D成本情景').selectOption('delay_stress');await expect(page.getByLabel('D历史全样本成本对照')).toContainText('-0.9345%');
 await expect(page.getByLabel('D历史逐日期结果').locator('tbody tr')).toHaveCount(10);
 await page.getByLabel('D历史逐日研究组').selectOption('S');await expect(page.getByLabel('D历史逐日期结果')).toContainText('无交易');
 await page.getByRole('button',{name:'先买后卖',exact:true}).click();await expect(page.locator('.d-purpose-panel')).toContainText('原形态顶退出，未套用C1入场过滤');
});

test('historical snapshot errors do not disable current-chart D observations',async({page})=>{
 await page.route('**/src/researchSnapshot.ts*',r=>r.fulfill({status:503,body:'unavailable'}));await fixture(page);
 await page.locator('.d-purpose-panel>summary').click();await page.locator('.d-history-details>summary').click();await expect(page.getByRole('alert')).toContainText('历史快照暂不可用');
 expect((await option(page)).series[0].markPoint.data.some((m:any)=>m.dRole==='entry')).toBe(true);
});

test('watchlist D and its inline history work with native-style RPC and the desktop connect-src restriction',async({page})=>{
 const bars=barsOf(metal),day=metal.day,code=metal.code;
 const source=JSON.parse(readFileSync('public/preview.json','utf8')).history.sh603002.source;
 const daily={date:day,open:String(metal.price[0]),close:String(metal.price.at(-1)),high:String(Math.max(...metal.price)),low:String(Math.min(...metal.price)),volume:'10000000'};
 const snapshot={watch:[{code,name:metal.name,enabled:1,health:'只读测试',candidates:[]}],events:[],config:{monitor:false},market_open:false,now:'2026-10-25T18:00:00+08:00',data_dir:'test-only',rule:'v1'};
 const history={code,daily:[daily],days:[{date:day,status:'ready',has_minutes:true,matches:[],signal_count:0,recorded_count:0}],events:[],minute_days:[day],source};
 await page.addInitScript(({snapshot,bars,day,daily,history})=>{
  (window as any).isTauri=true;(window as any).__TAURI_INTERNALS__={invoke:async(command:string,args:any)=>{
   if(command!=='rpc')return false;
   const method=args.method;
   if(method==='snapshot')return snapshot;
   if(method==='market')return {quotes:[],minute:null};
   if(method==='chart')return [{day,data:args.args.kind==='daily'?daily:{bars,source:'test'}}];
   if(method==='history')return history;
   return {};
  }};
 },{snapshot,bars,day,daily,history});
 await page.route('http://127.0.0.1:1420/',async route=>{const response=await route.fetch();await route.fulfill({response,headers:{...response.headers(),'content-security-policy':'connect-src ipc: http://ipc.localhost'}});});
 await page.goto('/');await expect(page.getByLabel('交易日期')).toHaveValue(day);
 await page.locator('.d-purpose-panel>summary').click();await expect(page.locator('.d-purpose-panel')).toContainText('283.41元');
 await page.locator('.d-history-details>summary').click();await expect(page.getByLabel('D历史全样本成本对照')).toContainText('-0.8083%');
 await expect(page.getByRole('alert')).toHaveCount(0);
});
