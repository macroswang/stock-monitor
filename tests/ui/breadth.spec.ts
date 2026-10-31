import {test,expect,type Page} from '@playwright/test';

async function openResearch(page:Page){
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('TRIN显示日期数').selectOption('60');
 await page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary-details > summary').click();
}
async function gotoResearch(page:Page){await page.goto('/?panel=breadth');await openResearch(page);}
import {readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';

function setTrin(row:any,value:number|null,basis:'amount'|'volume'){
 const field=basis==='amount'?'trin_amount':'trin';
 row[field]=value;
 if(value==null||value<=0)return;
 const down=row[`decline_${basis}`];
 row[`advance_${basis}`]=row.advance*down/(row.decline*value);
 row[basis==='amount'?'advancing_amount_percent':'advancing_volume_percent']=100*row[`advance_${basis}`]/(row[`advance_${basis}`]+down);
}

function rebuildPcrBand(report:any,date:string){
 const rows=report.days.filter((row:any)=>row.date<=date).sort((a:any,b:any)=>a.date.localeCompare(b.date)).slice(-20);
 if(rows.length!==20)throw new Error('需要20个期权样本');
 const mean=rows.reduce((sum:number,row:any)=>sum+row.pcr,0)/20;
 const sd=Math.sqrt(rows.reduce((sum:number,row:any)=>sum+(row.pcr-mean)**2,0)/20);
 Object.assign(rows.at(-1),{band_lower:mean-2*sd,band_upper:mean+2*sd});
}

test('home shows current market advice and opens the 30/60/90 day chart',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('2026-10-30 · 最近收盘');
 await expect(home).toContainText('静态预览');
 await expect(home).toContainText('先不加仓；空仓继续观望，持仓较重可考虑分批减仓');
 await expect(home).toContainText('原因：上涨股票 16.4%，个股跌多涨少；上证低于20日均线。');
 await expect(home.locator('.home-market-action')).toContainText('操作建议');
 await expect(home.locator('.home-market-reason').first()).toContainText('少数上涨股平均成交额高于下跌股。');
 await expect(home).toContainText('较 10-29 收盘：上涨股票占比上升 1.9 个百分点；上涨股相对平均成交减弱。');
 await expect(home.getByText('成交：少数上涨股相对放量；上涨股平均成交额约为下跌股的 1.48 倍（TRIN 0.674）。')).toBeHidden();
 await expect(home.locator('.home-market-core')).toHaveText('沪深300：上涨组成交额占比高于下跌组（35.4% 对 24.8%）。');
 await expect(home.getByText('后续关注：上涨股票能否变多、上证能否回到20日均线上方。')).toBeVisible();
 const evidence=home.locator('.home-market-evidence');
 await expect(evidence).not.toHaveAttribute('open','');
 await expect(evidence.locator('div')).toBeHidden();
 await evidence.locator('summary').click();
 await expect(evidence.locator('div')).toBeVisible();
 await expect(home.getByText('成交：少数上涨股相对放量；上涨股平均成交额约为下跌股的 1.48 倍（TRIN 0.674）。')).toBeVisible();
 await expect(evidence).toContainText('趋势阶段尚未确认；操作参考采用本地组合规则。');
 await expect(evidence).toContainText('2026-10-30 收盘沪深股票成交股数较 2026-10-29 增加 12.4%');
 await expect(home).toContainText('长期：8.3% 的有效股票高于年线（2026-10-30 收盘）。');
 await expect(home).toContainText('成交：少数上涨股相对放量；上涨股平均成交额约为下跌股的 1.48 倍（TRIN 0.674）。');
 await expect(home).toContainText('上涨组成交额更集中在沪深300。');
 await expect(home.locator('.home-market-core')).toBeVisible();
 await expect(page.locator('.detail')).toBeVisible();
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 const range=page.getByRole('group',{name:'图表时间范围'});
 await expect(range.getByRole('button',{name:'30日'})).toBeVisible();
 await expect(range.getByRole('button',{name:'60日'})).toBeVisible();
 await expect(range.getByRole('button',{name:'90日'})).toBeVisible();
});

test('home treats a broad rebound below the moving average as mixed, not a confirmed reversal',async({page})=>{
 // Use the real 10/28 numbers but synthetic collection times to exercise the
 // current-day UI; the underlying historical data was collected on 10/29.
 await page.clock.install({time:new Date('2026-10-28T09:30:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 breadth.days=breadth.days.filter((r:any)=>r.date<='2026-10-28');
 breadth.days.at(-1).collected_at='2026-10-28T17:00:00+08:00';
 const index=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 index.daily=index.daily.filter((r:any)=>r.date<='2026-10-28');
 index.weekly=index.weekly.filter((r:any)=>r.date<='2026-10-28');
 index.latest_eligible='2026-10-28';index.collected_at='2026-10-28T17:00:00+08:00';
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('市场分化，先观察');
 await expect(home).toContainText('暂不加仓，先观察');
 await expect(home).toContainText('上涨股票 74.2%，个股涨多跌少；上证低于20日均线');
 await expect(home).not.toContainText('分批加仓');
 await expect(home).not.toContainText('趋势反转');
});

test('a flat-dominated market does not trigger position changes from small moving groups',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const row=breadth.days.at(-1),active=row.covered-row.suspended;
 row.advance=600;row.decline=100;row.flat=active-700;row.advancing_percent=100*row.advance/active;
 setTrin(row,0.65,'amount');
 const index=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 const daily=index.daily.at(-1);daily.vw_dif=2;daily.vw_dea=1;
 index.weekly.at(-1).vw_dif=2;index.weekly.at(-1).vw_dea=1;
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 const home=page.getByRole('region',{name:'首页市场判断'});
 for(const [price,advance,decline] of [[3500,600,100],[3900,600,100],[3500,100,600],[3900,100,600]]){
  daily.close=price;row.advance=advance;row.decline=decline;row.advancing_percent=100*advance/active;
  setTrin(row,0.65,'amount');
  await page.goto('/?sample=csi300');
  await expect(home).toContainText('市场分化，先观察');
  await expect(home).toContainText('多数个股平盘');
  await expect(home).toContainText('暂不加仓，先观察');
  await expect(home).not.toContainText('分批减仓');
  await expect(home).not.toContainText('分批加仓');
  const reading=page.getByLabel('首页趋势解读');
  await expect(reading).toContainText('多数股票平盘，涨跌组的成交对比仅覆盖少数股票。');
  await expect(reading).not.toContainText('上涨股票很少，但这部分股票平均成交较大。');
 }
});

test('home shows historical breadth momentum only for comparable, available closes',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const prior=report.days.at(-2),current=report.days.at(-1);
 const make=(day:string,value:number,samples:number)=>({date:day,value,samples,source:'已核对历史来源',universe:'相同沪深股票范围',collected_at:'2026-10-31T03:00:00+08:00'});
 current.mcl_history=make(current.date,-342.98,143);prior.mcl_history=make(prior.date,-228.42,142);
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 const home=page.getByRole('region',{name:'首页市场判断'});
 await page.goto('/?sample=csi300');
 await home.locator('.home-market-evidence summary').click();
 await expect(home.getByText('宽度辅助：市场宽度动能较上一交易日减弱（2026-10-30 收盘参考）。')).toBeVisible();
 await expect(home).toContainText('先不加仓');
 prior.historical=true;prior.mcl_standard=-228.42;prior.mcl_samples=142;
 prior.source='已核对历史来源';prior.universe='相同沪深股票范围';prior.mcl_history=undefined;
 await page.goto('/?sample=csi300');
 await home.locator('.home-market-evidence summary').click();
 await expect(home.getByText('宽度辅助：市场宽度动能较上一交易日减弱（2026-10-30 收盘参考）。')).toBeVisible();
 prior.historical=false;prior.mcl_standard=null;prior.mcl_samples=0;
 for(const mutation of ['source','samples','future','date']){
  prior.mcl_history=make(prior.date,-228.42,142);
  if(mutation==='source')prior.mcl_history.source='另一来源';
  if(mutation==='samples')prior.mcl_history.samples=141;
  if(mutation==='future')prior.mcl_history.collected_at='2026-10-31T05:00:00+08:00';
  if(mutation==='date')prior.mcl_history.date='2026-10-28';
  await page.goto('/?sample=csi300');
  await expect(home).not.toContainText('宽度辅助：市场宽度动能');
  await expect(home).toContainText('先不加仓');
 }
});

test('compact home advice remains readable at desktop widths',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 for(const width of [1000,1380]){
  await page.setViewportSize({width,height:900});
  await expect(home.locator('.home-market-summary')).toBeVisible();
  await expect(home.locator('.home-market-reason')).toBeVisible();
  await expect(home.locator('.home-market-evidence div')).toBeHidden();
  expect(await home.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
 }
});

test('home highlights the low breadth and low TRIN combination only when both conditions hold',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const row=report.days.at(-1), total=row.advance+row.decline+row.flat;
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 setTrin(row,0.7,'amount');
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).not.toContainText('少数上涨股相对放量');
 row.advance=Math.ceil(total*0.25);row.decline=total-row.flat-row.advance;row.advancing_percent=100*row.advance/total;
 setTrin(row,0.69,'amount');
 await page.reload();
 await expect(home).not.toContainText('少数上涨股相对放量');
 row.advance=Math.floor(total*0.16);row.decline=total-row.flat-row.advance;row.advancing_percent=100*row.advance/total;
 setTrin(row,0.69,'amount');
 await page.reload();
 await expect(home).toContainText('少数上涨股相对放量');
 await expect(home).toContainText('TRIN 0.690');
});

test('home trend explains breadth and TRIN combinations in plain language',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const row=report.days.at(-1),total=row.advance+row.decline+row.flat;
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 const scenarios:[number,number,string][]=[
  [0.16,0.6,'上涨股票很少，但这部分股票平均成交较大'],
  [0.6,0.6,'上涨范围较广，上涨股平均成交也较大'],
  [0.6,1,'涨跌两组平均成交相近'],
  [0.16,1.2,'下跌股平均成交较高']
 ];
 for(const [fraction,trin,description] of scenarios){
  row.advance=Math.floor(total*fraction);row.decline=total-row.flat-row.advance;
  row.advancing_percent=100*row.advance/total;setTrin(row,trin,'amount');
  await page.goto('/?sample=csi300');
  await expect(page.getByLabel('首页趋势解读')).toContainText(description);
 }
});

test('home displays 30, 60 and 90 trading-day trends with real chart values and source gaps',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 await page.goto('/?sample=csi300');
 const region=page.getByRole('region',{name:'首页市场趋势'});
 const chart=region.getByRole('img',{name:'首页上涨家数、成交占比与TRIN趋势'});
 const range=region.getByRole('group',{name:'首页图表时间范围'});
 await expect(chart).toBeVisible();
 for(const n of [30,60,90]){
  await range.getByRole('button',{name:`${n}日`}).click();
  await expect(range.getByRole('button',{name:`${n}日`})).toHaveAttribute('aria-pressed','true');
  await expect(region).toContainText(`最近${n}个交易日`);
  await expect.poll(()=>chart.evaluate(async el=>{
   const source=await fetch('/src/HomeMarketTrend.tsx').then(r=>r.text());
   const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
   const o=e.getInstanceByDom(el)?.getOption(), labels=o?.xAxis[0].data||[];
   const last=labels.indexOf('2026-10-30');
   return {count:labels.filter((s:string)=>!s.startsWith('gap-')).length,hasGap:labels.some((s:string)=>s.startsWith('gap-')),lastTrin:o?.series[2].data[last]};
  })).toEqual({count:n,hasGap:true,lastTrin:0.6742833012775968});
 }
});

test('home trend does not draw a close before it was collected',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T19:00:00Z')});
 await page.goto('/?sample=csi300');
 const region=page.getByRole('region',{name:'首页市场趋势'});
 const chart=region.getByRole('img',{name:'首页上涨家数、成交占比与TRIN趋势'});
 await expect(region).toContainText('有效 29 条');
 await expect.poll(()=>chart.evaluate(async el=>{
  const source=await fetch('/src/HomeMarketTrend.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el)?.getOption(),idx=o?.xAxis[0].data.indexOf('2026-10-30');
  return o?.series.map((series:any)=>series.data[idx]);
 })).toEqual([null,null,null]);
});

test('trend charts break when an adjacent day has unknown provenance',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const prior=report.days.find((d:any)=>d.date==='2026-10-29');
 const source=prior.source,universe=prior.universe;
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 for(const field of ['source','universe']){
  prior.source=source;prior.universe=universe;prior[field]='';
  await page.goto('/?sample=csi300');
  const chart=page.getByRole('img',{name:'首页上涨家数、成交占比与TRIN趋势'});
  await expect.poll(()=>chart.evaluate(async el=>{
   const src=await fetch('/src/HomeMarketTrend.tsx').then(r=>r.text());
   const e=await import(src.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
   const labels=e.getInstanceByDom(el)?.getOption().xAxis[0].data||[];
   const i=labels.indexOf('2026-10-30');
   return i>0&&labels[i-1]?.startsWith('gap-');
  })).toBe(true);
  await page.getByRole('region',{name:'首页市场判断'}).getByRole('button',{name:'查看市场趋势'}).click();
  await openResearch(page);
  const detail=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
  await expect.poll(()=>detail.evaluate(async el=>{
   const src=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
   const e=await import(src.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
   const labels=e.getInstanceByDom(el)?.getOption().xAxis[0].data||[];
   const i=labels.indexOf('2026-10-30');
   return i>0&&labels[i-1]?.startsWith('gap-');
  })).toBe(true);
 }
});

test('home chart and advice both reject a conflicting transaction share',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const row=report.days.at(-1);
 row.advancing_amount_percent=99;
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'}),trend=page.getByRole('region',{name:'首页市场趋势'});
 const chart=trend.getByRole('img',{name:'首页上涨家数、成交占比与TRIN趋势'});
 await expect(home).toContainText('成交结构数据不足');
 await expect(trend.getByLabel('首页趋势解读')).toContainText('数据不足，暂无法解读');
 await expect.poll(()=>chart.evaluate(async el=>{
  const source=await fetch('/src/HomeMarketTrend.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el)?.getOption(),idx=o.xAxis[0].data.indexOf('2026-10-30');
  return {share:o.series[0].data[idx].value,trin:o.series[2].data[idx]};
 })).toEqual({share:null,trin:null});
 // An absent optional share is distinct from a contradictory supplied value.
 row.advancing_amount_percent=null;
 await page.reload();
 await expect(home).toContainText('先不加仓');
 await expect(trend.getByLabel('首页趋势解读')).toContainText('TRIN 0.674');
});

test('home chart explains the selected day without changing the current position reference',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 await page.goto('/?sample=csi300');
 const trend=page.getByRole('region',{name:'首页市场趋势'}),reading=trend.getByLabel('首页趋势解读');
 const chart=trend.getByRole('img',{name:'首页上涨家数、成交占比与TRIN趋势'});
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(reading).toContainText('2026-10-30 · 收盘：上涨 16.4%');
 await expect(reading).toContainText('TRIN 0.674。上涨股票很少，但这部分股票平均成交较大。');
 const point=await chart.evaluate(async el=>{
  const source=await fetch('/src/HomeMarketTrend.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const c=e.getInstanceByDom(el),o=c.getOption(),idx=o.xAxis[0].data.indexOf('2026-10-23');
  return c.convertToPixel({seriesIndex:0},['2026-10-23',o.series[0].data[idx].value/2]);
 });
 await chart.scrollIntoViewIfNeeded();const box=await chart.boundingBox();if(!box)throw Error('图表不可见');
 await page.mouse.click(box.x+point[0],box.y+point[1]);
 await expect(reading).toContainText('2026-10-23 · 收盘：上涨 80.4%');
 await expect(reading).toContainText('TRIN 1.066。涨跌两组平均成交相近');
 await expect(reading).toContainText('历史数据，操作参考以首页上方为准');
 await expect(home).toContainText('2026-10-30 · 最近收盘');
 await expect(home).toContainText('先不加仓；空仓继续观望');
 await reading.getByRole('button',{name:'查看最新'}).click();
 await expect(reading).toContainText('2026-10-30 · 收盘');
});

test('home chart and advice age out together for the captured intraday market',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 breadth.days=[...breadth.days.filter((row:any)=>row.date<captured.day.date),captured.day];
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:[captured.quote],minute:null};
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 const reading=page.getByLabel('首页趋势解读');
 await expect(home).toContainText('2026-10-30 · 盘中暂值');
 await expect(home).toContainText('先不加仓；空仓继续观望');
 await expect(reading).toContainText('2026-10-30 · 盘中暂值：上涨 18.2%');
 await expect(reading).toContainText('TRIN 0.735');
 await page.clock.fastForward('05:01');
 await expect(home).not.toContainText('先不加仓；空仓继续观望');
 await expect(reading).toContainText('2026-10-30 · 数据不足，暂无法解读');
});

