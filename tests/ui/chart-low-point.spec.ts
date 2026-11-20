import {expect,test,type Locator} from '@playwright/test';

const readChart=(chart:Locator,zoom?:number)=>chart.evaluate(async(node,start)=>{
 const source=await fetch('/src/Chart.tsx').then(r=>r.text());
 const echarts=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);
 const instance=echarts.getInstanceByDom(node);
 if(start!==undefined)instance.dispatchAction({type:'dataZoom',start,end:100});
 const option=instance.getOption(),axis=option.xAxis[0],window=option.dataZoom[0];
 const from=Math.round((axis.data.length-1)*window.start/100);
 const to=Math.round((axis.data.length-1)*window.end/100);
 const visible=option.series[0].data.slice(from,to+1).map((value:number|number[]|null)=>Array.isArray(value)?value[2]:value);
 const labels=instance.getZr().storage.getDisplayList(true).filter((item:any)=>item.type==='tspan'&&/^(?:←\d+\.\d{2}|\d+\.\d{2}→)$/.test(item.style.text));
 return {labels:labels.map((item:any)=>item.style.text.replace(/[←→]/g,'')),
  lowest:Math.min(...visible.filter((value:unknown)=>typeof value==='number'&&value>0)).toFixed(2),
  closingVolume:option.series.find((series:any)=>series.name==='总成交量（回退）')?.data.at(-1)};
},zoom);

test('个股日K和周K随可见范围重算最低价，分时也标出最低点',async({page})=>{
 await page.goto('/');
 for(const [view,label] of [['分时','分时价格及分钟成交量'],['日K','日K线及成交量'],['周K','周K线及成交量']]){
  await page.getByRole('button',{name:view,exact:true}).click();
  const chart=page.getByLabel(label,{exact:true});
  await expect(chart).toBeVisible();
  const before=await readChart(chart);
  expect(before.labels).toEqual([before.lowest]);
  if(view==='周K'){
   const after=await readChart(chart,60);
   expect(after.lowest).not.toBe(before.lowest);
   expect(after.labels).toEqual([after.lowest]);
  }
 }
});

test('指数分时标注蓝线低点并绘制盘后确认的15:00成交量',async({page})=>{
 const date='2026-11-20',stamp=`${date}T15:01:00+08:00`,code='sh000001',previous_close='3577.62';
 await page.clock.install({time:new Date(`${date}T15:02:00+08:00`)});
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:{collected_at:stamp,
  quotes:[{code,name:'上证指数',timestamp:stamp,source:'tencent',previous_close,price:'3533.79',change:'-43.83',percent:'-1.23'}],
  minute:{code,date,source:'tencent',cached_at:stamp,previous_close,bars:[
   {time:'14:59',close:'3531.12',volume_lots:0},{time:'15:00',close:'3533.79',volume_lots:7640181}]}}}));
 await page.goto('/');
 await page.getByRole('button',{name:'查看上证指数行情'}).click();
 const chart=page.locator('.index-detail').getByLabel('分时价格及分钟成交量',{exact:true});
 await expect(chart).toBeVisible();
 expect(await readChart(chart)).toMatchObject({labels:['3531.12'],closingVolume:7640181});
});
