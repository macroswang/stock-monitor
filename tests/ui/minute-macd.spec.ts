import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {benchmarkForStock,minuteMacd,minuteSlots,macdRange,parseMacdParameters,macdParametersKey} from '../../src/minuteMacd';
import {splitIndexVolume} from '../../src/indexVolume';

const at=(time:string)=>minuteSlots.indexOf(time);
test('market mapping distinguishes Shanghai, Shenzhen and ChiNext without guessing',()=>{
 for(const code of ['sh603938','sh688680','600519'])expect(benchmarkForStock(code)?.code).toBe('sh000001');
 for(const code of ['sz000981','sz002001','001001'])expect(benchmarkForStock(code)?.code).toBe('sz399001');
 for(const code of ['sz300672','sz301001','300001'])expect(benchmarkForStock(code)?.code).toBe('sz399006');
 expect(benchmarkForStock('bj920001')).toBeNull();expect(benchmarkForStock('')).toBeNull();
});
test('standard MACD has known EMA values, zero constant-price values and no future dependency',()=>{
 const bars=[{time:'09:30',close:10},{time:'09:31',close:11},{time:'09:32',close:12}];
 const result=minuteMacd(bars);
 expect(result[0]).toEqual({dif:0,dea:0,histogram:0});
 expect(result[1]!.dif).toBeCloseTo(.079772079772,10);expect(result[1]!.dea).toBeCloseTo(.0159544159544,10);expect(result[1]!.histogram).toBeCloseTo(.127635327635,10);
 expect(result[2]!.dif).toBeCloseTo(.221134568713,10);expect(result[2]!.histogram).toBeCloseTo(.328288244413,10);
 const all=minuteSlots.map((time,i)=>({time,close:10+Math.sin(i/9)}));
 expect(minuteMacd(all).slice(0,90)).toEqual(minuteMacd(all.slice(0,90)).slice(0,90));
 expect(minuteMacd(all.map(b=>({...b,close:20}))).every(p=>p?.histogram===0&&p?.dif===0&&p?.dea===0)).toBe(true);
});
test('lunch stays continuous; invalid, duplicate or missing minutes break and reset the curve',()=>{
 const bars=minuteSlots.map((time,i)=>({time,close:10+i/100}));
 expect(minuteMacd(bars)[at('13:01')]!.dif).toBeGreaterThan(0);
 for(const broken of [bars.filter(b=>b.time!=='10:00'),[...bars,{time:'10:00',close:11}],bars.map(b=>b.time==='10:00'?{...b,close:NaN}:b)]){
  const points=minuteMacd(broken);expect(points[at('10:00')]).toBeNull();expect(points[at('10:01')]).toEqual({dif:0,dea:0,histogram:0});
 }
 expect(minuteMacd(bars.slice(0,20))[20]).toBeNull();
});