test('home chart and advice refresh together when a new intraday snapshot arrives',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const row=structuredClone(captured.day);
 breadth.days=[...breadth.days.filter((item:any)=>item.date<row.date),row];
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:[captured.quote],minute:null};
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'}),reading=page.getByLabel('首页趋势解读');
 await expect(reading).toContainText('上涨 18.2%');
 await page.clock.fastForward('03:00');
 const total=row.advance+row.decline+row.flat;
 row.advance=Math.floor(total*.12);row.decline=total-row.flat-row.advance;row.advancing_percent=100*row.advance/total;
 Object.assign(row,{first_quote:'2026-10-30T10:05:00+08:00',last_quote:'2026-10-30T10:05:25+08:00',collected_at:'2026-10-30T10:05:27+08:00'});
 setTrin(row,.65,'amount');
 preview.market.quotes[0]={...captured.quote,timestamp:'2026-10-30T10:05:36+08:00',price:'3500'};
 preview.snapshot.now='2026-10-30T10:05:36+08:00';
 await page.clock.fastForward('00:30');
 await expect(reading).toContainText('上涨 12.0%');
 await expect(reading).toContainText('TRIN 0.650');
 await expect(home).toContainText('上涨股票 12.0%');
 await expect(home).toContainText('先不加仓；空仓继续观望');
});

test('volume comparison requires complete consecutive same-source closed sessions',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('总成交：2026-10-30 收盘沪深股票成交股数较 2026-10-29 增加 12.4%');
 const previous=breadth.days.at(-2),latest=breadth.days.at(-1);
 previous.source='另一个来源';
 await page.reload();
 await expect(home).not.toContainText('总成交：');
 previous.source=latest.source;latest.adl_gap_before=true;
 await page.reload();
 await expect(home).not.toContainText('总成交：');
 latest.adl_gap_before=false;latest.flat_volume=null;
 await page.reload();
 await expect(home).not.toContainText('总成交：');
});

test('home waits for index history collection before giving an action',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T09:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 breadth.days.at(-1).collected_at='2026-10-30T15:30:00+08:00';
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('数据不足，等待更新');
 await expect(home).not.toContainText('先不加仓');
 await page.clock.setFixedTime(new Date('2026-10-30T20:00:00Z'));
 await page.reload();
 await expect(home).toContainText('先不加仓');
});

test('home explains why an unconfigured calendar cannot produce intraday advice',async({page})=>{
 await page.clock.install({time:new Date('2027-01-04T02:00:30Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 Object.assign(breadth.days.at(-1),{date:'2027-01-04',status:'provisional',first_quote:'2027-01-04T10:00:00+08:00',last_quote:'2027-01-04T10:00:24+08:00',collected_at:'2027-01-04T10:00:28+08:00'});
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('交易日历未配置');
 await expect(home).toContainText('当年交易日历尚未配置，暂不提供盘中操作参考。');
 await expect(home).not.toContainText('可考虑小幅、分批加仓');
 await expect(home).not.toContainText('持仓较重可考虑分批减仓');
});

test('home does not recommend positions from a weekend or an unverified calendar year',async({page})=>{
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const day=breadth.days.at(-1);
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.clock.install({time:new Date('2026-10-31T09:00:00Z')});
 Object.assign(day,{date:'2026-10-31',status:'closed',collected_at:'2026-10-31T16:00:00+08:00'});
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('数据不足，等待更新');
 await expect(home).not.toContainText('持仓较重可考虑分批减仓');
 await page.clock.setFixedTime(new Date('2027-01-04T09:00:00Z'));
 Object.assign(day,{date:'2027-01-04',status:'closed',collected_at:'2027-01-04T16:00:00+08:00'});
 await page.reload();
 await expect(home).toContainText('当年交易日历尚未配置，暂不提供当前操作参考。');
 await expect(home).not.toContainText('可考虑小幅、分批加仓');
});

for(const kind of ['breadth','index'] as const){
 test(`home retries after a stalled ${kind} request and ignores its late response`,async({page})=>{
  await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
  const filename=kind==='breadth'?'breadth-csi300-preview.json':'index-csi300-preview.json';
  const report=JSON.parse(await readFile(`public/${filename}`,'utf8'));
  let calls=0,release:()=>void=()=>{};
  const pending=new Promise<void>(resolve=>{release=resolve;});
  await page.route(`**/${filename}`,async route=>{
   const first=++calls===1;
   if(first)await pending;
   await route.fulfill({json:first?{...report,error:'过期响应'}:report});
  });
  await page.goto('/?sample=csi300',{waitUntil:'domcontentloaded'});
  const home=page.getByRole('region',{name:'首页市场判断'});
  await expect.poll(()=>calls).toBe(1);
  await page.clock.fastForward(12001);
  await expect(home).toContainText(kind==='breadth'?'市场数据更新失败':'指数数据更新失败');
  await page.clock.fastForward(18000);
  await expect.poll(()=>calls).toBeGreaterThanOrEqual(2);
  await expect(home).toContainText('先不加仓；空仓继续观望');
  const late=page.waitForResponse(response=>response.url().includes(filename)&&response.status()===200);
  release();
  await late;
  await expect(home).not.toContainText('更新失败');
  await expect(home).toContainText('先不加仓；空仓继续观望');
 });
}

test('chart basis selection does not change the fixed amount-based advice',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('TRIN 0.674');
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(page.getByLabel('市场解读')).toContainText('TRIN 0.602');
 await page.getByRole('button',{name:'自选监控'}).click();
 await expect(home).toContainText('TRIN 0.674');
 await expect(home).toContainText('本机规则 · 成交额口径');
 await expect(page.getByLabel('首页趋势解读')).toContainText('TRIN 0.602');
 await expect(home).toContainText('上涨组成交额更集中在沪深300');
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 await expect(page.getByLabel('TRIN计算口径')).toHaveValue('volume');
 await expect(page.getByLabel('市场解读')).toContainText('TRIN 0.602');
});

for(const kind of ['csi300','pcr'] as const){
 test(`home retries stalled ${kind} observations without accepting the late response`,async({page})=>{
  await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
  const filename=kind==='csi300'?'csi300-preview.json':'pcr-preview.json';
  const report=JSON.parse(await readFile(`public/${filename}`,'utf8'));
  if(kind==='pcr'){
   const row=report.days.find((r:any)=>r.date==='2026-10-30');
   row.call_volume=1000;row.put_volume=400;row.pcr=.4;
   rebuildPcrBand(report,'2026-10-30');
  }
  let calls=0,release:()=>void=()=>{};
  const pending=new Promise<void>(resolve=>{release=resolve;});
  await page.route(`**/${filename}`,async route=>{
   const first=++calls===1;
   if(first)await pending;
   await route.fulfill({json:first?(kind==='csi300'?{...report,decline_amount_percent:99}:{...report,error:'过期响应',days:[]}):report});
  });
  await page.goto('/?sample=csi300');
  const home=page.getByRole('region',{name:'首页市场判断'});
  await expect.poll(()=>calls).toBe(1);
  await page.clock.fastForward(12001);
  if(kind==='csi300')await expect(home.locator('.home-market-core')).toHaveCount(0);
  else await expect(home).not.toContainText('50ETF 看跌/看涨成交比低于参考区间');
  await page.clock.fastForward('03:00');
  await expect.poll(()=>calls).toBeGreaterThanOrEqual(2);
  if(kind==='csi300')await expect(home.locator('.home-market-core')).toContainText('35.4% 对 24.8%');
  else await expect(home).toContainText('50ETF 看跌/看涨成交比低于参考区间');
  const late=page.waitForResponse(response=>response.url().includes(filename)&&response.status()===200);
  release();await late;
  if(kind==='csi300')await expect(home.locator('.home-market-core')).toContainText('35.4% 对 24.8%');
  else await expect(home).toContainText('50ETF 看跌/看涨成交比低于参考区间');
 });
}

test('home explains which completed trends support an add-position reference',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const day=breadth.days.at(-1),total=day.advance+day.decline+day.flat;
 day.advance=Math.floor(total*.6);day.decline=total-day.flat-day.advance;day.advancing_percent=100*day.advance/total;setTrin(day,.7,'amount');
 const index=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 Object.assign(index.daily.at(-1),{close:4000,boll_mid:3900,vw_dif:2,vw_dea:1});
 Object.assign(index.weekly.at(-1),{vw_dif:1,vw_dea:1});
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('可考虑小幅、分批加仓');
 await expect(home).toContainText('量价：日线和周线均偏强（日线 2026-10-30、周线 2026-10-30 收盘）。');
 index.weekly.at(-1).vw_dea=-1;
 await page.reload();
 await expect(home).toContainText('暂不加仓');
 await expect(home).not.toContainText('日线和周线均偏强');
});

test('late index response cannot overwrite a newer data failure',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 let release!:()=>void,requests=0;
 const delayed=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/index-csi300-preview.json',async route=>{
  requests++;
  if(requests===1){await delayed;await route.fulfill({json:report});}
  else await route.fulfill({json:{...report,error:'指数更新失败'}});
 });
 await page.goto('/?sample=csi300',{waitUntil:'domcontentloaded'});
 await expect.poll(()=>requests).toBe(1);
 await page.clock.fastForward('00:30');
 await expect.poll(()=>requests).toBe(2);
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('指数数据更新失败');
 const late=page.waitForResponse(response=>response.url().includes('/index-csi300-preview.json')&&response.status()===200);
 release();await late;
 await page.waitForTimeout(100);
 await expect(home).not.toContainText('先不加仓');
 await expect(home).toContainText('指数数据更新失败');
});

test('home expires a live action even if subsequent data requests hang',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 breadth.days=[...breadth.days.filter((row:any)=>row.date<captured.breadth.date),captured.breadth];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:captured.quotes,minute:null};
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 let release!:()=>void,halt=false;
 const stalled=new Promise<void>(resolve=>{release=resolve;});
 for(const [name,data] of [['breadth-preview.json',breadth],['preview.json',preview],['index-technical-preview.json',index]] as const){
  await page.route(`**/${name}`,async route=>{if(halt)await stalled;await route.fulfill({json:data});});
 }
 await page.goto('/');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('2026-10-30 · 盘中暂值');
 await expect(home).toContainText('先不加仓');
 halt=true;
 await page.clock.fastForward('02:00');
 await expect(home).toContainText('数据不足，等待更新');
 await expect(home).not.toContainText('先不加仓');
 release();
});

test('trend interpretation expires during stalled market requests',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 breadth.days=[...breadth.days.filter((row:any)=>row.date<captured.breadth.date),captured.breadth];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:captured.quotes,minute:null};
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 let release!:()=>void,halt=false;
 const stalled=new Promise<void>(resolve=>{release=resolve;});
 for(const [name,data] of [['breadth-preview.json',breadth],['preview.json',preview],['index-technical-preview.json',index]] as const){
  await page.route(`**/${name}`,async route=>{if(halt)await stalled;await route.fulfill({json:data});});
 }
 await page.goto('/?panel=breadth');
 const interpretation=page.getByLabel('市场解读');
 await expect(interpretation).toContainText('2026-10-30 · 盘中暂值');
 halt=true;
 await page.clock.fastForward('05:15');
 await expect(interpretation).toContainText('盘中数据已过期，等待更新后解读');
 await expect(page.getByText(/盘中快照已过期/)).toBeVisible();
 release();
});

test('home only describes CSI 300 concentration for the matching validated snapshot',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const core=JSON.parse(await readFile('public/csi300-preview.json','utf8'));
 let requests=0;
 await page.route('**/csi300-preview.json',route=>{requests++;return route.fulfill({json:core});});
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('上涨组成交额更集中在沪深300。');
 await expect(home.locator('.home-market-reason')).toContainText('上涨组成交额相对更集中在沪深300成分股。');
 await page.clock.fastForward('01:00');
 expect(requests).toBe(1);
 core.collected_at='2026-10-31T03:13:31.055070+08:00';
 await page.reload();
 await expect.poll(()=>requests).toBe(2);
 await expect(home).toContainText('少数上涨股相对放量');
 await expect(home).not.toContainText('成交额更集中在沪深300');
 await expect(home.locator('.home-market-reason')).not.toContainText('成交额相对更集中在沪深300成分股');
 await expect(home.locator('.home-market-core')).toHaveCount(0);
 core.collected_at='2026-10-31T03:14:31.055070+08:00';
 core.member_collected_at='2026-11-01T03:14:31.055070+08:00';
 core.available_at=core.member_collected_at;
 await page.reload();
 await expect.poll(()=>requests).toBe(3);
 await expect(home.locator('.home-market-reason')).not.toContainText('成交额相对更集中在沪深300成分股');
 await expect(home.locator('.home-market-core')).toHaveCount(0);
 core.member_collected_at='2026-10-31T03:14:31.055070+08:00';
 core.available_at=core.member_collected_at;
 core.decline_amount_percent=99;
 await page.reload();
 await expect.poll(()=>requests).toBe(4);
 await expect(home).not.toContainText('成交额更集中在沪深300');
 await expect(home.locator('.home-market-reason')).not.toContainText('成交额相对更集中在沪深300成分股');
 await expect(home.locator('.home-market-core')).toHaveCount(0);
});

test('home describes whether CSI 300 share is higher, lower or similar',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const core=JSON.parse(await readFile('public/csi300-preview.json','utf8'));
 await page.route('**/csi300-preview.json',route=>route.fulfill({json:core}));
 await page.goto('/?sample=csi300');
 const summary=page.locator('.home-market-core');
 await expect(summary).toContainText('上涨组成交额占比高于下跌组（35.4% 对 24.8%）');
 await expect(page.locator('.home-market-reason')).toContainText('上涨组成交额相对更集中在沪深300成分股。');
 core.decline_amount=core.market_decline_amount*.5;core.decline_amount_percent=50;
 await page.reload();
 await expect(summary).toContainText('上涨组成交额占比低于下跌组（35.4% 对 50.0%）');
 await expect(page.locator('.home-market-reason')).toContainText('下跌组成交额相对更集中在沪深300成分股。');
 core.decline_amount_percent=core.advance_amount_percent;
 core.decline_amount=core.market_decline_amount*core.decline_amount_percent/100;
 await page.reload();
 await expect(summary).toContainText('上涨组成交额占比接近下跌组（35.4% 对 35.4%）');
 await expect(page.locator('.home-market-reason')).not.toContainText('成交额相对更集中在沪深300成分股');
});

test('home surfaces only dated unusual ETF PCR readings without changing the action',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
 const a=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 const b=JSON.parse(await readFile('public/pcr300-preview.json','utf8'));
 const ar=a.days.find((row:any)=>row.date==='2026-10-30');
 const br=b.days.find((row:any)=>row.date==='2026-10-30');
 ar.call_volume=1000;ar.put_volume=400;ar.pcr=0.4;
 br.call_volume=1000;br.put_volume=1200;br.pcr=1.2;
 rebuildPcrBand(a,'2026-10-30');rebuildPcrBand(b,'2026-10-30');
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:a}));
 await page.route('**/pcr300-preview.json',route=>route.fulfill({json:b}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('期权：50ETF 看跌/看涨成交比低于参考区间；300ETF 看跌/看涨成交比高于参考区间（2026-10-30 收盘，20日参考）。');
 await expect(home).toContainText('先不加仓；空仓继续观望，持仓较重可考虑分批减仓');
 a.error='更新失败';br.collected_at='2026-11-01T10:00:00+08:00';
 await Promise.all([page.waitForResponse('**/pcr-preview.json'),page.waitForResponse('**/pcr300-preview.json'),page.reload()]);
 await expect(home).toContainText('先不加仓');
 await expect(home).not.toContainText('期权：');
});

test('home excludes PCR alerts with pre-close captures or inconsistent turnover',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
 const report=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 const row=report.days.find((value:any)=>value.date==='2026-10-30');
 Object.assign(row,{call_volume:1000,put_volume:400,pcr:0.4,collected_at:'2026-10-30T14:59:59+08:00'});
 rebuildPcrBand(report,'2026-10-30');
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('先不加仓');
 await expect(home).not.toContainText('期权：50ETF');
 row.collected_at='2026-10-30T15:01:00+08:00';
 row.put_volume=900;
 await page.reload();
 await expect(home).toContainText('先不加仓');
 await expect(home).not.toContainText('期权：50ETF');
 row.put_volume=400;
 await page.reload();
 await expect(home).toContainText('期权：50ETF 看跌/看涨成交比低于参考区间');
});

test('home PCR alert requires 20 validated consecutive observations and a matching band',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
 const report=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 const row=report.days.find((value:any)=>value.date==='2026-10-30');
 Object.assign(row,{call_volume:1000,put_volume:400,pcr:0.4});
 rebuildPcrBand(report,'2026-10-30');
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('期权：50ETF 看跌/看涨成交比低于参考区间');
 row.band_lower+=0.1;
 await page.reload();
 await expect(home).not.toContainText('期权：50ETF');
 rebuildPcrBand(report,'2026-10-30');
 const removed=report.days.findIndex((value:any)=>value.date==='2026-10-15');
 expect(removed).toBeGreaterThanOrEqual(0);report.days.splice(removed,1);
 await page.reload();
 await expect(home).not.toContainText('期权：50ETF');
 await expect(home).toContainText('先不加仓');
});

