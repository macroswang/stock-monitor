import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {candles,flag,bear,triangle,spring} from './fixtures/daily-patterns';
import {dailyPatterns} from '../../src/dailyPatterns';
import {selectDailyPatterns} from '../../src/dailyPatternSelection';
import {dailyPatternColors} from '../../src/dailyPatternOverlay';
import {dailyGaps} from '../../src/dailyGaps';

const oldFlag=candles([[0,8],[2,8.1],[7,12.2],[10,11.2],[13,11.9],[16,10.9],[18,11.3],[19,12],[20,12.1],[110,12.5]],'2026-04-01');
const multiple=candles([[0,8],[2,8.1],[7,12.2],[10,11.2],[13,11.9],[16,10.9],[18,11.3],[19,12],[20,12.1],[25,13],[28,12],[31,14],[34,12.5],[35,11.4],[36,12.8],[37,13],[39,14.5],[110,15]],'2026-04-01');
for(const [name,rows,kind] of [['下飘旗',flag,'falling-flag'],['上飘旗',bear,'rising-flag'],['收敛三角形',triangle,'triangle'],['破底翻',spring,'spring'],['历史下飘旗',oldFlag,'falling-flag'],['不同位置自动显示',multiple,'falling-flag']] as const){
 test(`daily ${name}: automatically draws resolved shapes without a picker`,async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const payload=JSON.parse(readFileSync('public/preview.json','utf8')),code='sh603002';
  payload.snapshot.watch=[{...payload.snapshot.watch.find((w:any)=>w.code===code),code,name:`${name}绘图样本`}];
  payload.minutes[code]=[];payload.daily[code]=rows.map(data=>({day:data.date,data}));
  payload.history[code]={...payload.history[code],code,daily:rows,events:[],days:rows.map(data=>({date:data.date,status:'missing_minutes',has_minutes:false,signal_count:0,recorded_count:0,matches:[]}))};
  await page.route('**/preview.json',route=>route.fulfill({json:payload}));
  await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
  const accepted=selectDailyPatterns(dailyPatterns([...rows])),p=accepted.find(p=>p.kind===kind)!;expect(p).toBeDefined();
  const controls=page.getByRole('group',{name:'日线形态显示选项'}),chart=page.getByLabel('日K线及成交量');
  await expect(controls.getByRole('combobox')).toHaveCount(0);await expect(page.getByLabel('选择日线形态')).toHaveCount(0);await expect(controls).toContainText('自动识别');
  const hi=Math.min(rows.length-1,Math.max(p.end.index+3,89)),lo=Math.max(0,hi-89);
  // Historical shapes appear while browsing dates; no manual pattern selection.
  await chart.evaluate(async(el,args)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]),c=e.getInstanceByDom(el),n=c.getOption().xAxis[0].data.length-1;c.dispatchAction({type:'dataZoom',start:args.lo/Math.max(1,n)*100,end:args.hi/Math.max(1,n)*100});c.trigger('click',{componentType:'series',name:args.date});},{lo,hi,date:p.end.date});
  const inspect=()=>chart.evaluate(async(el,args)=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),list=c.getZr().storage.getDisplayList(),grid=c.getModel().getComponent('grid',0).coordinateSystem.getRect();
   const outlines=list.filter((d:any)=>d.type==='line'&&args.colors.includes(d.style.stroke)),i=o.xAxis[0].data.indexOf(args.date);
   return {keys:o.series.find((s:any)=>s.name==='日线形态识别')?.data.map((d:any)=>d.patternKey)||[],segments:o.series.find((s:any)=>s.name==='日线形态轮廓')?.data||[],drawn:outlines.length,dashed:outlines.filter((d:any)=>d.style.lineDash?.length).length,references:o.series[0].markLine.data,areas:o.series[0].markArea.data,prices:o.series[0].data,hover:c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[args.date,o.series[0].data[i][1]]),pointerLines:list.filter((d:any)=>d.type==='line'&&['#a8bad1','#8baeed'].includes(d.style.stroke)).length,labels:list.filter((d:any)=>d.type==='tspan'&&/上飘旗|下飘旗|收敛三角形|破底翻/.test(String(d.style.text))).map((d:any)=>{const r=d.getBoundingRect().clone();r.applyTransform(d.getComputedTransform());return {bottom:r.y+r.height,gridTop:grid.y};})};
  },{colors:Object.values(dailyPatternColors),date:p.end.date});
  await expect.poll(async()=>(await inspect()).keys).toEqual(accepted.map(p=>p.key));
  const drawn=await inspect();expect(drawn.drawn).toBeGreaterThan(0);expect(drawn.dashed).toBe(0);expect(drawn.references).toEqual([]);
  expect(drawn.segments).toEqual(accepted.flatMap(p=>p.lines.filter(l=>l.role!=='neckline'&&l.role!=='outline').map(l=>[l.from.date,l.from.price,l.to.date,l.to.price])));
  if(name==='不同位置自动显示')expect(drawn.keys.length).toBeGreaterThan(1);
  const gap=dailyGaps([...rows]).filter(g=>!g.filledOn).at(-1);expect(drawn.areas).toHaveLength(gap?1:0);
  if(gap){expect(drawn.areas[0][0].yAxis).toBe(gap.low);expect(drawn.areas[0][1].yAxis).toBe(gap.high);expect(drawn.areas[0][0].itemStyle.color).toContain('.035');}
  expect(drawn.prices).toEqual(rows.map(b=>[+b.open,+b.close,+b.low,+b.high]));expect(drawn.labels.length).toBeGreaterThan(0);for(const label of drawn.labels)expect(label.bottom).toBeLessThan(label.gridTop);
  const box=(await chart.boundingBox())!;await page.mouse.move(box.x+drawn.hover[0],box.y+drawn.hover[1]);await expect(chart.locator('.quote-tooltip')).toContainText('收盘：');expect((await inspect()).pointerLines).toBe(0);
  await page.mouse.move(0,0);await page.addStyleTag({content:'.interactive-price-tooltip{visibility:hidden!important}'});
  await chart.screenshot({path:test.info().outputPath(`${kind}.png`)});await controls.screenshot({path:test.info().outputPath('automatic-controls.png')});
  await page.getByLabel('显示日线形态',{exact:true}).uncheck();expect((await inspect()).segments).toEqual([]);
  await page.getByLabel('显示日线形态',{exact:true}).check();await expect.poll(async()=>(await inspect()).keys).toEqual(accepted.map(p=>p.key));
  await expect(controls.getByRole('combobox')).toHaveCount(0);expect(errors).toEqual([]);
 });
}
