import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const fixture=JSON.parse(readFileSync('public/preview.json','utf8'));
const blue=JSON.parse(readFileSync('tests/ui/fixtures/blue-minute-20261113.json','utf8'));
const code='sz300058',day='2026-11-13',minute=blue.minute;
fixture.snapshot.watch=[{code,name:'蓝色光标',enabled:1,quote:blue.quote,health:'非交易时段 · 已刷新缓存',candidates:[]}];
fixture.snapshot.now='2026-11-15T10:00:00+08:00';
fixture.minutes[code]=[{day,data:minute}];fixture.daily[code]=[];
fixture.history[code]={code,daily:[],days:[],events:[],source:null,minute_days:[day]};
// Overview removal must not affect the real stock-minute quantities.
const read=(chart:any)=>chart.evaluate(async(el:any)=>{
 const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),m=c.getModel();
 const ig=m.getComponent('grid',3).coordinateSystem.getRect(),iv=o.series.find((s:any)=>s.name==='指数成交量').data,indexPeak=Math.max(...iv.filter((n:any)=>typeof n==='number')),indexMax=m.getComponent('yAxis',o.yAxis.findIndex((a:any)=>a.gridIndex===3)).axis.scale.getExtent()[1],indexPeakTime=o.xAxis[3].data[iv.indexOf(indexPeak)];
 const grid=m.getComponent('grid',1).coordinateSystem.getRect(),series=o.series.filter((s:any)=>s.stack==='minute-volume');
 const totals=o.xAxis[1].data.map((_:any,i:number)=>series.reduce((sum:number,s:any)=>sum+Number(s.data[i]||0),0)),peak=Math.max(...totals),first=totals.findIndex((v:number)=>v>0),highest=totals.indexOf(peak);
 return {indexMax,indexPeakTime,indexPeakY:c.convertToPixel({xAxisIndex:3,yAxisIndex:o.yAxis.findIndex((a:any)=>a.gridIndex===3)},[indexPeakTime,indexPeak])[1],indexTop:ig.y,indexHeight:ig.height,indexEarlierY:c.convertToPixel({xAxisIndex:3,yAxisIndex:o.yAxis.findIndex((a:any)=>a.gridIndex===3)},['09:31',500])[1],grids:[0,1,2,3,4].map(i=>m.getComponent('grid',i).coordinateSystem.getRect().height),height:c.getHeight(),max:m.getComponent('yAxis',1).axis.scale.getExtent()[1],totals,times:o.xAxis[1].data,first,highest,peak,top:grid.y,peakY:c.convertToPixel({xAxisIndex:1,yAxisIndex:1},[o.xAxis[1].data[highest],peak])[1],firstY:c.convertToPixel({xAxisIndex:1,yAxisIndex:1},[o.xAxis[1].data[first],totals[first]])[1],paneHeight:grid.height};
});

test('indexes move only to header and BlueFocus first displayed bar fills the enlarged volume pane',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-overview-collapsed','false'));
 await page.route('**/preview.json',r=>r.fulfill({json:fixture}));await page.goto('/');
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();
 await expect(page.locator('.market-header .overview-indexes')).toHaveCount(1);await expect(page.locator('.home-overview')).toHaveCount(0);
 await expect(page.locator('.market-header .overview-index')).toHaveCount(3);
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:980});await expect.poll(()=>page.locator('.workspace').evaluate(el=>getComputedStyle(el).marginLeft)).toBe(width<1151?'170px':'202px');
  await expect.poll(async()=>Math.abs((await read(chart)).peakY-(await read(chart)).top)).toBeLessThan(.5);
  const v=await read(chart);expect(v.first).toBe(v.highest);expect(v.times[v.first]).toBe('09:31');expect(v.peak).toBe(255821);
  expect(v.grids[1]-v.grids[3]).toBe(52);expect(v.firstY).toBeCloseTo(v.top,5);expect(v.max).toBe(v.peak);
  for(const b of minute.bars.filter((b:any)=>b.time>='09:31'&&b.time<='15:00'&&b.time!=='13:00'))expect(v.totals[v.times.indexOf(b.time)]).toBeCloseTo(b.volume/100,6);
  expect(minute.bars.find((b:any)=>b.time==='13:00').volume).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false);
  await page.mouse.move(0,0);await page.screenshot({path:`outputs/header-volume-blue-${width}.png`,fullPage:true});
 }
 await page.getByRole('button',{name:'大盘广度',exact:true}).click();await expect(page.locator('.market-header-indexes')).toHaveCount(0);
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await expect(page.locator('.market-header .overview-index')).toHaveCount(3);expect(errors).toEqual([]);
});

