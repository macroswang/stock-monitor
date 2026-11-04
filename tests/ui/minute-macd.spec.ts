import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {benchmarkForStock,minuteMacd,minuteSlots,macdRange} from '../../src/minuteMacd';

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
 for(const name of ['指数 MACD','指数成交量'])expect((await option(page)).series.find((s:any)=>s.name===name)?.data.every((v:any)=>v===null)).toBe(true);
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
 for(const name of ['指数 DIF','指数成交量']){const points=(await option(page)).series.find((s:any)=>s.name===name)!.data;expect(points[at('09:41')]).toBeNull();expect(points[at('10:00')]).toBeNull();expect(points[at('15:00')]).toBeNull();}
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
  if(width===1000){await page.mouse.move(5,5);await page.screenshot({path:'outputs/macd-compact-1000x680.png'});}
 }
 await page.setViewportSize({width:1380,height:900});
 await page.getByRole('button',{name:'展开市场趋势',exact:true}).click();
 await page.getByRole('button',{name:'收起市场趋势',exact:true}).click();
 await expect(async()=>{const box=(await chart.boundingBox())!;expect(box.y+box.height).toBeLessThanOrEqual(890);const d=await aligned();expect(d.canvas).toBe(d.height);for(const p of d.pairs)expect(p.header).toBeLessThan(p.grid);}).toPass();
 await page.mouse.move(5,5);await page.screenshot({path:'outputs/macd-compact-1380x900.png'});
});


test('index volume uses actual minute lots in its own pane and follows the linked cursor',async({page})=>{
 await setup(page);
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 const o=await option(page),v=o.series.find((s:any)=>s.name==='指数成交量')!;
 expect(v.xAxis).toBe(3);expect(v.data[at('10:30')]).toBe(2020);
 await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption();c.dispatchAction({type:'showTip',seriesIndex:o.series.findIndex((v:any)=>v.name==='指数成交量'),dataIndex:o.xAxis[3].data.indexOf('10:30')});});
 const header=page.locator('[data-volume-grid="3"]');await expect(header).toContainText('上证指数成交量（手） · 总量');await expect(header.locator('time')).toHaveText('10:30');await expect(header.locator('.volume-value')).toHaveText('2,020.00 手');
 await expect(page.getByRole('group',{name:'指数MACD',exact:true}).locator('time')).toHaveText('10:30');
 const rendered=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);const c=e.getInstanceByDom(el),models=c.getModel().getSeries(),series=models.find((s:any)=>s.name==='指数成交量'),data=series.getData();return {colors:[0,1,30,50].map(i=>data.getItemVisual(i,'style').fill),width:data.getItemLayout(50).width};});
 expect(v.data[0]).toBeNull();expect(rendered.colors.slice(1)).toEqual(['#ef6568','#36b898','#36b898']);expect(rendered.width).toBeGreaterThan(2);
});

test('old index caches with prices but no volume keep MACD and leave volume unavailable',async({page})=>{
 await setup(page);
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:{collected_at:'2026-10-16T15:01:00+08:00',quotes:[{code:'sh000001',name:'上证指数'}],minute:{code:'sh000001',date:'2026-10-16',previous_close:'3600',bars:minuteSlots.map((time,i)=>({time,close:String(3600+i)}))}}}));
 await page.reload();
 await expect.poll(async()=> (await option(page)).series.find((s:any)=>s.name==='指数 DIF')?.data.some((v:any)=>v!==null)).toBe(true);
 expect((await option(page)).series.find((s:any)=>s.name==='指数成交量')?.data.every((v:any)=>v===null)).toBe(true);
});