test('PCR details reject pre-close captures and inconsistent prior ratios',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
 const a=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 const b=JSON.parse(await readFile('public/pcr300-preview.json','utf8'));
 const currentA=a.days.find((row:any)=>row.date==='2026-10-30');
 const currentB=b.days.find((row:any)=>row.date==='2026-10-30');
 const priorA=a.days.find((row:any)=>row.date==='2026-10-29');
 currentA.collected_at=currentB.collected_at='2026-10-30T14:59:59+08:00';
 const validPrior=priorA.pcr;priorA.pcr=9.999;
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:a}));
 await page.route('**/pcr300-preview.json',route=>route.fulfill({json:b}));
 await page.goto('/?panel=breadth&sample=csi300');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('50ETF 无同日数据 · 300ETF 无同日数据');
 await expect(summary).not.toContainText('9.999');
 await expect(summary).toContainText('期权最近共同记录（2026-10-28 收盘）');
 priorA.pcr=validPrior;
 await page.reload();
 await expect(summary).toContainText('期权最近共同记录（2026-10-29 收盘）');
 currentA.collected_at=currentB.collected_at='2026-10-30T15:00:00+08:00';
 await page.reload();
 await expect(summary).toContainText('50ETF 0.740 · 300ETF 0.826');
});

test('home does not show a purported yearly close captured before market close',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 report.days.at(-1).ma_daily.collected_at='2026-10-30T14:59:59+08:00';
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('先不加仓');
 await expect(home).not.toContainText('长期：');
});

test('home explains both directions and equality of TRIN using the verified basis',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 const home=page.getByRole('region',{name:'首页市场判断'});
 setTrin(report.days.at(-1),1.25,'amount');
 await page.goto('/?sample=csi300');
 await expect(home).toContainText('成交：下跌股平均成交额约为上涨股的 1.25 倍（TRIN 1.250）。');
 await expect(home.locator('.home-market-reason').first()).toContainText('下跌股平均成交额较高。');
 await expect(home).not.toContainText('上涨股票较少，TRIN');
 await expect(home).not.toContainText('少数上涨股相对放量');
 setTrin(report.days.at(-1),1,'amount');
 await page.goto('/?sample=csi300');
 await expect(home).toContainText('成交：上涨与下跌股票平均成交额相同（TRIN 1.000）。');
 await expect(home.locator('.home-market-reason').first()).toContainText('涨跌股平均成交额相同。');
 setTrin(report.days.at(-1),null,'amount');
 await page.goto('/?sample=csi300');
 await expect(home).not.toContainText('成交：');
 await expect(home).toContainText('成交结构数据不足');
 await expect(home.locator('.home-market-reason').first()).not.toContainText('平均成交额');
});

test('home highlights shrinking participation only for comparable consecutive observations',async({page})=>{
 await page.clock.install({time:new Date('2026-10-26T10:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 report.days=report.days.filter((row:any)=>row.date<='2026-10-26');
 const latest=report.days.at(-1),previous=report.days.at(-2);
 latest.collected_at='2026-10-26T15:30:00+08:00';
 previous.collected_at='2026-10-23T15:30:00+08:00';
 const index=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 index.daily=index.daily.filter((row:any)=>row.date<='2026-10-26');
 index.weekly=index.weekly.filter((row:any)=>row.date<='2026-10-26');
 index.latest_eligible='2026-10-26';index.collected_at='2026-10-26T16:30:00+08:00';
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home.locator('.home-market-reason')).toContainText('指数上涨，但上涨股票占比从 80.4% 降至 39.9%');
 await expect(home.locator('.home-market-reason')).toBeVisible();
 await expect(home).toContainText('较 10-23 收盘：上涨股票占比下降');
 previous.source='另一数据源';
 await page.goto('/?sample=csi300');
 await expect(home.locator('.home-market-reason')).not.toContainText('占比从 80.4% 降至');
 await expect(home.locator('.home-market-reason')).toContainText('指数上涨，个股跌多涨少（上涨股票 39.9%）');
 await expect(home).not.toContainText('较 10-23 收盘：');
 previous.source=latest.source;previous.date='2026-10-22';
 await page.goto('/?sample=csi300');
 await expect(home.locator('.home-market-reason')).not.toContainText('占比从 80.4% 降至');
 await expect(home).not.toContainText('较 10-22 收盘：');
});

test('home does not use a prior-day close collected in the future',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T19:00:00Z')});
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('数据不足，等待更新');
 await expect(home).not.toContainText('先不加仓；空仓继续观望');
 await expect(home).not.toContainText('原因：');
});

test('a pre-close sample labelled closed remains unavailable on the next day',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 report.days.at(-1).collected_at='2026-10-30T14:59:59+08:00';
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('数据不足，等待更新');
 await expect(home).not.toContainText('先不加仓');
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 await expect(page.getByText('收盘数据时间尚未到达或采集时间异常，暂不用于市场判断。')).toBeVisible();
 await expect(page.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
});

test('market refresh failure pauses current advice on both home and trend page',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 report.error='全市场数据获取失败';
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('市场数据更新失败');
 await expect(home).not.toContainText('先不加仓');
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 const summary=page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary');
 await expect(summary).toContainText('市场数据更新失败，等待恢复后再查看操作参考');
 await expect(summary.locator('.market-summary-action')).not.toContainText('分批减仓');
 await expect(page.getByRole('img',{name:/上涨股成交额占比柱状图/})).toBeVisible();
 report.error='';
 await page.goto('/?sample=csi300');
 await expect(home).toContainText('先不加仓；空仓继续观望');
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 await expect(summary.locator('.market-summary-action')).toContainText('先不加仓；空仓继续观望');
});

test('index refresh failure pauses advice even when the last index snapshot exists',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 report.error='指数更新失败';
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('指数数据更新失败');
 await expect(home).not.toContainText('分批减仓');
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 const summary=page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary');
 await expect(summary.locator('.market-summary-action')).toContainText('指数数据更新失败，等待恢复后再查看操作参考');
 await expect(summary.locator('.market-summary-action')).not.toContainText('分批减仓');
 await expect(page.getByRole('img',{name:/上涨股成交额占比柱状图/})).toBeVisible();
 report.error='';
 await page.goto('/?sample=csi300');
 await expect(home).toContainText('先不加仓；空仓继续观望');
});

test('a failed breadth request pauses advice while preserving the chart',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 let calls=0;
 await page.route('**/breadth-csi300-preview.json',route=>++calls===1?route.fulfill({json:report}):route.abort());
 await page.goto('/?panel=breadth&sample=csi300');
 const summary=page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary');
 await expect(summary.locator('.market-summary-action')).toContainText('先不加仓');
 await page.clock.fastForward('00:30');
 await expect(summary.locator('.market-summary-action')).toContainText('市场数据更新失败');
 await expect(page.getByRole('img',{name:/上涨股成交额占比柱状图/})).toBeVisible();
});

test('main market chart switches 30 60 90 records and selects a date',async({page})=>{
 await page.goto('/?panel=breadth');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 const trend=page.getByRole('region',{name:'市场趋势图'}),guide=page.getByLabel('图表怎么看');
 const range=page.getByRole('group',{name:'图表时间范围'});
 await expect(chart).toBeVisible();
 await expect(guide).toContainText('蓝线 · 涨的股票多不多');
 await expect(guide).toContainText('红柱 · 成交集中在哪里');
 await expect(guide).toContainText('黄线 · TRIN 怎么看');
 await expect(guide).toContainText('低于 1：上涨股平均成交较高；高于 1：下跌股平均成交较高');
 await expect(guide).toContainText('多数股票下跌、TRIN 较低时，结合趋势阶段观察大资金是否进入少数上涨股');
 const reading=page.getByLabel('市场解读');
 await expect(reading).toContainText('2026-10-29 · 收盘统计 · 成交额口径');
 await expect(reading).toContainText('上涨 14.5%，上涨股票较少；TRIN 0.536，低于 0.6');
 await expect(reading).toContainText('关注大资金是否集中进入少数上涨股');
 await expect(trend).toContainText('2026-10-29 观察：上涨家数占比 14.5% · TRIN 0.536；上涨股平均成交额约为下跌股的 1.87 倍');
 await expect(range.getByRole('button',{name:'30日'})).toHaveAttribute('aria-pressed','true');
 const count=()=>chart.evaluate(async el=>{
  const src=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(src.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  return e.getInstanceByDom(el)?.getOption().xAxis[0].data.filter((s:string)=>!s.startsWith('gap-')).length??0;
 });
 for(const n of [30,60,90]){
  await range.getByRole('button',{name:`${n}日`}).click();
  await expect(range.getByRole('button',{name:`${n}日`})).toHaveAttribute('aria-pressed','true');
  await expect.poll(count).toBe(n);
 }
 await range.getByRole('button',{name:'30日'}).click();
 await expect.poll(count).toBe(30);
 const point=await chart.evaluate(async el=>{
  const src=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(src.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const c=e.getInstanceByDom(el),o=c.getOption(),index=o.xAxis[0].data.indexOf('2026-10-23');
  return c.convertToPixel({seriesIndex:1},['2026-10-23',o.series[1].data[index]]);
 });
 await chart.scrollIntoViewIfNeeded();const box=await chart.boundingBox();if(!box)throw Error('图表不可见');
 await page.mouse.click(box.x+point[0],box.y+point[1]);
 await expect(page.getByRole('region',{name:'市场状态与操作参考'})).toContainText('2026-10-23');
 await expect(trend).toContainText('2026-10-23 观察：上涨家数占比 80.4% · TRIN 1.066；下跌股平均成交额约为上涨股的 1.07 倍');
 await expect(reading).toContainText('2026-10-23 · 历史复核 · 成交额口径');
 await expect(reading).toContainText('上涨股票占比至少一半；TRIN 1.066，接近 1');
 await expect(reading).not.toContainText('关注大资金是否集中进入少数上涨股');
 await range.getByRole('button',{name:'60日'}).click();
 await expect(page.getByRole('region',{name:'市场状态与操作参考'})).toContainText('2026-10-23');
 await range.getByRole('button',{name:'查看最新市场数据'}).click();
 await expect(page.getByRole('region',{name:'市场状态与操作参考'})).toContainText('2026-10-29');
 await expect(reading).toContainText('2026-10-29 · 收盘统计');
 await expect(range.getByRole('button',{name:'查看最新市场数据'})).toBeDisabled();
});

test('main market chart leaves incomplete daily observations empty',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.at(-1).missing=1;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?panel=breadth');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 await expect(page.getByRole('region',{name:'市场趋势图'})).not.toContainText('2026-10-29 观察');
 await expect(page.getByLabel('市场解读')).toContainText('数据不足，暂无法解读市场');
 await expect.poll(()=>chart.evaluate(async el=>{
  const src=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(src.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el)?.getOption();if(!o)return false;
  const i=o.xAxis[0].data.indexOf('2026-10-29');return i>=0&&o.series.every((s:any)=>s.data[i]==null);
 })).toBe(true);
});

test('30-day range counts trading sessions instead of expanding to replace a missing day',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days=report.days.filter((d:any)=>d.date!=='2026-10-20');
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?panel=breadth');
 const trend=page.getByRole('region',{name:'市场趋势图'});
 await expect(trend).toContainText('2026-09-10 至 2026-10-29 · 29 条记录');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 await expect.poll(()=>chart.evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const labels=e.getInstanceByDom(el)?.getOption().xAxis[0].data||[];
  return labels.includes('2026-09-10')&&!labels.includes('2026-09-09')&&!labels.includes('2026-10-20')&&labels.some((x:string)=>x.startsWith('gap-'));
 })).toBe(true);
});

test('market interpretation updates for TRIN boundaries, breadth and selected basis',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const d=report.days.at(-1);
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 for(const [value,expected] of [[0.49,'低于 0.5'],[0.5,'低于 0.6'],[0.6,'低于 0.7'],[0.7,'低于 1'],[0.9,'接近 1'],[1.1,'接近 1'],[1.11,'高于 1']] as const){
  setTrin(d,value,'amount');
  await page.goto('/?panel=breadth');
  await expect(page.getByLabel('市场解读')).toContainText(expected);
 }
 setTrin(d,0.5,'amount');setTrin(d,1.2,'volume');
 await page.goto('/?panel=breadth');
 await expect(page.getByLabel('市场解读')).toContainText('关注大资金是否集中进入少数上涨股');
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(page.getByLabel('市场解读')).toContainText('成交股数口径');
 await expect(page.getByLabel('市场解读')).toContainText('高于 1，下跌组平均成交较高');
 await expect(page.getByLabel('市场解读')).not.toContainText('关注大资金是否集中进入少数上涨股');
});

test('market interpretation combines breadth and TRIN without conflating scenarios',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const d=report.days.at(-1),total=d.advance+d.decline+d.flat;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 for(const [breadth,trin,expected] of [
  [80,0.5,'上涨股票覆盖面较广，上涨组相对放量，多头量能较强'],
  [10,0.5,'上涨股票较少且 TRIN 较低，关注大资金是否集中进入少数上涨股'],
  [10,0.95,'量能结构相对中性，还需结合上涨家数观察市场宽度'],
  [10,1.2,'上涨股票不足一半，下跌组相对放量'],
  [80,1.2,'上涨股票覆盖面较广，但下跌组平均成交更高'],
 ] as const){
  d.advancing_percent=breadth;d.advance=Math.round(total*breadth/100);d.decline=total-d.advance-d.flat;setTrin(d,trin,'amount');
  await page.goto('/?panel=breadth');
  await expect(page.getByLabel('市场解读')).toContainText(expected);
 }
});

test('low TRIN interpretation follows manually chosen trend stage and resets for another date',async({page})=>{
 await page.goto('/?panel=breadth');
 const reading=page.getByLabel('市场解读');
 await expect(reading).toContainText('TRIN 0.536');
 await expect(reading).toContainText('趋势阶段未确认，低 TRIN 暂按成交结构观察');
 await expect(reading).not.toContainText('手动选择的趋势');
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('当前趋势阶段').selectOption('early');
 await expect(reading).toContainText('手动选择的趋势前段：低 TRIN 仅作成交结构观察，暂不直接判断反转');
 await expect(reading).not.toContainText('趋势阶段未确认');
 await page.getByLabel('当前趋势阶段').selectOption('late');
 await expect(reading).toContainText('手动选择的趋势中后段：结合市场宽度观察短线变化');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-22'}).click();
 await expect(reading).toContainText('2026-10-22');
 await expect(reading).not.toContainText('手动选择的趋势');
});

test('market chart connects verified holidays and breaks on missing days or source changes',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const dates=['2026-09-24','2026-09-28','2026-09-29','2026-09-30','2026-10-08','2026-10-09','2026-10-13','2026-10-14'];
 report.days=report.days.filter((d:any)=>dates.includes(d.date)).map((d:any)=>({...d,source:d.date==='2026-10-14'?'另一来源':'统一来源',universe:'相同股票池'}));
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?panel=breadth');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 await expect.poll(()=>chart.evaluate(async el=>{
  const src=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(src.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const labels=e.getInstanceByDom(el)?.getOption().xAxis[0].data||[];
  const i=labels.indexOf('2026-09-24'),j=labels.indexOf('2026-09-30'),k=labels.indexOf('2026-10-13'),m=labels.indexOf('2026-10-14');
  return i>=0&&labels[i+1]==='2026-09-28'&&labels[j+1]==='2026-10-08'&&labels[k-1]?.startsWith('gap-')&&labels[m-1]?.startsWith('gap-');
 })).toBe(true);
});