test('new stock and index volume peaks take the top while both earlier high bars shrink',async({page})=>{
 await page.addInitScript(({fixture,minute,code,day})=>{
  const w=window as any;w.__bars=minute.bars.filter((b:any)=>b.time<='10:00');w.__stamp='2026-11-13T10:00:00+08:00';w.__indexBars=w.__bars.map((b:any)=>({time:b.time,close:'2500',volume_lots:b.time==='09:31'?5000000:100000}));
  const clone=(v:any)=>JSON.parse(JSON.stringify(v));
  Object.assign(w,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},async invoke(command:string,p:any){
   if(command!=='rpc')return command==='plugin:autostart|is_enabled'?false:0;
   const {method,args={}}=p;
   switch(method){
    case 'snapshot':return clone({...fixture.snapshot,now:w.__stamp});
    case 'chart':return args.kind==='daily'?[]:[{day,data:{...minute,bars:clone(w.__bars)}}];
    case 'history':return {...fixture.history[code],source:{}};
    case 'market':case 'market_overview':return clone(fixture.market||{quotes:[],minute:null});
    case 'index_minute':return {quotes:[{code:args.code,name:'测试指数',timestamp:w.__stamp,previous_close:'2500',price:'2500',change:'0',percent:'0',source:'tencent'}],minute:{code:args.code,date:day,previous_close:'2500',source:'tencent',cached_at:w.__stamp,bars:clone(w.__indexBars)}};
    case 'breadth':case 'option_pcr':return {days:[],running:false,error:''};
    case 'index_technical':return {daily:[],weekly:[],running:false,error:''};
    case 'sector_flow':return {snapshot:null,running:false,error:''};
    case 'trading_chart':return {code,day,accounts:[],points:[]};
    case 'volume_flow':return {code,day,status:'unavailable',minutes:[]};
    case 'sources':case 'csi300':return null;
    case 'minute_ensure':case 'daily_load':return {job:'fixture'};
    case 'job':return {status:'done',result:[]};
    default:throw Error('Unexpected request '+method);
   }
  }}});
 },{fixture,minute,code,day});
 await page.goto('/');const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();
 await expect.poll(async()=>(await read(chart)).max).toBe(255821);
 await expect.poll(async()=>(await read(chart)).indexMax).toBe(500);
 await page.evaluate(()=>{const w=window as any;w.__indexBars.push({time:'10:01',close:'2500',volume_lots:8000000});w.__bars.push({...w.__bars.at(-1),time:'10:01',volume:40000000,complete:true});w.__stamp='2026-11-13T10:01:00+08:00';});
 await expect.poll(async()=>(await read(chart)).max,{timeout:10000}).toBe(400000);
 await expect.poll(async()=>(await read(chart)).indexMax).toBe(800);
 const v=await read(chart);expect(v.indexPeakTime).toBe('10:01');expect(v.indexPeakY).toBeCloseTo(v.indexTop,5);expect((v.indexTop+v.indexHeight-v.indexEarlierY)/v.indexHeight).toBeCloseTo(500/800,6);expect(v.times[v.highest]).toBe('10:01');expect(v.peakY).toBeCloseTo(v.top,5);
 expect((v.top+v.paneHeight-v.firstY)/v.paneHeight).toBeCloseTo(255821/400000,6);
});
