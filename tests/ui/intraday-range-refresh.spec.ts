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
  if(!c)return null;
  const {series,xAxis}=c.getOption();
  const latest=series.find((s:any)=>s.name==='最新价')?.data||[];
  return {extent:c.getModel().getComponent('yAxis',0).axis.scale.getExtent(),historicalPixel:c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['11:10',29.3]),
   price:series.find((s:any)=>s.name==='价格').data,livePoint:latest[xAxis[0].data.indexOf('14:58')],liveIndex:xAxis[0].data.indexOf('14:58')};
 });
}

test('full App snapshot/cache arrival order never shrinks known tick extrema or moves historical pixels',async({page},info)=>{
 await page.clock.install({time:new Date(stamp('14:59:00'))});const f=fixture();let reads=0;const writes:string[]=[];
 const buyDay='2026-11-12',sellDay='2026-11-13',emptyDay='2026-11-16';
 const candle=f.history[code].daily[0];
 f.history[code].daily=[...[buyDay,sellDay,emptyDay].map(date=>({...candle,date})),candle];
 let quoteReads=0,quoteRead:{now:string;quotes:Record<string,unknown>}|undefined,holdSnapshot:Promise<void>|undefined;
 let releaseDaily!:()=>void;
 const dailyGate=new Promise<void>(resolve=>{releaseDaily=resolve;});
 await page.exposeFunction('rangeRpc',async(method:string,args:any)=>{
  if(method==='snapshot'){
   const result=structuredClone({...f.snapshot,data_revisions:{code,history:[1],chart:[++reads],market:[1]}});
   await holdSnapshot;
   return result;
  }
  if(method==='watch_quotes'){quoteReads++;return quoteRead;}
  if(method==='chart'){
   if(args.kind==='minute')return f.minutes[code];
   await dailyGate;
   return f.daily[code];
  }
  if(method==='history')return f.history[code];
  if(method==='market'||method==='index_minute')return {quotes:[],minute:null};
  if(method==='trading_chart')return {code,day,accounts:[],points:[]};
  if(method==='trading_chart_daily')return {...args,marks:[
   {day:buyDay,value:'B',buyShares:300,buyAverage:28,sellShares:0,sellAverage:null},
   {day:sellDay,value:'S',buyShares:0,buyAverage:null,sellShares:200,sellAverage:28.1},
   {day,value:'T',buyShares:200,buyAverage:28.2,sellShares:400,sellAverage:28.5},
  ]};
  if(method==='daily_load')return {job:'isolated-daily'};
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
 // The quote and minute cache can disagree legitimately within one minute.
 // The watch row, live marker and newest tooltip must share the quote anyway.
 f.snapshot.watch[0].quote.price='28.57';
 f.snapshot.watch[0].quote.timestamp=stamp('14:58:36');
 f.minutes[code][0].data.bars.push({time:'14:58',close:'28.63',average:'28.23',volume:7300,complete:true});
 await page.clock.runFor(3500);
 await expect(page.locator('.stock.selected .stock-right strong')).toHaveText('28.57');
 await expect.poll(async()=>(await axes(page))?.livePoint).toBe(28.57);
 const projected=(await axes(page))!;
 expect(projected.price[projected.liveIndex]).toBe(28.57);
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 const hover=async(time:string,value:number)=>{
  const point=await chart.evaluate(async(el,{time,value})=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]),c=e.getInstanceByDom(el);
   const [x,y]=c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[time,value]),bounds=el.getBoundingClientRect();
   return {x:bounds.left+x,y:bounds.top+y};
  },{time,value});
  await page.mouse.move(point.x,point.y);
 };
 const tooltip=chart.locator('.minute-tooltip');
 await hover('14:57',28.22);
 await expect(tooltip).toContainText('分钟收盘：28.22 元');
 await expect(tooltip).not.toContainText('最新价');
 await hover('14:58',28.57);
 await expect(tooltip).toContainText('14:58:36');
 await expect(tooltip).toContainText('最新价：28.57 元');
 await expect(tooltip).toContainText('涨跌幅：+2.77%');
 await expect(tooltip).not.toContainText(/28\.63|分钟收盘|分钟量|均价/);
 await hover('11:10',29.3);
 await expect(tooltip).toContainText('分钟收盘：29.30 元');
 await expect(tooltip).not.toContainText('最新价');
 f.snapshot.watch[0].quote.timestamp=stamp('15:01:00');
 await page.clock.runFor(3500);
 await expect.poll(async()=>(await axes(page))?.livePoint).toBeNull();
 const historical=(await axes(page))!;
 expect(historical.price[historical.liveIndex]).toBe(28.63);
 await hover('14:58',28.63);
 await expect(tooltip).toContainText('分钟收盘：28.63 元');
 await expect(tooltip).not.toContainText('最新价');
 expect(writes).toEqual([]);await info.attach('async-range-sequence',{body:JSON.stringify(observed),contentType:'application/json'});
 await page.screenshot({path:info.outputPath('stable-range.png')});
 // Cache rewind must still remove references not yet reached, including retained ones.
 f.minutes[code][0].data.cached_at=stamp('14:30:00');f.minutes[code][0].data.limit_reference_time=stamp('14:58:00');
 await page.clock.runFor(3500);await expect.poll(async()=>(await axes(page))?.extent).toEqual([26.3,29.3]);

 // The lightweight read runs independently of a full snapshot already in flight.
 const oldQuote={...f.snapshot.watch[0].quote,price:'28.57',timestamp:stamp('14:58:36')};
 f.snapshot.watch[0].quote=oldQuote;f.snapshot.now=stamp('14:59:05');f.snapshot.config.monitor=true;
 quoteRead={now:f.snapshot.now,quotes:{[code]:oldQuote}};
 await page.clock.runFor(3500);
 await expect.poll(()=>quoteReads).toBeGreaterThan(0);
 let releaseSnapshot!:()=>void;
 holdSnapshot=new Promise<void>(resolve=>{releaseSnapshot=resolve;});
 try{
  f.snapshot.now=stamp('14:59:06');
  const beforeSnapshot=reads;await page.clock.runFor(3500);
  await expect.poll(()=>reads).toBeGreaterThan(beforeSnapshot);
  const recent={...oldQuote,price:'28.61',timestamp:stamp('14:58:46'),source:'eastmoney'};
  quoteRead={now:stamp('14:59:07'),quotes:{[code]:recent}};
  const beforeQuote=quoteReads;await page.clock.runFor(1100);
  await expect.poll(()=>quoteReads).toBeGreaterThan(beforeQuote);
  await expect(page.locator('.stock.selected .stock-right strong')).toHaveText('28.61');
  await expect(page.locator('.stock.selected .watch-quote-details')).toHaveAttribute('title',/^东方财富备用/);
  await expect.poll(async()=>(await axes(page))?.livePoint).toBe(28.61);
 }finally{releaseSnapshot();}
 await page.clock.runFor(600);
 await expect(page.locator('.stock.selected .stock-right strong')).toHaveText('28.61');
 await expect.poll(async()=>(await axes(page))?.livePoint).toBe(28.61);

 await page.getByRole('button',{name:'日K',exact:true}).click();
 const dailyChart=page.getByLabel('日K线及成交量',{exact:true});
 await expect.poll(()=>dailyChart.evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]);
  const series=e.getInstanceByDom(el)?.getOption().series||[];
  return {marks:series[0]?.markPoint?.data.filter((m:any)=>m.autoTradeDaily).map((m:any)=>[m.coord[0],m.value,m.symbol,m.symbolOffset[1]]),
   lines:series.find((s:any)=>s.name==='实盘成交标记连线')?.data.length};
 })).toEqual({marks:[[buyDay,'B','circle',18],[sellDay,'S','circle',-18],[day,'T','circle',-18]],lines:3});
 const hoverDaily=async(date:string)=>{
  const point=await dailyChart.evaluate(async(el,date)=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]);
   const [x,y]=e.getInstanceByDom(el).convertToPixel({xAxisIndex:0,yAxisIndex:0},[date,28]);const r=el.getBoundingClientRect();
   return {x:r.x+x,y:r.y+y};
  },date);
  await page.mouse.move(point.x,point.y);
 };
 await hoverDaily(buyDay);
 const dailyTooltip=dailyChart.locator('.daily-tooltip');
 await expect(dailyTooltip).toContainText('实盘成交 B');
 await expect(dailyTooltip).toContainText('买入300股 · 均价28.00元');
 await hoverDaily(emptyDay);
 await expect(dailyTooltip).toContainText(emptyDay);
 await expect(dailyTooltip).not.toContainText('实盘成交');
});
