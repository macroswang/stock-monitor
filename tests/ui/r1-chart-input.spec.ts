import {test,expect,Locator} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {turningFinal,TURNING_FINAL_MODES} from '../../src/turningFinal';
import {turningDisplayPoints} from '../../src/turningDisplay';
import {turningQualityQ1} from '../../src/turningQualityQ1';
const source=JSON.parse(readFileSync('tests/fixtures/zhangle-reconstruction.json','utf8'));
const slots=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:120},(_,i)=>781+i)].map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

async function rendered(chart:Locator){
 return chart.evaluate(async el=>{
  const s=await fetch('/src/Chart.tsx').then(r=>r.text());
  const url=s.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1];
  const e=await import(/* @vite-ignore */url),c=e.getInstanceByDom(el),o=c?.getOption();
  if(!o?.series)return null;
  const shapes=o.series[0].markPoint.data.filter((m:any)=>m.observationKey?.startsWith('shape-v2|'));
  return {points:shapes.map((m:any)=>[m.turningKind,m.coord[0],m.coord[1]]),
   labels:c.getZr().storage.getDisplayList().filter((m:any)=>m.type==='tspan'&&['底','顶'].includes(m.style?.text)).map((m:any)=>m.style.text),
   plottedOpening:o.series[0].data[0],firstMacd:o.series.find((s:any)=>s.name==='个股 MACD')?.data[1]};
 });
}
const labels=(events:ReturnType<typeof turningFinal>)=>events.map(m=>[m.kind==='bottom'?'底':'顶',m.time,m.price]);

for(const [code,previousClose] of [['sh603938',30.01],['sz002639',15.95]] as const){
 test(`real watchlist and linked minute charts show fixed v2.4 labels: ${code}`,async({page},info)=>{
  const c=source.cases.find((c:any)=>c.code===code&&c.day==='2026-11-10');
  const rows:any[]=[{time:'09:30',close:String(c.opening_price),average:String(c.opening_price),volume:0,complete:true},
   ...c.prices.map((p:number,i:number)=>({time:slots[i],close:String(p),average:String(c.averages[i]),volume:c.volumes[i],complete:true}))];
  const expected=labels(turningDisplayPoints(turningFinal(rows,TURNING_FINAL_MODES.zhangle),turningQualityQ1(rows),true,true).filter(p=>p.shape).map(p=>p.shape!));
  expect(expected.length).toBeGreaterThan(0);
  const payload=JSON.parse(readFileSync('public/preview.json','utf8'));
  const daily={date:c.day,open:String(c.opening_price),close:String(c.prices.at(-1)),high:String(Math.max(c.opening_price,...c.prices)),low:String(Math.min(c.opening_price,...c.prices)),volume:String(c.volumes.reduce((a:number,b:number)=>a+b,0)),provisional:true};
  const quote={code:c.code,name:c.name,price:daily.close,previous_close:String(previousClose),high:daily.high,low:daily.low,timestamp:c.day+'T11:30:05+08:00',change:String(Number(daily.close)-previousClose)};
  payload.snapshot.watch=[{code:c.code,name:c.name,enabled:1,quote,candidates:[],health:'shape-v2 display regression'}];payload.snapshot.events=[];payload.snapshot.now=c.day+'T11:30:05+08:00';payload.snapshot.config.trading_paused=true;
  payload.minutes[c.code]=[{day:c.day,data:{date:c.day,source:'public_quote_regression',bars:rows,previous_close:String(previousClose),volume_unit:'shares'}}];
  payload.daily[c.code]=[{day:c.day,data:daily}];
  payload.history[c.code]={...payload.history.sh603002,code:c.code,daily:[daily],days:[{date:c.day,status:'ready',has_minutes:true,signal_count:0,recorded_count:0,matches:[]}],events:[],minute_days:[c.day]};
  await page.route('**/preview.json',route=>route.fulfill({json:payload}));
  await page.goto('/');await page.locator('.stock').filter({hasText:c.name}).click();
  const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();
  await expect.poll(async()=>(await rendered(chart))?.points).toEqual(expected);
  const normal=(await rendered(chart))!;expect(normal.labels.length).toBeGreaterThanOrEqual(expected.length);
  expect(normal.plottedOpening).toBeNull();expect(normal.firstMacd).toBe(0);
  await expect(page.getByTestId('turning-cap-count')).toHaveCount(0);
  await expect(page.getByLabel('顶底模式')).toHaveCount(0);
  await page.getByRole('checkbox',{name:'开盘量',exact:true}).uncheck();
  await expect.poll(async()=>(await rendered(chart))?.points).toEqual(expected);
  await page.getByRole('checkbox',{name:'底/顶',exact:true}).uncheck();
  await expect.poll(async()=>(await rendered(chart))?.points).toEqual([]);
  await page.getByRole('checkbox',{name:'底/顶',exact:true}).check();
  await expect.poll(async()=>(await rendered(chart))?.points).toEqual(expected);
  await chart.screenshot({path:info.outputPath('shape-v2-watchlist-labels.png')});
  await page.getByRole('button',{name:'日K',exact:true}).click();
  const linked=page.locator('.linked-minute').getByLabel('分时价格及分钟成交量',{exact:true});
  await expect(linked).toBeVisible();await expect.poll(async()=>(await rendered(linked))?.points).toEqual(expected);
  expect((await rendered(linked))!.labels.length).toBeGreaterThanOrEqual(expected.length);
 });
}
