import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {minuteSlots} from '../../src/minuteMacd';
import {turningFinal,TURNING_FINAL_MODES} from '../../src/turningFinal';
import {turningQualityQ1} from '../../src/turningQualityQ1';
import {turningDisplayPoints} from '../../src/turningDisplay';

const code='sh603002',day='2026-11-17',current='2026-11-18',missingIndex='2026-11-16',missingStock='2026-11-13';
const bars=[['09:30','10'],['09:31','10.1'],['09:32','16'],['11:30','10.4'],['13:01','10.2'],['15:00','10.3']]
 .map(([time,close],i)=>({time,close,average:i<2?'10.05':'10.20',volume:(i+1)*100,complete:true}));
const indexBars=bars.map(({time},i)=>({time,close:String(3600+i),volume_lots:(i+1)*10000}));
const plot=(page:Page)=>page.getByLabel('分时价格及分钟成交量',{exact:true});
const cursor=(page:Page)=>page.getByLabel('回放时刻',{exact:true});

async function frame(page:Page){
 return plot(page).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());
  const e=await import(source.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]);
  const chart=e.getInstanceByDom(el);if(!chart)return null;
  const option=chart.getOption(),wanted=['价格','均价','总成交量（回退）','指数成交量','个股 MACD','指数 MACD'];
  const series=Object.fromEntries(wanted.map(name=>[name,option.series.find((s:any)=>s.name===name)?.data]));
  return {id:chart.id,series,max:option.yAxis[0].max,marks:option.series[0].markPoint.data};
 });
}