test('market summary gives a concise dated action and keeps research collapsed',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T11:00:00Z')});
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('市场偏弱，防守为主');
 await expect(summary).toContainText('操作参考：先不加仓；空仓继续观望，持仓较重可考虑分批减仓');
 await expect(summary).toContainText('原因：上涨股票 14.5%，个股跌多涨少；上证低于20日均线');
 await expect(summary).toContainText('资金观察：上涨股票较少但相对放量，关注大资金是否集中进入少数上涨股');
 await expect(summary).toContainText('市场数据：');
 await expect(summary).toContainText('先不加仓');
 await expect(summary).toContainText('上涨 14.5%');
 await expect(summary).toContainText('TRIN 0.536');
 await expect(summary.locator('.market-summary-structure')).toContainText('不足一半的活跃股票上涨；上涨组的每只平均成交额较高');
 await expect(summary.locator('.market-summary-structure')).toContainText('上涨股平均成交额约为下跌股的 1.87 倍');
 await expect(summary).toContainText('涨跌股成交额占比：上涨股 24.3% · 下跌股 75.7%（不含平盘）');
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(summary.locator('.market-summary-structure')).toContainText('上涨股平均成交额约为下跌股的');
 await expect(summary).toContainText('涨跌股成交额占比：上涨股 24.3% · 下跌股 75.7%（不含平盘）');
 await page.getByLabel('TRIN计算口径').selectOption('amount');
 const evidence=summary.getByLabel('指标依据');
 await expect(evidence).not.toHaveAttribute('open','');
 await evidence.locator(':scope > summary').click();
 await expect(evidence).toHaveAttribute('open','');
 await expect(summary).toContainText('均线上方个股（2026-10-29 收盘，未复权）');
 await expect(summary).toContainText('50ETF 无同日数据 · 300ETF 无同日数据');
 await expect(summary).toContainText('期权最近共同记录（2026-10-28 收盘）：50ETF 0.688 · 300ETF 0.698');
 await expect(summary).toContainText('操作参考结合上证20日均线、涨跌家数与 TRIN');
 const research=page.getByLabel('市场图表与研究详情');
 await expect(research).not.toHaveAttribute('open','');
 await research.locator(':scope > summary').click();
 await expect(research).toHaveAttribute('open','');
 await research.getByLabel('当前趋势阶段').selectOption('late');
 await expect(summary).toContainText('当前趋势阶段：趋势中后段');
 await research.getByLabel('当前趋势阶段').selectOption('early');
 await expect(summary).toContainText('当前趋势阶段：趋势前段');
 await expect(page.getByRole('img',{name:/上涨股成交额占比柱状图/})).toBeVisible();
 await expect.poll(()=>page.getByRole('img',{name:/上涨股成交额占比柱状图/}).evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  return e.getInstanceByDom(el)?.getWidth()??0;
 })).toBeGreaterThan(0);
 await research.locator('.breadth-table tbody tr').filter({hasText:'2026-10-28'}).click();
 await expect(summary).toContainText('历史回看');
 await expect(summary).toContainText('当前趋势阶段：尚未判断');
 await expect(summary).toContainText('50ETF 0.688 · 300ETF 0.698');
 await expect(summary).not.toContainText('期权最近共同记录（2026-10-28 收盘）');
 await expect(summary).toContainText('暂不依据它调整仓位');
 await expect(summary).not.toContainText('已有持仓可按计划观察');
 await research.locator('.breadth-table tbody tr').filter({hasText:'2026-10-23'}).click();
 await expect(summary).toContainText('较上个交易日：上涨家数占比 +71.8 个百分点 · TRIN +0.557');
});

test('market summary explains comparable changes and suppresses mismatched sources',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const current=report.days.at(-1),previous=structuredClone(current);
 previous.date='2026-10-28';
 const total=previous.advance+previous.decline+previous.flat;
 previous.advance=500;previous.decline=total-previous.flat-previous.advance;
 previous.advancing_percent=100*previous.advance/total;
 setTrin(previous,0.4,'amount');
 current.adl_gap_before=false;
 report.days=report.days.filter((d:any)=>d.date!=='2026-10-28');
 report.days.splice(report.days.length-1,0,previous);
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.clock.install({time:new Date('2026-10-29T11:00:00Z')});
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('较上一交易日：上涨股票占比上升 4.9 个百分点；上涨股相对平均成交减弱。');
 previous.source='另一来源';
 await page.reload();
 await expect(summary).not.toContainText('较上一交易日：');
});

test('intraday summary does not show future same-day PCR close',async({page})=>{
 const errors:Error[]=[];page.on('pageerror',error=>errors.push(error));
 await page.clock.install({time:new Date('2026-10-29T02:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 breadth.days.at(-1).status='provisional';
 const pcr=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 pcr.days.push({date:'2026-10-29',pcr:9.999,call_volume:1000,put_volume:9999,band_mid:null,band_upper:null,band_lower:null,collected_at:'2026-10-29T16:30:00+08:00'});
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:pcr}));
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('50ETF 收盘后更新 · 300ETF 收盘后更新');
 await expect(summary).not.toContainText('9.999');
 expect(errors).toEqual([]);
});

test('future same-day close cannot produce an action or appear as chart data',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T02:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const pcr=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 pcr.days.push({date:'2026-10-29',pcr:9.999,call_volume:1000,put_volume:9999,band_mid:null,band_upper:null,band_lower:null,collected_at:'2026-10-29T16:30:00+08:00'});
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:pcr}));
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 await expect(summary).not.toContainText('先不加仓；空仓继续观望');
 await expect(summary).not.toContainText('9.999');
 await expect(page.getByText('收盘数据时间尚未到达或采集时间异常，暂不用于市场判断。')).toBeVisible();
 await expect(page.getByLabel('市场解读')).toContainText('数据不足，暂无法解读市场');
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 const observation=page.getByRole('region',{name:'市场观察框架'});
 await expect(observation).toContainText('数据不足，无法比较');
 await expect(observation).not.toContainText('TRIN 0.536');
 const ad=page.getByRole('region',{name:'腾落线和涨跌比参考'});
 await expect(ad.locator('.option-readout')).toContainText('—');
 const row=page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-29'});
 await expect(row).toContainText('数据不完整');
 await expect(row).not.toContainText('0.536');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 await expect.poll(()=>chart.evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el)?.getOption(),i=o?.xAxis[0].data.indexOf('2026-10-29');
  return i>=0&&o.series.every((s:any)=>s.data[i]==null);
 })).toBe(true);
 await page.clock.setFixedTime(new Date('2026-10-29T07:30:00Z'));
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(summary.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 await page.clock.setFixedTime(new Date('2026-10-29T08:03:00Z'));
 await page.getByLabel('TRIN计算口径').selectOption('amount');
 await expect(summary.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 await page.clock.setFixedTime(new Date('2026-10-29T10:00:00Z'));
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(summary.locator('.market-summary-action')).toContainText('先不加仓');
 await expect(page.getByLabel('市场解读')).toContainText('2026-10-29 · 收盘统计');
});


test('incomplete breadth never produces an actionable market summary',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T09:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.at(-1).missing=1;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('数据不足，等待更新');
 await expect(summary).toContainText('暂不依据它调整仓位');
 await expect(summary).not.toContainText('先不加仓；空仓继续观望');
 await expect(summary).not.toContainText('涨跌股成交额占比');
});

test('inconsistent breadth counts never produce a recommendation or chart point',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T11:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.at(-1).advancing_percent=90;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?panel=breadth');
 await expect(page.getByText('涨跌家数或上涨比例异常，暂不进行市场判断。')).toBeVisible();
 await expect(page.locator('.market-summary > strong')).toHaveText('数据不足，等待更新');
 await expect(page.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 await expect(page.getByLabel('市场解读')).toContainText('数据不足，暂无法解读市场');
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('数据不足，无法比较');
 await expect(page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-29'})).not.toContainText('90.0%');
 await expect(page.getByRole('region',{name:'腾落线和涨跌比参考'}).locator('.option-readout')).toContainText('—');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 await expect.poll(()=>chart.evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el)?.getOption(),i=o?.xAxis[0].data.indexOf('2026-10-29');
  return i>=0&&o.series.every((s:any)=>s.data[i]==null);
 })).toBe(true);
});

test('mismatched TRIN is not used for recommendations and the other valid basis remains available',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T11:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.at(-1).trin_amount=0.1;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?panel=breadth');
 await expect(page.getByText('当前图表口径的 TRIN 与成交数据不一致，可切换口径或刷新数据。')).toBeVisible();
 await expect(page.locator('.market-summary-action')).toContainText('成交结构数据不足');
 await expect(page.getByLabel('市场解读')).toContainText('数据不足，暂无法解读市场');
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(page.getByText('当前图表口径的 TRIN 与成交数据不一致，可切换口径或刷新数据。')).toHaveCount(0);
 await expect(page.getByLabel('市场解读')).toContainText('2026-10-29 · 收盘统计 · 成交股数口径');
 await expect(page.locator('.market-summary-action')).toContainText('成交结构数据不足');
});

test('an inconsistent transaction share is hidden and blocks the selected-basis recommendation',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T11:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.at(-1).advancing_amount_percent=88;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.goto('/?panel=breadth');
 await expect(page.getByText('当前图表口径的成交占比与成交数据不一致，可切换口径或刷新数据。')).toBeVisible();
 await expect(page.locator('.market-summary-action')).toContainText('成交结构数据不足');
 await expect(page.getByLabel('市场解读')).toContainText('数据不足，暂无法解读市场');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 await expect.poll(()=>chart.evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el)?.getOption(),i=o?.xAxis[0].data.indexOf('2026-10-29');
  return i>=0&&o.series[0].data[i]?.value==null;
 })).toBe(true);
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(page.getByText('当前图表口径的成交占比与成交数据不一致，可切换口径或刷新数据。')).toHaveCount(0);
 await expect(page.locator('.market-summary-action')).toContainText('成交结构数据不足');
});

test('browser preview identifies static market data before interaction',async({page})=>{
 await gotoResearch(page);
 const notice=page.locator('.breadth-preview-notice');
 await expect(notice).toBeVisible();
 await expect(notice).toContainText('行情为静态快照');
 await expect(notice).toContainText('不会自动更新');
 await expect(page.locator('.breadth-stats')).toContainText('2026-10-29');
});

test('advance decline references preserve history and break at source changes',async({page})=>{
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'腾落线和涨跌比参考'});
 await expect(panel).toContainText('2026-10-29');
 await expect(panel).toContainText('-3,643');
 await expect(panel).toContainText('0.17');
 await expect(panel).toContainText('2026-10-29 / 1 天');
 const data=await panel.locator('.option-chart').evaluate(async el=>{
  const source=await fetch('/src/AdvanceDeclinePanel.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el).getOption();return {labels:o.xAxis[0].data,adl:o.series[0].data};
 });
 const i=data.labels.indexOf('2026-10-27');
 expect(data.adl[i]).toBe(-35321);
 expect(data.adl[i+1]).toBe(-32624);
 expect(data.adl[i+2]).toBeNull();
 expect(data.adl[i+3]).toBe(-3643);
 const graph=panel.locator('.option-chart');
 await graph.scrollIntoViewIfNeeded();
 const point=await graph.evaluate(async el=>{
  const source=await fetch('/src/AdvanceDeclinePanel.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  return e.getInstanceByDom(el).convertToPixel({xAxisIndex:0,yAxisIndex:0},['2026-10-27',-35321]);
 });
 const box=await graph.boundingBox();
 if(!box)throw new Error('图表不可见');
 await page.mouse.click(box.x+point[0],box.y+point[1]);
 await expect(panel).toContainText('历史参照');
 await expect(panel).toContainText('-35,321');
 await expect(panel).toContainText('2026-06-01 / 100 天');
 await expect(panel).toContainText('未与当前报价拼接');
});

test('market observation links point to the selected-date research panels',async({page})=>{
 await gotoResearch(page);
 const nav=page.getByRole('navigation',{name:'市场观察顺序'});
 for(const [label,id] of [['1 中期估值','breadth-equity-bond'],['2 指数位置','breadth-index-technical'],['3 宽度与量价','breadth-structure'],['4 期权情绪','breadth-option-pcr']]){
  const link=nav.getByRole('link',{name:label});
  await expect(link).toHaveAttribute('href',`#${id}`);
  await expect(page.locator(`#${id}`)).toHaveCount(1);
 }
 await nav.getByRole('link',{name:'4 期权情绪'}).click();
 await expect(page).toHaveURL(/#breadth-option-pcr$/);
 await expect(page.getByRole('region',{name:'期权PCR比较'})).toBeInViewport();
});

test('provisional market data does not display same-day historical 250-day close reference',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const day=report.days.find((row:any)=>row.date==='2026-10-28');
 day.historical=false;day.status='provisional';
 day.mcl_history={value:9999,samples:100,source:'晚于盘中的历史数据'};
 day.ma_daily={date:day.date,source:'晚于盘中的历史数据',windows:{'20':{percent:99},'60':{percent:99},'250':{percent:99,eligible:5000}}};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-28'}).click();
 const observation=page.getByRole('region',{name:'市场观察框架'});
 await expect(observation).toContainText('2026-10-28 · 盘中暂值');
 await expect(observation).toContainText('前一交易日收盘参照');
 await expect(observation).toContainText('2026-10-27 · 有效样本');
 await expect(observation).not.toContainText('晚于盘中的历史数据');
 await expect(observation).not.toContainText('9999');
 await expect(observation).not.toContainText('20日 99.0%');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('均线上方个股（2026-10-27 收盘，未复权）');
 await expect(summary).not.toContainText('20日 99.0%');
});

test('intraday view uses only the contiguous previous close for MA breadth',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const previous=report.days.find((row:any)=>row.date==='2026-10-29');
 previous.status='closed';previous.historical=false;
 previous.ma_daily={date:'2026-10-29',source:'腾讯收盘参考',windows:{'20':{percent:15.914,eligible:5184},'60':{percent:14.138,eligible:5121},'250':{percent:9.682,eligible:4679}}};
 const captured=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 const day={...captured.day,adl_gap_before:false,ma_daily:{...previous.ma_daily,date:'2026-10-30',source:'不应显示的当日收盘'}};
 report.days=[...report.days.filter((x:any)=>x.date<day.date),day];
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 const observation=page.getByRole('region',{name:'市场观察框架'});
 await expect(observation).toContainText('前一交易日收盘参照');
 await expect(observation).toContainText('20日 15.9% · 60日 14.1%');
 await expect(observation).toContainText('2026-10-29 · 有效样本');
 await expect(observation).not.toContainText('不应显示的当日收盘');
 day.adl_gap_before=true;
 await page.reload();await openResearch(page);
 await expect(observation).toContainText('20日 — · 60日 —');
});

test('intraday breadth cannot show same-day or later closes across reference panels',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const day=report.days.find((row:any)=>row.date==='2026-10-28');
 day.historical=false;day.status='provisional';
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-28'}).click();
 const compare=page.getByRole('region',{name:'同日期权PCR对照'});
 const pcr=page.getByRole('region',{name:'上证50ETF期权PCR'});
 const bond=page.getByRole('region',{name:'股债估值参考'});
 const index=page.getByRole('region',{name:'上证指数技术参考'});
 await expect(compare).toContainText('盘中不显示当日收盘');
 await expect(pcr).toContainText('盘中不显示当日及之后的收盘期权统计');
 await expect(bond).toContainText('盘中不显示当日及之后的收盘股债参考');
 await expect(index).toContainText('盘中不显示当日及之后收盘数据');
 await expect(index.locator('.option-readout strong').first()).toHaveText('—');
 for(const [chart,sourcePath] of [[pcr.locator('.option-chart'),'/src/OptionPCRPanel.tsx'],[bond.locator('.option-chart'),'/src/EquityBondPanel.tsx'],[index.locator('.index-technical-chart'),'/src/IndexTechnicalPanel.tsx']] as const){
  const dates=await chart.evaluate(async(el,path)=>{
   const source=await fetch(path).then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
   return e.getInstanceByDom(el).getOption().xAxis[0].data;
  },sourcePath);
  expect(dates.at(-1)).toBe('2026-10-27');
 }
 await page.getByLabel('期权统计日期').selectOption('2026-10-27');
 await expect(pcr.locator('.option-readout strong').first()).toHaveText('0.781');
 await page.getByLabel('股债参考日期').selectOption('2026-10-27');
 await expect(bond.locator('.option-readout strong').first()).toHaveText('4.62 个百分点');
});

