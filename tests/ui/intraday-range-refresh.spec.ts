import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {IntradayRangeReferenceCache} from '../../src/intradayRangeReference';
const day='2026-11-17',code='sh603938',base=27.8;
const stamp=(time:string)=>day+'T'+time+'+08:00';
const instant=(time:string)=>Date.parse(stamp(time));
const reference=(time='14:58:00',high=29.39,low=27.2)=>({code,day,previousClose:base,timestamp:stamp(time),high,low});

test('staggered quotes retain only already admitted extrema and accept later valid corrections',()=>{
 const cache=new IntradayRangeReferenceCache(),known=reference(),pending=reference('14:58:10',29.5,27.1),now=instant('14:59:00');
 expect(cache.resolve(known,undefined,code,day,base,instant('14:58:05'),now)).toEqual(known);
 expect(cache.resolve(pending,undefined,code,day,base,instant('14:58:05'),now)).toEqual(known);
 expect(cache.resolve(pending,undefined,code,day,base,instant('14:58:15'),now)).toEqual(pending);
 const corrected=reference('14:58:16',29.35,27.3);
 expect(cache.resolve(corrected,undefined,code,day,base,instant('14:58:20'),now)).toEqual(corrected);
});

test('a first pending quote uses the qualified cache; absent low metadata retains the previous qualified low',()=>{
 const cache=new IntradayRangeReferenceCache(),known=reference(),cached={...reference('14:58:05',29.4),low:NaN},now=instant('14:59:00');
 expect(cache.resolve(reference('14:58:10'),known,code,day,base,instant('14:58:05'),now)).toEqual(known);
 const result=cache.resolve(reference('14:58:15',30,27),cached,code,day,base,instant('14:58:05'),now);
 expect(result).toEqual({...cached,low:known.low});
});

for(const scenario of ['stock','day','previous-close','rewind','missing','corrupt','future-clock','null-cutoff'] as const)test('range evidence resets on '+scenario,()=>{
 const cache=new IntradayRangeReferenceCache(),known=reference(),now=instant('14:59:00');
 cache.resolve(known,undefined,code,day,base,instant('14:58:05'),now);
 const q=scenario==='missing'?undefined:scenario==='corrupt'?{...reference('14:58:10'),high:20,low:30}:scenario==='future-clock'?reference('15:00:00'):reference('14:58:10');
 const result=cache.resolve(q,undefined,scenario==='stock'?'sz300364':code,scenario==='day'?'2026-11-16':day,scenario==='previous-close'?28:base,scenario==='rewind'?instant('14:57:00'):scenario==='null-cutoff'?null:instant('14:58:05'),now);
 expect(result).toBeUndefined();
});

function fixture(){
 const f=JSON.parse(readFileSync('public/preview.json','utf8'));
 f.snapshot.watch=[{code,name:'三孚股份',enabled:1,health:'实时采样监控',candidates:[],quote:{code,name:'三孚股份',price:'28.22',previous_close:String(base),open:'27.4',high:'29.39',low:'27.2',timestamp:stamp('14:58:00'),volume:100000,amount:10000000}}];
 f.snapshot.events=[];f.snapshot.now=stamp('14:58:05');f.snapshot.config={monitor:false,trading_paused:true};f.snapshot.market_open=true;
 const candle={date:day,open:'27.4',close:'28.22',high:'29.39',low:'27.2',volume:10000};
 f.minutes[code]=[{day,data:{date:day,trading_date:day,symbol:code.slice(2),previous_close:String(base),day_high:'29.39',day_low:'27.2',limit_reference_time:stamp('14:58:00'),cached_at:stamp('14:58:05'),bars:[27.4,29.3,28.22].map((v,i)=>({time:['09:31','11:10','14:57'][i],close:String(v),average:'28.3',volume:10000,complete:true}))}}];
 f.daily[code]=[{day,data:candle}];f.history[code]={code,daily:[candle],days:[{date:day,status:'ready',has_minutes:true,signal_count:0,matches:[]}],events:[],source:null,minute_days:[day]};
 return f;
}
async function axes(page:Page){
 return page.getByLabel('分时价格及分钟成交量',{exact:true}).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]),c=e.getInstanceByDom(el);
  return c?{extent:c.getModel().getComponent('yAxis',0).axis.scale.getExtent(),historicalPixel:c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['11:10',29.3]),price:c.getOption().series.find((s:any)=>s.name==='价格').data}:null;
 });
}

