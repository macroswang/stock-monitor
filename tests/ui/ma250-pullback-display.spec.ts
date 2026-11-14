import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

const mounts=async(page:any,signal:Record<string,unknown>)=>{
 const payload=JSON.parse(readFileSync('public/preview.json','utf8')),code='sh603002';
 const history=payload.history[code],dates=history.daily.map((row:any)=>row.date);
 const date=dates.at(-12),touch=dates.at(-26),candle=history.daily.at(-12);
 const base={key:date,date,close:+candle.close,ma250:+candle.close*0.94,ma5:+candle.close*0.97,
  distance_pct:6.4,touch_date:touch,touch_low:+candle.close*0.90,touch_depth_pct:1.2,pullback_pct:12.5,stop:+candle.close*0.88};
 history.ma250={signals:[{...base,...signal}],latest:{date:dates.at(-1),close:+history.daily.at(-1).close,ma250:+candle.close*0.94,distance_pct:6.4,status:'above',bars:dates.length},version:'ma250-pullback-v2'};
 payload.minutes[code]=[];
 await page.route('**/preview.json',route=>route.fulfill({json:payload}));
 await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
 const chart=page.getByLabel('日K线及成交量');await expect(chart).toBeVisible();
 const inspect=()=>chart.evaluate(async(el,args)=>{
  const source=await fetch('/src/Chart.tsx').then(response=>response.text());
  const echarts=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const instance=echarts.getInstanceByDom(el),option=instance.getOption();
  const marker=option.series.find((series:any)=>series.name==='年线回踩信号');
  const areas=(option.series[0].markArea?.data||[]).map((area:any[])=>area.map(point=>point.xAxis));
  const labels=instance.getZr().storage.getDisplayList().filter((item:any)=>item.type==='tspan'&&String(item.style.text).includes('年线回踩')).map((item:any)=>String(item.style.text));
  return {markers:marker?.data.map((point:any)=>point.value[0])||[],areas,strong:marker?.data.map((point:any)=>point.strong)||[],labels};
 },{date,touch});
 return {chart,date,touch,inspect,toggle:page.getByRole('checkbox',{name:'年线信号'})};
};

test('strong annual-line signal retains its marker and tooltip with controls hidden',async({page})=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 const {chart,date,touch,inspect,toggle}=await mounts(page,{strong:true,strong_reasons:[],market_above:true,higher_low:true});
 await expect.poll(async()=>(await inspect()).markers).toEqual([date]);
 const drawn=await inspect();
 expect(drawn.labels).toContain('年线回踩·强');
 expect(drawn.areas).toContainEqual([touch,date]);
 await expect(toggle).toHaveCount(0);
 expect(drawn.strong).toEqual([true]);
 const point=await chart.evaluate(async(el,args)=>{
  const source=await fetch('/src/Chart.tsx').then(response=>response.text());
  const echarts=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const instance=echarts.getInstanceByDom(el),option=instance.getOption(),index=option.xAxis[0].data.indexOf(args.date);
  return instance.convertToPixel({xAxisIndex:0,yAxisIndex:0},[args.date,option.series[0].data[index][1]]);
 },{date});
 const box=(await chart.boundingBox())!;await page.mouse.move(box.x+point[0],box.y+point[1]);
 await expect(chart.locator('.quote-tooltip')).toContainText('年线回踩（强）');
 await expect(chart.locator('.quote-tooltip')).toContainText('强信号：');
 await page.mouse.move(0,0);
 await expect.poll(async()=>(await inspect()).markers).toEqual([date]);
 expect(errors).toEqual([]);
});

test('a normal reclaim stays visible with the unmet strong reasons',async({page})=>{
 const {chart,inspect,date}=await mounts(page,{strong:false,strong_reasons:['extended'],market_above:true,higher_low:true});
 await expect.poll(async()=>(await inspect()).markers).toEqual([date]);
 expect((await inspect()).labels).toContain('年线回踩');
 expect((await inspect()).labels).not.toContain('年线回踩·强');
 const point=await chart.evaluate(async(el,args)=>{
  const source=await fetch('/src/Chart.tsx').then(response=>response.text());
  const echarts=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const instance=echarts.getInstanceByDom(el),option=instance.getOption(),index=option.xAxis[0].data.indexOf(args.date);
  return instance.convertToPixel({xAxisIndex:0,yAxisIndex:0},[args.date,option.series[0].data[index][1]]);
 },{date});
 const box=(await chart.boundingBox())!;await page.mouse.move(box.x+point[0],box.y+point[1]);
 await expect(chart.locator('.quote-tooltip')).toContainText('强信号未满足：距年线超过7%');
});

test('settings expose the annual-line alert switch',async({page})=>{
 await page.goto('/');
 await page.getByRole('button',{name:'设置与通知'}).click();
 const toggle=page.getByLabel('年线回踩强信号提醒');
 await expect(toggle).toBeVisible();
 await expect(toggle).toBeChecked();
});