test('MACD scales include both curves and histogram without mirroring unused space',()=>{
 const points=[{dif:.3,dea:.25,histogram:.1},{dif:.2,dea:.25,histogram:-.1}],range=macdRange(points);
 expect(range.min).toBeCloseTo(-.132);expect(range.max).toBeCloseTo(.332);
 for(const p of points)for(const value of Object.values(p)){expect(value).toBeGreaterThan(range.min);expect(value).toBeLessThan(range.max);}
 expect(macdRange([null,{dif:0,dea:0,histogram:0}])).toEqual({min:-.001,max:.001});
});
test('custom MACD periods use their own EMA weights and reject invalid parameters',()=>{
 const bars=[{time:'09:30',close:10},{time:'09:31',close:11},{time:'09:32',close:12}];
 const periods={fast:2,slow:4,signal:3},points=minuteMacd(bars,periods);
 expect(points[1]!.dif).toBeCloseTo(4/15,12);expect(points[1]!.dea).toBeCloseTo(2/15,12);expect(points[1]!.histogram).toBeCloseTo(4/15,12);
 expect(points).not.toEqual(minuteMacd(bars));expect(minuteMacd(bars,periods).slice(0,2)).toEqual(minuteMacd(bars.slice(0,2),periods).slice(0,2));
 for(const invalid of [null,{}, {fast:12,slow:12,signal:9},{fast:26,slow:12,signal:9},{fast:0,slow:26,signal:9},{fast:12.5,slow:26,signal:9},{fast:12,slow:251,signal:9},{fast:12,slow:26,signal:NaN},{fast:'12',slow:26,signal:9}])expect(parseMacdParameters(invalid)).toBeNull();
 expect(()=>minuteMacd(bars,{fast:0,slow:26,signal:9})).toThrow(RangeError);
});
test('index direction accepts only fully matched trade-side lots and keeps unknown totals intact',()=>{
 const direction={code:'sh000001',day:'2026-10-16',time:'10:30',source:'TEST_ONLY',unit:'lots',scope:'index_total',basis:'trade_initiator',complete:true,total_lots:1000,buy_lots:600,sell_lots:250,neutral_lots:100,unknown_lots:50} as const;
 const bar={time:'10:30',close:'3600',volume_lots:1000,volume_direction:direction};
 expect(splitIndexVolume(bar,'sh000001','2026-10-16')).toEqual({total:1000,buy:600,sell:250,unclassified:150,verified:true});
 for(const change of [{code:'sz399001'},{day:'2026-10-15'},{time:'10:31'},{unit:'yuan'},{scope:'sample_stocks'},{basis:'price_change'},{complete:false},{source:''},{buy_lots:601},{sell_lots:-1},{unknown_lots:50.5},{total_lots:999}]){
  expect(splitIndexVolume({...bar,volume_direction:{...direction,...change}} as any,'sh000001','2026-10-16')).toEqual({total:1000,buy:0,sell:0,unclassified:1000,verified:false});
 }
 expect(splitIndexVolume({...bar,volume_lots:undefined},'sh000001','2026-10-16')).toBeNull();
});

const fixture=JSON.parse(readFileSync('public/preview.json','utf8'));
async function setup(page:Page,wrongDate=false){
 await page.clock.install({time:new Date('2026-11-02T12:00:00+08:00')});
 for(const [file,code,name,base] of [['market-overview-preview.json','sh000001','上证指数',3600],['szse-preview.json','sz399001','深证成指',11000],['chinext-preview.json','sz399006','创业板指',2500]] as const){
  await page.route('**/'+file,route=>route.fulfill({json:{quotes:[{code,name,timestamp:'2026-10-16T15:00:00+08:00',previous_close:String(base),price:String(base)}],collected_at:'2026-10-16T15:01:00+08:00',minute:{code,name,date:wrongDate?'2026-10-15':'2026-10-16',previous_close:String(base),bars:minuteSlots.map((time,i)=>({time,close:String(base+12*Math.sin(i/14)+i/20),volume_lots:1000+i*17}))}}}));
 }
 const data=structuredClone(fixture);data.minutes['sz000981'][0].data.previous_close='2.40';await page.route('**/preview.json',route=>route.fulfill({json:data}));
 await page.goto('/');await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await expect(page.getByRole('group',{name:'个股MACD',exact:true})).toBeVisible();
}
async function option(page:Page){
 return page.getByLabel('分时价格及分钟成交量',{exact:true}).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption();
  return {grids:o.grid.length,axes:o.xAxis.length,series:o.series.map((s:any)=>({name:s.name,xAxis:s.xAxisIndex,yAxis:s.yAxisIndex,data:s.data})),zoom:o.dataZoom[0].xAxisIndex};
 });
}
test('both MACD panes follow the selected market, keep one timeline and expose matching hover values',async({page})=>{
 await setup(page);
 for(const [stock,index] of [['宏昌电子','上证指数'],['山子高科','深证成指'],['国科微','创业板指']]){
  await page.locator('.stock').filter({hasText:stock}).click();
  const indicator=page.getByRole('group',{name:'指数MACD',exact:true});await expect(indicator).toContainText(index);
  await expect.poll(async()=> (await option(page)).series.find((s:any)=>s.name==='指数 DIF')?.data.some((v:any)=>v!==null)).toBe(true);
  const o=await option(page);expect(o.grids).toBe(5);expect(o.axes).toBe(5);expect(o.zoom).toEqual([0,1,2,3,4]);if(stock==='山子高科'){expect(o.series.find((s:any)=>s.name==='个股 DIF')?.yAxis).toBe(3);expect(o.series.find((s:any)=>s.name==='指数 DIF')?.yAxis).toBe(5);}
 }
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption();c.dispatchAction({type:'showTip',seriesIndex:o.series.findIndex((v:any)=>v.name==='指数 DIF'),dataIndex:atBrowser('10:30')});function atBrowser(time:string){return o.xAxis[2].data.indexOf(time);}});
 await expect(page.getByRole('group',{name:'个股MACD',exact:true}).locator('time')).toHaveText('10:30');
 await expect(page.getByRole('group',{name:'指数MACD',exact:true}).locator('time')).toHaveText('10:30');
 await page.locator('.chart-shell').screenshot({path:'outputs/macd-comparison-chinext.png'});
});
test('missing date leaves both index panes empty instead of borrowing another day',async({page})=>{
 await setup(page,true);
 await expect(page.locator('.macd-unavailable')).toContainText('暂无可用分钟数据');
 for(const name of ['指数 MACD','指数买入量','指数卖出量','指数中性 / 未识别量'])expect((await option(page)).series.find((s:any)=>s.name===name)?.data.every((v:any)=>v===null)).toBe(true);
 expect((await option(page)).grids).toBe(5);
});

