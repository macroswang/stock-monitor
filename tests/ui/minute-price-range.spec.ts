import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {intradayPriceScale} from '../../src/priceLimits';
import {reachedPriceRange} from '../../src/pricePresentation';

test('previous close is centered and the farther extreme fits without coarse rounding',()=>{
 for(const [base,prices,min,max] of [[31.17,[31.55,29.31],29.31,33.03],[15.23,[15.30,14.39],14.39,16.07],[10,[10.18,10.63],9.37,10.63],[10,[9.91,10.02],9.9,10.1]] as const){
  const range=intradayPriceScale(base,[...prices]);
  expect(range.min).toBeCloseTo(min);expect(range.max).toBeCloseTo(max);
  expect((range.min!+range.max!)/2).toBeCloseTo(base);
  expect(range.interval!*8).toBeCloseTo(range.max!-range.min!);
 }
});

test('new extrema expand both sides; flat, invalid and no-limit sessions remain usable',()=>{
 const early=intradayPriceScale(10,[10]),late=intradayPriceScale(10,[10,10.37]);
 expect(early).toEqual({min:9.9,max:10.1,interval:.025});
 expect(late.min).toBeCloseTo(9.63);expect(late.max).toBeCloseTo(10.37);
 for(const base of [undefined,0,-1,Infinity,NaN])expect(intradayPriceScale(base,[10])).toEqual({});
 expect(intradayPriceScale(10,[NaN,Infinity,0,-2])).toEqual({});
 expect(intradayPriceScale(10,[12,NaN,-2])).toEqual(intradayPriceScale(10,[12]));
 const ipo=intradayPriceScale(10,[35]);expect(ipo.min).toBeGreaterThan(0);expect(ipo.max).toBeGreaterThanOrEqual(35);
});

function fixture(){
 const f=JSON.parse(readFileSync('public/preview.json','utf8'));
 f.minutes.sh603002[0].data={...f.minutes.sh603002[0].data,previous_close:'10',cached_at:'2026-10-16T15:00:00+08:00',bars:[10,9.8,10.3,10.1].map((v,i)=>({time:`09:3${i}`,close:String(v),average:'10',volume:10000,complete:true}))};
 return f;
}
async function inspect(page:Page){
 return page.getByLabel('分时价格及分钟成交量',{exact:true}).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),m=c.getModel(),o=c.getOption(),left=m.getComponent('yAxis',0),right=m.getComponent('yAxis',2),rect=m.getComponent('grid',0).coordinateSystem.getRect();
  const ticks=left.axis.scale.getTicks().map((t:any)=>t.value);
  return {left:left.axis.scale.getExtent(),right:right.axis.scale.getExtent(),ticks,rightTicks:right.axis.scale.getTicks().map((t:any)=>t.value),leftText:ticks.map((v:number)=>o.yAxis[0].axisLabel.formatter(v)),rightText:ticks.map((v:number)=>o.yAxis[2].axisLabel.formatter(v)),centerY:c.convertToPixel({yAxisIndex:0},10),midY:rect.y+rect.height/2,baseline:o.series[0].markLine.data.find((r:any)=>r.name==='昨收')?.yAxis,color:o.series[0].lineStyle.color,width:o.series[0].lineStyle.width,averageWidth:o.series.find((s:any)=>s.name==='均价')?.lineStyle.width,price:o.series[0].data,legend:o.legend[0].data};
 });
}

test('main and linked minutes align price/percent ticks at yesterday close and retain the blue curve',async({page},info)=>{
 await page.route('**/preview.json',r=>r.fulfill({json:fixture()}));await page.goto('/');
 const check=async()=>{
  await expect.poll(async()=>(await inspect(page)).left).toEqual([9.7,10.3]);const r=await inspect(page);
  expect(r.left).toEqual(r.right);expect(r.ticks).toEqual(r.rightTicks);expect(r.ticks).toHaveLength(9);
  expect(r.centerY).toBeCloseTo(r.midY,5);expect(r.baseline).toBe(10);expect(r.color).toBe('#8cbcff');expect(r.width).toBe(.8);expect(r.averageWidth).toBe(1);expect(r.legend).toEqual(['价格','均价']);
  expect(r.leftText[4]).toBe('{flat|10.00}');expect(r.rightText[4]).toBe('{flat|0.00%}');expect(r.leftText[0]).toBe('{fall|9.70}');expect(r.rightText[8]).toBe('{rise|+3.00%}');
 };
 await check();await page.locator('.minute-detail').screenshot({path:info.outputPath('symmetric-minute-range.png')});
 for(const view of ['日K','周K']){await page.getByRole('button',{name:view,exact:true}).click();await check();}
});

