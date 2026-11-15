import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {PRICE_UP,PRICE_DOWN,PRICE_FLAT,priceColor,minuteTimeCutoff} from '../../src/pricePresentation';

test('red and green compare every price with the same-day previous close, not the preceding minute',()=>{
 expect(priceColor(10.5,10)).toBe(PRICE_UP);expect(priceColor(9.5,10)).toBe(PRICE_DOWN);expect(priceColor(10,10)).toBe(PRICE_FLAT);
 for(const base of [undefined,0,-1,NaN])expect(priceColor(10,base)).toBe(PRICE_FLAT);
});

test('capture time and wall time are independent display cutoffs and old-day baselines are not invented',()=>{
 const now=Date.parse('2026-10-30T10:32:00+08:00');
 expect(minuteTimeCutoff('2026-10-30',now,'2026-10-30T10:30:20+08:00')).toBe(Date.parse('2026-10-30T10:30:20+08:00'));
 expect(minuteTimeCutoff('2026-10-31',now)).toBeNull();expect(minuteTimeCutoff('2026-10-30',now,'invalid')).toBeNull();
 expect(minuteTimeCutoff('2026-10-30',now,'2026-10-29T15:00:00+08:00')).toBeNull();
});

test('stock prices stay blue on both sides of previous close after reverting only their colour treatment',async({page})=>{
 const f=JSON.parse(readFileSync('public/preview.json','utf8')),row=f.minutes.sh603002[0],bars=[9,9.5,10,11,10.5].map((p,i)=>({time:`09:3${i+1}`,close:String(p),volume:10000+i*100,average:'10',complete:true}));
 row.data={...row.data,bars,previous_close:'10'};row.data.cached_at='2026-10-16T15:00:00+08:00';await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');
 const c=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(c).toBeVisible();
 const r=await c.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),m=c.getModel(),o=c.getOption(),price=m.getSeries()[0],d=price.getData();return{colors:[1,2,3,4,5].map(i=>d.getItemVisual(i,'style').fill),values:o.series[0].data.slice(1,6),average:o.series.find((s:any)=>s.name==='均价').lineStyle.color,averageWidth:o.series.find((s:any)=>s.name==='均价').lineStyle.width,averages:o.series.find((s:any)=>s.name==='均价').data.slice(1,6),origin:o.series[0].areaStyle.origin,baseline:o.series[0].markLine.data.find((v:any)=>v.name==='昨收')?.yAxis,volume:o.series.filter((s:any)=>s.stack==='minute-volume').map((s:any)=>s.data.slice(1,6)),zoom:o.dataZoom[0],maps:o.visualMap?.length||0,lineColor:o.series[0].lineStyle.color,stops:o.series[0].areaStyle.color.colorStops,flat:o.series.some((s:any)=>s.name==='昨收平盘线')};});
 expect(r.lineColor).toBe('#8cbcff');expect(r.stops).toEqual([{offset:0,color:'rgba(83,139,230,.16)'},{offset:1,color:'rgba(83,139,230,0)'}]);expect(r.values).toEqual([9,9.5,10,11,10.5]);expect(r.average).toBe('#e9b949');expect(r.averageWidth).toBe(1);expect(r.averages).toEqual([10,10,10,10,10]);expect(r.origin).toBeUndefined();expect(r.baseline).toBe(10);expect(r.maps).toBe(0);expect(r.flat).toBe(false);
 for(let i=0;i<5;i++)expect(r.volume.reduce((sum:number,row:number[])=>sum+row[i],0)).toBe(bars[i].volume/100);
 await c.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);e.getInstanceByDom(el).dispatchAction({type:'dataZoom',start:0,end:3});});
 const readPixels=()=>c.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),canvas=c.renderToCanvas({pixelRatio:1}),ctx=canvas.getContext('2d')!,ratio=canvas.width/c.getWidth();return [[1,2,9.25],[4,5,10.75]].map(([a,b,value])=>{const x=(c.convertToPixel({xAxisIndex:0},a)+c.convertToPixel({xAxisIndex:0},b))/2,y=c.convertToPixel({yAxisIndex:0},value),p=ctx.getImageData(Math.round(x*ratio)-1,Math.round(y*ratio)-1,3,3).data;let blue=-255;for(let i=0;i<p.length;i+=4){blue=Math.max(blue,Math.min(p[i+2]-p[i],p[i+2]-p[i+1]));}return {blue};});});
 await expect.poll(async()=>Math.min(...(await readPixels()).map((p:any)=>p.blue))).toBeGreaterThan(30);
 await page.screenshot({path:'outputs/stock-blue-restored.png',fullPage:true});
});

test('future minutes stay outside stock prices and index volume even when a cache contains the whole day',async({page})=>{
 await page.clock.install({time:new Date('2026-10-16T10:30:20+08:00')});const f=JSON.parse(readFileSync('public/preview.json','utf8'));f.minutes.sh603002[0].data.cached_at='2026-10-16T10:30:20+08:00';
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();
 const prices=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),o=e.getInstanceByDom(el).getOption();return {future:o.series[0].data.slice(o.xAxis[0].data.indexOf('10:31')),marks:o.series[0].markPoint.data.map((p:any)=>p.coord[0])};});
 expect(prices.future.every((p:any)=>p===null)).toBe(true);expect(prices.marks.every((time:string)=>time<='10:30')).toBe(true);
});