test('comparison is always on despite an old hidden preference, including the linked daily chart',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-show-minute-macd','false'));
 await setup(page);
 await expect(page.getByRole('checkbox',{name:'显示MACD对照',exact:true})).toHaveCount(0);
 expect((await option(page)).grids).toBe(5);
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(page.getByLabel('日K线及成交量',{exact:true})).toBeVisible();
 await expect(page.getByRole('group',{name:'指数MACD',exact:true})).toBeVisible();
 expect((await option(page)).grids).toBe(5);
 await page.getByRole('button',{name:'分时',exact:true}).click();
 expect((await option(page)).grids).toBe(5);
 await expect(page.getByRole('checkbox',{name:'显示MACD对照',exact:true})).toHaveCount(0);
});

test('daily and weekly linked minutes collapse without affecting K candles and remember the choice',async({page})=>{
 await setup(page);
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const linked=page.getByRole('region',{name:'K线关联分时'}),minute=linked.getByLabel('分时价格及分钟成交量',{exact:true});
 await expect(minute).toBeVisible();
 const dailyCount=await page.getByLabel('日K线及成交量',{exact:true}).locator('canvas').count();
 await linked.getByRole('button',{name:'收起当日分时',exact:true}).click();
 await expect(minute).toHaveCount(0);await expect(linked.getByRole('button',{name:'展开当日分时',exact:true})).toHaveAttribute('aria-expanded','false');
 await expect(page.getByLabel('日K线及成交量',{exact:true}).locator('canvas')).toHaveCount(dailyCount);
 await page.getByRole('button',{name:'周K',exact:true}).click();
 await expect(page.getByLabel('周K线及成交量',{exact:true})).toBeVisible();await expect(minute).toHaveCount(0);
 await page.reload();await page.getByRole('button',{name:'周K',exact:true}).click();
 await expect(minute).toHaveCount(0);await linked.getByRole('button',{name:'展开当日分时',exact:true}).click();
 await expect(minute).toBeVisible();await expect.poll(async()=> (await option(page)).grids).toBe(5);
 await expect(linked.getByRole('group',{name:'指数MACD',exact:true})).toContainText('上证指数');
 await page.getByRole('button',{name:'日K',exact:true}).click();await expect(minute).toBeVisible();
 await page.reload();await page.getByRole('button',{name:'日K',exact:true}).click();await expect(minute).toBeVisible();
 await linked.getByRole('button',{name:'收起当日分时',exact:true}).click();await page.getByRole('button',{name:'分时',exact:true}).click();
 await expect(page.getByLabel('分时价格及分钟成交量',{exact:true})).toBeVisible();expect((await option(page)).grids).toBe(5);
});