test('historical replay advances all requested panels on the same clock and leaves the normal chart available',async({page})=>{
 await page.clock.install({time:new Date(current+'T14:59:00+08:00')});
 const fixture=JSON.parse(readFileSync('public/preview.json','utf8'));
 const other='sh688680';
 fixture.snapshot.watch=fixture.snapshot.watch.filter((row:any)=>[code,other].includes(row.code));
 fixture.snapshot.market_open=true;
 fixture.snapshot.watch[0].quote={code,price:'10.75',previous_close:'10',timestamp:current+'T14:59:00+08:00'};
 fixture.minutes[other]=[{day:current,data:{date:current,symbol:other,bars:[{...bars[1],close:'32.50'}]}}];
 fixture.minutes[code]=[missingStock,missingIndex,day,current].map(date=>({day:date,data:{date,symbol:code,previous_close:'10',bars:date===missingStock?[]:bars,cached_at:date+'T14:58:00+08:00'}}));
 await page.route('**/preview.json',route=>route.fulfill({json:fixture}));
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:{collected_at:day+'T15:01:00+08:00',
  quotes:[{code:'sh000001',name:'上证指数',price:'3600',previous_close:'3600',timestamp:day+'T15:01:00+08:00'}],
  minute:{code:'sh000001',date:day,previous_close:'3600',bars:indexBars}}}));
 await page.goto('/');
 const replay=page.getByRole('button',{name:'历史回放',exact:true}),date=page.getByLabel('交易日期',{exact:true});
 await expect(date).toHaveValue(current);await expect(replay).toBeDisabled();
 await expect(replay).toHaveAttribute('title','当天收盘后可回放，盘中请选择以前的交易日');
 await expect(page.getByRole('group',{name:'分时显示选项'})).toBeVisible();
 await date.selectOption(day);await replay.click();
 await expect(cursor(page)).toHaveText('09:30');
 await expect.poll(async()=>(await frame(page))?.series['价格'][0]).toBe(10);
 const original=await frame(page);
 expect(original?.marks).toEqual([]);
 expect(original?.series['指数成交量'][0]).toBe(1);
 for(const series of Object.values(original!.series) as any[][])expect(series[1]).toBeNull();
 await page.clock.runFor(1050);
 await expect(cursor(page)).toHaveText('09:31');
 await page.getByRole('button',{name:'暂停回放'}).click();
 await page.clock.runFor(2050);
 await expect(cursor(page)).toHaveText('09:31');
 const next=(await frame(page))!;
 expect(next.id).toBe(original?.id);
 for(const [name,value] of Object.entries({'价格':10.1,'均价':10.05,'总成交量（回退）':2,'指数成交量':2}))expect(next.series[name][1]).toBe(value);
 for(const name of ['个股 MACD','指数 MACD'])expect(next.series[name][1]).not.toBeNull();
 for(const series of Object.values(next.series) as any[][])expect(series[2]).toBeNull();
 expect(next.max).toBeLessThan(16);
 await page.getByRole('button',{name:'单步前进'}).click();await expect(cursor(page)).toHaveText('09:32');
 await expect.poll(async()=>(await frame(page))?.series['价格'][2]).toBe(16);
 const step=page.getByRole('button',{name:'单步前进'});
 const stepMany=(count:number)=>step.evaluate((button,n)=>{for(let i=0;i<n;i++)(button as HTMLButtonElement).click();},count);
 await stepMany(118);await expect(cursor(page)).toHaveText('11:30');
 await step.click();await expect(cursor(page)).toHaveText('13:01');
 await stepMany(119);await expect(cursor(page)).toHaveText('15:00');
 await expect(step).toBeDisabled();await expect(page.getByText('回放结束',{exact:true})).toBeVisible();
 // Stock cache stopped at 14:58, while the index has a genuine closing bar.
 const close=(await frame(page))!.series;
 expect(close['价格'].at(-1)).toBeNull();expect(close['指数成交量'].at(-1)).toBe(6);
 await page.getByRole('button',{name:'从头播放'}).click();await expect(cursor(page)).toHaveText('09:30');
 await expect.poll(async()=>(await frame(page))?.series['价格'][2]).toBeNull();
 await page.getByRole('button',{name:'退出回放'}).click();
 await expect(date).toHaveValue(day);
 await expect(page.getByRole('group',{name:'分时显示选项'})).toBeVisible();
 await expect.poll(async()=>(await frame(page))?.series['价格'][2]).toBe(16);

 await date.selectOption(missingIndex);await replay.click();
 await expect(page.getByText('上证指数分时缺失，个股继续回放')).toBeVisible();
 await page.getByRole('button',{name:'单步前进'}).click();
 expect((await frame(page))?.series['指数成交量'].every((value:unknown)=>value===null)).toBe(true);
 await date.selectOption(missingStock);await expect(cursor(page)).toHaveCount(0);await replay.click();
 await expect(page.getByText('该日暂无可用的个股分时数据，无法回放。')).toBeVisible();
 // Returning must work even if the replay never loaded, and show a fresh quote after exit.
 await page.getByRole('button',{name:'返回最新分时'}).click();
 await expect(date).toHaveValue(current);await expect(cursor(page)).toHaveCount(0);
 const latest=minuteSlots.indexOf('14:59');
 await expect.poll(async()=>(await frame(page))?.series['价格'][latest]).toBe(10.75);
 fixture.snapshot.watch[0].quote.price='10.82';
 await page.clock.runFor(3100);
 await expect.poll(async()=>(await frame(page))?.series['价格'][latest]).toBe(10.82);

 // The current trading day becomes replayable only after the market is closed.
 fixture.snapshot.market_open=false;
 await page.clock.runFor(121000);
 await expect(date).toHaveValue(current);await expect(replay).toBeEnabled();
 await replay.click();await expect(cursor(page)).toHaveText('09:30');
 await expect(page.getByRole('button',{name:'返回最新分时'})).toBeVisible();
 await page.getByRole('button',{name:'退出回放'}).click();
 await expect(page.getByRole('group',{name:'分时显示选项'})).toBeVisible();

 await date.selectOption(day);await replay.click();
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(cursor(page)).toHaveCount(0);
 await page.getByRole('button',{name:'分时',exact:true}).click();
 await expect(page.getByRole('group',{name:'分时显示选项'})).toBeVisible();
 await replay.click();await page.getByRole('button',{name:'下一支自选股'}).click();
 await expect(date).toHaveValue(current);await expect(cursor(page)).toHaveCount(0);
 await expect.poll(async()=>(await frame(page))?.series['价格'][1]).toBe(32.5);
 expect(minuteSlots.slice(120,122)).toEqual(['11:30','13:01']);
 expect(minuteSlots.at(-1)).toBe('15:00');
});

