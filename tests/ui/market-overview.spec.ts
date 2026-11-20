import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {indexSparkline} from '../../src/indexSparkline';

const files=['market-overview-preview.json','szse-preview.json','chinext-preview.json'];
const codes=['sh000001','sz399001','sz399006'],names=['上证指数','深证成指','创业板指'];
const feeds=files.map((file,i)=>{const data=JSON.parse(readFileSync('public/'+file,'utf8'));return {...data,quotes:data.quotes.filter((q:any)=>q.code===codes[i]),minute:{...data.minute,code:codes[i]}};});
const now=Date.parse('2026-11-15T10:00:00+08:00');
const copy=(v:any)=>structuredClone(v);

test('all three miniatures use their own confirmed index cache, a zero baseline and truthful colour',()=>{
 for(const [i,feed] of feeds.entries()){
  const before=copy(feed),spark=indexSparkline(feed,codes[i],now)!;expect(spark).not.toBeNull();expect(spark.day).toBe(feed.minute.date);
  expect(spark.points[0].value).toBe(Number(feed.minute.bars[0].close));expect(spark.until).toBe('15:00');expect(spark.baseline).toBe(20);
  const last=Number(feed.minute.bars.at(-1).close)-Number(feed.minute.previous_close);expect(spark.color).toBe(last>0?'#ef6568':last<0?'#36b898':'#8c9db6');
  expect(spark.line).not.toContain('NaN');expect(spark.area).toContain(',20 Z');expect(feed).toEqual(before);
 }
});

test('missing, inconsistent, duplicate, cross-index or future-cached data never draws a fake sparkline',()=>{
 const feed=feeds[0];
 const variants=[{...feed,minute:null},{...feed,minute:{...feed.minute,code:'sz399001'}},{...feed,minute:{...feed.minute,date:'2026-10-29'}},{...feed,minute:{...feed.minute,previous_close:'1'}},{...feed,minute:{...feed.minute,bars:[]}},{...feed,minute:{...feed.minute,bars:[feed.minute.bars[0],feed.minute.bars[0]]}},{...feed,minute:{...feed.minute,cached_at:'2026-11-16T09:00:00+08:00'}},{...feed,quotes:[{...feed.quotes[0],price:'1'}]}];
 for(const value of variants)expect(indexSparkline(value,codes[0],now)).toBeNull();
});

test('pending minute stays hidden until reached, sparse data breaks the line and lunch remains continuous',()=>{
 const feed=copy(feeds[0]),stamp='2026-10-30T10:30:20+08:00';feed.quotes[0].timestamp=stamp;feed.collected_at=stamp;
 feed.minute.cached_at=stamp;feed.minute.bars=feed.minute.bars.filter((b:any)=>b.time<='10:31');
 const first=indexSparkline(feed,codes[0],Date.parse(stamp))!;expect(first.until).toBe('10:30');expect(first.points.some(p=>p.time==='10:31')).toBe(false);
 expect(indexSparkline(feed,codes[0],Date.parse(stamp)+50000)!.until).toBe('10:30');
 feed.minute.cached_at='2026-10-30T10:31:10+08:00';expect(indexSparkline(feed,codes[0],Date.parse(stamp)+50000)!.until).toBe('10:31');
 feed.minute.cached_at=stamp;
 feed.minute.bars=feed.minute.bars.filter((b:any)=>b.time!=='10:00');expect(indexSparkline(feed,codes[0],Date.parse(stamp))!.line.split('M')).toHaveLength(3);
 const whole=indexSparkline(feeds[0],codes[0],now)!;expect(whole.line.split('M')).toHaveLength(2);expect(whole.points.some(p=>p.time==='13:00')).toBe(false);
});

test('top index cells contain three independent filled miniature charts and no market-trend block',async({page})=>{
 await page.clock.install({time:new Date(now)});await page.goto('/');
 const header=page.locator('.market-header');await expect(header.locator('.overview-index')).toHaveCount(3);
 for(const name of names){const mini=header.getByRole('img',{name:name+'当日缩略分时',exact:true});await expect(mini).toBeVisible();await expect(mini.locator('.index-spark-area')).toHaveAttribute('fill',/url\(#/);}
 await expect(page.locator('.home-overview')).toHaveCount(0);await expect(page.getByText('市场趋势',{exact:true})).toHaveCount(0);
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:980});
  await expect(async()=>{for(const mini of await header.locator('.index-sparkline').all()){const box=(await mini.boundingBox())!;expect(box.width).toBeGreaterThan(15);expect(box.height).toBe(40);}expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);}).toPass();
  await page.screenshot({path:`outputs/index-miniatures-${width}.png`,fullPage:true});
 }
});

test('one missing index leaves the other two miniatures intact and transport failures are labelled cache until recovery',async({page})=>{
 await page.clock.install({time:new Date(now)});await page.goto('/');const header=page.locator('.market-header'),mini=header.getByRole('img',{name:'深证成指当日缩略分时',exact:true});
 await expect(header.locator('.index-sparkline')).toHaveCount(3);
 await page.route('**/szse-preview.json',r=>r.abort());await page.clock.fastForward(15500);
 await expect(mini.locator('title')).toContainText('缓存');await expect(header.locator('.index-sparkline')).toHaveCount(3);
 await page.unroute('**/szse-preview.json');await page.route('**/szse-preview.json',r=>r.fulfill({json:{quotes:[],minute:null}}));await page.clock.fastForward(15500);
 await expect(header.locator('.index-sparkline')).toHaveCount(2);await expect(header.getByText('暂无分时',{exact:true})).toHaveCount(1);
 await page.unroute('**/szse-preview.json');await page.clock.fastForward(15500);await expect(header.locator('.index-sparkline')).toHaveCount(3);
});

test('header cache reads share one 15-second cadence and stop when leaving self-watch',async({page})=>{
 await page.clock.install({time:new Date(now)});const counts=[0,0,0];
 for(const [i,file] of files.entries())await page.route('**/'+file,r=>{counts[i]++;return r.fulfill({json:feeds[i]});});
 await page.goto('/');await expect(page.locator('.market-header .index-sparkline')).toHaveCount(3);await page.waitForLoadState('networkidle');const before=[...counts];
 await page.clock.fastForward(15500);await expect.poll(()=>counts.map((n,i)=>n-before[i])).toEqual([1,1,1]);
 await page.getByRole('button',{name:'数据管理',exact:true}).click();const left=[...counts];await page.clock.fastForward(31000);expect(counts).toEqual(left);
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await expect(page.locator('.market-header .index-sparkline')).toHaveCount(3);expect(counts.map((n,i)=>n-left[i])).toEqual([1,1,1]);
});

test('stock price and indicator panes retain their existing compact desktop geometry',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-overview-collapsed','true'));await page.goto('/');const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 // Exact geometry independently verified against HEAD before the index-chart feature.
 const baseline=[{width:1380,height:980,y:164,chart:801,grids:[255,132,96,80,96]},{width:1000,height:680,y:164,chart:490,grids:[166,82,35,30,35]}];
 for(const b of baseline){await page.setViewportSize({width:b.width,height:b.height});await expect(async()=>{
  const box=(await chart.boundingBox())!;expect(box.y).toBe(b.y);expect(box.height).toBe(b.chart);
  const grids=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el);return [0,1,2,3,4].map(i=>c.getModel().getComponent('grid',i).coordinateSystem.getRect().height);});
  expect(grids).toEqual(b.grids);
 }).toPass();}
});