test('MACD panels are passive references and zoom shares all five time axes',async({page})=>{
 await setup(page);
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await chart.scrollIntoViewIfNeeded();
 const point=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el);return c.convertToPixel({xAxisIndex:2,yAxisIndex:2},['10:30',0]);});
 const box=(await chart.boundingBox())!;await page.mouse.click(box.x+point[0],box.y+point[1],{button:'right'});
 await expect(page.getByRole('dialog')).toHaveCount(0);
 const before=(await option(page)).series.find((s:any)=>s.name==='个股 DIF')!.data;
 await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);e.getInstanceByDom(el).dispatchAction({type:'dataZoom',start:30,end:70});});
 expect((await option(page)).series.find((s:any)=>s.name==='个股 DIF')!.data).toEqual(before);
 const pixels=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el);return [0,1,2,3,4].map(xAxisIndex=>c.convertToPixel({xAxisIndex},'11:00'));});
 for(const x of pixels)expect(x).toBeCloseTo(pixels[0],5);
});


test('index MACD never reveals later minutes than the selected stock data',async({page})=>{
 const data=structuredClone(fixture);data.minutes.sh603002[0].data.bars=data.minutes.sh603002[0].data.bars.filter((b:{time:string})=>b.time>='09:30'&&b.time<='09:40');
 await setup(page);
 await page.route('**/preview.json',route=>route.fulfill({json:data}));await page.reload();
 await expect.poll(async()=> typeof (await option(page)).series.find((s:any)=>s.name==='指数 DIF')?.data[at('09:40')]).toBe('number');
 for(const name of ['指数 DIF','指数买入量','指数卖出量','指数中性 / 未识别量']){const points=(await option(page)).series.find((s:any)=>s.name===name)!.data;expect(points[at('09:41')]).toBeNull();expect(points[at('10:00')]).toBeNull();expect(points[at('15:00')]).toBeNull();}
});


