import {test,expect} from '@playwright/test';
import {minuteSlots} from '../../src/minuteMacd';
const inspect=async(page:any)=>page.getByLabel('分时价格及分钟成交量',{exact:true}).evaluate(async(el:any)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),m=c.getModel(),o=c.getOption();return {max:m.getComponent('yAxis',o.yAxis.findIndex((a:any)=>a.gridIndex===3)).axis.scale.getExtent()[1],data:o.series.find((s:any)=>s.name==='指数成交量').data,zoom:o.dataZoom[0].start};});
test('zooming past the opening index peak puts the biggest visible bar at the upper edge without changing the raw values',async({page})=>{
 await page.route('**/market-overview-preview.json',r=>r.fulfill({json:{collected_at:'2026-10-16T16:00:00+08:00',quotes:[{code:'sh000001',name:'上证指数',timestamp:'2026-10-16T16:00:00+08:00',price:'3600',previous_close:'3600',change:'0',percent:'0',source:'tencent'}],minute:{code:'sh000001',date:'2026-10-16',previous_close:'3600',source:'tencent',bars:minuteSlots.map((time,i)=>({time,close:'3600',volume_lots:i===1?5000000:100000}))}}}));
 await page.goto('/');const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();await expect.poll(async()=>(await inspect(page)).max).toBe(500);const before=await inspect(page);
 await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);e.getInstanceByDom(el).dispatchAction({type:'dataZoom',start:50,end:90});});
 await expect.poll(async()=>(await inspect(page)).max).toBe(10);expect((await inspect(page)).data).toEqual(before.data);expect((await inspect(page)).zoom).toBe(50);
 await expect(page.locator('[data-volume-grid="3"] time')).toHaveText('14:36');await expect(page.locator('[data-volume-grid="3"] .volume-value')).toHaveText('10.00 万手');
 for(const name of ['个股MACD','指数MACD'])await expect(page.getByRole('group',{name,exact:true}).locator('time')).toHaveText('14:36');
});

test('future index volume cannot set today’s peak before both the clock and the cached snapshot reach that minute',async({page})=>{
 await page.clock.install({time:new Date('2026-10-16T10:32:00+08:00')});
 const {readFileSync}=await import('node:fs'),fixture=JSON.parse(readFileSync('public/preview.json','utf8'));let stamp='2026-10-16T10:30:20+08:00';
 await page.route('**/preview.json',r=>{fixture.minutes.sh603002[0].data.cached_at=stamp;return r.fulfill({json:fixture});});
 await page.route('**/market-overview-preview.json',r=>r.fulfill({json:{collected_at:stamp,quotes:[{code:'sh000001',name:'上证指数',timestamp:stamp,price:'3600',previous_close:'3600',change:'0',percent:'0',source:'tencent'}],minute:{code:'sh000001',date:'2026-10-16',previous_close:'3600',source:'tencent',cached_at:stamp,bars:minuteSlots.map((time,i)=>({time,close:'3600',volume_lots:time==='15:00'?1000000000:i===1?5000000:100000}))}}}));
 await page.goto('/');const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();
 const read=async()=>chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),i=o.xAxis[0].data.indexOf('10:31');return {price:o.series[0].data[i],volume:o.series.find((s:any)=>s.name==='指数成交量').data[i],lastVolume:o.series.find((s:any)=>s.name==='指数成交量').data.at(-1),max:c.getModel().getComponent('yAxis',o.yAxis.findIndex((a:any)=>a.gridIndex===3)).axis.scale.getExtent()[1]};});
 await expect.poll(async()=>(await read()).max).toBe(500);expect(await read()).toMatchObject({price:null,volume:null,lastVolume:null});
 stamp='2026-10-16T10:31:30+08:00';await page.reload();await expect.poll(async()=>(await read()).volume).toBe(10);expect((await read()).price).not.toBeNull();expect((await read()).lastVolume).toBeNull();
});
