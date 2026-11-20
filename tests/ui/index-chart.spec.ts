import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {candleMacd,minuteMacd,minuteSlots,defaultMacdParameters} from '../../src/minuteMacd';
import {weeklyBars} from '../../src/candleData';
import {indexLeadingPoints} from '../../src/indexLeading';
const codes=['sh000001','sz399001','sz399006'],names=['上证指数','深证成指','创业板指'];
const files=['market-overview-preview.json','szse-preview.json','chinext-preview.json'];
const feeds=files.map((file,i)=>{const data=JSON.parse(readFileSync('public/'+file,'utf8'));return {...data,quotes:data.quotes.filter((q:any)=>q.code===codes[i]),minute:{...data.minute,code:codes[i]}};});
const daily=JSON.parse(readFileSync('fixtures/opportunity/index-daily-20261108.json','utf8'));
daily.indices=codes.map((code,i)=>{
 const rows=[];for(let ms=Date.UTC(2014,0,1);ms<=Date.UTC(2026,10,13);ms+=86400000){const date=new Date(ms);if([0,6].includes(date.getUTCDay()))continue;const close=3000+i*4000+rows.length/100;rows.push({date:date.toISOString().slice(0,10),open:close-1,close,high:close+2,low:close-2,volume:1000000});}
 return {code,name:names[i],rows};
});
async function boot(page:Page){
 await page.clock.install({time:new Date('2026-11-15T10:00:00+08:00')});
 for(const [i,file] of files.entries())await page.route('**/'+file,route=>route.fulfill({json:feeds[i]}));
 await page.route('**/index-daily-20261108.json*',route=>route.fulfill({json:daily}));
 await page.goto('/');await expect(page.locator('.market-header .index-sparkline')).toHaveCount(3);
 await expect(page.locator('.stock.selected')).toHaveCount(1);
}
async function chartState(page:Page){
 return page.locator('.index-detail .chart').evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),labels=o.xAxis[0].data,z=o.dataZoom[0];
  const lo=Math.round((labels.length-1)*z.start/100),hi=Math.round((labels.length-1)*z.end/100);
  return {visible:hi-lo+1,labels,first:o.series[0].data[0],last:o.series[0].data.at(-1),marks:o.series[0].markPoint.data,names:o.series.map((s:any)=>s.name),mas:o.series.filter((s:any)=>/^MA\d+$/.test(s.name)).map((s:any)=>s.data.at(-1)),macd:o.series.filter((s:any)=>/^指数 (MACD|DIF|DEA)$/.test(s.name)).map((s:any)=>({name:s.name,data:s.data,x:s.xAxisIndex,y:s.yAxisIndex})),zoom:o.dataZoom[0].xAxisIndex,grids:o.grid.length};
 });
}
test('blue and yellow index lines have plain reminders, aligned minutes and no effect on stock charts or MACD',async({page},info)=>{
 await boot(page);
 const paired=feeds.map(feed=>({...feed,leading:{code:feed.minute.code,date:feed.minute.date,previous_close:feed.minute.previous_close,source:'eastmoney',timestamp:feed.collected_at,cached_at:feed.collected_at,
  bars:feed.minute.bars.map((bar:any,i:number)=>({time:bar.time,close:bar.close,value:String(Number(bar.close)*(.98+i*.00001))}))}}));
 for(const [i,file] of files.entries()){await page.unroute('**/'+file);await page.route('**/'+file,route=>route.fulfill({json:paired[i]}));}
 await page.clock.fastForward(15001);
 const now=new Date('2026-11-15T10:01:00+08:00').getTime();
 for(const [i,feed] of paired.entries()){
  await page.getByRole('button',{name:'查看'+names[i]+'行情',exact:true}).click();await page.getByRole('button',{name:'分时',exact:true}).click();
  const read=()=>page.locator('.index-detail .chart').evaluate(async el=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption();
   const line=o.series.find((s:any)=>s.name==='黄线');
   c.dispatchAction({type:'showTip',seriesIndex:o.series.findIndex((s:any)=>s.name==='蓝线'),dataIndex:2});
   return {data:line?.data,color:line?.lineStyle.color,blue:o.series.find((s:any)=>s.name==='蓝线')?.lineStyle.color,min:o.yAxis[0].min,legend:o.legend[0].data,connect:line?.connectNulls};
  });
  const expected=indexLeadingPoints(feed,codes[i],now);
  await expect.poll(async()=>(await read()).data?.filter((v:any)=>v!==null)).toEqual(expected.map(point=>point.value));
  const state=await read();expect(state.legend).toEqual(['蓝线','黄线']);expect(state.color).toBe('#e9b949');expect(state.blue).toBe('#8cbcff');expect(state.connect).toBe(false);
  expect(state.min).toBeLessThanOrEqual(Math.min(...expected.map(point=>point.value)));
  await expect(page.getByLabel('指数分时线说明')).toContainText('黄线在蓝线上方：通常中小盘股相对强');
  await expect(page.getByLabel('指数分时线说明')).toContainText('黄线在蓝线下方：通常权重股相对强');
  await expect(page.locator('.index-detail .minute-tooltip')).toContainText('黄线：');
  expect((await chartState(page)).macd.find((s:any)=>s.name==='指数 DIF')!.data).toEqual(minuteMacd(feed.minute.bars).map(point=>point?.dif??null));
  const changed=(patch:object)=>({...feed,leading:{...feed.leading,...patch}});
  for(const patch of [{code:codes[(i+1)%3]},{date:'2026-11-12'},{previous_close:'1'},{timestamp:'2026-11-16T09:30:00+08:00'},{cached_at:'2026-11-12T15:00:00+08:00'}])expect(indexLeadingPoints(changed(patch),codes[i],now)).toEqual([]);
  expect(indexLeadingPoints(changed({cached_at:'2026-11-15T09:00:00+08:00'}),codes[i],now)).toEqual(expected);
  const until=feed.minute.date+'T10:01:30+08:00';
  expect(indexLeadingPoints(changed({timestamp:until}),codes[i],now).every(point=>point.time<='10:01')).toBe(true);
  expect(indexLeadingPoints(changed({bars:[{...feed.leading.bars[0],close:'1'}]}),codes[i],now)).toEqual([]);
 }
 await page.screenshot({path:info.outputPath('index-two-lines.png'),fullPage:true});
 await page.getByRole('button',{name:'日K',exact:true}).click();await expect(page.getByLabel('指数分时线说明')).toHaveCount(0);
 await page.getByRole('button',{name:'返回个股',exact:true}).click();
 await expect(page.getByRole('button',{name:'同步券商成交',exact:true})).toBeVisible();
 await expect(page.getByLabel('指数分时线说明')).toHaveCount(0);
});
test('three header indices share the right chart, all views and zoom, and return to the same stock without trading controls',async({page},info)=>{
 await boot(page);const stock=await page.locator('.stock.selected .watch-stock-title strong').innerText();
 for(const [i,name] of names.entries()){
  await page.getByRole('button',{name:'查看'+name+'行情',exact:true}).click();await expect(page.locator('.detail h2')).toContainText(name);
  await page.getByRole('button',{name:'分时',exact:true}).click();
  await expect.poll(async()=>(await chartState(page)).last).toBe(Number(feeds[i].minute.bars.at(-1).close));
  expect((await chartState(page)).marks).toEqual([]);
  let state=await chartState(page);expect(state.grids).toBe(3);expect(state.zoom).toEqual([0,1,2]);
  expect(state.macd).toHaveLength(3);expect(state.macd.every((series:any)=>series.x===2&&series.y===3)).toBe(true);
  expect(state.macd.find((series:any)=>series.name==='指数 DIF')!.data).toEqual(minuteMacd(feeds[i].minute.bars).map(point=>point?.dif??null));
  await expect(page.getByRole('group',{name:'指数MACD',exact:true})).toContainText('1分钟');
  await expect(page.getByRole('button',{name:name+' MACD周期设置',exact:true})).toHaveText(`(${defaultMacdParameters.fast},${defaultMacdParameters.slow},${defaultMacdParameters.signal})`);
  if(i===0)await page.screenshot({path:info.outputPath('index-minute-macd.png'),fullPage:true});
  await expect(page.getByRole('group',{name:'分时显示选项'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'同步券商成交',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'日K',exact:true}).click();
  await expect.poll(async()=>(await chartState(page)).visible).toBe(120);
  const last=daily.indices[i].rows.at(-1);expect((await chartState(page)).last).toEqual([last.open,last.close,last.low,last.high]);
  state=await chartState(page);const loaded=daily.indices[i].rows.filter((row:any)=>row.date>=state.labels[0]);
  expect(state.macd.every((series:any)=>series.x===2&&series.y===2)).toBe(true);
  expect(state.macd.find((series:any)=>series.name==='指数 MACD')!.data).toEqual(candleMacd(loaded).map(point=>point?.histogram??null));
  await expect(page.getByRole('group',{name:'指数MACD',exact:true})).toContainText('1日');
  const chart=page.locator('.index-detail .chart');await chart.focus();await chart.press('ArrowUp');await expect.poll(async()=>(await chartState(page)).visible).toBe(90);
  expect((await chartState(page)).macd).toEqual(state.macd);
  await page.getByRole('button',{name:'周K',exact:true}).click();await expect.poll(async()=>(await chartState(page)).visible).toBe(250);
  expect((await chartState(page)).mas.every((n:unknown)=>typeof n==='number')).toBe(true);
  state=await chartState(page);const weeks=weeklyBars(daily.indices[i].rows.filter((row:any)=>row.date>=state.labels[0]));
  const expected=candleMacd(weeks).at(-1)!;
  for(const [suffix,value] of [['MACD',expected.histogram],['DIF',expected.dif],['DEA',expected.dea]] as const)expect(state.macd.find((series:any)=>series.name==='指数 '+suffix)!.data.at(-1)).toBeCloseTo(value,9);
  await expect(page.getByRole('group',{name:'指数MACD',exact:true})).toContainText('1周');
  const hover=await chart.evaluate(async el=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),idx=o.xAxis[0].data.length-7,date=o.xAxis[0].data[idx];
   c.dispatchAction({type:'showTip',seriesIndex:o.series.findIndex((series:any)=>series.name==='指数 DIF'),dataIndex:idx});
   return {date,pixels:[0,1,2].map(xAxisIndex=>c.convertToPixel({xAxisIndex},date))};
  });
  await expect(page.getByRole('group',{name:'指数MACD',exact:true}).locator('time')).toHaveText(hover.date);
  for(const x of hover.pixels)expect(x).toBeCloseTo(hover.pixels[0],5);
 }
 await page.screenshot({path:info.outputPath('index-weekly.png'),fullPage:true});
 await page.getByRole('button',{name:'分时',exact:true}).click();await page.locator('.stock').filter({hasText:stock}).click();
 await expect(page.locator('.detail h2')).toContainText(stock);await expect(page.locator('.index-detail')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'同步券商成交',exact:true})).toBeVisible();
});
test('late history cannot cross index scopes; hidden index charts stop history refreshes',async({page})=>{
 await boot(page);let release!:()=>void,reads=0;
 const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.unroute('**/index-daily-20261108.json*');
 await page.route('**/index-daily-20261108.json*',async route=>{const first=++reads===1;if(first)await gate;await route.fulfill({json:daily});});
 await page.getByRole('button',{name:'查看上证指数行情',exact:true}).click();await page.getByRole('button',{name:'日K',exact:true}).click();await expect.poll(()=>reads).toBe(1);
 await page.getByRole('button',{name:'查看深证成指行情',exact:true}).click();await expect.poll(async()=>(await chartState(page)).last?.[1]).toBe(daily.indices[1].rows.at(-1).close);
 release();await page.waitForLoadState('networkidle');await expect(page.locator('.detail h2')).toContainText('深证成指');expect((await chartState(page)).last[1]).toBe(daily.indices[1].rows.at(-1).close);
 await page.getByRole('button',{name:'股票池',exact:true}).click();const before=reads;await page.clock.fastForward(65000);expect(reads).toBe(before);
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await expect(page.locator('.detail h2')).toContainText('深证成指');await expect.poll(()=>reads).toBeGreaterThan(before);
});