test('replay shows confirmed top, bottom and volume signals using only reached minutes',async({page})=>{
 await page.clock.install({time:new Date(current+'T16:00:00+08:00')});
 const target='sh603938',date='2026-11-12';
 const source=JSON.parse(readFileSync('tests/ui/fixtures/turning-final-20261112-cases.json','utf8')).find((row:any)=>row.code===target);
 const rows=[{time:'09:30',close:String(source.opening_price),average:String(source.opening_price),volume:0,complete:true},
  ...source.prices.map((price:number,i:number)=>({time:minuteSlots[i+1],close:String(price),average:String(source.averages[i]),volume:source.volumes[i],complete:true}))];
 const fixture=JSON.parse(readFileSync('public/preview.json','utf8'));
 fixture.snapshot.watch=fixture.snapshot.watch.filter((row:any)=>row.code===target);
 fixture.minutes[target]=[{day:date,data:{date,symbol:target,bars:rows,previous_close:String(source.opening_price),cached_at:date+'T15:01:00+08:00'}}];
 const event={key:'replay-volume',symbol:target.slice(2),trading_date:date,candidate_time:'09:32',confirmation_label:'09:34',event_label:'09:34',mode:'history',volumes:[1,2,3]};
 fixture.snapshot.events=[event,{...event,key:'other-stock',symbol:'000981',candidate_time:'09:33'},
  {...event,key:'other-day',trading_date:day,candidate_time:'09:34'}];
 fixture.history[target].events=[];
 await page.route('**/preview.json',route=>route.fulfill({json:fixture}));
 await page.addInitScript(()=>{localStorage.setItem('stock-monitor-show-turning-shapes-v1','false');localStorage.setItem('stock-monitor-show-trigger-volume','false');});
 await page.goto('/');await page.getByRole('button',{name:'历史回放',exact:true}).click();
 await expect(cursor(page)).toHaveText('09:30');
 await page.getByRole('button',{name:'暂停回放'}).click();
 const advance=async(count:number)=>{
  await page.getByRole('button',{name:'单步前进'}).evaluate((button,n)=>{for(let i=0;i<n;i++)(button as HTMLButtonElement).click();},count);
 };
 await advance(3);await expect(cursor(page)).toHaveText('09:33');
 expect((await frame(page))!.marks.some((m:any)=>m.value==='高')).toBe(false);
 await advance(1);await expect(cursor(page)).toHaveText('09:34');
 await expect.poll(async()=>(await frame(page))!.marks.filter((m:any)=>m.value==='高').map((m:any)=>m.coord[0])).toEqual(['09:32']);
 const expected=(time:string)=>turningDisplayPoints(turningFinal(rows.filter(b=>b.time<=time),TURNING_FINAL_MODES.zhangle),
  turningQualityQ1(rows.filter(b=>b.time<='15:00'&&b.time!=='09:30'&&b.time<=time)),true,true)
  .map(m=>[m.kind==='bottom'?'底信号':'顶信号',m.time,m.price]).sort();
 const all=expected('15:00');
 expect(all.some(m=>m[0]==='顶信号')).toBe(true);expect(all.some(m=>m[0]==='底信号')).toBe(true);
 const actual=async()=>((await frame(page))!.marks.filter((m:any)=>m.turningKind).map((m:any)=>[m.value,...m.coord]).sort());
 const first=all.map(m=>String(m[1])).sort()[0],at=minuteSlots.indexOf(first);
 expect(at).toBeGreaterThan(4);
 await advance(at-5);await expect(cursor(page)).toHaveText(minuteSlots[at-1]);
 expect(await actual()).toEqual(expected(minuteSlots[at-1]));
 await advance(1);await expect(cursor(page)).toHaveText(first);
 await expect.poll(actual).toEqual(expected(first));
 await advance(minuteSlots.length-1-at);await expect(cursor(page)).toHaveText('15:00');
 await expect.poll(actual).toEqual(all);
 await page.getByRole('button',{name:'从头播放'}).click();
 await expect.poll(async()=>(await frame(page))!.marks.length).toBe(0);
 await page.getByRole('button',{name:'退出回放'}).click();
 await expect(page.getByRole('checkbox',{name:'底/顶',exact:true})).not.toBeChecked();
});