test('comparison panes fit common desktop windows and reflow after the market overview collapses',async({page})=>{
 await page.addInitScript(()=>{localStorage.setItem('stock-monitor-overview-collapsed','true');localStorage.setItem('stock-monitor-sidebar-collapsed','true');});
 await setup(page);
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 const aligned=async()=>chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el),box=el.getBoundingClientRect();return {height:box.height,canvas:c.getHeight(),panes:[0,1,2,3,4].map(i=>c.getModel().getComponent('grid',i).coordinateSystem.getRect().height),price:c.getModel().getComponent('grid',0).coordinateSystem.getRect().height,pairs:[...[...el.parentElement!.querySelectorAll('.macd-panel-header')].map((h,i)=>({h,grid:i?4:2})),...[...el.parentElement!.querySelectorAll('[data-volume-grid]')].map(h=>({h,grid:Number((h as HTMLElement).dataset.volumeGrid)}))].map(({h,grid})=>({header:h.getBoundingClientRect().bottom-box.top,grid:c.getModel().getComponent('grid',grid).coordinateSystem.getRect().y}))};});
 for(const [width,height] of [[1380,1200],[1380,900],[1280,800],[1100,768],[1000,680]]){
  await page.setViewportSize({width,height});
  await expect(async()=>{const box=(await chart.boundingBox())!;expect(box.y).toBeGreaterThan(0);expect(box.y+box.height).toBeCloseTo(height-22,0);expect(box.height).toBeGreaterThanOrEqual(350);const d=await aligned();expect(d.canvas).toBe(d.height);for(const p of d.pairs)expect(p.header).toBeLessThan(p.grid);if(height>=900){expect(d.panes[1]).toBeGreaterThanOrEqual(54);expect(d.panes[2]).toBeGreaterThanOrEqual(80);expect(d.panes[3]).toBe(d.panes[1]);expect(d.panes[4]).toBe(d.panes[2]);}if(height===1200){expect(box.height).toBeGreaterThan(700);expect(d.price).toBeGreaterThan(380);}}).toPass();
  for(const name of ['个股MACD','指数MACD']){
   const header=page.getByRole('group',{name,exact:true});await expect(header).toBeInViewport({ratio:1});
   expect(await header.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  }
  for(const header of await page.locator('[data-volume-grid]').all())expect(await header.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  if(width===1000){await page.mouse.move(5,5);await page.screenshot({path:'outputs/macd-compact-1000x680.png'});}
 }
 await page.setViewportSize({width:1380,height:900});
 await page.getByRole('button',{name:'展开市场趋势',exact:true}).click();
 await page.getByRole('button',{name:'收起市场趋势',exact:true}).click();
 await expect(async()=>{const box=(await chart.boundingBox())!;expect(box.y+box.height).toBeLessThanOrEqual(890);const d=await aligned();expect(d.canvas).toBe(d.height);for(const p of d.pairs)expect(p.header).toBeLessThan(p.grid);}).toPass();
 await page.mouse.move(5,5);await page.screenshot({path:'outputs/macd-compact-1380x900.png'});
});


test('index volume converts minute lots to ten-thousand lots and follows the linked cursor',async({page})=>{
 await setup(page);
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 const o=await option(page),v=o.series.find((s:any)=>s.name==='指数中性 / 未识别量')!;
 expect(v.xAxis).toBe(3);expect(v.data[at('10:30')]).toBe(2020/10000);
 await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption();c.dispatchAction({type:'showTip',seriesIndex:o.series.findIndex((v:any)=>v.name==='指数中性 / 未识别量'),dataIndex:o.xAxis[3].data.indexOf('10:30')});});
 const header=page.locator('[data-volume-grid="3"]');await expect(header).toContainText('上证指数成交量（万手） · 总量');await expect(header.locator('time')).toHaveText('10:30');await expect(header.locator('.volume-value')).toHaveText('0.20 万手');
 await expect(page.getByRole('group',{name:'指数MACD',exact:true}).locator('time')).toHaveText('10:30');
 const rendered=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el),models=c.getModel().getSeries(),series=models.find((s:any)=>s.name==='指数中性 / 未识别量'),data=series.getData();return {colors:[0,1,30,50].map(i=>data.getItemVisual(i,'style').fill),width:data.getItemLayout(50).width};});
 expect(v.data[0]).toBeNull();expect(rendered.colors.slice(1)).toEqual(['#000000','#000000','#000000']);expect(rendered.width).toBeGreaterThan(2);
 await expect(chart.locator('.index-volume-tooltip')).toContainText('主动买入：—');await expect(chart.locator('.index-volume-tooltip')).toContainText('中性 / 未识别：0.20 万手');
});

test('million-lot index volume uses the same ten-thousand-lot value in its header and axis',async({page})=>{
 await setup(page);
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:{collected_at:'2026-10-16T15:01:00+08:00',quotes:[{code:'sh000001',name:'上证指数'}],minute:{code:'sh000001',date:'2026-10-16',previous_close:'3600',bars:[{time:'10:30',close:'3600',volume_lots:1068276}]}}}));
 await page.reload();
 await expect.poll(async()=>(await option(page)).series.find((s:any)=>s.name==='指数中性 / 未识别量').data[at('10:30')]).toBe(106.8276);
 const formats=await page.getByLabel('分时价格及分钟成交量',{exact:true}).evaluate(async el=>{
  const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),axis=o.yAxis.find((a:any)=>a.gridIndex===3);
  c.dispatchAction({type:'showTip',seriesIndex:o.series.findIndex((s:any)=>s.name==='指数中性 / 未识别量'),dataIndex:o.xAxis[3].data.indexOf('10:30')});
  return {tick:axis.axisLabel.formatter(106.8276),pointer:axis.axisPointer.label.formatter({value:106.8276})};
 });
 expect(formats).toEqual({tick:'106.83',pointer:'106.83 万手'});
 await expect(page.locator('[data-volume-grid="3"] .volume-value')).toHaveText('106.83 万手');
 await expect(page.locator('[data-volume-grid="1"]')).toContainText('成交量（手）');
});