test('index minute MACD waits for the reached cache minute and retains edited periods after reload',async({page})=>{
 await boot(page);const feed=structuredClone(feeds[0]),day=feed.minute.date,stamp=day+'T10:30:20+08:00';
 feed.minute.bars=feed.minute.bars.filter((bar:any)=>bar.time<='10:31');
 const update=(clock:string,time:string)=>{feed.collected_at=clock;feed.minute.cached_at=clock;const quote=feed.quotes[0];quote.timestamp=clock;quote.price=feed.minute.bars.find((bar:any)=>bar.time===time).close;quote.change=String(Number(quote.price)-Number(quote.previous_close));quote.percent=String((Number(quote.price)/Number(quote.previous_close)-1)*100);};
 update(stamp,'10:30');await page.clock.setFixedTime(new Date(stamp));
 await page.unroute('**/'+files[0]);await page.route('**/'+files[0],route=>route.fulfill({json:feed}));await page.reload();
 await page.getByRole('button',{name:'查看上证指数行情',exact:true}).click();
 const dif=async()=>(await chartState(page)).macd.find((series:any)=>series.name==='指数 DIF')!.data;
 await expect.poll(async()=>(await dif())[minuteSlots.indexOf('10:30')]).not.toBeNull();
 const before=await dif();expect(before[minuteSlots.indexOf('10:31')]).toBeNull();
 await page.clock.setFixedTime(new Date(day+'T10:31:20+08:00'));await page.clock.fastForward(60000);expect((await dif())[minuteSlots.indexOf('10:31')]).toBeNull();
 update(day+'T10:31:10+08:00','10:31');await page.clock.fastForward(15000);
 await expect.poll(async()=>(await dif())[minuteSlots.indexOf('10:31')]).not.toBeNull();
 expect((await dif()).slice(0,minuteSlots.indexOf('10:31'))).toEqual(before.slice(0,minuteSlots.indexOf('10:31')));
 await page.getByRole('button',{name:'上证指数 MACD周期设置',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'MACD周期设置'});
 await dialog.getByLabel('短周期',{exact:true}).fill('2');await dialog.getByLabel('长周期',{exact:true}).fill('4');await dialog.getByLabel('信号周期',{exact:true}).fill('3');await dialog.getByRole('button',{name:'保存',exact:true}).click();
 expect(await dif()).toEqual(minuteMacd(feed.minute.bars,{fast:2,slow:4,signal:3}).map(point=>point?.dif??null));
 await page.reload();await page.getByRole('button',{name:'查看上证指数行情',exact:true}).click();
 await expect(page.getByRole('button',{name:'上证指数 MACD周期设置',exact:true})).toHaveText('(2,4,3)');
 expect(await dif()).toEqual(minuteMacd(feed.minute.bars,{fast:2,slow:4,signal:3}).map(point=>point?.dif??null));
});
