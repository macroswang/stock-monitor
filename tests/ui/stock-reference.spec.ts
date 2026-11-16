import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {stockTraits} from '../../src/stockTraits';
import {exchangeCalendar} from '../../src/exchangeCalendar';
import type {Daily} from '../../src/models';
const now='2026-11-16T14:30:00+08:00';
const days:string[]=[];
for(let t=Date.parse('2026-11-13T00:00:00Z');days.length<21;t-=86400000){const day=new Date(t).toISOString().slice(0,10);if(exchangeCalendar.tradingDay(day))days.unshift(day);}
const bars:Daily[]=days.map((date,i)=>({date,open:String(10+i),close:String(10+i),high:String(11+i),low:String(9+i),volume:String(100+i)}));
const profiles:any={
 sh688218:{code:'sh688218',data:{code:'sh688218',industry:['机械设备','机器人','工业机器人'],boards:[{name:'机械设备'},{name:'江苏板块'}],concepts:[{name:'人形机器人'},{name:'低空经济'},{name:'新能源车'},{name:'华为汽车'}],attributes:[{name:'小盘股'}],collected_at:'2026-11-16T14:00:00+08:00'},themes:[{name:'具身智能',kind:'研究题材'}],running:false,error:''},
 sz300364:{code:'sz300364',data:{code:'sz300364',industry:['传媒','数字媒体'],boards:[{name:'北京板块'}],concepts:[{name:'AI语料'}],attributes:[],collected_at:'2026-11-16T14:00:00+08:00'},themes:[],running:false,error:''},
};
async function boot(page:Page,delay=false){
 await page.clock.setFixedTime(new Date(now));
 const fixture=JSON.parse(readFileSync('public/preview.json','utf8'));
 fixture.snapshot.watch=[['sh688218','江苏北人'],['sz300364','中文在线']].map(([code,name])=>({code,name,enabled:1,health:'测试行情',candidates:[]}));
 for(const code of ['sh688218','sz300364']){
  fixture.minutes[code]=[{day:'2026-11-13',data:{bars:[]}},{day:'2026-11-16',data:{bars:[]}}];fixture.daily[code]=bars;
  fixture.history[code]={code,daily:bars,days:[],events:[],source:null,minute_days:[]};
 }
 await page.route('**/preview.json',r=>r.fulfill({json:fixture}));
 let calls=0;
 await page.route('**/stock-profiles-preview.json*',async r=>{
  if(delay&&calls++===0)await new Promise(resolve=>setTimeout(resolve,400));
  await r.fulfill({json:profiles});
 });
 await page.goto('/');
 await expect(page.getByLabel('江苏北人个股资料',{exact:true})).toBeVisible();
}

test('compact header shows categories and expands full references without source/date text',async({page})=>{
 await boot(page);
 const summary=page.getByLabel('江苏北人个股资料',{exact:true});
 await expect(summary).toContainText('工业机器人');await expect(summary).toContainText('人形机器人');
 await expect(summary).toContainText('具身智能');await expect(summary).toContainText('小盘股');
 await summary.click();
 const details=page.getByRole('region',{name:'江苏北人资料详情'});
 await expect(details).toBeVisible();await expect(details).toContainText('华为汽车');
 await expect(details).toContainText('机械设备 / 机器人 / 工业机器人');
 await expect(details).toContainText('上涨天数');await expect(details).toContainText('20/20');
 await expect(details.locator('.stock-traits>span').filter({hasText:'成交量比'})).toBeInViewport();
 await expect(details.locator('.stock-reference-method')).toBeInViewport();
 await expect(details).not.toContainText(/来源|日期|2026-/);
 await page.screenshot({path:'docs/stock-reference-20261116/header-expanded.png',fullPage:true});
 for(const tab of ['日K','周K','分时']){
  await page.getByRole('button',{name:tab,exact:true}).click();await expect(summary).toBeVisible();
  await expect(page.locator('summary').filter({hasText:'运行说明'})).toHaveCount(0);
  await expect(page.locator('.workspace>footer')).toHaveCount(0);
  await expect(page.getByText('观量 · 数据留在本机，交易由你决定',{exact:true})).toHaveCount(0);
 }
});