test('verified index sides stack red green and black; mismatched minutes stay entirely black',async({page})=>{
 await setup(page);
 const bars=minuteSlots.map((time,i)=>({time,close:String(3600+i),volume_lots:100000,...(time>='10:30'&&time<='10:34'?{volume_direction:{code:'sh000001',day:'2026-10-16',time,source:'TEST_ONLY_DIRECTION_SOURCE',unit:'lots',scope:'index_total',basis:'trade_initiator',complete:time!=='10:34',total_lots:100000,buy_lots:time==='10:31'?60001:60000,sell_lots:25000,neutral_lots:10000,unknown_lots:5000,...(time==='10:32'?{code:'sz399001'}:{}),...(time==='10:33'?{unit:'yuan'}:{})}}:{})}));
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:{collected_at:'2026-10-16T15:01:00+08:00',quotes:[{code:'sh000001',name:'上证指数'}],minute:{code:'sh000001',date:'2026-10-16',previous_close:'3600',bars}}}));
 await page.reload();
 const names=['指数买入量','指数卖出量','指数中性 / 未识别量'];
 await expect.poll(async()=>(await option(page)).series.find((s:any)=>s.name===names[0])?.data[at('10:30')]).toBe(6);
 const o=await option(page);
 expect(names.map(name=>o.series.find((s:any)=>s.name===name).data[at('10:30')])).toEqual([6,2.5,1.5]);
 for(const time of ['10:31','10:32','10:33','10:34'])expect(names.map(name=>o.series.find((s:any)=>s.name===name).data[at(time)])).toEqual([0,0,10]);
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 const visuals=await chart.evaluate(async(el,names)=>{
  const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),i=o.xAxis[3].data.indexOf('10:30');
  c.dispatchAction({type:'showTip',seriesIndex:o.series.findIndex((s:any)=>s.name===names[0]),dataIndex:i});
  return names.map(name=>{const series=c.getModel().getSeries().find((s:any)=>s.name===name);return {color:series.getData().getItemVisual(i,'style').fill,stack:series.option.stack};});
 },names);
 expect(visuals.map((v:any)=>v.color)).toEqual(['#ef6568','#36b898','#000000']);expect(new Set(visuals.map((v:any)=>v.stack)).size).toBe(1);
 const tip=chart.locator('.index-volume-tooltip');await expect(tip).toContainText('总量：10.00 万手');await expect(tip).toContainText('主动买入：6.00 万手');await expect(tip).toContainText('主动卖出：2.50 万手');await expect(tip).toContainText('中性 / 未识别：1.50 万手');
 await page.mouse.move(5,5);await page.locator('.chart-shell').screenshot({path:test.info().outputPath('index-directions-test-data.png')});
});