test('full App snapshot/cache arrival order never shrinks known tick extrema or moves historical pixels',async({page},info)=>{
 await page.clock.install({time:new Date(stamp('14:59:00'))});const f=fixture();let reads=0;const writes:string[]=[];
 let releaseDaily!:()=>void;
 const dailyGate=new Promise<void>(resolve=>{releaseDaily=resolve;});
 await page.exposeFunction('rangeRpc',async(method:string,args:any)=>{
  if(method==='snapshot'){reads++;return {...f.snapshot,data_revisions:{code,history:[1],chart:[reads],market:[1]}};}
  if(method==='chart'){
   if(args.kind==='minute')return f.minutes[code];
   await dailyGate;
   return f.daily[code];
  }
  if(method==='history')return f.history[code];
  if(method==='market'||method==='index_minute')return {quotes:[],minute:null};
  if(method==='trading_chart')return {code,day,accounts:[],points:[]};
  if(method==='volume_flow')return {code,day,status:'unavailable',minutes:[]};
  if(method==='stock_profile')return {code,data:null,themes:[],theme_status:'unavailable',running:false,error:''};
  if(method==='paper_account_state'||method==='pool_signals')return null;
  if(method==='minute_ensure')return {job:'isolated-cache-check'};
  if(method==='job')return {status:'done',result:{}};
  writes.push(method);throw Error('Unexpected RPC '+method);
 });
 await page.addInitScript(()=>{
  const w=window as any;w.isTauri=true;w.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:(command:string,args:any)=>command==='rpc'?w.rangeRpc(args.method,args.args):Promise.resolve(command==='plugin:app|version'?'test':false)};w.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
 });
 if(process.env.RANGE_REFERENCE_BASELINE==='1')await page.route('**/src/intradayRangeReference.ts*',r=>r.fulfill({contentType:'application/javascript',body:'export class IntradayRangeReferenceCache {resolve(quote,cached){return quote||cached;}}'}));
 try{
  await page.goto('/');
  await expect.poll(async()=>(await axes(page))?.extent).toEqual([26.21,29.39]);
 }finally{releaseDaily();}
 const initial=(await axes(page))!;
 const observed=[];
 for(const [quoteTime,cacheTime] of [['14:58:10','14:58:05'],['14:58:10','14:58:15'],['14:58:16','14:58:15'],['14:58:16','14:58:20']] as const){
  f.snapshot.watch[0].quote.timestamp=stamp(quoteTime);f.snapshot.now=stamp(quoteTime);f.minutes[code][0].data.cached_at=stamp(cacheTime);
  const before=reads;await page.clock.runFor(3500);await expect.poll(()=>reads).toBeGreaterThan(before);
  await page.waitForTimeout(150);const state=(await axes(page))!;observed.push(state);
  expect(state.extent).toEqual(initial.extent);expect(state.historicalPixel).toEqual(initial.historicalPixel);expect(state.price).toEqual(initial.price);
 }
 // A genuine new extreme stays gated until its capture, then expands normally.
 f.snapshot.watch[0].quote.timestamp=stamp('14:58:21');f.snapshot.watch[0].quote.high='29.6';
 await page.clock.runFor(3500);await page.waitForTimeout(100);expect((await axes(page))!.extent).toEqual(initial.extent);
 f.minutes[code][0].data.cached_at=stamp('14:58:25');await page.clock.runFor(3500);
 await expect.poll(async()=>(await axes(page))?.extent).toEqual([26,29.6]);
 // A qualified later correction is allowed to shrink the display; it is not frozen.
 f.snapshot.watch[0].quote.timestamp=stamp('14:58:26');f.snapshot.watch[0].quote.high='29.35';f.minutes[code][0].data.cached_at=stamp('14:58:30');
 await page.clock.runFor(3500);await expect.poll(async()=>(await axes(page))?.extent).toEqual([26.25,29.35]);
 expect(writes).toEqual([]);await info.attach('async-range-sequence',{body:JSON.stringify(observed),contentType:'application/json'});
 await page.screenshot({path:info.outputPath('stable-range.png')});
 // Cache rewind must still remove references not yet reached, including retained ones.
 f.minutes[code][0].data.cached_at=stamp('14:30:00');f.minutes[code][0].data.limit_reference_time=stamp('14:58:00');
 await page.clock.runFor(3500);await expect.poll(async()=>(await axes(page))?.extent).toEqual([26.3,29.3]);
});