test('verified market breadth renders actual dates and market-wide counts',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const errors:string[]=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('/');await page.getByRole('button',{name:'大盘广度',exact:true}).click();await openResearch(page);
 await expect(page.getByRole('heading',{name:'大盘阿姆氏 TRIN'})).toBeVisible();
 await expect(page.getByLabel('TRIN计算口径')).toHaveValue('amount');
 await expect(page.locator('.breadth-stats')).toContainText('2026-10-29');
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('250日研究参照 9.7%');
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('当日昨收不一致排除 2 只');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-28'}).click();
 await expect(page.locator('.breadth-stats')).toContainText('2026-10-28');
 await expect(page.locator('.breadth-stats')).toContainText('0.878');
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('20日 20.2% · 60日 18.6%');
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('250日研究参照 11.6%');
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('通达信逐股核对收盘价');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 await expect(page.locator('.breadth-stats')).toContainText('0.466');
 await expect(page.locator('.breadth-stats')).toContainText('11.0%');
 await expect(page.locator('.breadth-stats')).toContainText('5223');
 const observation=page.getByRole('region',{name:'市场观察框架'});
 await expect(observation).toContainText('上涨组平均成交额较高');
 await expect(observation).toContainText('2026-10-27');
 await expect(observation).toContainText('历史起点会影响结果');
 await expect(observation).toContainText('历史数据连续 100 天');
 await expect(observation).toContainText('历史收盘参照');
 await expect(observation).toContainText('20日 14.6% · 60日 14.6%');
 await expect(observation).toContainText('有效样本 5185 / 5118 只');
 await expect(observation).toContainText('非实时数据');
 const options=page.getByRole('region',{name:'上证50ETF期权PCR'});
 await expect(options).toContainText('2026-10-27');
 await expect(options).toContainText('0.781');
 await expect(options).toContainText('不代表全市场 PCR');
 await page.getByLabel('当前趋势阶段').selectOption('late');
 await expect(observation).toContainText('结合市场宽度和成交结构观察');
 await page.getByLabel('TRIN显示日期数').selectOption('120');
 await expect(page.locator('.breadth-table tbody tr')).toHaveCount(report.days.length);
 await expect(page.locator('.breadth-table')).toContainText('2026-10-27');
 await expect(page.locator('.breadth-table')).toContainText('2026-03-23');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-26'}).click();
 await expect(observation).toContainText('连续 99 个完整交易日');
 await expect(observation).toContainText('-133.0');
 await expect(observation).toContainText('20日 21.5% · 60日 20.6%');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-23'}).click();
 await expect(page.getByRole('region',{name:'市场状态与操作参考'})).toContainText('超过一半的活跃股票上涨；下跌组的每只平均成交额较高');
 await expect(options).toContainText('2026-10-23');
 await expect(options).toContainText('0.766');
 await expect(page.locator('.breadth-stats')).toContainText('历史复核');
 await expect(page.locator('.breadth-stats')).toContainText('1.066');
 await expect(observation).toContainText('下跌组平均成交额较高');
 await expect(observation).toContainText('2026-10-23');
 await expect(page.locator('.breadth-footnote')).toContainText('BaoStock');
 await expect(page.locator('.breadth-footnote')).toContainText('日期间隔不代表连续交易日');
 await expect(page.locator('.breadth-stats')).toContainText('成交额对照');
 await expect(page.locator('.breadth-stats')).toContainText('1.066');
 await expect(observation).toContainText('下跌组平均成交额较高');
 await expect(page.locator('.breadth-key').first()).toContainText('上涨股成交额占比');
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(page.locator('.breadth-stats')).toContainText('1.457');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 await expect.poll(()=>page.locator('.breadth-chart').first().evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const c=e.getInstanceByDom(el);return c?.getOption().series[2].data[0];
 })).toBeCloseTo(report.days[0].trin,8);
 await page.screenshot({path:'docs/trin-validation-20261028/ui-1380.png',fullPage:true});
 await page.getByRole('button',{name:'刷新全市场',exact:true}).click();
 await expect(page.locator('.breadth-error')).toContainText('只读预览');
 await expect(page.locator('.breadth-stats')).toContainText('0.379');
 await page.getByText('计算口径与数据明细',{exact:true}).click();
 await expect(page.locator('details.breadth-method').filter({has:page.getByText('计算口径与数据明细',{exact:true})}).last()).toContainText('平盘、停牌及零成交不进入公式');
 await page.setViewportSize({width:1000,height:900});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'docs/trin-validation-20261028/ui-1000.png',fullPage:true});
 expect(errors).toEqual([]);
});



test('MCL historical reference is identified separately from a live-source series',async({page})=>{
 const r=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const d=r.days.find((x:any)=>x.date==='2026-10-27');
 d.mcl_standard=null;d.mcl_history={date:d.date,value:-295.3,samples:100,source:'示例历史来源',universe:'示例股票池',collected_at:'2026-10-29T10:00:00+08:00'};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:r}));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 const observation=page.getByRole('region',{name:'市场观察框架'});
 await expect(observation).toContainText('历史收盘参照');
 await expect(observation).toContainText('-295.3');
 await expect(observation).toContainText('示例历史来源');
 await expect(observation).toContainText('未与当前报价拼接');
});

test('dated MA references stay distinguishable and missing stays empty',async({page})=>{
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-21'}).click();
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('250日研究参照');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-09-17'}).click();
 await expect(page.getByRole('region',{name:'市场观察框架'})).not.toContainText('250日研究参照');
});

test('new closed-date MA reference displays its exclusions and source',async({page})=>{
 const r=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 r.days=r.days.filter((d:any)=>d.date!=='2026-10-29');
 const old=r.days.at(-1);
 r.days.push({...old,date:'2026-10-29',collected_at:'2026-10-29T16:00:00+08:00',historical:false,status:'closed',ma_daily:{
  date:'2026-10-29',active:5215,source:'已核对历史与腾讯收盘报价',previous_close_mismatches:2,
  warning:'未复权价格可能受除权影响',windows:{'20':{eligible:5184,above:877,percent:16.9},
   '60':{eligible:5121,above:755,percent:14.7},'250':{eligible:4679,above:468,percent:10.0}}}});
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:r}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场观察框架'});
 await expect(panel).toContainText('20日 16.9% · 60日 14.7%');
 await expect(panel).toContainText('250日研究参照 10.0% · 样本 4679 只');
 await expect(panel).toContainText('当日昨收不一致排除 2 只');
 await expect(panel).toContainText('未复权价格可能受除权影响');
});


test('PCR keeps a missing selected date empty and refresh failure keeps verified values',async({page})=>{
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 await page.getByLabel('TRIN显示日期数').selectOption('120');
 const options=page.getByRole('region',{name:'上证50ETF期权PCR'});
 await expect(options).toContainText('0.781');
 await options.getByRole('button',{name:'刷新期权统计'}).click();
 await expect(options.getByRole('status')).toContainText('只读预览');
 await expect(options).toContainText('0.781');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-03-23'}).click();
 await expect(options).toContainText('所选日期没有可用');
 await expect(options.locator('.option-readout strong').first()).toHaveText('—');
});

test('missing PCR date offers only an explicitly dated earlier observation',async({page})=>{
 const report=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 report.days=report.days.filter((r:any)=>r.date<'2026-10-29');
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'上证50ETF期权PCR'});
 await expect(panel.locator('.option-readout strong').first()).toHaveText('—');
 const latest=report.days.at(-1);
 await panel.getByRole('button',{name:`查看最近有效记录 · ${latest.date}`}).click();
 await expect(panel.getByLabel('期权统计日期')).toHaveValue(latest.date);
 await expect(panel.locator('.option-readout strong').first()).toHaveText(latest.pcr.toFixed(3));
 await expect(page.getByRole('region',{name:'同日期权PCR对照'})).toContainText(latest.date);
 await panel.getByRole('button',{name:'返回大盘所选日期 · 2026-10-29'}).click();
 await expect(panel.getByLabel('期权统计日期')).toHaveValue('2026-10-29');
 await expect(panel.locator('.option-readout strong').first()).toHaveText('—');
});

test('PCR panel displays a previously missing selected date after background data arrives',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T08:30:00Z')});
 const report=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 report.days=report.days.filter((r:any)=>r.date<'2026-10-29');
 const row={...report.days.at(-1),date:'2026-10-29',pcr:.625,collected_at:'2026-10-30T16:30:00+08:00'};
 let published=false;
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:{...report,error:published?'':'上交所尚未返回所选日期期权统计',days:published?[...report.days,row]:report.days}}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'上证50ETF期权PCR'});
 await expect(panel).toContainText('尚未返回所选日期');
 await expect(panel.locator('.option-readout strong').first()).toHaveText('—');
 await panel.getByRole('button',{name:/查看最近有效记录/}).click();
 await panel.getByRole('button',{name:'返回大盘所选日期 · 2026-10-29'}).click();
 published=true;
 await page.clock.fastForward('00:31');
 await expect(panel.locator('.option-readout strong').first()).toHaveText('0.625');
 await expect(panel).not.toContainText('尚未返回所选日期');
});

test('separate ETF PCR products use the selected date without mixing their data',async({page})=>{
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 await page.getByLabel('期权标的').selectOption('510300');
 const options=page.getByRole('region',{name:'沪深300ETF期权PCR'});
 await expect(options).toContainText('2026-10-27');
 await expect(options).toContainText('0.804');
 await expect(options).toContainText('320,562 / 398,540 张');
 await page.getByLabel('期权统计日期').selectOption('2026-10-28');
 await expect(options).toContainText('0.698');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-23'}).click();
 await expect(options).toContainText('0.942');
 await page.getByLabel('期权标的').selectOption('510050');
 await expect(page.getByRole('region',{name:'上证50ETF期权PCR'})).toContainText('0.766');
});

test('index-option PCR shows crosschecked close dates without looking ahead',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T22:00:00Z')});
 await page.goto('/?panel=breadth&sample=csi300');
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('期权标的').selectOption('cffex-IO');
 const panel=page.getByRole('region',{name:'沪深300股指期权PCR'});
 await expect(panel.locator('.option-readout strong').first()).toHaveText('0.612');
 await expect(panel).toContainText('47,939 / 78,341 张');
 await expect(panel).toContainText('中金所单一股指期权，不代表全市场');
 await expect(panel).toContainText('20 个连续交易日不足时通道留空');
 await panel.getByLabel('期权统计日期').selectOption('2026-10-29');
 await expect(panel.locator('.option-readout strong').first()).toHaveText('0.590');
 await page.clock.setFixedTime(new Date('2026-10-30T21:52:00Z'));
 await page.reload();
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('期权标的').selectOption('cffex-IO');
 await expect(panel.locator('.option-readout strong').first()).toHaveText('—');
});

test('index-option chart adds history only after its documented verification time',async({page})=>{
 const rows=JSON.parse(await readFile('fixtures/cffex-index-pcr-verified.json','utf8'));
 const capture=Math.max(...rows.map((row:{collected_at:string})=>Date.parse(row.collected_at)));
 await page.clock.install({time:new Date(capture-60_000)});
 await page.goto('/?panel=breadth&sample=csi300');
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('期权标的').selectOption('cffex-IO');
 const dates=page.getByRole('region',{name:'沪深300股指期权PCR'}).getByLabel('期权统计日期');
 await expect(dates.locator('option')).toHaveCount(3);
 await page.clock.setFixedTime(new Date(capture+60_000));
 await page.reload();
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('期权标的').selectOption('cffex-IO');
 await expect(dates.locator('option')).toHaveCount(18);
 await dates.selectOption('2026-09-30');
 await expect(dates).toHaveValue('2026-09-30');
});

test('newly verified 50 and 300 ETF PCR rows appear only after their capture time',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:10:00Z')});
 await page.goto('/?panel=breadth&sample=csi300');
 await openResearch(page);
 const comparison=page.getByRole('region',{name:'同日期权PCR对照'});
 await expect(comparison).toContainText('无同日数据');
 await expect(comparison).not.toContainText('0.740');
 await page.clock.setFixedTime(new Date('2026-10-30T20:30:00Z'));
 await page.reload();await openResearch(page);
 await expect(comparison).toContainText('2026-10-30');
 await expect(comparison).toContainText('0.740');
 await expect(comparison).toContainText('0.826');
});

test('exchange ETF total is dated, labelled as partial, and never shows a future capture',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
 await gotoResearch(page);
 await page.getByLabel('期权标的').selectOption('etf-exchanges');
 const options=page.getByRole('region',{name:'沪深ETF合计期权PCR'});
 await expect(options.locator('.option-readout strong').first()).toHaveText('0.907');
 await expect(options).toContainText('3,569,015 / 3,935,317 张');
 await expect(options).toContainText('不含中金所');
 await expect(options).toContainText('深交所数据日期按查询确认');
 await options.getByLabel('期权统计日期').selectOption('2026-10-30');
 await expect(options.locator('.option-readout strong').first()).toHaveText('0.851');
 await expect(options).toContainText('3,926,198 / 4,611,003 张');
 await page.clock.setFixedTime(new Date('2026-10-30T20:00:00Z'));
 await page.reload();await openResearch(page);
 await page.getByLabel('期权标的').selectOption('etf-exchanges');
 await expect(options.locator('.option-readout strong').first()).toHaveText('—');
});

test('PCR comparison uses the same date and reports missing or incomplete channels',async({page})=>{
 const a=JSON.parse(await readFile('public/pcr-preview.json','utf8'));
 const b=JSON.parse(await readFile('public/pcr300-preview.json','utf8'));
 const at=(r:any,d:string)=>r.days.find((x:any)=>x.date===d);
 Object.assign(at(a,'2026-10-27'),{pcr:.5,band_lower:.6,band_upper:.9});
 Object.assign(at(b,'2026-10-27'),{pcr:.8,band_lower:.6,band_upper:.9});
 Object.assign(at(a,'2026-10-26'),{band_lower:null,band_upper:null});
 b.days=b.days.filter((x:any)=>x.date!=='2026-10-26');
 await page.route('**/pcr-preview.json',route=>route.fulfill({json:a}));
 await page.route('**/pcr300-preview.json',route=>route.fulfill({json:b}));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 const compare=page.getByRole('region',{name:'同日期权PCR对照'});
 await expect(compare).toContainText('2026-10-27');
 await expect(compare).toContainText('低于下轨');
 await expect(compare).toContainText('通道内');
 await page.getByLabel('期权统计日期').selectOption('2026-10-26');
 await expect(compare).toContainText('通道样本不足');
 await expect(compare).toContainText('无同日数据');
 await expect(compare).toContainText('日终统计无法反映盘中是否击穿');
});

test('equity bond reference follows the selected date and explains timing and scope',async({page})=>{
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 await page.getByLabel('TRIN显示日期数').selectOption('120');
 const panel=page.getByRole('region',{name:'股债估值参考'});
 await expect(panel).toContainText('2026-10-27');
 await expect(panel).toContainText('4.62 个百分点');
 await expect(panel).toContainText('15.99 倍');
 await expect(panel).toContainText('1.6305%');
 await expect(panel).toContainText('主板 A、B 股和科创板');
 await page.getByLabel('股债参考日期').selectOption('2026-10-28');
 await expect(panel).toContainText('1.6237%');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-23'}).click();
 await expect(panel).toContainText('4.57 个百分点');
 await panel.getByRole('button',{name:'刷新股债参考'}).click();
 await expect(panel.getByRole('status')).toContainText('只读预览');
 await expect(panel).toContainText('4.57 个百分点');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-03-23'}).click();
 await expect(panel).toContainText('所选日期没有两项齐全的数据');
});

test('historical PCR and equity bond charts do not show later data',async({page})=>{
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-23'}).click();
 const pcr=page.getByRole('region',{name:'上证50ETF期权PCR'});
 const bond=page.getByRole('region',{name:'股债估值参考'});
 await expect(pcr).toContainText('图表仅显示所选日期及之前的数据');
 await expect(bond).toContainText('图表仅显示所选日期及之前的数据');
 for(const [chart,sourcePath] of [[pcr.locator('.option-chart'),'/src/OptionPCRPanel.tsx'],[bond.locator('.option-chart'),'/src/EquityBondPanel.tsx']] as const){
  const dates=await chart.evaluate(async(el,path)=>{
   const source=await fetch(path).then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
   return e.getInstanceByDom(el).getOption().xAxis[0].data;
  },sourcePath);
  expect(dates.at(-1)).toBe('2026-10-23');
 }
});

test('index technical chart switches between finalized daily and complete weekly bars',async({page})=>{
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 const panel=page.getByRole('region',{name:'上证指数技术参考'});
 await expect(panel).toContainText('大盘所选日期：2026-10-27');
 await expect(panel).toContainText('3,648.30');
 await expect(panel).toContainText('-91.72');
 await page.getByLabel('指数技术周期').selectOption('weekly');
 await expect(panel).toContainText('2026-10-23');
 await expect(panel).toContainText('最近的完整周线');
 await expect(panel).toContainText('周线由完整交易周合成');
 await panel.getByRole('button',{name:'刷新指数参考'}).click();
 await expect(panel.getByRole('status')).toContainText('只读预览');
 await expect(panel).toContainText('2026-10-23');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-22'}).click();
 await expect(panel).toContainText('大盘所选日期：2026-10-22');
 await expect(panel.locator('.option-readout')).toContainText('2026-10-16');
 await page.getByLabel('指数技术周期').selectOption('daily');
 await expect(panel.locator('.option-readout')).toContainText('3,658.03');
 const dates=await panel.locator('.index-technical-chart').evaluate(async el=>{
  const source=await fetch('/src/IndexTechnicalPanel.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  return e.getInstanceByDom(el).getOption().xAxis[0].data;
 });
 expect(dates.at(-1)).toBe('2026-10-22');
});

test('index technical reference leaves a missing same-day close empty',async({page})=>{
 const r=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 r.daily=r.daily.filter((d:any)=>d.date!=='2026-10-23');
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:r}));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-23'}).click();
 const panel=page.getByRole('region',{name:'上证指数技术参考'});
 await expect(panel).toContainText('所选日期没有同日指数收盘数据');
 await expect(panel.locator('.option-readout')).toContainText('—');
 await expect(panel.locator('.option-readout')).not.toContainText('3,697.52');
});

