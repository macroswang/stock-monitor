import {test,expect} from '@playwright/test';
test('charts, navigation and push setup render without runtime errors',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();
 await expect(page.locator('.stock')).toHaveCount(12);
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 const minuteChart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 await expect(minuteChart).toHaveCount(1);
 await expect(minuteChart.locator('.minute-frame-surface')).toBeVisible();
 await page.screenshot({path:'outputs/client-clean-preview.png',fullPage:true});
 await page.getByRole('button',{name:'日K',exact:true}).click();await expect(page.getByLabel('日K线及成交量')).toBeVisible();
 await page.locator('.stock').filter({hasText:'海优新材'}).click();await expect(page.locator('.detail h2')).toContainText('海优新材');
 await page.getByRole('button',{name:/数据管理/}).click();await expect(page.getByRole('heading',{name:'下载与本地缓存'})).toBeVisible();
 await page.getByRole('button',{name:/设置与通知/}).click();await expect(page.getByRole('heading',{name:'iPhone 锁屏通知'})).toBeVisible();
 await expect(page.getByRole('button',{name:'保存密钥'})).toBeDisabled();
 await page.getByRole('button',{name:'发送测试通知'}).click();await expect(page.getByRole('status')).toContainText('浏览器仅用于界面预览');
 expect(errors).toEqual([]);
});

test('four real raw-backed preview curves retain matching average values',async({page})=>{
 await page.goto('/');
 for(const [name,code,average] of [['宏昌电子','sh603002','15.72'],['海优新材','sh688680','34.23'],['盛和资源','sh600392','17.74'],['山子高科','sz000981','2.44']]){
  await page.locator('.stock').filter({hasText:name}).click();await expect(page.locator('.detail h2')).toContainText(name);
  const chart=page.getByLabel('分时价格及分钟成交量');
  await expect(page.locator('.average-caption')).toHaveCount(0);
  await chart.screenshot({path:'outputs/client-clean-curve-'+code+'.png'});
 }
});


test('folding the watchlist preserves loaded chart data, candle zoom and the chart instance across views',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'我的自选',exact:true})).toBeVisible();
 await expect(page.locator('.detail h2')).toContainText('宏昌电子');
 const heading=await page.locator('.detail h2').innerText();
 for(const [view,label] of [['分时','分时价格及分钟成交量'],['日K','日K线及成交量'],['周K','周K线及成交量']]){
  await page.getByRole('button',{name:view,exact:true}).click();
  const chart=page.getByLabel(label);await expect(chart.locator('canvas').first()).toBeVisible();
  const inspect=(zoom=false)=>chart.evaluate(async(el,zoom)=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]),c=e.getInstanceByDom(el);
   if(zoom)c.dispatchAction({type:'dataZoom',start:20,end:80});
   const option=c.getOption(),labels=option.xAxis[0].data as string[];
   // ECharts snaps a percentage range to category indices. Compare the actual visible labels.
   const windows=option.dataZoom.map((z:{startValue:number;endValue:number})=>
    [labels[z.startValue],labels[z.endValue]]);
   return {id:el.getAttribute('_echarts_instance_'),data:option.series[0].data,windows};
  },zoom);
  const before=await inspect(view!=='分时'),width=(await chart.boundingBox())!.width;
  expect(before.data.length).toBeGreaterThan(0);
  for(const range of before.windows)expect(range).toEqual([expect.any(String),expect.any(String)]);
  await page.getByRole('button',{name:'折叠我的自选',exact:true}).click();
  await expect.poll(async()=>(await chart.boundingBox())!.width).toBeGreaterThan(width+250);
  await expect.poll(async()=>await inspect()).toEqual(before);
  await expect.poll(async()=>(await chart.locator('canvas').first().boundingBox())!.width).toBeCloseTo((await chart.boundingBox())!.width,0);
  await page.screenshot({path:`outputs/watchlist-loaded-collapsed-${view}.png`,fullPage:true});
  await page.getByRole('button',{name:'展开我的自选',exact:true}).click();
  await expect.poll(async()=>(await chart.boundingBox())!.width).toBeCloseTo(width,0);
  await expect.poll(async()=>await inspect()).toEqual(before);
  await expect(page.locator('.detail h2')).toHaveText(heading);
 }
 expect(errors).toEqual([]);
});


test('chart-side navigation updates loaded minute, daily and weekly charts and stays on the right',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/');
 await expect(page.locator('.detail h2')).toContainText('宏昌电子');
 await page.getByRole('button',{name:'置顶宏昌电子',exact:true}).click();
 await page.getByRole('button',{name:'置顶海优新材',exact:true}).click();
 await page.getByRole('button',{name:'折叠我的自选',exact:true}).click();
 const nav=page.getByRole('group',{name:'自选股切换',exact:true});
 for(const [view,label] of [['分时','分时价格及分钟成交量'],['日K','日K线及成交量'],['周K','周K线及成交量']]){
  await page.getByRole('button',{name:view,exact:true}).click();
  const chart=page.getByLabel(label);await expect(chart.locator('canvas').first()).toBeVisible();
  const data=()=>chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].data;});
  await expect.poll(async()=>(await data()).length).toBeGreaterThan(0);const before=await data();
  const plot=(await chart.boundingBox())!,buttons=(await nav.boundingBox())!;
  expect(buttons.x).toBeGreaterThanOrEqual(plot.x+plot.width-40);expect(buttons.x+buttons.width).toBeLessThanOrEqual(plot.x+plot.width);
  expect(Math.abs(buttons.y+buttons.height/2-plot.y-plot.height/2)).toBeLessThan(1);
  await nav.getByRole('button',{name:'下一支自选股'}).click();
  await expect(page.locator('.detail h2')).toContainText('海优新材');
  await expect(chart).toBeVisible();await expect.poll(async()=>(await data()).length).toBeGreaterThan(0);await expect.poll(data).not.toEqual(before);
  await expect(page.getByRole('button',{name:view,exact:true})).toHaveClass(/chosen/);
  await expect(page.getByRole('button',{name:'展开我的自选',exact:true})).toBeVisible();
  await nav.getByRole('button',{name:'上一支自选股'}).click();
  await expect(page.locator('.detail h2')).toContainText('宏昌电子');await expect.poll(data).toEqual(before);
  if(view==='分时')await page.screenshot({path:'outputs/watch-stock-switcher.png',fullPage:true});
 }
 await page.setViewportSize({width:1000,height:980});
 await expect(nav).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false);
 expect(errors).toEqual([]);
});