test('day extrema require the same stock, date, prior close and an already observed snapshot',()=>{
 const ref={code:'sz300364',day:'2026-11-13',timestamp:'2026-11-13T16:14:12+08:00',previousClose:27.13,high:28.77,low:26.90},now=Date.parse('2026-11-15T12:00:00+08:00');
 expect(reachedPriceRange(ref,ref.code,ref.day,27.13,now)).toEqual([28.77,26.9]);
 for(const change of [{code:'sh603938'},{day:'2026-11-12'},{timestamp:'invalid'},{timestamp:'2026-11-12T16:00:00+08:00'},{previousClose:28},{previousClose:NaN},{high:25,low:26}])expect(reachedPriceRange({...ref,...change},ref.code,ref.day,27.13,now)).toEqual([]);
 expect(reachedPriceRange(ref,ref.code,ref.day,27.13,Date.parse('2026-11-13T10:30:00+08:00'))).toEqual([]);
 expect(reachedPriceRange(ref,ref.code,ref.day,27.13,null)).toEqual([]);
});

test('Zhongwen range uses observed tick high 28.77 rather than the 28.65 minute close, with a thinner blue line',async({page},info)=>{
 const raw=JSON.parse(readFileSync('tests/ui/fixtures/zhongwen-minute-20261113.json','utf8')),f=fixture(),code='sz300364',day='2026-11-13';
 f.snapshot.watch=[{code,name:'中文在线',enabled:1,quote:raw.quote,health:'非交易时段 · 已刷新缓存',candidates:[]}];f.snapshot.now='2026-11-15T12:00:00+08:00';
 const candle={date:day,open:raw.quote.open,close:raw.quote.price,high:raw.quote.high,low:raw.quote.low,volume:raw.quote.volume};
 f.minutes[code]=[{day,data:raw.minute}];f.daily[code]=[{day,data:candle}];f.history[code]={code,daily:[candle],days:[{date:day,status:'ready',has_minutes:true,signal_count:0,recorded_count:0,matches:[]}],events:[],source:null,minute_days:[day]};
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');
 await expect.poll(async()=>(await inspect(page)).left).toEqual([25.49,28.77]);const r=await inspect(page);
 expect(Math.max(...r.price.filter((v:any)=>typeof v==='number'))).toBe(28.65);expect(r.baseline).toBe(27.13);expect(r.width).toBe(.8);expect(r.left).toEqual(r.right);
 expect(r.leftText[8]).toBe('{rise|28.77}');expect(r.rightText[8]).toBe('{rise|+6.04%}');
 await page.locator('.minute-detail').screenshot({path:info.outputPath('zhongwen-tick-range-thin-line.png')});
 for(const view of ['日K','周K']){await page.getByRole('button',{name:view,exact:true}).click();await expect.poll(async()=>(await inspect(page)).left).toEqual([25.49,28.77]);expect((await inspect(page)).width).toBe(.8);}
 await page.getByRole('button',{name:'分时',exact:true}).click();
 // A later quote may not leak into an older minute-cache capture, even on the same day.
 f.minutes[code][0].data.cached_at='2026-11-13T10:30:20+08:00';f.minutes[code][0].data.bars=[{time:'10:30',close:'27.5',average:'27.4',volume:10000,complete:true}];await page.reload();
 await expect.poll(async()=>(await inspect(page)).left).toEqual([26.76,27.5]);
 // A reference from another day must not expand the selected historical range.
 f.minutes[code][0].data.cached_at='2026-11-15T12:00:00+08:00';f.snapshot.watch[0].quote.timestamp='2026-11-14T16:00:00+08:00';delete f.minutes[code][0].data.limit_reference_time;await page.reload();
 await expect.poll(async()=>(await inspect(page)).left).toEqual([26.76,27.5]);
 f.snapshot.watch[0].quote={...raw.quote,code:'sh603938',timestamp:'2026-11-13T16:14:12+08:00',price:'27.5'};await page.reload();
 await expect.poll(async()=>(await inspect(page)).left).toEqual([26.76,27.5]);
});

test('future cached extremes cannot expand the range before the snapshot reaches them',async({page})=>{
 await page.clock.install({time:new Date('2026-10-16T10:32:00+08:00')});const f=fixture();let stamp='2026-10-16T10:30:20+08:00';
 f.minutes.sh603002[0].data.bars.push({time:'10:31',close:'12',average:'10',volume:10000,complete:true},{time:'15:00',close:'1000',average:'10',volume:10000,complete:true});
 await page.route('**/preview.json',r=>{f.minutes.sh603002[0].data.cached_at=stamp;return r.fulfill({json:f});});await page.goto('/');
 await expect.poll(async()=>(await inspect(page)).left).toEqual([9.7,10.3]);expect((await inspect(page)).price.at(-1)).toBeNull();
 stamp='2026-10-16T10:31:30+08:00';await page.reload();await expect.poll(async()=>(await inspect(page)).left).toEqual([8,12]);expect((await inspect(page)).price.at(-1)).toBeNull();
});