test('TRIN gaps stay null and provisional values stay visibly distinct',async({page})=>{
 const r=JSON.parse(await readFile('public/breadth-preview.json','utf8')),d=r.days[0];
 const a={...d,date:'2026-10-20',historical:false},b={...d,date:'2026-10-26',historical:false,undefined_reason:'上涨或下跌组为空，TRIN无定义'},c={...d,date:'2026-10-27',status:'provisional',historical:false};
 setTrin(a,1.2,'volume');setTrin(b,null,'volume');setTrin(c,.65,'volume');r.days=[a,b,c];
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:r}));
 await page.goto('/');await page.getByRole('button',{name:'大盘广度',exact:true}).click();await openResearch(page);
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(page.locator('.breadth-stats')).toContainText('盘中暂值');
 await expect(page.locator('.breadth-footnote')).toContainText('共收录 3 个日期，当前显示 3 个；盘中暂值单独标示');
 await expect(page.locator('.breadth-footnote')).not.toContainText('已核验 3 个日期');
 await expect(page.locator('.breadth-table tbody tr')).toHaveCount(3);
 await expect(page.locator('.breadth-table tbody tr').nth(1)).toContainText('—');
 const o=await page.locator('.breadth-chart').first().evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  return e.getInstanceByDom(el).getOption();
 });
 expect(o.series[2].data).toEqual([1.2,null,null,.65]);
 expect(o.series[0].data[0].itemStyle.opacity).toBe(1);expect(o.series[0].data[3].itemStyle.opacity).toBe(.55);
 expect(o.yAxis[1].min).toBe(0);expect(o.series[2].markLine.data.map((x:any)=>x.yAxis)).toEqual([1]);
 await page.locator('.breadth-table tbody tr').nth(1).click();await expect(page.locator('.breadth-stats').locator('strong').first()).toHaveText('—');
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('数据不足，无法比较');
});

test('empty and unavailable market history is explained without fabricated bars',async({page})=>{
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:{days:[],error:'全市场数据获取失败',running:false,history_note:'尚无完整历史'}}));
 await page.goto('/');await page.getByRole('button',{name:'大盘广度',exact:true}).click();await openResearch(page);
 await expect(page.locator('.breadth-empty')).toContainText('尚无完整市场统计');
 await expect(page.locator('.breadth-error')).toContainText('全市场数据获取失败');
 await expect(page.locator('.breadth-table')).toHaveCount(0);
 await expect(page.getByRole('region',{name:'市场观察框架'})).toContainText('数据不足，无法比较');
});


test('public holdings reference distinguishes disclosed snapshot from real time flows',async({page})=>{
 await gotoResearch(page);
 await expect(page.getByRole('navigation',{name:'市场观察顺序'}).getByRole('link',{name:'5 公开持仓'})).toHaveAttribute('href','#breadth-institution');
 const panel=page.getByLabel('公开持仓观察');
 await panel.locator('summary').click();
 await expect(panel).toContainText('不能直接认定已清仓');
 await expect(panel).toContainText('不能作为实时资金流向');
 await expect(panel).toContainText('496,639,800 股');
 await expect(panel.getByRole('link',{name:'一季报'})).toHaveAttribute('href',/ccb\.com/);
 await expect(panel.getByRole('link',{name:'半年报'})).toHaveAttribute('href',/cninfo\.com\.cn/);
});

test('market state uses same-date finished index and never invents a position instruction',async({page})=>{
 await gotoResearch(page);
 const market=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(market).toContainText('普跌 · 指数低于20日均线');
 await expect(market).toContainText('2026-10-29');
 await expect(market).toContainText('判断依据与历史试算');
 await expect(market).toContainText('22 次中 10 次优于一直持有、12 次较差');
 await expect(market).toContainText('不能识别主力身份');
 await expect(market).toContainText('不足一半的活跃股票上涨；上涨组的每只平均成交额较高');
 await expect(market).toContainText('上涨股平均成交额约为下跌股的 1.87 倍');
 await expect(market).toContainText('上涨股成交额 24.3%');
 await expect(market).toContainText('下跌股成交额 75.7%');
 await expect(market).toContainText('不是主动买卖量');
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(market).toContainText('不足一半的活跃股票上涨；上涨组的每只平均成交额较高');
 await expect(market).toContainText('上涨股平均成交额约为下跌股的 1.87 倍');
 await expect(market).toContainText('上涨股成交额 24.3%');
 await expect(market).toContainText('下跌股成交额 75.7%');
 await expect(page.getByLabel('市场解读')).toContainText('成交股数口径');
 await page.getByLabel('TRIN计算口径').selectOption('amount');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-28'}).click();
 await expect(market).toContainText('超过一半的活跃股票上涨；上涨组的每只平均成交额较高');
 await expect(market).toContainText('历史回看，不作为当前操作依据');
 await expect(market).toContainText('指数低于20日均线 · 个股涨多跌少');
 await expect(market).toContainText('暂无法与上一交易日同口径比较');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-23'}).click();
 await expect(market).toContainText('上涨家数占比相比上一交易日 +71.8 个百分点');
 await expect(market).toContainText('TRIN 相比上一交易日 +0.557');
 await expect(market).toContainText('下跌股平均成交额约为上涨股的 1.07 倍');
});

test('prior close is visibly dated and cannot be mistaken for the current market',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T02:00:00Z')});
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('当前展示 2026-10-29 的历史收盘数据，不是当前行情');
 await expect(panel).toContainText('历史回看，不作为当前操作依据');
 await expect(panel).not.toContainText('弱势风险检查：');
});

test('latest completed close can guide during rest but not after the next open',async({page})=>{
 await page.clock.install({time:new Date('2026-10-31T03:00:00Z')});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 b.days.push({...b.days.at(-1),date:'2026-10-30',collected_at:'2026-10-30T15:30:00+08:00',status:'closed'});
 const idx=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 idx.daily.push({...idx.daily.at(-1),date:'2026-10-30'});
 idx.collected_at='2026-10-30T16:30:00+08:00';idx.latest_eligible='2026-10-30';
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:idx}));
 await page.goto('/?panel=breadth');
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('2026-10-30 · 收盘统计 · 最近交易日收盘参考');
 await expect(panel).toContainText('最近收盘操作参考：先不加仓');
 await expect(panel).toContainText('依据 2026-10-30 收盘数据；开盘后请以更新的盘中行情为准');
 await page.clock.setFixedTime(new Date('2026-11-02T02:00:00Z'));
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(panel).toContainText('当前展示 2026-10-30 的历史收盘数据，不是当前行情');
 await expect(panel.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
});

test('missing latest close is never presented as a recent close recommendation',async({page})=>{
 await page.clock.install({time:new Date('2026-10-31T03:00:00Z')});
 await page.goto('/?panel=breadth');
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('当前展示 2026-10-29 的历史收盘数据，不是当前行情');
 await expect(panel.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
});

test('index and stock breadth divergence is shown only with valid matching data',async({page})=>{
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-26'}).click();
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('指数上涨，个股跌多涨少');
 await expect(panel.locator('.market-summary')).toContainText('盘面分化：指数上涨，但上涨股票占比从上一交易日收盘的 80.4% 降至 39.9%，上涨范围收窄。');
 await expect(panel).toContainText('上证较昨收 +0.19%');
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-10-27'}).click();
 await expect(panel).not.toContainText('指数上涨，个股跌多涨少');
 await expect(panel.locator('.market-summary')).not.toContainText('盘面分化：');
});

test('historical narrowing breadth uses comparable observations only',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-09-22'}).click();
 const summary=page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary');
 await expect(summary).toContainText('指数上涨，但上涨股票占比从上一交易日收盘的 80.9% 降至 43.9%，上涨范围收窄');
 report.days.find((row:any)=>row.date==='2026-09-21').source='不同数据源';
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-09-22'}).click();
 await expect(summary).not.toContainText('上涨范围收窄');
 await expect(summary).toContainText('指数上涨，个股跌多涨少');
});

test('future-collected previous close cannot be used for breadth comparisons',async({page})=>{
 await page.clock.install({time:new Date('2026-10-31T03:00:00Z')});
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.find((row:any)=>row.date==='2026-09-21').collected_at='2026-11-01T17:00:00+08:00';
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 await page.locator('.breadth-table tbody tr').filter({hasText:'2026-09-22'}).click();
 const summary=page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary');
 await expect(summary).not.toContainText('上涨范围收窄');
 await expect(summary).not.toContainText('较上一交易日：');
 await expect(summary).toContainText('指数上涨，个股跌多涨少');
});

test('invalid stock counts cannot produce a breadth state or divergence',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.at(-1).advance=-1;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('数据不足');
 await expect(page.getByText('涨跌家数或上涨比例异常，暂不进行市场判断。')).toBeVisible();
 await expect(panel).not.toContainText('普跌 · 指数低于20日均线');
 await expect(panel).not.toContainText('指数上涨，个股跌多涨少');
 await expect(panel).not.toContainText('的活跃股票上涨；');
 await expect(panel).not.toContainText('弱势风险检查：');
});

test('unaccounted covered stocks block market and position guidance',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 report.days.at(-1).suspended+=1;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await page.clock.install({time:new Date('2026-10-29T11:00:00Z')});
 await page.goto('/?panel=breadth');
 await expect(page.getByText('涨跌家数或上涨比例异常，暂不进行市场判断。')).toBeVisible();
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 await expect(panel.locator('.market-summary-action')).not.toContainText('分批加仓');
});

for(const [name,invalid] of [
 ['缺失股票',{missing:1}],
 ['无上涨股票',{advance:0}],
 ['无下跌股票',{decline:0}],
 ['无效 TRIN',{trin_amount:0}],
] as const){
 test(`成交结构不使用不完整或无效数据：${name}`,async({page})=>{
  const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
  Object.assign(report.days.at(-1),invalid);
  await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
  await gotoResearch(page);
  const panel=page.getByRole('region',{name:'市场状态与操作参考'});
  const structure=panel.locator('.observation-item').filter({hasText:'成交结构'});
  await expect(structure).toContainText('数据不足');
  await expect(panel.locator('.market-summary-structure')).toHaveCount(0);
  await expect(structure).toContainText('TRIN —');
  await expect(structure).toContainText('上涨股成交额 —');
  await expect(structure.locator('.market-flow-bar')).toHaveCount(0);
  await expect(structure).not.toContainText('相比上一交易日 +');
  await expect(structure).not.toContainText('倍。');
 });
}

test('TRIN equal to one describes equal averages without assigning a larger group',async({page})=>{
 const report=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 setTrin(report.days.at(-1),1,'amount');
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:report}));
 await gotoResearch(page);
 const structure=page.getByRole('region',{name:'市场状态与操作参考'}).locator('.observation-item').filter({hasText:'成交结构'});
 await expect(structure).toContainText('两组平均成交相同');
 await expect(page.locator('.market-summary-structure')).toContainText('上涨与下跌组的每只平均成交额相同');
 await expect(structure).not.toContainText('约为下跌股的');
 await expect(structure).not.toContainText('约为上涨股的');
});

test('intraday divergence follows fresh index price and breadth rather than previous close direction alone',async({page})=>{
 const result=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 await page.clock.install({time:new Date(result.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 breadth.days=[...breadth.days.filter((x:any)=>x.date<result.day.date),result.day];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:[{...result.quote,previous_close:'3600.00'}],minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('指数上涨，个股跌多涨少');
 await expect(panel.locator('.market-summary')).toContainText('盘面分化：指数上涨，个股跌多涨少。');
 await expect(panel).toContainText('上证较昨收 +0.25%（盘中暂值）');
 await page.clock.fastForward('05:01');
 await expect(panel).not.toContainText('指数上涨，个股跌多涨少');
 await expect(panel.locator('.market-summary')).not.toContainText('盘面分化：');
});

test('market state leaves same-day index hidden for provisional breadth',async({page})=>{
 const r=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 r.days=[{...r.days.at(-1),status:'provisional'}];
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:r}));
 await gotoResearch(page);
 const market=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(market).toContainText('数据不足');
 await expect(market).not.toContainText('3651.43');
 await expect(market.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
});

test('explains why a closed breadth snapshot lacks the same-day index reference',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T07:45:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 breadth.days=[{...breadth.days.at(-1),date:'2026-10-30',collected_at:'2026-10-30T15:30:00+08:00',status:'closed'}];
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 index.daily=index.daily.filter((x:any)=>x.date<'2026-10-30');index.latest_eligible='2026-10-29';
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('同日指数收盘参考尚未进入采集范围');
 await expect(panel).toContainText('北京时间 16:30 后检查');
 await expect(panel).toContainText('上涨个股不足两成 · 指数数据不足或不同步');
 await expect(panel).toContainText('暂不判断综合状态和仓位');
 await expect(panel).not.toContainText('普跌 · 指数低于20日均线');
});

test('missing transaction share remains unknown instead of becoming zero',async({page})=>{
 const r=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 r.days=[{...r.days.at(-1),advancing_amount_percent:null}];
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:r}));
 await gotoResearch(page);
 const flow=page.getByLabel('上涨和下跌股票成交占比');
 await expect(flow).toContainText('上涨股成交额 —');
 await expect(flow).toContainText('下跌股成交额 —');
 await expect(flow.locator('.market-flow-bar')).toHaveCount(0);
});

test('provisional state uses timely quote and previous nineteen completed closes',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T02:00:30Z')});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 b.days=[{...b.days.at(-1),status:'provisional',first_quote:'2026-10-29T10:00:00+08:00',last_quote:'2026-10-29T10:00:24+08:00',collected_at:'2026-10-29T10:00:28+08:00'}];
 const idx=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 idx.daily=idx.daily.filter((x:any)=>x.date<'2026-10-29');idx.latest_eligible='2026-10-28';
 idx.collected_at='2026-10-28T16:30:00+08:00';
 const d=JSON.parse(await readFile('public/preview.json','utf8'));
 d.market={quotes:[{code:'sh000001',price:'3600',timestamp:'2026-10-29T10:00:24+08:00',source:'tencent'}],minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:idx}));
 await page.route('**/preview.json',route=>route.fulfill({json:d}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('盘中暂值');
 await expect(panel).toContainText('上证现价 3600.00');
 await expect(panel).toContainText('前19日收盘及现价计算');
 await expect(panel).toContainText('盘中状态尚未做历史验证');
 await expect(panel).toContainText('普跌 · 指数低于20日均线');
});

test('captured live input displays and then marks the provisional snapshot stale',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 captured.breadth.adl_gap_before=false;
 b.days=[...b.days.filter((x:any)=>x.date<captured.breadth.date),captured.breadth];
 const d=JSON.parse(await readFile('public/preview.json','utf8'));
 d.market={quotes:captured.quotes,minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/preview.json',route=>route.fulfill({json:d}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('2026-10-30 · 盘中暂值');
 await expect(panel).toContainText('上证现价 3618.61');
 await expect(panel).toContainText('上涨家数 23.4%');
 await expect(panel).toContainText('指数低于20日均线且跌多涨少：检查持仓风险');
 await expect(page.getByLabel('市场解读')).toContainText('2026-10-30 · 盘中暂值');
 await expect(page.getByText(/盘中快照已过期/)).toHaveCount(0);
 await page.clock.fastForward('05:01');
 await expect(page.getByText(/盘中快照已过期/)).toBeVisible();
 await expect(page.getByLabel('市场解读')).toContainText('盘中数据已过期，等待更新后解读');
 await expect(panel).toContainText('数据不足');
 await expect(panel).toContainText('上涨家数 —');
 await expect(panel).not.toContainText('的活跃股票上涨；');
 await expect(panel).not.toContainText('弱势风险检查：');
 await expect(panel).toContainText('前一交易日收盘参考 · 2026-10-29');
 await expect(panel).toContainText('不是当前行情或操作指令');
 const observation=page.getByRole('region',{name:'市场观察框架'});
 await expect(observation).toContainText('快照已过期，仅供回看');
 await expect(observation).toContainText('不是当前行情');
 await expect(page.locator('.breadth-stats')).toContainText('快照已过期，仅供回看');
});

