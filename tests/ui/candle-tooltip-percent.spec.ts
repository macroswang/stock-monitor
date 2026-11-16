import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

function fixture(){
 const f=JSON.parse(readFileSync('public/preview.json','utf8'));
 const rows=[['2026-10-09',9,10],['2026-10-12',12,11],['2026-10-13',9,9.9],['2026-10-14',9.8,9.9],['2026-10-15',9.9,9.90001],['2026-10-16',10,11],['2026-10-19',12,9]].map(([date,open,close])=>({date,open:String(open),close:String(close),high:String(Math.max(Number(open),Number(close))+.1),low:String(Math.min(Number(open),Number(close))-.1),volume:'10000',provisional:date==='2026-10-19'}));
 f.history.sh603002.daily=rows;f.daily.sh603002=rows.map(data=>({day:data.date,data}));
 // Today's quote is deliberately unrelated to the selected historical candle.
 f.snapshot.watch[0].quote={code:'sh603002',price:'999',previous_close:'1',change:'998',timestamp:'2026-10-16T16:00:00+08:00'};
 return f;
}
async function tip(page:Page,view:'日K'|'周K',date:string){
 const chart=page.getByLabel(view==='日K'?'日K线及成交量':'周K线及成交量',{exact:true});
 // The viewport fit and ECharts resize each run on the next render cycle.
 // Hover only after both have settled; keep the exact OHLC/return assertions.
 await chart.evaluate(async()=>{for(let i=0;i<3;i++)await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));});
 await chart.evaluate(async(el,date)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),index=o.xAxis[0].data.indexOf(date);
  if(index<0)throw Error('Missing test candle '+date);c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:index});
 },date);
 return chart.locator('.daily-tooltip .quote-detail').filter({hasText:/^涨跌幅：/});
}

test('daily tooltip compares the hovered close to the prior close, preserves OHLC layout and rounds flat changes neutrally',async({page},info)=>{
 const f=fixture();await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
 for(const [date,value,color] of [['2026-10-12','+10.00%','rgb(237, 125, 129)'],['2026-10-13','-10.00%','rgb(81, 199, 170)'],['2026-10-14','0.00%','rgb(231, 237, 247)'],['2026-10-15','0.00%','rgb(231, 237, 247)']]){
  const row=await tip(page,'日K',date);await expect(row).toHaveText('涨跌幅：'+value);await expect(row.locator('span').last()).toHaveCSS('color',color);
 }
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:900});const row=await tip(page,'日K','2026-10-12');await expect(row).toHaveText('涨跌幅：+10.00%');
  const popup=page.getByLabel('日K线及成交量',{exact:true}).locator('.daily-tooltip');await expect(popup).toContainText('开盘：12.00 元');await expect(popup).toContainText('收盘：11.00 元');
  expect(await popup.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);const box=(await popup.boundingBox())!;expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(width);
 }
 await page.getByLabel('日K线及成交量',{exact:true}).screenshot({path:info.outputPath('daily-tooltip-percent.png')});
});

test('weekly tooltip uses the preceding week close and marks an unfinished week without using later candles',async({page})=>{
 const f=fixture();await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'周K',exact:true}).click();
 await expect(await tip(page,'周K','2026-10-16')).toHaveText('涨跌幅：+10.00%');
 const negative=await tip(page,'周K','2026-10-19');await expect(negative).toHaveText('涨跌幅：-18.18%');await expect(negative.locator('span').last()).toHaveCSS('color','rgb(81, 199, 170)');
 await expect(page.getByLabel('周K线及成交量',{exact:true}).locator('.daily-tooltip')).toContainText('含盘中数据');
 f.history.sh603002.daily.at(-1).close='888';f.daily.sh603002.at(-1).data.close='888';await page.reload();await page.getByRole('button',{name:'周K',exact:true}).click();
 await expect(await tip(page,'周K','2026-10-16')).toHaveText('涨跌幅：+10.00%');
});

test('missing or invalid prior close displays unavailable instead of inventing an opening-price return',async({page})=>{
 const f=fixture();await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(await tip(page,'日K','2026-10-09')).toHaveText('涨跌幅：—（缺少前收盘）');
 for(const invalid of ['0','NaN','']){
  f.history.sh603002.daily[0].close=invalid;await page.reload();await page.getByRole('button',{name:'日K',exact:true}).click();
  await expect(await tip(page,'日K','2026-10-12')).toHaveText('涨跌幅：—（缺少前收盘）');
 }
});

test('unfinished prior candles are not presented as settled previous closes in either view',async({page})=>{
 const f=fixture();f.history.sh603002.daily[0].provisional=true;
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');
 for(const [view,date] of [['日K','2026-10-12'],['周K','2026-10-16']] as const){
  await page.getByRole('button',{name:view,exact:true}).click();
  await expect(await tip(page,view,date)).toHaveText('涨跌幅：—（前收盘未确认）');
 }
});

test('invalid hovered closes have their own unavailable reason in daily and weekly tooltips',async({page})=>{
 const f=fixture();await page.route('**/preview.json',r=>r.fulfill({json:f}));
 for(const invalid of ['','0','NaN','Infinity','-1']){
  f.history.sh603002.daily.at(-1).close=invalid;
  await page.goto('/');
  for(const view of ['日K','周K'] as const){
   await page.getByRole('button',{name:view,exact:true}).click();
   if(invalid==='NaN'||invalid==='Infinity'){
    // ECharts omits a non-finite candle from hit testing. Exercise the actual
    // registered formatter directly, rather than expecting a hover target.
    const chart=page.getByLabel(view==='日K'?'日K线及成交量':'周K线及成交量',{exact:true});
    const text=await chart.evaluate(async el=>{
     const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),o=e.getInstanceByDom(el).getOption();
     const root=o.tooltip[0].formatter([{dataIndex:o.xAxis[0].data.indexOf('2026-10-19')}]);
     return Array.from(root.querySelectorAll('.quote-detail')).find(row=>row.textContent?.startsWith('涨跌幅：'))?.textContent;
    });
    expect(text).toBe('涨跌幅：—（当前收盘价无效）');
   }else await expect(await tip(page,view,'2026-10-19')).toHaveText('涨跌幅：—（当前收盘价无效）');
  }
 }
});

test('a week with only completed daily bars still describes its return as observed through that date',async({page})=>{
 const f=fixture();f.history.sh603002.daily.at(-1).provisional=false;
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'周K',exact:true}).click();
 await expect(await tip(page,'周K','2026-10-19')).toHaveText('涨跌幅：-18.18%');
 const popup=page.getByLabel('周K线及成交量',{exact:true}).locator('.daily-tooltip');
 await expect(popup).toContainText('截至该日');await expect(popup).not.toContainText('含盘中数据');
});