test('MACD period dialog recalculates both panes, persists and restores defaults without changing signals or zoom',async({page})=>{
 await setup(page);
 const stock=page.getByRole('group',{name:'个股MACD',exact:true}),index=page.getByRole('group',{name:'指数MACD',exact:true});
 const before=await option(page);
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 const marks=()=>chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),o=e.getInstanceByDom(el).getOption();return {marks:o.series[0].markPoint.data,zoom:o.dataZoom.map((z:any)=>({start:z.start,end:z.end}))};});
 const original=await marks();
 await stock.getByRole('button',{name:/MACD周期设置/}).click();
 let dialog=page.getByRole('dialog',{name:'MACD周期设置'});
 await expect(dialog.getByLabel('短周期')).toBeFocused();
 await dialog.getByLabel('短周期').fill('30');await dialog.getByRole('button',{name:'保存',exact:true}).click();
 await expect(dialog.getByRole('alert')).toContainText('短周期须小于长周期');
 await dialog.getByLabel('短周期').fill('5');await dialog.getByLabel('长周期').fill('13');await dialog.getByLabel('信号周期').fill('4');
 await page.screenshot({path:test.info().outputPath('macd-period-dialog.png')});
 await dialog.getByRole('button',{name:'保存',exact:true}).click();await expect(dialog).toHaveCount(0);
 for(const pane of [stock,index])await expect(pane.getByRole('button')).toHaveText('(5,13,4)');
 const after=await option(page);
 for(const name of ['个股 DIF','个股 DEA','个股 MACD','指数 DIF','指数 DEA','指数 MACD'])expect(after.series.find((s:any)=>s.name===name).data).not.toEqual(before.series.find((s:any)=>s.name===name).data);
 const bars=fixture.minutes.sh603002.find((r:any)=>r.day==='2026-10-16').data.bars.filter((b:any)=>b.time>='09:31');
 expect(after.series.find((s:any)=>s.name==='个股 DIF').data).toEqual(minuteMacd(bars,{fast:5,slow:13,signal:4}).map(p=>p?.dif??null));
 expect(await marks()).toEqual(original);
 expect(await page.evaluate(key=>JSON.parse(localStorage.getItem(key)!),macdParametersKey)).toEqual({fast:5,slow:13,signal:4});
 await page.reload();await expect(stock.getByRole('button')).toHaveText('(5,13,4)');
 await index.getByRole('button').click();dialog=page.getByRole('dialog',{name:'MACD周期设置'});
 await dialog.getByLabel('短周期').fill('6');await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
 await expect(index.getByRole('button')).toBeFocused();await expect(stock.getByRole('button')).toHaveText('(5,13,4)');
 await index.getByRole('button').click();await dialog.getByRole('button',{name:'恢复默认'}).click();
 await dialog.getByRole('button',{name:'保存',exact:true}).click();
 for(const pane of [stock,index])await expect(pane.getByRole('button')).toHaveText('(12,26,9)');
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(page.locator('.linked-minute').getByRole('group',{name:'个股MACD',exact:true}).getByRole('button')).toHaveText('(12,26,9)');
});

test('invalid stored MACD periods fall back to the standard periods',async({page})=>{
 await page.addInitScript(key=>localStorage.setItem(key,JSON.stringify({fast:26,slow:12,signal:9})),macdParametersKey);
 await setup(page);await expect(page.getByRole('group',{name:'个股MACD',exact:true}).getByRole('button')).toHaveText('(12,26,9)');
 expect((await option(page)).series.find((s:any)=>s.name==='个股 DIF').data.some((v:any)=>v!==null)).toBe(true);
});

test('old index caches with prices but no volume keep MACD and leave volume unavailable',async({page})=>{
 await setup(page);
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:{collected_at:'2026-10-16T15:01:00+08:00',quotes:[{code:'sh000001',name:'上证指数'}],minute:{code:'sh000001',date:'2026-10-16',previous_close:'3600',bars:minuteSlots.map((time,i)=>({time,close:String(3600+i)}))}}}));
 await page.reload();
 await expect.poll(async()=> (await option(page)).series.find((s:any)=>s.name==='指数 DIF')?.data.some((v:any)=>v!==null)).toBe(true);
 for(const name of ['指数买入量','指数卖出量','指数中性 / 未识别量'])expect((await option(page)).series.find((s:any)=>s.name===name)?.data.every((v:any)=>v===null)).toBe(true);
});