test('late profile response cannot populate another stock and narrow layout does not overflow',async({page})=>{
 await boot(page,true);
 await page.locator('.stock').filter({hasText:'中文在线'}).click();
 const summary=page.getByLabel('中文在线个股资料',{exact:true});
 await expect(summary).toContainText('数字媒体');await page.waitForTimeout(500);
 await expect(summary).not.toContainText('工业机器人');await expect(summary).toContainText('暂无匹配');
 await page.setViewportSize({width:1000,height:900});await summary.click();
 await expect(page.getByRole('region',{name:'中文在线资料详情'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
 await page.screenshot({path:'docs/stock-reference-20261116/header-narrow.png',fullPage:true});
});

test('missing profile stays unknown instead of inventing sectors',async({page})=>{
 await boot(page);
 await page.unroute('**/stock-profiles-preview.json*');
 await page.route('**/stock-profiles-preview.json*',r=>r.fulfill({json:{}}));
 await page.locator('.stock').filter({hasText:'中文在线'}).click();
 const summary=page.getByLabel('中文在线个股资料',{exact:true});
 await expect(summary).toContainText('待补充');await expect(summary).not.toContainText('工业机器人');
});

test('stock traits are exact complete-bar statistics with a trailing volume baseline',()=>{
 const result=stockTraits(bars,'2026-11-16',Date.parse(now))!;
 expect(result.amplitude).toBeCloseTo(bars.slice(0,20).reduce((s,b)=>s+2/+b.close*100,0)/20,10);
 expect(result.change).toBe(200);expect(result.up).toBe(20);expect(result.volumeRatio).toBeCloseTo(120/109.5,10);
});

test('stock traits exclude future, unclosed and historically out-of-window bars',()=>{
 const baseline=stockTraits(bars,'2026-11-16',Date.parse(now));
 const extra=[{...bars[0],date:'2026-11-17',close:'1000',high:'1100'},{...bars[0],date:'2026-11-16'}];
 expect(stockTraits([...bars,...extra],'2026-11-16',Date.parse(now))).toEqual(baseline);
 expect(stockTraits(bars,bars[19].date,Date.parse(now))).toBeNull();
 expect(stockTraits(bars.map((b,i)=>i===20?{...b,provisional:true}:b),'2026-11-16',Date.parse(now))).toBeNull();
 expect(stockTraits(bars.map((b,i)=>i===20?{...b,cached_at:'2026-11-17T00:00:00+08:00'}:b),'2026-11-16',Date.parse(now))).toBeNull();
});


test('toolbar remains one horizontal row at wide and minimum desktop widths',async({page})=>{
 await boot(page);
 const toolbar=page.locator('.stock-reference-toolbar');
 for(const width of [1800,1380,1150,1000]){
  await page.setViewportSize({width,height:900});
  await expect.poll(async()=>toolbar.evaluate(el=>getComputedStyle(el).flexWrap)).toBe('nowrap');
  const bounds=await toolbar.evaluate(el=>{
   const a=el.querySelector('.tabs')!.getBoundingClientRect(),b=el.querySelector('.stock-reference')!.getBoundingClientRect(),c=el.querySelector('.chart-date-actions')!.getBoundingClientRect();
   return {centerA:(a.top+a.bottom)/2,centerB:(b.top+b.bottom)/2,centerC:(c.top+c.bottom)/2,topA:a.top,topB:b.top,bottomA:a.bottom,bottomB:b.bottom,heightA:a.height,heightB:b.height,ordered:a.right<=b.left+1&&b.right<=c.left+1};
  });
  expect(Math.abs(bounds.heightA-bounds.heightB)).toBeLessThan(.5);
  expect(Math.abs(bounds.topA-bounds.topB)).toBeLessThan(.5);
  expect(Math.abs(bounds.bottomA-bounds.bottomB)).toBeLessThan(.5);
  expect(Math.abs(bounds.centerA-bounds.centerB)).toBeLessThan(2);
  expect(Math.abs(bounds.centerB-bounds.centerC)).toBeLessThan(2);expect(bounds.ordered).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
 }
 await page.screenshot({path:'docs/production-0.6.136/toolbar-minimum.png',fullPage:true});
});

test('changing historical range clears later themes before its response arrives',async({page})=>{
 await boot(page);
 await page.unroute('**/stock-profiles-preview.json*');
 await page.route('**/stock-profiles-preview.json*',async route=>{
  const data=structuredClone(profiles) as any;
  const past=new URL(route.request().url()).searchParams.get('day')==='2026-11-13';
  data.sh688218.themes=[{name:past?'历史题材':'后来题材',kind:'研究题材'}];
  data.sh688218.theme_published_at=past?'2026-11-13T14:00:00+08:00':'2026-11-16T14:00:00+08:00';
  if(past)await new Promise(resolve=>setTimeout(resolve,300));
  await route.fulfill({json:data});
 });
 const summary=page.getByLabel('江苏北人个股资料',{exact:true});
 await page.getByLabel('交易日期',{exact:true}).selectOption('2026-11-13');
 await expect(summary).not.toContainText('后来题材');await expect(summary).toContainText('历史题材');
 await page.getByLabel('交易日期',{exact:true}).selectOption('2026-11-16');await expect(summary).toContainText('后来题材');
});

test('market close does not promote an old intraday snapshot to a completed daily bar',()=>{
 const intraday={...bars[20],date:'2026-11-16',cached_at:'2026-11-16T14:00:00+08:00',quote_time:'2026-11-16T14:00:00+08:00'};
 const afterClose=Date.parse('2026-11-16T15:30:00+08:00');
 expect(stockTraits([...bars,intraday],'2026-11-16',afterClose)).toBeNull();
 const settled={...intraday,cached_at:'2026-11-16T15:20:00+08:00',quote_time:'2026-11-16T15:00:00+08:00'};
 expect(stockTraits([...bars,settled],'2026-11-16',afterClose)).not.toBeNull();
 const pastPartial=bars.map((b,i)=>i===20?{...b,cached_at:b.date+'T14:00:00+08:00'}:b);
 expect(stockTraits(pastPartial,'2026-11-16',Date.parse(now))).toBeNull();
});

test('invalid, conflicting or mixed-unit rows do not produce misleading statistics',()=>{
 const last=bars.at(-1)!;
 expect(stockTraits([...bars,{...last,close:'99',high:'100'}],'2026-11-16',Date.parse(now))).toBeNull();
 expect(stockTraits(bars.map((b,i)=>i===20?{...b,high:'0'}:b),'2026-11-16',Date.parse(now))).toBeNull();
 const mixed=bars.map((b,i)=>({...b,volume_unit:i===20?'hands':'shares'}));
 expect(stockTraits(mixed,'2026-11-16',Date.parse(now))!.volumeRatio).toBeNull();
 const missingUnits=bars.map((b,i)=>({...b,source:i===20?'sina':'tencent'}));
 expect(stockTraits(missingUnits,'2026-11-16',Date.parse(now))!.volumeRatio).toBeNull();
 const weekend={...last,date:'2026-11-14',close:'999',high:'1000'};
 expect(stockTraits([...bars,weekend],'2026-11-16',Date.parse(now))).toEqual(stockTraits(bars,'2026-11-16',Date.parse(now)));
 expect(stockTraits(bars,'2026-02-30',Date.parse(now))).toBeNull();
});

test('Retina control borders stay equal in minute, daily and weekly views',async({browser})=>{
 const context=await browser.newContext({baseURL:'http://127.0.0.1:1420',deviceScaleFactor:2,viewport:{width:1380,height:900}});
 try{
  const page=await context.newPage();await boot(page);
  for(const tab of ['分时','日K','周K']){
   await page.getByRole('button',{name:tab,exact:true}).click();
   const bounds=await page.locator('.stock-reference-toolbar').evaluate(el=>{
    const a=el.querySelector('.tabs')!.getBoundingClientRect(),b=el.querySelector('.stock-reference>summary')!.getBoundingClientRect();
    return {top:a.top-b.top,bottom:a.bottom-b.bottom,height:a.height-b.height,dpr:devicePixelRatio};
   });
   expect(bounds.dpr).toBe(2);expect(Math.abs(bounds.top)).toBeLessThan(.5);expect(Math.abs(bounds.bottom)).toBeLessThan(.5);expect(Math.abs(bounds.height)).toBeLessThan(.5);
  }
  await page.screenshot({path:'docs/production-0.6.137/retina-aligned.png',fullPage:true});
 }finally{await context.close();}
});


test('reference panel uses one third of the available width and sits against right actions',async({page})=>{
 await boot(page);
 for(const tab of ['分时','日K','周K']){
  await page.getByRole('button',{name:tab,exact:true}).click();
  await page.setViewportSize({width:1800,height:900});
  const layout=await page.locator('.stock-reference-toolbar').evaluate(el=>{
   const a=el.querySelector('.tabs')!.getBoundingClientRect(),b=el.querySelector('.stock-reference')!.getBoundingClientRect(),c=el.querySelector('.chart-date-actions')?.getBoundingClientRect();
   const gap=parseFloat(getComputedStyle(el).columnGap);
   return {blank:b.left-a.right-2*gap,width:b.width,rightGap:c?c.left-b.right:el.getBoundingClientRect().right-parseFloat(getComputedStyle(el).paddingRight)-b.right,gap:c?gap:0,valueSize:getComputedStyle(el.querySelector('.stock-reference summary b')!).fontSize,labelSize:getComputedStyle(el.querySelector('.stock-reference summary i')!).fontSize};
  });
  expect(Math.abs(layout.blank-2*layout.width)).toBeLessThan(1);
  expect(Math.abs(layout.rightGap-layout.gap)).toBeLessThan(1);
  expect(layout.valueSize).toBe('7px');expect(layout.labelSize).toBe('8px');
 }
 await page.screenshot({path:'docs/production-0.6.140/toolbar-right-third.png',fullPage:true});
});