test('intraday snapshot with invalid timestamps cannot produce a chart reading or action',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 captured.breadth.last_quote=null;
 b.days=[...b.days.filter((x:any)=>x.date<captured.breadth.date),captured.breadth];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:captured.quotes,minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.goto('/?panel=breadth');
 await expect(page.getByText('盘中快照时间信息异常，暂不用于市场判断；请刷新数据。')).toBeVisible();
 await expect(page.getByLabel('市场解读')).toContainText('盘中数据时间异常，等待更新后解读');
 await expect(page.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 const chart=page.getByRole('img',{name:/上涨股成交额占比柱状图/});
 await expect.poll(()=>chart.evaluate(async el=>{
  const source=await fetch('/src/MarketBreadth.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const option=e.getInstanceByDom(el)?.getOption();if(!option)return false;
  const index=option.xAxis[0].data.indexOf('2026-10-30');
  return index>=0&&option.series.every((s:any)=>s.data[index]==null);
 })).toBe(true);
});

test('CSI 300 observation is shown only for matching complete market data',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 b.days=[...b.days.filter((x:any)=>x.date<captured.breadth.date),captured.breadth];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:captured.quotes,minute:null};
 const total=captured.breadth.advance_amount;
 const down=captured.breadth.decline_amount;
 const core={date:captured.breadth.date,member_date:captured.breadth.date,collected_at:captured.breadth.collected_at,member_collected_at:captured.breadth.collected_at,available_at:captured.breadth.collected_at,status:'provisional',advance:100,decline:150,flat:40,suspended:10,advance_amount:total*.35,market_advance_amount:total,advance_amount_percent:35,decline_amount:down*.25,market_decline_amount:down,decline_amount_percent:25};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.route('**/csi300-preview.json',route=>route.fulfill({json:core}));
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('沪深300：跌多涨少（100 只上涨、150 只下跌）；占全市场对应组成交额：上涨股 35.0%，下跌股 25.0%');
 await expect(summary).toContainText('上涨组成交额更集中在沪深300');
 core.decline_amount_percent=26;
 await page.reload();
 await expect(summary).toContainText('上涨股成交额占全市场上涨组 35.0%');
 await expect(summary).not.toContainText('下跌组 26.0%');
 core.decline_amount_percent=25;
 core.advance=150;core.decline=100;
 await page.reload();
 await expect(summary).toContainText('沪深300：涨多跌少（150 只上涨、100 只下跌）');
 core.advance=125;core.decline=125;
 await page.reload();
 await expect(summary).toContainText('沪深300：涨跌家数持平（125 只上涨、125 只下跌）');
 core.advance=100;core.decline=150;
 core.member_date='2026-10-29';
 await page.reload();
 await expect(summary).not.toContainText('100 只上涨');
 await expect(summary).toContainText('沪深300：等待同日成分和行情数据');
 core.member_date=captured.breadth.date;core.advance_amount_percent=36;
 await page.reload();
 await expect(summary).not.toContainText('100 只上涨');
 core.advance_amount_percent=35;
 await page.reload();
 await expect(summary).toContainText('100 只上涨');
 await page.clock.fastForward('05:01');
 await expect(summary).not.toContainText('100 只上涨');
});

test('dated local preview shows the checked CSI 300 close',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 await page.goto('/?panel=breadth&sample=csi300');
 await expect(page.getByRole('status').filter({hasText:'本地只读预览'})).toBeVisible();
 const summary=page.locator('.market-summary');
 await expect(summary.locator(':scope > p')).toHaveCount(3);
 await expect(summary.getByLabel('指标依据')).not.toHaveAttribute('open','');
 await expect(summary).toContainText('沪深300：跌多涨少（102 只上涨、189 只下跌）；占全市场对应组成交额：上涨股 35.4%，下跌股 24.8%');
 await expect(summary).toContainText('上涨组成交额更集中在沪深300');
 await expect(summary).toContainText('长期参考：仅 8.3% 的有效股票在各自年线上方（2026-10-30 收盘）');
 await expect(summary).toContainText('周线量价偏弱（2026-10-30 收盘参考）');
 await expect(page.getByRole('region',{name:'市场状态与操作参考'})).toContainText('2026-10-30 · 收盘统计');
 const details=page.getByLabel('指标依据');
 await details.getByText('查看指标依据').click();
 await expect(details).toContainText('周线量价（2026-10-30 收盘）：12周成交加权均价低于26周');
 await expect(details).toContainText('日线量价（2026-10-30 收盘）：指标偏弱，快慢线均在零轴下方');
});

test('market summary renders real isolated backend RPC results',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const rpc=JSON.parse(execFileSync('.venv/bin/python',['-m','tests.market_decision_rpc_sample'],{encoding:'utf8',maxBuffer:4_000_000}));
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:rpc.breadth}));
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:rpc.index}));
 await page.route('**/csi300-preview.json',route=>route.fulfill({json:rpc.csi300}));
 await page.goto('/?panel=breadth&sample=csi300');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('先不加仓；空仓继续观望，持仓较重可考虑分批减仓');
 await expect(summary).toContainText('上涨股票 16.4%');
 await expect(summary).toContainText('长期参考：仅 8.3% 的有效股票在各自年线上方（2026-10-30 收盘）');
 await expect(summary).toContainText('沪深300：跌多涨少（102 只上涨、189 只下跌）；占全市场对应组成交额：上涨股 35.4%，下跌股 24.8%');
});

test('year-line summary validates sample and dates the prior close',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const current=breadth.days.at(-1),prior=breadth.days.at(-2),window=prior.ma_daily.windows['250'];
 delete current.ma_daily;
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.goto('/?panel=breadth&sample=csi300');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('长期参考：仅 9.7% 的有效股票在各自年线上方（2026-10-29 收盘）');
 current.ma_daily={...structuredClone(prior.ma_daily),date:current.date,collected_at:'2026-10-30T22:30:00+08:00'};
 await page.reload();
 await expect(summary).toContainText('长期参考：仅 9.7% 的有效股票在各自年线上方（2026-10-30 收盘）');
 delete current.ma_daily;
 current.adl_gap_before=true;
 await page.reload();
 await expect(summary).toContainText('长期参考：年线数据暂缺。');
 current.adl_gap_before=false;current.universe='';
 await page.reload();
 await expect(summary).toContainText('长期参考：年线数据暂缺。');
 current.universe=prior.universe;
 current.adl_gap_before=false;window.above=window.eligible+1;
 await page.reload();
 await expect(summary).toContainText('长期参考：年线数据暂缺。');
 window.above=453;prior.ma_daily.collected_at='2026-11-02T16:00:00+08:00';
 await page.reload();
 await expect(summary).toContainText('长期参考：年线数据暂缺。');
});

test('daily volume-weighted reference follows both lines and hides incomplete data',async({page})=>{
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 const row=index.daily.at(-1);
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 const details=page.getByLabel('指标依据');
 for(const [dif,dea,expected] of [[-2,-1,'指标偏弱，快慢线均在零轴下方'],[2,1,'指标偏强，快慢线均在零轴上方'],[2,-1,'指标分化，快慢线分别位于零轴两侧或触及零轴']] as const){
  row.vw_dif=dif;row.vw_dea=dea;
  await page.goto('/?panel=breadth');
  await details.getByText('查看指标依据').click();
  await expect(details).toContainText(expected);
 }
 row.vw_dea=null;
 await page.goto('/?panel=breadth');
 await details.getByText('查看指标依据').click();
 await expect(details).not.toContainText('日线量价');
});

test('mixed market and same-day weak volume-weighted trend suppresses adding',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T11:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const day=breadth.days.at(-1),total=day.advance+day.decline+day.flat;
 day.advance=Math.floor(total*.6);day.decline=total-day.flat-day.advance;day.advancing_percent=100*day.advance/total;
 setTrin(day,.7,'amount');
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 const row=index.daily.find((r:any)=>r.date===day.date);
 index.weekly=[{date:'2026-10-23',vw_dif:2,vw_dea:1}];
 row.close=4000;row.boll_mid=3900;row.vw_dif=-2;row.vw_dea=-1;
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary).toContainText('市场信号分化，先观察');
 await expect(summary.locator('.market-summary-action')).toContainText('暂不加仓，先观察；上涨股票较多，但日线量价指标偏弱');
 await expect(summary.locator('.market-summary-action')).not.toContainText('分批加仓');
 row.vw_dif=2;row.vw_dea=1;
 await page.reload();
 await expect(summary.locator('.market-summary-action')).toContainText('可考虑小幅、分批加仓');
 row.vw_dea=-1;
 await page.reload();
 await expect(summary.locator('.market-summary-action')).toContainText('日线量价指标仍有分歧');
 row.vw_dea=null;
 await page.reload();
 await expect(summary).toContainText('量价数据不足，先观察');
 await expect(summary.locator('.market-summary-action')).toContainText('缺少可用的最近收盘量价数据');
 await expect(summary.locator('.market-summary-action')).not.toContainText('分批加仓');
});

test('recent weak weekly volume-price signal blocks adding in a strong daily market',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const breadth=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8'));
 const day=breadth.days.at(-1),total=day.advance+day.decline+day.flat;
 day.advance=Math.floor(total*.6);day.decline=total-day.flat-day.advance;day.advancing_percent=100*day.advance/total;setTrin(day,.7,'amount');
 const index=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 const daily=index.daily.at(-1),weekly=index.weekly.at(-1);
 Object.assign(daily,{close:4000,boll_mid:3900,vw_dif:2,vw_dea:1});
 Object.assign(weekly,{vw_dif:-2,vw_dea:-1});
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 await page.goto('/?panel=breadth&sample=csi300');
 const summary=page.locator('.market-summary'),action=summary.locator('.market-summary-action');
 await expect(summary.locator('strong').first()).toHaveText('短期转强，周线偏弱');
 await expect(action).toContainText('暂不加仓，先观察；短期量价偏强，但 2026-10-30 收盘的周线量价仍偏弱');
 weekly.vw_dif=1;weekly.vw_dea=1;
 await page.reload();
 await expect(action).toContainText('可考虑小幅、分批加仓');
 weekly.vw_dif=1;weekly.vw_dea=-1;
 await page.reload();
 await expect(action).toContainText('周线量价仍有分歧');
 weekly.vw_dif=-2;weekly.vw_dea=null;
 await page.reload();
 await expect(action).toContainText('暂不加仓，等待最近完整周线量价数据');
 weekly.vw_dea=-1;weekly.date='2026-10-23';
 await page.reload();
 await expect(action).toContainText('暂不加仓，等待最近完整周线量价数据');
 await expect(summary.locator('p').filter({hasText:'原因：'})).not.toContainText('周线量价');
 weekly.date='2026-11-06';
 await page.reload();
 await expect(action).toContainText('暂不加仓，等待最近完整周线量价数据');
});

test('intraday decision uses the latest completed week and ignores the unfinished week',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const day=captured.breadth,total=day.advance+day.decline+day.flat;
 day.advance=Math.floor(total*.6);day.decline=total-day.flat-day.advance;day.advancing_percent=100*day.advance/total;setTrin(day,.7,'amount');
 breadth.days=[...breadth.days.filter((r:any)=>r.date<day.date),day];
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 Object.assign(index.daily.find((r:any)=>r.date==='2026-10-29'),{vw_dif:2,vw_dea:1});
 index.weekly=[{date:'2026-10-23',vw_dif:-2,vw_dea:-1},{date:'2026-10-30',vw_dif:3,vw_dea:2}];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:captured.quotes,minute:null};
 preview.market.quotes.find((r:any)=>r.code==='sh000001').price='5000';
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.goto('/?panel=breadth');
 const action=page.locator('.market-summary-action');
 await expect(action).toContainText('2026-10-23 收盘的周线量价仍偏弱');
 await expect(action).not.toContainText('2026-10-30 收盘');
 await page.clock.fastForward('05:01');
 await expect(action).toContainText('暂不依据它调整仓位');
});

test('weekly reference follows the last trading day of a holiday-shortened week',async({page})=>{
 await page.clock.install({time:new Date('2026-10-08T02:00:30Z')});
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const day={...captured.breadth,date:'2026-10-08',first_quote:'2026-10-08T10:00:00+08:00',last_quote:'2026-10-08T10:00:24+08:00',collected_at:'2026-10-08T10:00:28+08:00'};
 const total=day.advance+day.decline+day.flat;
 day.advance=Math.floor(total*.6);day.decline=total-day.flat-day.advance;day.advancing_percent=100*day.advance/total;setTrin(day,.7,'amount');
 breadth.days=[...breadth.days.filter((r:any)=>r.date<day.date),day];
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 index.latest_eligible='2026-09-30';
 index.daily=index.daily.filter((r:any)=>r.date<='2026-09-30');index.collected_at='2026-09-30T16:30:00+08:00';
 Object.assign(index.daily.find((r:any)=>r.date==='2026-09-30'),{vw_dif:2,vw_dea:1});
 index.weekly=[{date:'2026-09-30',vw_dif:-2,vw_dea:-1}];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:[{...captured.quotes[0],price:'5000',timestamp:'2026-10-08T10:00:24+08:00'}],minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.goto('/?panel=breadth');
 await expect(page.locator('.market-summary-action')).toContainText('2026-09-30 收盘的周线量价仍偏弱');
});

test('live conflict uses a dated prior close, never a future close or stale market data',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const day=captured.breadth,total=day.advance+day.decline+day.flat;
 day.advance=Math.floor(total*.6);day.decline=total-day.flat-day.advance;day.advancing_percent=100*day.advance/total;
 setTrin(day,.7,'amount');
 breadth.days=[...breadth.days.filter((r:any)=>r.date<day.date),day];
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 const prior=index.daily.find((r:any)=>r.date==='2026-10-29');prior.vw_dif=-2;prior.vw_dea=-1;
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:captured.quotes,minute:null};
 preview.market.quotes.find((r:any)=>r.code==='sh000001').price='5000';
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary.locator('.market-summary-action')).toContainText('2026-10-29 收盘的日线量价指标偏弱');
 await expect(summary).toContainText('2026-10-29日线量价');
 const details=summary.getByLabel('指标依据');await details.getByText('查看指标依据').click();
 await expect(details).toContainText('日线量价（2026-10-29 收盘）');
 await expect(details).not.toContainText('日线量价（2026-10-30 收盘）');
 index.daily.push({...prior,date:'2026-10-30',vw_dif:100,vw_dea:100});
 await page.reload();
 await expect(summary.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 await expect(summary).not.toContainText('日线量价（2026-10-30 收盘）');
 index.daily.pop();
 await page.reload();
 await expect(summary.locator('.market-summary-action')).toContainText('2026-10-29 收盘的日线量价指标偏弱');
 await page.clock.fastForward('05:01');
 await expect(summary.locator('.market-summary-action')).toContainText('暂不依据它调整仓位');
 await expect(summary).not.toContainText('2026-10-29 收盘的日线量价指标偏弱');
});

test('weekly volume-weighted reference respects the selected date and missing data',async({page})=>{
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 index.weekly=[{date:'2026-10-23',vw_dif:-3},{date:'2026-10-30',vw_dif:4}];
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await page.goto('/?panel=breadth');
 const details=page.getByLabel('指标依据');
 await details.getByText('查看指标依据').click();
 await expect(details).toContainText('周线量价（2026-10-23 收盘）：12周成交加权均价低于26周');
 await expect(details).not.toContainText('2026-10-30 收盘');
 index.weekly[0].vw_dif=null;
 await page.reload();
 await details.getByText('查看指标依据').click();
 await expect(details).not.toContainText('周线量价（');
});

test('weekly trend reference shows both checked lines without changing the action',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 const index=JSON.parse(await readFile('public/index-csi300-preview.json','utf8'));
 const row=index.weekly.at(-1);
 await page.route('**/index-csi300-preview.json',route=>route.fulfill({json:index}));
 const summary=page.locator('.market-summary');
 for(const [dif,dea,expected] of [[-2,-1,'偏弱'],[2,1,'偏强'],[2,-1,'分化']] as const){
  row.vw_dif=dif;row.vw_dea=dea;
  await page.goto('/?panel=breadth&sample=csi300');
  await expect(summary).toContainText(`周线量价${expected}（2026-10-30 收盘参考）`);
  await expect(summary.locator('.market-summary-action')).toContainText('先不加仓');
 }
 row.vw_dea=null;
 await page.reload();
 await expect(summary).not.toContainText('周线量价偏');
 await expect(summary).not.toContainText('周线量价分化');
});

test('stale snapshot does not borrow a mismatched previous close',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(new Date(captured.finished_at).getTime()+6*60*1000)});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 captured.breadth.adl_gap_before=false;
 captured.breadth.source='different source';
 b.days=[...b.days.filter((x:any)=>x.date<captured.breadth.date),captured.breadth];
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(page.getByText(/盘中快照已过期/)).toBeVisible();
 await expect(panel).not.toContainText('前一交易日收盘参考');
});

test('captured isolated core RPC results render the corresponding intraday state',async({page})=>{
 const result=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 expect(result.breadth_error).toBe('');expect(result.market_error).toBe('');expect(result.index_error).toBe('');
 await page.clock.install({time:new Date(result.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 breadth.days=[...breadth.days.filter((x:any)=>x.date<result.day.date),result.day];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:[result.quote],minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('2026-10-30 · 盘中暂值');
 await expect(panel).toContainText('上涨家数 18.2%');
 await expect(panel).toContainText('弱势风险检查：评估持仓和减仓计划');
 await expect(panel).toContainText('上证现价 3608.88');
 await expect(panel).toContainText('TRIN 0.735');
 await expect(panel).toContainText('判断依据与历史试算');
});

test('home pauses intraday advice if the latest available index close is stale',async({page})=>{
 const result=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 await page.clock.install({time:new Date(result.finished_at)});
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 breadth.days=[...breadth.days.filter((x:any)=>x.date<result.day.date),result.day];
 const preview=JSON.parse(await readFile('public/preview.json','utf8'));
 preview.market={quotes:[result.quote],minute:null};
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:breadth}));
 await page.route('**/preview.json',route=>route.fulfill({json:preview}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await page.goto('/');
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('先不加仓');
 index.daily=index.daily.filter((row:any)=>row.date<index.latest_eligible);
 index.latest_eligible=index.daily.at(-1).date;
 await page.reload();
 await expect(home).toContainText('等待最新市场数据');
 await expect(home).not.toContainText('分批减仓');
 await expect(home).not.toContainText('分批加仓');
});

for(const [name,price,advance,decline,breadth,expected] of [
 ['跌多且指数偏弱','3500',1220,3830,23.4,'指数低于20日均线且跌多涨少：检查持仓风险'],
 ['涨多且指数偏强','3900',3100,2000,59.4,'指数高于20日均线且涨多跌少：结合仓位计划观察'],
 ['跌多但指数偏强','3900',1220,3830,23.4,'指数位置与涨跌家数表现分化：先观察'],
 ['涨多但指数偏弱','3500',3100,2000,59.4,'指数位置与涨跌家数表现分化：先观察'],
 ['涨跌家数持平','3500',2500,2500,47.9,'指数或个股涨跌接近均衡'],
] as const){
 test(`仓位提示解释当前指标组合：${name}`,async({page})=>{
  const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
  await page.clock.install({time:new Date(captured.finished_at)});
  const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
  const flat=captured.breadth.covered-captured.breadth.suspended-advance-decline;
  const row={...captured.breadth,advance,decline,flat,advancing_percent:100*advance/(advance+decline+flat)};
  setTrin(row,captured.breadth.trin_amount,'amount');setTrin(row,captured.breadth.trin,'volume');
  b.days=[...b.days.filter((x:any)=>x.date<row.date),row];
  const d=JSON.parse(await readFile('public/preview.json','utf8'));
  d.market={quotes:[{...captured.quotes[0],price}],minute:null};
  const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
  Object.assign(index.daily.at(-1),{vw_dif:2,vw_dea:1});
  index.weekly=[{date:'2026-10-23',vw_dif:2,vw_dea:1}];
  await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
  await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
  await page.route('**/preview.json',route=>route.fulfill({json:d}));
  await gotoResearch(page);
  const panel=page.getByRole('region',{name:'市场状态与操作参考'});
  await expect(panel).toContainText(expected);
  const action=panel.locator('.market-summary-action');
  await expect(action).toContainText(name==='跌多且指数偏弱'?'先不加仓；空仓继续观望，持仓较重可考虑分批减仓':name==='涨多且指数偏强'?'可考虑小幅、分批加仓':'暂不加仓，先观察');
  await expect(panel).toContainText('判断依据与历史试算');
  await page.clock.fastForward('05:01');
  await expect(panel).not.toContainText(expected);
  await expect(action).toContainText('暂不依据它调整仓位');
  await expect(panel).toContainText('数据暂不足以给出当前风险提示');
 });
}

test('stale intraday index quote hides combined state but retains fresh breadth',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T02:00:30Z')});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 b.days=[{...b.days.at(-1),status:'provisional',first_quote:'2026-10-29T10:00:00+08:00',last_quote:'2026-10-29T10:00:24+08:00',collected_at:'2026-10-29T10:00:28+08:00'}];
 const d=JSON.parse(await readFile('public/preview.json','utf8'));
 d.market={quotes:[{code:'sh000001',price:'3600',timestamp:'2026-10-29T09:57:00+08:00',source:'tencent'}],minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/preview.json',route=>route.fulfill({json:d}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('数据不足');
 await expect(panel).not.toContainText('上证现价 3600.00');
 await expect(panel).toContainText('指数数据不足或过期，暂不判断综合状态和仓位');
 await expect(panel).toContainText(`上涨家数 ${b.days[0].advancing_percent.toFixed(1)}%`);
 await expect(panel).toContainText(`TRIN ${b.days[0].trin_amount.toFixed(3)}`);
 await expect(panel).toContainText(`上涨股成交额 ${b.days[0].advancing_amount_percent.toFixed(1)}%`);
 await expect(panel).not.toContainText('弱势风险检查：');
});

test('strong index and breadth require compatible TRIN before a gradual-add reference',async({page})=>{
 const captured=JSON.parse(await readFile('fixtures/market-live-20261030.json','utf8'));
 await page.clock.install({time:new Date(captured.finished_at)});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 const advance=3100,decline=2000,flat=captured.breadth.covered-captured.breadth.suspended-advance-decline;
 const row={...captured.breadth,advance,decline,flat,advancing_percent:100*advance/(advance+decline+flat),trin_amount:0.7,trin:1.2};
 setTrin(row,0.7,'amount');setTrin(row,1.2,'volume');
 b.days=[...b.days.filter((x:any)=>x.date<row.date),row];
 const d=JSON.parse(await readFile('public/preview.json','utf8'));
 d.market={quotes:[{...captured.quotes[0],price:'3900'}],minute:null};
 const index=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 Object.assign(index.daily.at(-1),{vw_dif:2,vw_dea:1});
 index.weekly=[{date:'2026-10-23',vw_dif:2,vw_dea:1}];
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:index}));
 await page.route('**/preview.json',route=>route.fulfill({json:d}));
 await page.goto('/?panel=breadth');
 const summary=page.locator('.market-summary');
 await expect(summary.locator('strong').first()).toHaveText('指数高于均线，涨多跌少');
 await expect(summary).toContainText('中期趋势尚未确认');
 await expect(summary.locator('.market-summary-action')).toContainText('可考虑小幅、分批加仓');
 await page.getByLabel('TRIN计算口径').selectOption('volume');
 await expect(summary).toContainText('指数高于均线，涨多跌少');
 await expect(summary.locator('.market-summary-action')).toContainText('可考虑小幅、分批加仓');
 await expect(page.getByLabel('市场解读')).toContainText('成交股数口径');
 row.trin_amount=null;
 await page.goto('/?panel=breadth');
 await expect(summary).toContainText('市场数据待核对');
 await expect(summary.locator('.market-summary-action')).toContainText('成交结构数据不足');
 await expect(summary.locator('.market-summary-action')).not.toContainText('可考虑小幅、分批加仓');
});

test('fresh index is shown independently when breadth and index timestamps do not align',async({page})=>{
 await page.clock.install({time:new Date('2026-10-29T02:03:00Z')});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 b.days=[{...b.days.at(-1),status:'provisional',first_quote:'2026-10-29T10:00:00+08:00',last_quote:'2026-10-29T10:00:24+08:00',collected_at:'2026-10-29T10:00:28+08:00'}];
 const idx=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 idx.daily=idx.daily.filter((x:any)=>x.date<'2026-10-29');idx.latest_eligible='2026-10-28';
 idx.collected_at='2026-10-28T16:30:00+08:00';
 const d=JSON.parse(await readFile('public/preview.json','utf8'));
 d.market={quotes:[{code:'sh000001',price:'3600',timestamp:'2026-10-29T10:02:55+08:00',source:'tencent'}],minute:null};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/index-technical-preview.json',route=>route.fulfill({json:idx}));
 await page.route('**/preview.json',route=>route.fulfill({json:d}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('上证现价 3600.00');
 await expect(panel).toContainText('两类数据不同步，暂不判断综合状态和仓位');
 await expect(panel).toContainText('指数报价 10:02:55');
 await expect(panel).toContainText('上证现价与20日暂时均线仅供单独查看');
 await expect(panel).not.toContainText('弱势风险检查：');
 await page.clock.fastForward('03:00');
 await expect(panel).toContainText('TRIN —');
 await expect(panel).not.toContainText('上证现价 3600.00');
});

test('minute chart failure does not hide an independently fresh index quote',async({page})=>{
 const result=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 await page.clock.install({time:new Date(result.finished_at)});
 const b=JSON.parse(await readFile('public/breadth-preview.json','utf8'));
 b.days=[...b.days.filter((x:any)=>x.date<result.day.date),result.day];
 const d=JSON.parse(await readFile('public/preview.json','utf8'));
 d.market={quotes:[result.quote],minute:null,error:'上证分时暂时不可用'};
 await page.route('**/breadth-preview.json',route=>route.fulfill({json:b}));
 await page.route('**/preview.json',route=>route.fulfill({json:d}));
 await gotoResearch(page);
 const panel=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(panel).toContainText('上证现价 3608.88');
 await expect(panel).toContainText('弱势风险检查：评估持仓和减仓计划');
 await page.clock.fastForward('05:01');
 await expect(panel).not.toContainText('上证现价 3608.88');
 await expect(panel).not.toContainText('弱势风险检查：');
});

test('position experiment is a fixed cost-aware comparison, not an account result',async({page})=>{
 await gotoResearch(page);
 const decision=page.getByRole('region',{name:'市场状态与操作参考'});
 await expect(decision).toContainText('历史试算：弱势条件下模拟减半仓');
 await expect(decision).toContainText('22 次中 10 次优于一直持有、12 次较差');
 const panel=page.getByLabel('仓位动作历史实验');
 await panel.locator('summary').click();
 await expect(panel).toContainText('顺势代理试算');
 await expect(panel).toContainText('2026-01-19 至 2026-10-29');
 await expect(panel).toContainText('期末收益 -7.12%，最大收盘回撤 12.25%，交易 26 笔');
 await expect(panel).toContainText('趋势代理 3.23%／持有 5.91%');
 await expect(panel).toContainText('趋势代理 -9.89%／持有 -17.91%');
 await expect(panel).toContainText('不是样本外验证');
 await expect(panel).toContainText('低 TRIN 买入试算');
 await expect(panel).toContainText('19 个可比较案例');
 await expect(panel).toContainText('10 次盈利、9 次亏损或持平');
 await expect(panel).toContainText('全部可比较日期 174 个');
 await expect(panel).toContainText('案例仅 2 个，无法判断低 TRIN 的独立作用');
 await expect(panel).toContainText('22 个单次对照案例');
 await expect(panel).toContainText('优于一直持有 10 次');
 await expect(panel).toContainText('低于一直持有 12 次');
 await expect(panel).toContainText('剩余 12 个案例');
 await expect(panel).toContainText('较好 5 次、较差 7 次');
 await expect(panel).toContainText('放宽条件对照');
 await expect(panel).toContainText('19 个案例，较好 8 次、较差 11 次');
 await expect(panel).toContainText('该条件同样未证明能改善收益');
 await expect(panel).toContainText('平均差额 -178.33 元');
 await expect(panel).toContainText('不代表样本在统计上独立');
 await expect(panel).toContainText('非账户实际盈亏');
 await expect(panel).toContainText('开盘价不保证成交');
});


test('market interface removes author material while retaining indicators',async({page})=>{
 await page.goto('/?panel=breadth');
 await expect(page.getByRole('region',{name:'市场趋势图'})).toContainText('黄线 · TRIN 怎么看');
 await page.getByLabel('指标依据').locator(':scope > summary').click();
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.locator('.market-summary-details > summary').click();
 const body=page.locator('body');
 await expect(body).not.toContainText(/博主|作者|原视频|抖音/);
 await expect(page.locator('a[href*="douyin.com"]')).toHaveCount(0);
 await expect(page.getByText('计算口径与数据明细',{exact:true})).toBeVisible();
 await expect(page.getByRole('img',{name:/上涨股成交额占比柱状图/})).toBeVisible();
});

test('固定规则回放对照显示收益、回撤及成交次数',async({page})=>{
 await page.goto('/?sample=csi300');
 await page.getByRole('button',{name:'查看市场趋势'}).click();
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary-details > summary').click();
 const research=page.getByLabel('仓位动作历史实验');await research.locator(':scope > summary').click();
 await expect(research).toContainText('均线＋广度＋TRIN');await expect(research).toContainText('-8.30%');
 await expect(research).toContainText('非独立样本外验证');await expect(research.getByRole('columnheader',{name:'最大回撤'})).toBeVisible();
});

test('首页趋势对齐三项指标并支持从下方图表选择日期',async({page})=>{
 await page.clock.install({time:new Date('2026-10-30T20:00:00Z')});
 await page.goto('/?sample=csi300');
 const region=page.getByRole('region',{name:'首页市场趋势'}),metrics=region.getByLabel('同日市场指标');
 const chart=region.getByRole('img',{name:'首页上涨家数、成交占比与TRIN趋势'});
 const option=()=>chart.evaluate(async el=>{
  const source=await fetch('/src/HomeMarketTrend.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const o=e.getInstanceByDom(el).getOption();return {grids:o.grid.length,aligned:JSON.stringify(o.xAxis[0].data)===JSON.stringify(o.xAxis[1].data),series:o.series.length,lowerAxis:o.series[2].xAxisIndex};
 });
 await expect(metrics).toContainText('上涨股票 16.4%');await expect(metrics).toContainText('TRIN 0.674');
 await expect(region.locator('.home-trend-explanation')).toContainText('同一日期对齐');
 await expect.poll(option).toEqual({grids:2,aligned:true,series:3,lowerAxis:1});
 await expect(region.getByLabel('首页趋势解读')).toContainText('2026-10-30 · 收盘');
 const point=await chart.evaluate(async el=>{
  const source=await fetch('/src/HomeMarketTrend.tsx').then(r=>r.text());
  const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  return e.getInstanceByDom(el).convertToPixel({xAxisIndex:1,yAxisIndex:1},['2026-10-23',1.066]);
 });
 const chartBox=await chart.boundingBox();expect(chartBox).not.toBeNull();await page.mouse.click(chartBox!.x+point[0],chartBox!.y+point[1]);
 await expect(region.getByLabel('首页趋势解读')).toContainText('2026-10-23 · 收盘');
 await expect(metrics).toContainText('TRIN 1.066');
 await page.mouse.move(chartBox!.x+point[0],chartBox!.y+point[1]);
 await expect(chart).toContainText('上涨股票：80.4%');await expect(chart).toContainText('TRIN：1.066');
 await page.setViewportSize({width:1000,height:680});
 await expect(async()=>{
  const bounds=await region.boundingBox();expect(bounds).not.toBeNull();
  for(const item of await metrics.locator(':scope > span').all()){
   const box=await item.boundingBox();expect(box).not.toBeNull();
   expect(box!.x).toBeGreaterThanOrEqual(bounds!.x-1);expect(box!.x+box!.width).toBeLessThanOrEqual(bounds!.x+bounds!.width+1);
  }
 }).toPass();
});

test('首页行业资金展示来源时间和正负方向，缺数据时不编造排行',async({page})=>{
 await page.route('**/sector-flow-preview.json',route=>route.fulfill({json:{running:false,error:'',source_url:'https://data.eastmoney.com/bkzj/hy.html',snapshot:{date:'2026-10-30',quote_time:'2026-10-30T15:39:30+08:00',collected_at:'2026-10-31T01:00:00+08:00',source:'东方财富行业板块资金流',inflow:[{code:'BK0001',name:'示例甲',net_yuan:230000000,change_percent:1.5}],outflow:[{code:'BK0002',name:'示例乙',net_yuan:-80000000,change_percent:-0.5}]}}}));
 await page.goto('/?sample=csi300');const panel=page.getByLabel('行业资金观察');
 await expect(panel).toContainText('2026-10-30 · 15:39:30');await expect(panel).toContainText('示例甲');await expect(panel).toContainText('+2.30亿');
 await expect(panel).toContainText('示例乙');await expect(panel).toContainText('−8000万');await expect(panel).toContainText('板块可能重叠');
 await page.unroute('**/sector-flow-preview.json');await page.route('**/sector-flow-preview.json',route=>route.fulfill({json:{snapshot:null,running:false,error:'不可用'}}));await page.reload();
 await expect(panel).toContainText('板块资金暂不可用');await expect(panel).not.toContainText('示例甲');
});

test('新浪备源明确标注推定日期和统计口径',async({page})=>{
 await page.clock.install({time:new Date('2026-10-31T08:00:00Z')});
 await page.route('**/sector-flow-preview.json',route=>route.fulfill({json:{running:false,error:'',snapshot:{date:'2026-10-30',date_inferred:true,quote_time:null,collected_at:'2026-10-31T13:00:00+08:00',source:'新浪行业资金流',inflow:[{code:'new_a',name:'行业甲',net_yuan:100000000,change_percent:1}],outflow:[{code:'new_b',name:'行业乙',net_yuan:-200000000,change_percent:-2}]}}}));
 await page.goto('/?sample=csi300');const panel=page.getByLabel('行业资金观察');
 await expect(panel).toContainText('2026-10-30 · 日期推定 · 新浪行业资金流');await expect(panel).toContainText('方向净流入较多');
 await expect(panel).toContainText('行业统计时间未提供');await expect(panel).not.toContainText('大单净流入');
 await expect(panel).toContainText('可先观察行业甲');await expect(panel).toContainText('持有行业乙');
});
