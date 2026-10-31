import {test,expect,Page} from '@playwright/test';
import {spawn,ChildProcessWithoutNullStreams} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {turningShapes} from '../../src/turningShapes';
let process:ChildProcessWithoutNullStreams;let directory:string;let paperChartRequests=0;let dailyLoadRequests:any[]=[];
let waiting:{resolve:(r:any)=>void;reject:(e:Error)=>void}[]=[];
async function rpc(method:string,args:Record<string,unknown>={}){if(process.stdin.writableEnded)return null;return new Promise<any>((resolve,reject)=>{waiting.push({resolve,reject});process.stdin.write(JSON.stringify({method,args})+'\n');});}
test.beforeEach(async({page})=>{
 paperChartRequests=0;dailyLoadRequests=[];
 directory=await mkdtemp(join(tmpdir(),'stock-ui-audit-'));
 process=spawn('.venv/bin/python',['tests/ui/rpc_fixture.py'],{env:{...global.process.env,PYTHONPATH:global.process.cwd(),STOCK_MONITOR_DATA:directory},stdio:'pipe'});
 waiting=[];
 createInterface({input:process.stdout}).on('line',line=>{const reply=JSON.parse(line),p=waiting.shift();if(reply.ok)p?.resolve(reply.data);else p?.reject(Error(reply.error));});
 process.stderr.on('data',chunk=>console.error(String(chunk)));
 await page.exposeFunction('__auditRpc',async(cmd:string,args:any)=>{
  if(cmd==='plugin:autostart|is_enabled')return false;
  if(cmd==='rpc'){
   if(args.method==='paper_chart')paperChartRequests++;
   if(args.method==='daily_load')dailyLoadRequests.push(args.args);
   if(args.method==='chart'&&args.args.code==='sh603002')await new Promise(r=>setTimeout(r,220));
   return rpc(args.method,args.args);
  }
  return true;
 });
 await page.addInitScript(()=>{if(!sessionStorage.getItem('__audit-turning-version-initialized')){localStorage.setItem('stock-monitor-turning-version','v1');sessionStorage.setItem('__audit-turning-version-initialized','true');}(window as any).isTauri=true;(window as any).__TAURI_INTERNALS__={invoke:(cmd:string,args:any)=>(window as any).__auditRpc(cmd,args)};});
 await page.goto('/');await expect(page.locator('.stock')).toHaveCount(12);
});
test.afterEach(async({page})=>{await page.close();process.stdin.end();await new Promise(resolve=>process.once('exit',resolve));await rm(directory,{recursive:true,force:true});});

test('market guidance uses isolated real RPC data and pauses after a backend failure',async({page})=>{
 await rpc('__audit_market_decision_reference');
 await page.clock.install({time:new Date('2026-10-30T19:30:00Z')});
 await page.reload();
 const home=page.getByRole('region',{name:'首页市场判断'});
 await expect(home).toContainText('数据不足，等待更新');
 await expect(home).not.toContainText('先不加仓');
 await page.clock.setFixedTime(new Date('2026-10-30T20:00:00Z'));
 await page.reload();
 await expect(home).toContainText('2026-10-30 · 最近收盘');
 await expect(home).not.toContainText('静态预览');
 await expect(home).toContainText('先不加仓；空仓继续观望');
 await expect(home).toContainText('上涨股票 16.4%');
 await expect(home).toContainText('上涨组成交额更集中在沪深300');
 await expect(home.locator('.home-market-core')).toHaveText('沪深300：上涨组成交额占比高于下跌组（35.4% 对 24.8%）。');
 const evidence=home.locator('.home-market-evidence');
 await evidence.locator('summary').click();
 await expect(evidence).toContainText('2026-10-30 收盘沪深股票成交股数较 2026-10-29 增加 12.4%');
 await rpc('__audit_breadth_error',{error:'全市场数据获取失败'});
 await page.reload();
 await expect(home).toContainText('市场数据更新失败');
 await expect(home).not.toContainText('先不加仓');
 await expect(home.locator('.home-market-core')).toHaveCount(0);
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 const summary=page.getByRole('region',{name:'市场状态与操作参考'}).locator('.market-summary');
 await expect(summary.locator('.market-summary-action')).toContainText('市场数据更新失败');
 await expect(page.getByRole('img',{name:/上涨股成交额占比柱状图/})).toBeVisible();
 await rpc('__audit_breadth_error',{error:''});
 await page.goto('/');
 await expect(home).toContainText('先不加仓；空仓继续观望');
 await expect(home).toContainText('少数上涨股相对放量');
 await rpc('__audit_index_error',{error:'指数数据获取失败'});
 await page.reload();
 await expect(home).toContainText('指数数据更新失败');
 await expect(home).not.toContainText('分批减仓');
 await home.getByRole('button',{name:'查看市场趋势'}).click();
 await expect(summary.locator('.market-summary-action')).toContainText('指数数据更新失败');
 await expect(page.getByRole('img',{name:/上涨股成交额占比柱状图/})).toBeVisible();
 await rpc('__audit_index_error',{error:''});
 await page.goto('/');
 await expect(home).toContainText('先不加仓；空仓继续观望');
});

test('exchange ETF PCR reaches the chart through the real isolated backend',async({page})=>{
 await rpc('__audit_market_decision_reference');
 await rpc('__audit_etf_option_clock',{now:'2026-10-31T05:00:00+08:00'});
 await page.clock.install({time:new Date('2026-10-30T21:00:00Z')});
 await page.reload();
 await page.getByRole('region',{name:'首页市场判断'}).getByRole('button',{name:'查看市场趋势'}).click();
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('期权标的').selectOption('etf-exchanges');
 const panel=page.getByRole('region',{name:'沪深ETF合计期权PCR'});
 await expect(panel.locator('.option-readout strong').first()).toHaveText('0.851');
 await expect(panel).toContainText('3,926,198 / 4,611,003 张');
 await expect(panel).toContainText('不含中金所');
});

test('index-option PCR reaches the chart through the real isolated backend',async({page})=>{
 await rpc('__audit_market_decision_reference');
 await page.clock.install({time:new Date('2026-10-30T22:00:00Z')});
 await page.reload();
 await page.getByRole('region',{name:'首页市场判断'}).getByRole('button',{name:'查看市场趋势'}).click();
 await page.getByLabel('市场图表与研究详情').locator(':scope > summary').click();
 await page.getByLabel('期权标的').selectOption('cffex-IO');
 const panel=page.getByRole('region',{name:'沪深300股指期权PCR'});
 await expect(panel.locator('.option-readout strong').first()).toHaveText('0.612');
 await expect(panel).toContainText('47,939 / 78,341 张');
 await expect(panel).toContainText('不代表全市场');
});

test('same-stock click preserves graph; rapid selection never shows the previous stock cache',async({page})=>{
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 await page.locator('.stock').filter({hasText:'宏昌电子'}).click();
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 await page.locator('.stock').filter({hasText:'海优新材'}).click();
 await page.locator('.stock').filter({hasText:'宏昌电子'}).click();
 await page.locator('.stock').filter({hasText:'海优新材'}).click();
 await expect(page.locator('.detail h2')).toContainText('海优新材');
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 // Inspect only the chart instance created by this page to verify actual displayed data identity.
 const expected=await rpc('chart',{code:'sh688680',kind:'minute'});
 expect(expected[0].data.bars.find((b:any)=>b.time==='09:31').close).not.toBe('16.20');
 const chart=page.locator('.chart');
 await expect.poll(()=>chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const option=e.getInstanceByDom(el).getOption();return option.series[0].data[option.xAxis[0].data.indexOf('09:31')];})).toBe(+expected[0].data.bars.find((b:any)=>b.time==='09:31').close);
 const point=await chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption(),i=o.xAxis[0].data.indexOf('09:31');return c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:31',o.series[0].data[i]]);});
 const box=(await chart.boundingBox())!;await page.mouse.move(box.x+point[0],box.y+point[1]);
 await expect(chart).toContainText(Number(expected[0].data.bars.find((b:any)=>b.time==='09:31').close).toLocaleString('zh-CN',{maximumFractionDigits:2}));
 await expect(page.locator('.chart-caption')).toContainText('2026-10-16');
});

test('add, duplicate, invalid code, pause, remove and last-stock removal',async({page})=>{
 await page.getByLabel('股票代码').fill('600519');await page.getByRole('button',{name:'＋',exact:true}).click();
 await expect(page.locator('.stock')).toHaveCount(13);await expect(page.locator('.detail h2')).toContainText('贵州茅台');
 await page.getByLabel('股票代码').fill('600519');await page.getByRole('button',{name:'＋',exact:true}).click();await expect(page.locator('.stock')).toHaveCount(13);
 await page.getByRole('button',{name:'暂停',exact:true}).click();await expect(page.getByRole('button',{name:'恢复',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'恢复',exact:true}).click();await expect(page.getByRole('button',{name:'暂停',exact:true})).toBeVisible();
 await page.getByLabel('股票代码').fill('699999');await page.getByRole('button',{name:'＋',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('股票不存在');await expect(page.locator('.stock')).toHaveCount(13);
 await page.getByRole('button',{name:'移除',exact:true}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'取消',exact:true}).click();await expect(page.locator('.stock')).toHaveCount(13);await page.getByRole('button',{name:'移除',exact:true}).click();await page.getByRole('button',{name:'确认移除',exact:true}).click();await expect(page.locator('.stock')).toHaveCount(12);
 for(const w of (await rpc('snapshot')).watch)await rpc('remove',{code:w.code});
 await expect(page.getByText('自选池为空，请输入股票代码添加。')).toBeVisible();await expect(page.locator('.detail')).toHaveCount(0);
 await page.getByLabel('股票代码').fill('600519');await page.getByRole('button',{name:'＋',exact:true}).click();await expect(page.locator('.stock')).toHaveCount(1);
});

test('manual refresh updates displayed quote and daily/minute cache without live notifications',async({page})=>{
 await page.getByRole('button',{name:'刷新行情',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('行情刷新完成');
 await expect(page.locator('.stock.selected .stock-right strong')).toHaveText('9.99');
 await expect(page.locator('.detail-top p')).toContainText('2026-10-16 15:00:00');
 expect((await rpc('snapshot')).events.filter((e:any)=>e.mode==='live')).toHaveLength(0);
});

test('latest-day chart follows new cache while manually selected history stays pinned',async({page})=>{
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 const old=await rpc('chart',{code:'sh603002',kind:'minute'});
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{...old[0].data,trading_date:'2026-10-19'}});
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19',{timeout:10000});
 await page.getByLabel('交易日期').selectOption('2026-10-16');
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-20',data:{...old[0].data,trading_date:'2026-10-20'}});
 await expect(page.getByLabel('交易日期').locator('option')).toHaveCount(3,{timeout:10000});
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
});

test('trigger records show Chinese stock name and ten-thousand shares',async({page})=>{
 await rpc('replay',{code:'sh603002',day:'2026-10-16'});
 // Trigger records are now inline below the chart; the removed navigation is not required.
 await expect(page.getByRole('columnheader',{name:'三分钟量（万股）'})).toBeVisible();
 const row=page.locator('tbody tr').filter({hasText:'宏昌电子'});await expect(row).toContainText('603002');
 await expect(row).toContainText('438.45 / 146.10 / 195.70');await expect(row).toContainText('腾讯行情');
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/0.4.0/records.png',fullPage:true});
});

test('daily keyboard navigation and double click open selected intraday without date query fields',async({page})=>{
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(page.getByLabel('日K开始日期')).toHaveCount(0);
 const chart=page.getByLabel('日K线及成交量');await chart.focus();
 await chart.press('ArrowLeft');await expect(page.locator('.linked-minute h3')).toContainText('2026-10-15');
 await expect(chart.locator('.quote-tooltip')).toContainText('开盘：');
 await chart.press('ArrowRight');await expect(page.locator('.linked-minute h3')).toContainText('2026-10-16');
 const box=(await chart.boundingBox())!;
 // Last visible daily volume bar, which shares the candle's trading date.
 await page.mouse.dblclick(box.x+box.width-40,box.y+box.height*.86);
 await expect(page.getByRole('button',{name:'分时',exact:true})).toHaveClass('chosen');
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 await expect(page.locator('.day-signals')).toContainText('438.45 / 146.10 / 195.70');
 await page.getByRole('button',{name:'日K',exact:true}).click();await expect(page.locator('.linked-minute h3')).toContainText('2026-10-16');
 await chart.focus();await chart.press('ArrowLeft');await chart.press('Enter');
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-15');
 expect((await rpc('messages')).total).toBe(0);
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/0.4.0/intraday.png',fullPage:true});
});

async function selectDailyDate(page:Page,date?:string){
 return page.getByLabel('日K线及成交量').evaluate(async(el,date)=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const c=e.getInstanceByDom(el),day=date||c.getOption().xAxis[0].data[0];c.trigger('click',{componentType:'series',name:day});return day as string;},date);
}

test('daily left boundary expands using local cached history and retains selected date',async({page})=>{
 await rpc('__audit_daily',{code:'sh603002',day:'2025-01-15',data:{date:'2025-01-15',open:'10',close:'10.1',high:'10.2',low:'9.9',volume:'10000',volume_unit:'shares',source:'tencent'}});
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const before=await selectDailyDate(page);
 await page.getByLabel('日K线及成交量').focus();await page.getByLabel('日K线及成交量').press('ArrowLeft');
 await expect(page.locator('.linked-minute h3')).not.toContainText(before.slice(0,10));
 const day=await page.locator('.linked-minute h3').innerText();expect(day<before.slice(0,10)).toBeTruthy();
 await expect(page.locator('.chart-caption')).toContainText('本地缓存优先');
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/0.4.0/history.png',fullPage:true});
});

test('hidden message navigation keeps existing records and read state intact',async({page})=>{
 const e={key:'2026-10-16|603002|09:31',symbol:'603002',trading_date:'2026-10-16',candidate_time:'09:31',confirmation_label:'09:33',event_label:'09:33',volumes:[4384500,1461000,1957000],kind:'TWO_MINUTE_CONFIRMATION',observed_at:'2026-10-16T09:33:05+08:00'};
 await rpc('__audit_event',e);await rpc('__audit_event',e);
 await expect(page.getByRole('button',{name:'消息中心',exact:true})).toHaveCount(0);
 const messages=await rpc('messages');expect(messages.items).toHaveLength(1);expect(JSON.stringify(messages.items)).toContain('宏昌电子');
 await rpc('message_read',{all:true});await page.reload();
 expect((await rpc('messages')).items[0].read_at).toBeTruthy();
});

test('source addresses and safe reserved provider switch are visible',async({page})=>{
 await page.locator('.source-details summary').click();await expect(page.locator('.source-details')).toContainText('https://qt.gtimg.cn/q=sh603002');await expect(page.locator('.source-details')).toContainText('https://web.ifzq.gtimg.cn/appstock/app/day/query?code=sh603002');
 await page.getByRole('button',{name:/设置与通知/}).click();await expect(page.getByLabel('行情数据来源')).toHaveValue('tencent');
 await expect(page.getByLabel('行情数据来源').locator('option[value=sina]')).toBeDisabled();
});

test('historical minute cache with unknown limit shows pending reference, manual confirmation enables read-only replay',async({page})=>{
 const old=(await rpc('chart',{code:'sh603002',kind:'minute'}))[0].data;const changed={...old,trading_date:'2026-10-15'};delete changed.limit_up;
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-15',data:changed});
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await selectDailyDate(page,'2026-10-15');
 await expect(page.locator('.history-status')).toContainText('缺少当日可靠涨停价');
 await page.getByLabel('历史涨停价').fill('17.89');await page.getByRole('button',{name:'保存参考价并回放'}).click();
 await expect(page.locator('.history-status')).toContainText('完整分钟量回放');await expect(page.locator('.day-signals')).toContainText('438.45');
 expect((await rpc('messages')).total).toBe(0);
});

test('confirmed shapes and frozen Q1 quality have independent displays without changing formal triggers',async({page})=>{
 const {readFileSync}=await import('node:fs');
 const example=JSON.parse(readFileSync('tests/ui/fixtures/turning-q1.json','utf8'))[1];
 await page.evaluate(()=>{localStorage.setItem('stock-monitor-show-turning-v1','false');localStorage.setItem('stock-monitor-bottom-quality-v1','true');localStorage.setItem('stock-monitor-top-supplement-v2','true');localStorage.setItem('stock-monitor-turning-version','v4');localStorage.setItem('stock-monitor-show-turning-shapes-v1','true');localStorage.setItem('stock-monitor-show-turning-v2','true');});
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'frozen-q1-ui-test-only',bars:example.bars}});
 await rpc('__audit_event',{key:'2026-10-19|603002|09:50',symbol:'603002',trading_date:'2026-10-19',candidate_time:'09:50',confirmation_label:'09:52',event_label:'09:52',volumes:[300000,100000,100000],kind:'TWO_MINUTE_CONFIRMATION'});
 const before=await rpc('snapshot'),messages=await rpc('messages');
 await page.reload();await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19');
 const chart=page.getByLabel('分时价格及分钟成交量'),shapeToggle=page.getByRole('checkbox',{name:'显示形态底/顶',exact:true}),qualityToggle=page.getByRole('checkbox',{name:'显示Q1质量',exact:true});
 const marks=(field:'observationKey'|'qualityKey')=>chart.evaluate(async(el,field)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].markPoint.data.filter((m:any)=>m[field]).map((m:any)=>({coord:m.coord,key:m[field]}));},field);
 const expected=example.expected.map((m:any)=>({coord:[m.time,m.price],key:m.key}));
 const shapeExpected=turningShapes(example.bars).map(m=>({coord:[m.time,m.price],key:m.key}));
 await expect(shapeToggle).toBeChecked();await expect(qualityToggle).toBeChecked();await expect.poll(()=>marks('qualityKey')).toEqual(expected);await expect.poll(()=>marks('observationKey')).toEqual(shapeExpected);
 for(const label of ['显示开盘量','显示形态底/顶','显示Q1质量'])await expect(page.getByRole('checkbox',{name:label,exact:true})).toHaveCount(1);
 for(const description of ['09:31单独标记','小点彩签 · 已确认反转','白边小点 · 冻结筛选'])await expect(page.locator('.opening-volume-toggle')).not.toContainText([description]);
 await expect(page.getByRole('checkbox',{name:/缩量顶补漏/})).toHaveCount(0);await expect(page.getByLabel('底顶观察版本')).toHaveCount(0);
 await expect(page.locator('.average-caption')).toContainText('Q1筛选未改');
 const show=async(time:string)=>chart.evaluate(async(el,time)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el);c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:c.getOption().xAxis[0].data.indexOf(time)});},time);
 await show(example.expected[0].time);const tooltip=chart.locator('.quote-tooltip');
 await expect(tooltip).toContainText('底形态：');for(const hidden of ['Q1质量：','Q1假设净空间','Q1冻结版','确认依据：','研究滑点：','信号间隔：','验证状态：'])await expect(tooltip).not.toContainText(hidden);await expect(tooltip).toContainText('候选点：09:57');await expect(tooltip).toContainText('确认时间：09:59');
 await expect(tooltip).toContainText('基准触发：09:50');
 const dock=(await tooltip.locator('..').boundingBox())!,plotBox=(await chart.boundingBox())!;
 expect(dock.y+dock.height).toBeLessThanOrEqual(plotBox.y+30);
 expect(await tooltip.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el),m=c.getOption().series[0].markPoint.data.find((m:any)=>m.value==='底形态');c.trigger('click',{componentType:'markPoint',data:m});});
 await show(example.expected[0].time);await expect(tooltip).toContainText(`基准底：${example.expected[0].time}`);await expect(tooltip).toContainText('相对底涨跌幅：');
 for(const kind of ['底','顶']){
  const selected=await chart.evaluate(async(el,kind)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const c=e.getInstanceByDom(el),m=c.getOption().series[0].markPoint.data.find((m:any)=>m.turningKind===kind);if(!m)return null;c.trigger('click',{componentType:'markPoint',data:m});return m.coord;},kind);
  expect(selected).not.toBeNull();
  await show('15:00');await expect(tooltip).toContainText(`基准${kind}：${selected[0]}`);
  await expect(tooltip).toContainText(`相对${kind}涨跌幅：`);
  await expect(tooltip.locator('.quote-trade-prices')).toContainText(`卖出 ${Number(selected[1]).toFixed(2)} 元`);
  await page.getByRole('button',{name:'先买后卖',exact:true}).click();await show('15:00');
  await expect(tooltip.locator('.quote-trade-prices')).toContainText(`买入 ${Number(selected[1]).toFixed(2)} 元`);
  await page.getByRole('button',{name:'先卖后买',exact:true}).click();
 }
 await qualityToggle.uncheck();await expect.poll(()=>marks('qualityKey')).toEqual([]);await expect.poll(()=>marks('observationKey')).toEqual(shapeExpected);
 await page.reload();await expect(qualityToggle).not.toBeChecked();await expect(shapeToggle).toBeChecked();await qualityToggle.check();
 await shapeToggle.uncheck();await expect.poll(()=>marks('observationKey')).toEqual([]);await expect.poll(()=>marks('qualityKey')).toEqual(expected);
 await qualityToggle.uncheck();await expect.poll(()=>marks('qualityKey')).toEqual([]);await page.reload();await expect(shapeToggle).not.toBeChecked();await expect(qualityToggle).not.toBeChecked();await shapeToggle.check();await qualityToggle.check();
 await page.getByRole('button',{name:'日K',exact:true}).click();const linked=page.locator('.linked-minute');await expect(linked.getByRole('checkbox',{name:'显示形态底/顶',exact:true})).toBeChecked();await linked.getByRole('checkbox',{name:'显示Q1质量',exact:true}).uncheck();
 await page.getByRole('button',{name:'分时',exact:true}).click();await expect(qualityToggle).not.toBeChecked();await expect(shapeToggle).toBeChecked();await qualityToggle.check();await expect.poll(()=>marks('qualityKey')).toEqual(expected);
 await page.mouse.move(10,10);await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);e.getInstanceByDom(el).dispatchAction({type:'hideTip'});});await page.screenshot({path:test.info().outputPath('shape-q1-display.png'),fullPage:true});
 expect((await rpc('snapshot')).events).toEqual(before.events);expect(await rpc('messages')).toEqual(messages);
});

test('actual missing-side caches show confirmed bottom and top with concise independent Q1 markers',async({page})=>{
 const {readFileSync}=await import('node:fs');
 const cases=JSON.parse(readFileSync('tests/ui/fixtures/turning-shapes.json','utf8'));
 const before=await rpc('snapshot'),messages=await rpc('messages');
 for(const c of cases){
  await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'shape-ui-test-only',bars:c.bars}});
  await page.reload();await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19');
  const chart=page.getByLabel('分时价格及分钟成交量');
  const marks=()=>chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].markPoint.data.filter((m:any)=>m.observationKey||m.qualityKey).map((m:any)=>({coord:m.coord,shape:m.observationKey||null,q1:m.qualityKey||null,label:m.label.show,symbol:m.symbol}));});
  await expect.poll(async()=>{const all=await marks();return all.filter((m:any)=>m.shape).map((m:any)=>m.coord);}).toEqual(c.expectedShapes.map((m:any)=>[m.time,m.price]));
  const all=await marks();expect(all.filter((m:any)=>m.q1).map((m:any)=>m.coord)).toEqual(c.expectedQ1.map((m:any)=>[m.time,m.price]));
  expect(all.filter((m:any)=>m.label).length).toBe(c.expectedShapes.length);
  for(const m of all.filter((m:any)=>m.q1&&!m.shape)){expect(m.symbol).toBe('circle');expect(m.label).toBe(false);}
  expect(new Set(all.map((m:any)=>m.coord[0])).size).toBe(all.length);
  const qualityToggle=page.getByRole('checkbox',{name:'显示Q1质量',exact:true});await qualityToggle.uncheck();
  await expect.poll(async()=>(await marks()).filter((m:any)=>m.shape).map((m:any)=>m.coord)).toEqual(c.expectedShapes.map((m:any)=>[m.time,m.price]));
  const shapeOnly=await marks();expect(shapeOnly.some((m:any)=>m.q1)).toBe(false);expect(shapeOnly.filter((m:any)=>m.shape&&m.coord[0]===c.expectedShapes.find((m:any)=>m.kind==='bottom').time)).toHaveLength(1);
  await qualityToggle.check();
 }
 expect((await rpc('snapshot')).events).toEqual(before.events);expect(await rpc('messages')).toEqual(messages);
});

test('intraday average is shown from turnover data and removed daily toolbar stays absent',async({page})=>{
 const old=await rpc('chart',{code:'sh603002',kind:'minute'});const data=old[0].data;
 data.bars=data.bars.map((b:any)=>({...b,average:'15.4321'}));
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-16',data});
 await page.reload();await expect(page.locator('.average-caption')).toContainText('累计成交额');
 const chart=page.getByLabel('分时价格及分钟成交量');
 const point=await chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption(),i=o.xAxis[0].data.indexOf('09:31');return c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:31',o.series[0].data[i]]);});
 const box=(await chart.boundingBox())!;await page.mouse.move(box.x+point[0],box.y+point[1]);
 await expect(chart.locator('.quote-tooltip')).toContainText('均价：15.43 元');
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(page.locator('.daily-navigation')).toHaveCount(0);await expect(page.getByRole('button',{name:'← 上一交易日',exact:true})).toHaveCount(0);
});

test('old daily selection explains missing intraday and can return to available history',async({page})=>{
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await selectDailyDate(page);
 await page.getByLabel('日K线及成交量').focus();await page.getByLabel('日K线及成交量').press('Enter');
 await expect(page.getByRole('button',{name:'查看最近可用分时'})).toBeVisible();
 await expect(page.locator('.detail')).toContainText('日K历史范围比分钟接口更长');
 await page.getByRole('button',{name:'查看最近可用分时'}).click();
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 await expect(page.getByLabel('分时价格及分钟成交量')).toBeVisible();
});

test('twenty-day coverage shows whole-day Sina history without claiming certified signals',async({page})=>{
 const rows=await rpc('chart',{code:'sh603002',kind:'minute'});
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-09',data:{...rows[0].data,date:'2026-10-09',source:'sina',rule_compatible:false,source_note:'新浪历史补充，规则回放暂未认证'}});
 await page.getByRole('button',{name:/数据管理/}).click();
 await expect(page.getByRole('heading',{name:'最近20个交易日 · 分时缓存完整性'})).toBeVisible();
 await expect(page.locator('.coverage-day')).toHaveCount(20);
 const day=page.locator('.coverage-day').filter({hasText:'2026-10-09'});
 await expect(day).toContainText('新浪行情');await expect(day).toContainText('新浪口径待核对');
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/0.4.0/coverage.png',fullPage:true});
 await day.click();await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-09');
 await expect(page.locator('.day-signals')).toContainText('规则回放暂未认证');
 expect((await rpc('messages')).total).toBe(0);
});

test('index cards replace old summary and chart keyboard focus has no enclosing outline',async({page})=>{
 await rpc('__audit_market',{quotes:[{code:'sh000001',price:'3697.52',change:'7.04',percent:'0.19',timestamp:'2026-10-26T16:14:00+08:00'},{code:'sz399001',price:'11534.38',change:'-139.45',percent:'-1.19',timestamp:'2026-10-26T16:14:57+08:00'},{code:'sz399006',price:'2638.23',change:'-45.87',percent:'-1.71',timestamp:'2026-10-26T16:14:12+08:00'}]});
 await page.reload();await expect(page.locator('.summary .index-value')).toHaveCount(3);await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 const layout=[];
 for(const width of [1984,1380,1000]){
  await page.setViewportSize({width,height:980});
  for(const collapsed of [true,false]){
   const button=page.getByRole('button',{name:collapsed?'折叠侧栏':'展开侧栏',exact:true});if(await button.count())await button.click();
   await expect(async()=>{const left=(await page.locator('.workspace').boundingBox())!.x;expect(left).toBeCloseTo(collapsed?68:width<=1150?170:202,0);}).toPass();
   await expect(async()=>{const top=(await page.locator('.market-grid').boundingBox())!.y;expect(top).toBeLessThan(130);}).toPass();
   const geometry=await page.locator('.market-header').evaluate(el=>{const rect=el.getBoundingClientRect();return {top:rect.y,bottom:rect.bottom,height:rect.height,overflow:el.scrollWidth>el.clientWidth,cards:[...el.querySelectorAll('.summary>div')].map(e=>{const r=e.getBoundingClientRect();return {left:r.x,right:r.right,top:r.y,bottom:r.bottom,overflow:e.scrollWidth>e.clientWidth};})};});
   expect(geometry.overflow).toBe(false);expect(geometry.cards).toHaveLength(5);for(const card of geometry.cards)expect(card.overflow).toBe(false);for(let i=1;i<geometry.cards.length;i++)expect(geometry.cards[i].left).toBeGreaterThanOrEqual(geometry.cards[i-1].right);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
   const marketTop=(await page.locator('.market-grid').boundingBox())!.y;layout.push({width,collapsed,marketTop,...geometry});
   if(collapsed)await page.screenshot({path:`docs/compact-market-overview-${width}.png`});
  }
 }
 const {writeFileSync}=await import('node:fs');writeFileSync('docs/compact-market-overview-after.json',JSON.stringify(layout,null,2));
 await page.setViewportSize({width:1380,height:980});
 await expect(page.getByText('上证指数',{exact:true})).toBeVisible();
 await expect(page.getByText('深证成指',{exact:true})).toBeVisible();
 await expect(page.getByText('创业板指',{exact:true})).toBeVisible();
 expect(await page.locator('.summary > div > span').allTextContents()).toEqual(['监控股票','上证指数','深证成指','创业板指','当前状态']);
 await expect(page.getByText('实时触发',{exact:true})).toHaveCount(0);
 await expect(page.getByText('通知通道',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const chart=page.getByLabel('日K线及成交量');await chart.click();await chart.press('ArrowLeft');
 await expect(chart).toBeFocused();
 expect(await chart.evaluate(e=>getComputedStyle(e).outlineStyle)).toBe('none');
});

test('trigger comparison stays available without header or tooltip inputs',async({page})=>{
 const bars=['100','99','98','110','108','105'].map((close,i)=>({time:`09:${31+i}`,close,volume:100,complete:true}));
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'tencent',bars}});
 for(const [candidate_time,confirmation_label] of [['09:31','09:33'],['09:34','09:36']])await rpc('__audit_event',{key:`2026-10-19|603002|${candidate_time}`,symbol:'603002',trading_date:'2026-10-19',candidate_time,confirmation_label,event_label:confirmation_label,volumes:[300,100,100],kind:'TWO_MINUTE_CONFIRMATION'});
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19',{timeout:10000});
 const chart=page.getByLabel('分时价格及分钟成交量');const box=(await chart.boundingBox())!;
 const point=async(time:string,price:number)=>chart.evaluate(async(el,args)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);return e.getInstanceByDom(el).convertToPixel({seriesIndex:0},[args.time,args.price]) as number[];
 },{time,price});
 const xy=await point('09:36',105);
 await expect(async()=>{await page.mouse.move(box.x+xy[0]-1,box.y+80);await page.mouse.move(box.x+xy[0],box.y+80);await expect(chart.locator('.quote-tooltip')).toContainText('基准触发：09:34',{timeout:500});}).toPass({timeout:10000});
 await expect(chart.locator('.quote-tooltip')).toContainText('扣费后预计盈利（1000股）');
 await expect(chart.locator('.quote-trade-context')).toContainText('先卖后买');
 await expect(chart.locator('.quote-trade-prices')).toHaveText('卖出 110.00 元 → 买入 105.00 元');
 await page.getByRole('button',{name:'先买后卖',exact:true}).click();
 await expect(page.getByRole('button',{name:'先买后卖',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.mouse.move(box.x+xy[0]-1,box.y+80);await page.mouse.move(box.x+xy[0],box.y+80);
 await expect(chart.locator('.quote-trade-prices')).toHaveText('买入 110.00 元 → 卖出 105.00 元');
 await expect(chart.locator('.quote-tooltip')).toContainText('扣费后预计亏损（1000股）：-5097.65 元');
 await page.getByRole('button',{name:'先卖后买',exact:true}).click();
 await page.mouse.move(box.x+xy[0]-1,box.y+80);await page.mouse.move(box.x+xy[0],box.y+80);
 await expect(chart.locator('.quote-tooltip')).toContainText('扣费后预计盈利（1000股）');
 await chart.locator('.quote-tooltip').screenshot({path:test.info().outputPath('compact-trade-tooltip.png')});
 await expect(page.locator('.trigger-comparison')).toHaveCount(0);
 await expect(chart.locator('input')).toHaveCount(0);
 const mark=await point('09:31',100);await page.mouse.click(box.x+mark[0],box.y+mark[1]-18);
 await page.mouse.move(box.x+xy[0],box.y+80);await expect(chart.locator('.quote-tooltip')).toContainText('基准触发：09:31');
 const opening=page.getByRole('checkbox',{name:'显示开盘量'});
 await expect(opening).toBeChecked();
 await opening.uncheck();
 await expect.poll(()=>chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].markPoint.data.map((m:any)=>m.value);})).toEqual(['触发']);
 await page.mouse.move(box.x+xy[0]-1,box.y+80);await page.mouse.move(box.x+xy[0],box.y+80);
 await expect(chart.locator('.quote-tooltip')).toContainText('基准触发：09:34');
 expect(await page.evaluate(()=>localStorage.getItem('stock-monitor-show-opening'))).toBe('false');
 await opening.check();
 await expect.poll(()=>chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].markPoint.data.map((m:any)=>m.value).sort();})).toEqual(['开盘量','触发'].sort());
 await page.mouse.click(box.x+mark[0],box.y+mark[1]-18);
 await page.locator('.t-cost-settings summary').click();await page.getByLabel('试算股数',{exact:true}).fill('2000');await page.locator('.t-cost-settings summary').click();
 const updated=(await chart.boundingBox())!;await page.mouse.move(updated.x+xy[0],updated.y+80);
 await expect(chart.locator('.quote-tooltip')).toContainText('扣费后预计亏损（2000股）');
});

test('watch list shows quote change percent and amplitude, with missing fields explicit',async({page})=>{
 await rpc('__audit_quote',{code:'sh603002',quote:{price:'10.50',previous_close:'10',high:'10.8',low:'9.8',change:'5',timestamp:'2026-10-19T14:30:00+08:00'}});
 const stock=page.locator('.stock').filter({hasText:'宏昌电子'});
 await expect(stock.getByLabel('涨跌额').locator('strong')).toHaveText('+0.50',{timeout:10000});
 await expect(stock.getByLabel('涨跌幅').locator('strong')).toHaveText('+5.00%');await expect(stock.getByLabel('振幅').locator('strong')).toHaveText('10.00%');
 await expect(page.getByRole('button',{name:/买点研究/})).toHaveCount(0);
 await page.screenshot({path:test.info().outputPath('watch-quotes-local.png'),fullPage:true});
 await rpc('__audit_quote',{code:'sh603002',quote:{price:'9',timestamp:'2026-10-19T14:31:00+08:00'}});
 await expect(stock.getByLabel('涨跌幅').locator('strong')).toHaveText('—',{timeout:10000});
 await expect(stock.getByLabel('涨跌额').locator('strong')).toHaveText('—');await expect(stock.getByLabel('振幅').locator('strong')).toHaveText('—');
});

test('intraday header uses full width and tooltip overlays controls without moving the plot',async({page})=>{
 await page.addStyleTag({content:'.rail,.workspace{transition:none!important}'});
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 const chart=page.getByLabel('分时价格及分钟成交量'),tooltip=chart.locator('.quote-tooltip');
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:980});await page.evaluate(()=>new Promise<void>(resolve=>{window.scrollTo(0,0);requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()));}));
  await page.mouse.move(0,0);await expect(tooltip.locator('..')).toBeHidden();
  const box=(await chart.boundingBox())!,card=(await page.locator('.detail').boundingBox())!;
  expect(box.y-card.y).toBeLessThan(245);
  for(const selector of ['.detail-actions','.chart-toolbar>div:last-child']){const r=(await page.locator(selector).boundingBox())!;expect(Math.abs(r.x+r.width-(card.x+card.width-21))).toBeLessThan(4);}
  await page.screenshot({path:`docs/header-overlay-idle-${width}.png`});
  const hover=async(fraction:number)=>{
   const target=await chart.evaluate(async(el,f)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]),c=e.getInstanceByDom(el),labels=c.getOption().xAxis[0].data,i=Math.round((labels.length-1)*f);return {xy:c.convertToPixel({seriesIndex:0},[labels[i],10]),time:labels[i]};},fraction);
   await page.mouse.move(box.x+target.xy[0],box.y+150);await expect(tooltip.locator(':scope>div').first()).toHaveText(target.time,{timeout:1000});
  };
  await hover(.35);const first=(await tooltip.locator('..').boundingBox())!,detail=(await page.locator('.detail').boundingBox())!;
  expect(first.y).toBeGreaterThanOrEqual(detail.y);expect(first.y+first.height).toBeLessThanOrEqual(box.y+30);
  expect(Math.abs(first.x+first.width-(detail.x+detail.width-13))).toBeLessThan(3);
  expect(first.width).toBeLessThanOrEqual(325);expect(first.height).toBeLessThan(240);
  expect(await tooltip.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeLessThanOrEqual(10);
  expect(await tooltip.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  expect(await tooltip.locator('..').evaluate(el=>getComputedStyle(el).pointerEvents)).toBe('none');
  let covered=0;
  for(const control of await page.locator('.detail-actions button,.chart-toolbar button,.chart-toolbar select,.minute-chart-controls summary,.chart-display-options label').all()){
   if(!await control.isVisible())continue;const r=(await control.boundingBox())!;
   covered+=Math.max(0,Math.min(r.x+r.width,first.x+first.width)-Math.max(r.x,first.x))*Math.max(0,Math.min(r.y+r.height,first.y+first.height)-Math.max(r.y,first.y));
  }
  expect(covered).toBeGreaterThan(0);
  for(const fraction of [.2,.55,.85,.4,.75,.25]){await hover(fraction);const rect=(await tooltip.locator('..').boundingBox())!;expect(Math.abs(rect.x-first.x)).toBeLessThan(1);expect(Math.abs(rect.y-first.y)).toBeLessThan(1);}
  await expect(chart.locator('input')).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`docs/header-overlay-hover-${width}.png`});
  await page.getByRole('button',{name:'暂停',exact:true}).click();await expect(page.getByRole('button',{name:'恢复',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'恢复',exact:true}).click();
 }
});

test('daily tooltip stays compact at the header right and leaves controls clickable',async({page})=>{
 await page.addStyleTag({content:'.rail,.workspace{transition:none!important}'});
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const chart=page.getByLabel('日K线及成交量'),tooltip=chart.locator('.daily-tooltip');
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:980});await page.evaluate(()=>new Promise<void>(resolve=>{window.scrollTo(0,0);requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()));}));
  const box=(await chart.boundingBox())!,card=(await page.locator('.detail').boundingBox())!;
  const hover=async(fraction:number)=>{
   const target=await chart.evaluate(async(el,f)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]),c=e.getInstanceByDom(el),labels=c.getOption().xAxis[0].data.filter((d:string)=>{const x=c.convertToPixel({xAxisIndex:0},d);return x>=65&&x<=c.getWidth()-35;}),i=Math.round((labels.length-1)*f);return {xy:c.convertToPixel({xAxisIndex:0},labels[i]),date:labels[i]};},fraction);
   await page.mouse.move(box.x+target.xy,box.y+150);await expect(tooltip.locator('..')).toBeVisible();await expect(tooltip.locator(':scope>div').first()).toHaveText(target.date);
  };
  await hover(.35);const first=(await tooltip.locator('..').boundingBox())!;
  expect(first.y).toBeGreaterThanOrEqual(card.y);expect(first.y+first.height).toBeLessThanOrEqual(box.y+30);
  expect(Math.abs(first.x+first.width-(card.x+card.width-13))).toBeLessThan(3);
  expect(first.width).toBeLessThanOrEqual(325);expect(await tooltip.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeLessThanOrEqual(10);
  await expect(tooltip).toContainText('开盘：');await expect(tooltip).toContainText('成交量：');
  expect(await tooltip.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  expect(await tooltip.locator('..').evaluate(el=>getComputedStyle(el).pointerEvents)).toBe('none');
  await hover(.75);const second=(await tooltip.locator('..').boundingBox())!;
  expect(Math.abs(second.x-first.x)).toBeLessThan(1);expect(Math.abs(second.y-first.y)).toBeLessThan(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:test.info().outputPath(`daily-overlay-${width}.png`)});
  await page.mouse.move(0,0);await expect(tooltip.locator('..')).toBeHidden();
  await page.getByRole('button',{name:'暂停',exact:true}).click();await expect(page.getByRole('button',{name:'恢复',exact:true})).toBeVisible();await page.getByRole('button',{name:'恢复',exact:true}).click();
 }
});

test('intraday grid is sparse dark red and price/volume use identical time coordinates',async({page})=>{
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 const chart=page.getByLabel('分时价格及分钟成交量');
 const result=await chart.evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);const c=e.getInstanceByDom(el),o=c.getOption();
  return {gaps:o.xAxis.map((a:any)=>a.boundaryGap),colors:o.yAxis.map((a:any)=>a.splitLine.lineStyle.color),ticks:o.xAxis.map((a:any)=>a.data.filter((t:string,i:number)=>a.splitLine.interval(i,t))),x:[0,60,119,120,180,239].map(i=>[c.convertToPixel({xAxisIndex:0},i),c.convertToPixel({xAxisIndex:1},i)])};
 });
 expect(result.gaps).toEqual([false,false]);expect(result.colors).toEqual(['#69343f','#69343f']);
 expect(result.ticks[0]).toEqual(result.ticks[1]);expect(result.ticks[0].length).toBeLessThanOrEqual(10);
 for(const [price,volume] of result.x)expect(price).toBeCloseTo(volume,5);
 await page.mouse.move(10,10);await chart.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/intraday-red-grid-local.png'});
});

test('sidebar collapses, keeps navigation usable and remembers state after reload',async({page})=>{
 const workspace=page.locator('.workspace');const before=(await workspace.boundingBox())!.x;
 await page.getByRole('button',{name:'折叠侧栏',exact:true}).click();
 await expect(page.getByRole('button',{name:'展开侧栏',exact:true})).toHaveAttribute('aria-expanded','false');
 await expect(async()=>{expect((await workspace.boundingBox())!.x).toBeLessThan(before-80);}).toPass();
 await expect(page.locator('.nav-label').first()).toBeHidden();
 await page.getByRole('button',{name:'数据管理',exact:true}).click();await expect(page.getByRole('heading',{name:'下载与本地缓存'})).toBeVisible();
 await page.reload();await expect(page.getByRole('button',{name:'展开侧栏',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/sidebar-collapsed-local.png',fullPage:true});
 await page.getByRole('button',{name:'展开侧栏',exact:true}).click();
 await expect(page.getByRole('button',{name:'折叠侧栏',exact:true})).toHaveAttribute('aria-expanded','true');
 await expect(page.locator('.nav-label').first()).toBeVisible();
 await expect(async()=>{expect((await workspace.boundingBox())!.x).toBeCloseTo(before,0);}).toPass();
});

test('right percent axis mirrors price ticks using same-day previous close',async({page})=>{
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 const rows=await rpc('chart',{code:'sh603002',kind:'minute'});
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-16',data:{...rows[0].data,previous_close:'16'}});
 const chart=page.getByLabel('分时价格及分钟成交量');
 const inspect=()=>chart.evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);const c=e.getInstanceByDom(el),o=c.getOption(),right=o.yAxis[2];
  if(!right)return null;
  return {left:{min:o.yAxis[0].min,max:o.yAxis[0].max,interval:o.yAxis[0].interval},right:{min:right.min,max:right.max,interval:right.interval},labels:[right.axisLabel.formatter(16.16),right.axisLabel.formatter(15.84),right.axisLabel.formatter(16)],pixels:[15,15.5,16].map(v=>[c.convertToPixel({yAxisIndex:0},v),c.convertToPixel({yAxisIndex:2},v)]),gridRight:o.grid.map((g:any)=>g.right)};
 });
 await expect(async()=>{expect(await inspect()).not.toBeNull();}).toPass({timeout:10000});
 const result=(await inspect())!;expect(result.left).toEqual(result.right);expect(result.labels).toEqual(['{rise|+1.00%}','{fall|-1.00%}','{flat|0.00%}']);
 for(const [price,percent] of result.pixels)expect(price).toBeCloseTo(percent,5);
 expect(result.gridRight).toEqual([72,72]);
 for(const bar of [rows[0].data.bars.find((b:any)=>b.time==='09:31'),rows[0].data.bars.find((b:any)=>b.time==='15:00')]){
  const xy=await chart.evaluate(async(el,b)=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);return e.getInstanceByDom(el).convertToPixel({seriesIndex:0},[b.time,+b.close]) as number[];},bar);
  const box=(await chart.boundingBox())!;await page.mouse.move(box.x+xy[0],box.y+80);
  const pct=(Number(bar.close)/16-1)*100;
  await expect(chart.locator('.quote-tooltip .quote-detail').filter({hasText:'涨跌幅：'})).toHaveText(`涨跌幅：${pct>0?'+':''}${pct.toFixed(2)}%`);
 }
 await chart.locator('.quote-tooltip').screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/intraday-hover-percent-local.png'});
 await page.mouse.move(10,10);await chart.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/intraday-percent-axis-local.png'});
});

test('daily zoom is locked and latest upward gap remains visible as a shaded range',async({page})=>{
 for(const [day,low,high] of [['2026-10-19','100','101'],['2026-10-20','105','106']])await rpc('__audit_daily',{code:'sh603002',day,data:{date:day,open:low,close:high,low,high,volume:'10000',volume_unit:'shares',source:'tencent'}});
 await page.getByRole('button',{name:'日K',exact:true}).click();const chart=page.getByLabel('日K线及成交量');
 const inspect=()=>chart.evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);const o=e.getInstanceByDom(el).getOption();return {zoom:o.dataZoom.map((z:any)=>({start:z.start,end:z.end,zoomLock:z.zoomLock,zoomOnMouseWheel:z.zoomOnMouseWheel,handleSize:z.handleSize})),areas:o.series[0].markArea.data};
 });
 await expect(async()=>{expect((await inspect()).areas.some((a:any)=>a[0].name.includes('101.00—105.00'))).toBeTruthy();}).toPass({timeout:10000});
 const before=await inspect();expect(before.zoom.every((z:any)=>z.zoomLock)).toBeTruthy();expect(before.zoom[0].zoomOnMouseWheel).toBe(false);expect(before.zoom[1].handleSize).toBe(0);
 const area=before.areas.find((a:any)=>a[0].name.includes('101.00—105.00'));expect(area[0].xAxis).not.toBe(area[1].xAxis);
 const box=(await chart.boundingBox())!;await page.mouse.move(box.x+box.width*.5,box.y+100);await page.mouse.wheel(0,-600);
 await expect(async()=>{expect((await inspect()).zoom.map((z:any)=>[z.start,z.end])).toEqual(before.zoom.map((z:any)=>[z.start,z.end]));}).toPass();
 await page.mouse.move(10,10);await chart.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/daily-gaps-local.png'});
 await page.getByRole('button',{name:'分时',exact:true}).click();
 const minute=await page.getByLabel('分时价格及分钟成交量').evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);return e.getInstanceByDom(el).getOption().dataZoom[0].zoomLock;
 });expect(minute).not.toBe(true);
});

test('intraday axis spans full trading day with future gaps and time-aligned tooltip',async({page})=>{
 const bars=[{time:'09:31',close:'10',volume:100,complete:true},{time:'09:33',close:'11',volume:200,complete:true}];
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'tencent',bars}});
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19',{timeout:10000});
 const chart=page.getByLabel('分时价格及分钟成交量');
 const inspect=()=>chart.evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption();
  return {labels:o.xAxis.map((a:any)=>a.data),prices:o.series[0].data,volume:o.xAxis[0].data.map((_:string,i:number)=>{const bars=o.series.filter((s:any)=>s.type==='bar');return bars.every((s:any)=>s.data[i]===null)?null:bars.reduce((n:number,s:any)=>n+(s.data[i]||0),0);}),end:o.dataZoom[0].end,point:c.convertToPixel({seriesIndex:0},['09:33',11])};
 });
 await expect.poll(async()=> (await inspect()).prices[3]).toBe(11);
 const o=await inspect();expect(o.labels[0]).toEqual(o.labels[1]);expect(o.labels[0][0]).toBe('09:30');expect(o.labels[0].at(-1)).toBe('15:00');expect(o.labels[0]).not.toContain('12:00');
 expect(o.prices.slice(0,5)).toEqual([null,10,null,11,null]);expect(o.prices.at(-1)).toBeNull();expect(o.volume.slice(0,5)).toEqual([null,1,null,2,null]);expect(o.end).toBe(100);
 const box=(await chart.boundingBox())!;await page.mouse.move(box.x+o.point[0],box.y+100);
 await expect(chart.locator('.quote-tooltip')).toContainText('09:33');await expect(chart.locator('.quote-tooltip')).toContainText('11.00');
 await page.mouse.move(10,10);await chart.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/full-day-time-axis-local.png'});
});

test('watch card aligns with entire detail card without stretching stock rows',async({page})=>{
 const card=page.locator('.watchlist'),detail=page.locator('.market-grid > .detail');
 for(const height of [680,1200]){
  await page.setViewportSize({width:1380,height});
  await expect(async()=>{
   const left=(await card.boundingBox())!,right=(await detail.boundingBox())!;
   expect(Math.abs(left.y-right.y)).toBeLessThan(2);
   expect(Math.abs(left.y+left.height-right.y-right.height)).toBeLessThan(2);
  }).toPass();
 }
 for(const w of (await rpc('snapshot')).watch.slice(2))await rpc('remove',{code:w.code});
 await expect(card.locator('.stock')).toHaveCount(2);
 await expect(async()=>{const left=(await card.boundingBox())!,right=(await detail.boundingBox())!;expect(Math.abs(left.height-right.height)).toBeLessThan(2);}).toPass();
 expect((await card.locator('.stock').first().boundingBox())!.height).toBeLessThan(200);
 await card.locator('.stock').last().getByLabel('振幅').locator('span').scrollIntoViewIfNeeded();
 await expect(card.locator('.stock').last().getByLabel('振幅').locator('span')).toBeInViewport();
 await page.screenshot({path:test.info().outputPath('watchlist-equal-height-local.png'),fullPage:true});
});

test('any intraday location opens a limit ticket; pending partial fills cancel and persist',async({page})=>{
 const bars=[{time:'09:31',close:'10',volume:10000,complete:true},{time:'09:32',close:'9.5',volume:10000,complete:true},{time:'09:33',close:'11',volume:10000,complete:true}];
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'paper-test',volume_unit:'shares',bars}});
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByLabel('模拟初始资金').fill('100000');await page.getByRole('button',{name:'创建模拟账户',exact:true}).click();
 const panel=page.getByLabel('历史回放模拟交易');await expect(panel).toContainText('100,000.00');
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19');
 const chart=page.getByLabel('分时价格及分钟成交量');
 // Click empty grid space at an arbitrary price, independent of any signal.
 const xy=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({seriesIndex:0},['09:31',10.05]);});
 const box=(await chart.boundingBox())!;await page.mouse.click(box.x+xy[0],box.y+xy[1]);
 await expect(page.locator('.paper-quick-trade')).toHaveCount(0);await expect(page.getByText('委托 / 比较位置', {exact:false})).toHaveCount(0);await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});
 await expect(page.getByLabel('模拟委托限价')).toHaveValue('10.05');await page.getByLabel('模拟委托限价').fill('10');await page.getByLabel('模拟交易股数').fill('200');
 await page.getByRole('button',{name:/^确认(买入|卖出)$/,exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByRole('button',{name:'委托记录（1）',exact:true}).click();await expect(panel).toContainText('未成交');
 let snap=await rpc('paper_snapshot');expect(snap.positions).toEqual([]);expect(snap.frozen_cash).toBeGreaterThan(200000);
 await rpc('paper_advance',{account:(await rpc('paper_snapshot')).account.id,code:'sh603002',stamp:'2026-10-19 09:32'});await page.getByRole('button',{name:'刷新',exact:true}).click();
 await expect(panel).toContainText('部分成交');snap=await rpc('paper_snapshot');expect(snap.positions[0].shares).toBe(100);expect(snap.fills[0].price).toBe(950);
 await page.getByRole('button',{name:'撤单',exact:true}).click();await expect(panel).toContainText('已撤单');snap=await rpc('paper_snapshot');expect(snap.frozen_cash).toBe(0);expect(snap.positions[0].shares).toBe(100);
 await page.getByRole('button',{name:'成交明细（1）',exact:true}).click();await expect(panel.locator('.paper-record-table tbody tr')).toHaveCount(1);
 await expect(page.getByRole('button',{name:'导出明细',exact:true})).toHaveCount(0);
 await page.reload();await page.getByRole('button',{name:'模拟交易',exact:true}).click();await expect(panel).toContainText('100 / 0');
 snap=await rpc('paper_snapshot');expect(snap.orders).toHaveLength(1);expect(snap.profit).toBe(snap.account.realized+snap.unrealized);
 await page.screenshot({path:'docs/paper-limit-orders-local.png',fullPage:true});
});

test('today Shanzi limit buy automatically matches later cached prices and updates B without manual advance',async({page})=>{
 const code='sz000981',day='2026-10-27';
 await rpc('__audit_clock',{now:day+'T10:53:01+08:00'});
 const bars=[{time:'10:52',close:'2.36',volume:100000,complete:true}];
 const cache=()=>rpc('__audit_cache',{code,day,data:{date:day,source:'paper-auto-test',volume_unit:'shares',bars}});
 await rpc('__audit_daily',{code,day,data:{date:day,open:'2.36',close:'2.34',high:'2.36',low:'2.34',volume:'410000',volume_unit:'shares',source:'paper-auto-test'}});
 await cache();await page.getByRole('button',{name:'模拟交易',exact:true}).click();
 await page.getByLabel('模拟初始资金').fill('100000');await page.getByRole('button',{name:'创建模拟账户',exact:true}).click();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await page.locator('.stock').filter({hasText:'山子高科'}).click();
 await expect(page.getByLabel('交易日期')).toHaveValue(day);
 const chart=page.getByLabel('分时价格及分钟成交量');
 const xy=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({seriesIndex:0},['10:52',2.36]);});
 const box=(await chart.boundingBox())!;await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});
 await page.getByLabel('模拟委托限价').fill('2.35');await page.getByLabel('模拟交易股数').fill('2000');
 await page.getByRole('button',{name:'确认买入',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
 expect((await rpc('paper_snapshot')).fill_count).toBe(0);
 bars.push({time:'10:53',close:'2.34',volume:10000,complete:true});await cache();await rpc('__audit_clock',{now:day+'T10:54:01+08:00'});
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByRole('button',{name:'刷新',exact:true}).click();expect((await rpc('paper_snapshot')).fill_count).toBe(0);
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 bars.push({time:'10:55',close:'2.34',volume:10000,complete:true});await cache();await rpc('__audit_clock',{now:day+'T10:56:01+08:00'});
 await expect.poll(async()=>(await rpc('paper_snapshot')).orders[0].status,{timeout:10000}).toBe('partial');
 // Matching/marker updates continue while the paper-trading panel is hidden.
 const marks=()=>chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].markPoint.data.filter((m:any)=>m.paperTrade).map((m:any)=>m.value);});
 await expect.poll(marks).toEqual(['B']);
 bars.push({time:'10:56',close:'2.34',volume:300000,complete:true});await cache();await rpc('__audit_clock',{now:day+'T10:57:01+08:00'});
 await expect.poll(async()=>(await rpc('paper_snapshot')).orders[0].status,{timeout:10000}).toBe('filled');
 const showOrderTip=(target:any)=>target.evaluate(async(el:Element)=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]),c=e.getInstanceByDom(el);c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:c.getOption().xAxis[0].data.indexOf('10:55')});});
 await expect.poll(async()=>{await showOrderTip(chart);return chart.locator('.quote-tooltip').textContent();}).toContain('委托累计 B：买入2000股');
 await expect(chart.locator('.quote-tooltip')).toContainText('2次成交，10:55—10:56');
 expect(await marks()).toEqual(['B']);
 const orderChart=await rpc('paper_chart',{account:(await rpc('paper_snapshot')).account.id,code,start:day,end:day});
 expect(orderChart.points).toHaveLength(2);expect(orderChart.order_points).toHaveLength(1);expect(orderChart.order_points[0].stamp).toBe(day+' 10:55');
 await page.getByRole('button',{name:'日K',exact:true}).click();const linked=page.locator('.linked-minute').getByLabel('分时价格及分钟成交量');
 await expect.poll(async()=>{await showOrderTip(linked);return linked.locator('.quote-tooltip').textContent();}).toContain('委托累计 B：买入2000股');
 const dock=(await linked.locator('.quote-tooltip').locator('..').boundingBox())!,linkedBox=(await linked.boundingBox())!;
 expect(dock.y+dock.height).toBeLessThanOrEqual(linkedBox.y+30);
 expect(await linked.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].markPoint.data.filter((m:any)=>m.paperTrade).map((m:any)=>({value:m.value,coord:m.coord}));})).toEqual([{value:'B',coord:['10:55',2.34]}]);
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByRole('button',{name:'委托记录（1）',exact:true}).click();
 await expect(page.getByLabel('历史回放模拟交易').locator('.paper-record-table')).toContainText('2000 / 2000 / 0');
 const s=await rpc('paper_snapshot');expect(s.frozen_cash).toBe(0);expect(s.positions[0].shares).toBe(2000);expect(s.fills.every((f:any)=>f.price===234)).toBe(true);
 await page.reload();await page.getByRole('button',{name:'模拟交易',exact:true}).click();await expect(page.getByLabel('历史回放模拟交易')).toContainText('2000 / 0');
 expect((await rpc('paper_snapshot')).fill_count).toBe(2);
});

test('today chart reference does not backdate order acceptance or buy at a later 2.33 price above 2.32 limit',async({page})=>{
 const code='sz000981',day='2026-10-27';await rpc('__audit_clock',{now:day+'T13:29:10+08:00'});
 const bars=[{time:'13:28',close:'2.32',volume:2999700,complete:true},{time:'13:29',close:'2.32',volume:127000,complete:true},{time:'13:30',close:'2.33',volume:120100,complete:true}];
 const cache=()=>rpc('__audit_cache',{code,day,data:{date:day,source:'acceptance-time-test',volume_unit:'shares',bars}});await cache();
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByLabel('模拟初始资金').fill('100000');await page.getByRole('button',{name:'创建模拟账户',exact:true}).click();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await page.locator('.stock').filter({hasText:'山子高科'}).click();await expect(page.getByLabel('交易日期')).toHaveValue(day);
 const chart=page.getByLabel('分时价格及分钟成交量');const xy=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({seriesIndex:0},['13:28',2.32]);});
 const box=(await chart.boundingBox())!;await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});
 await expect(page.getByRole('dialog')).toContainText('参考位置 2026-10-27 13:28');await expect(page.getByRole('dialog')).toContainText('当日模拟');
 await page.getByLabel('模拟委托限价').fill('2.32');await page.getByLabel('模拟交易股数').fill('1600');
 await rpc('__audit_clock',{now:day+'T13:30:21+08:00'});await page.getByRole('button',{name:'确认买入',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.getByRole('status')).toContainText('生效时间13:30:21');
 let s=await rpc('paper_snapshot');expect(s.fill_count).toBe(0);expect(s.orders[0].stamp).toBe(day+' 13:30');expect(s.orders[0].reference_stamp).toBe(day+' 13:28');
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByRole('button',{name:'委托记录（1）',exact:true}).click();await page.locator('.paper-record-details summary').click();
 await expect(page.locator('.paper-record-details dl')).toContainText('2026-10-27 13:30:21');await expect(page.locator('.paper-record-details dl')).toContainText('2026-10-27 13:32');
 bars.push({time:'13:32',close:'2.33',volume:144600,complete:true});await cache();await rpc('__audit_clock',{now:day+'T13:33:01+08:00'});await page.getByRole('button',{name:'刷新',exact:true}).click();
 expect((await rpc('paper_snapshot')).fill_count).toBe(0);await expect(page.locator('.paper-record-table')).toContainText('未成交');
 bars.push({time:'13:33',close:'2.32',volume:100000,complete:true});await cache();await rpc('__audit_clock',{now:day+'T13:34:01+08:00'});
 await expect.poll(async()=>(await rpc('paper_snapshot')).fill_count,{timeout:10000}).toBe(1);
 s=await rpc('paper_snapshot');expect(s.fills[0].stamp).toBe(day+' 13:33');expect(s.fills[0].price).toBe(232);expect(s.orders[0].filled).toBe(1000);
});

test('only executed account trades paint intraday B/S and daily T and survive reload',async({page})=>{
 const code='sh603002',day='2026-10-19';
 const bars=[{time:'09:31',close:'10',volume:100000,complete:true},{time:'09:32',close:'9.5',volume:100000,complete:true},{time:'09:33',close:'11',volume:100000,complete:true}];
 await rpc('__audit_cache',{code,day,data:{date:day,source:'paper-marker-test',volume_unit:'shares',bars}});
 await rpc('__audit_daily',{code,day,data:{date:day,open:'10',close:'10.5',high:'11',low:'9',volume:'300000',volume_unit:'shares',source:'test'}});
 const a=await rpc('paper_create',{name:'有成交账户',cash:100000});
 await rpc('paper_seed',{account:a.id,code,shares:1000,cost:9});
 const submit=async(time:string,side:string,limit_price:number,id:string)=>{const stamp=day+' '+time,q=await rpc('paper_quote',{code,stamp});await rpc('paper_order',{account:a.id,id,code,stamp,token:q.token,side,shares:100,limit_price});};
 await submit('09:31','buy',10,'chart-buy-01');await rpc('paper_advance',{account:a.id,code,stamp:day+' 09:32'});
 await submit('09:32','sell',10,'chart-sell-01');await rpc('paper_advance',{account:a.id,code,stamp:day+' 09:33'});
 await submit('09:33','buy',1,'chart-unfilled');await rpc('paper_cancel',{account:a.id,id:'chart-unfilled'});
 await page.reload();await expect(page.getByLabel('交易日期')).toHaveValue(day);
 const chart=page.getByLabel('分时价格及分钟成交量');
 const marks=(locator:any)=>locator.evaluate(async(el:Element)=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series[0].markPoint?.data?.filter((m:any)=>m.paperTrade).map((m:any)=>({value:m.value,coord:m.coord}))||[];});
 await expect.poll(()=>marks(chart)).toEqual([{value:'B',coord:['09:32',9.5]},{value:'S',coord:['09:33',11]}]);
 await expect(page.locator('.paper-day-t')).toHaveText('T · 当日有买有卖');
 const requestCount=paperChartRequests;await page.waitForTimeout(3500);expect(paperChartRequests).toBe(requestCount);
 await chart.evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el);c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:c.getOption().xAxis[0].data.indexOf('09:32')});});
 await expect(chart.locator('.quote-tooltip')).toContainText('模拟成交 B：买入100股 · 均价9.50元');
 await chart.screenshot({path:'docs/paper-bs-intraday-local.png'});
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const daily=page.getByLabel('日K线及成交量');await expect.poll(()=>marks(daily)).toEqual([{value:'T',coord:[day,11]}]);
 await daily.screenshot({path:'docs/paper-t-daily-local.png'});
 const b=await rpc('paper_create',{name:'空账户',cash:50000});
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByRole('button',{name:'刷新',exact:true}).click();await page.getByLabel('模拟账户').selectOption(b.id);
 await expect(page.getByLabel('历史回放模拟交易')).toContainText('50,000.00');
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await expect.poll(()=>marks(page.getByLabel('日K线及成交量'))).toEqual([]);
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();await page.getByLabel('模拟账户').selectOption(a.id);
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await expect.poll(()=>marks(page.getByLabel('日K线及成交量'))).toEqual([{value:'T',coord:[day,11]}]);
});

test('daily and intraday executed B S markers are half-size with red blue dashed connectors',async({page})=>{
 const code='sz000981',days=['2026-10-19','2026-10-20','2026-10-21'];
 const account=(await rpc('paper_create',{cash:100000})).id;
 await rpc('paper_seed',{account,code,shares:300,cost:2.4});
 for(const day of days){
  await rpc('__audit_cache',{code,day,data:{date:day,source:'marker-style-test',volume_unit:'shares',bars:[
   {time:'09:31',close:'2.4',volume:100000,complete:true},{time:'09:32',close:'2.35',volume:100000,complete:true},{time:'09:33',close:'2.46',volume:100000,complete:true}]}});
  await rpc('__audit_daily',{code,day,data:{date:day,open:'2.4',close:'2.45',low:'2.3',high:'2.5',volume:'300000',volume_unit:'shares',source:'marker-style-test'}});
 }
 const order=async(day:string,time:string,side:string,key:string)=>{const q=await rpc('paper_quote',{code,stamp:day+' '+time});await rpc('paper_order',{account,id:key,code,stamp:q.stamp,token:q.token,side,shares:100,limit_price:side==='buy'?'2.4':'2.45'});};
 await order(days[0],'09:31','buy','small-marker-buy');await rpc('paper_advance',{account,code,stamp:days[0]+' 09:32'});
 await order(days[1],'09:32','sell','small-marker-sell');await rpc('paper_advance',{account,code,stamp:days[1]+' 09:33'});
 await order(days[2],'09:31','buy','small-marker-t-buy');await rpc('paper_advance',{account,code,stamp:days[2]+' 09:32'});
 await order(days[2],'09:32','sell','small-marker-t-sell');await rpc('paper_advance',{account,code,stamp:days[2]+' 09:33'});
 await page.reload();await page.locator('.stock').filter({hasText:'山子高科'}).click();await page.getByLabel('交易日期').selectOption(days[2]);
 const read=(chart:any)=>chart.evaluate(async(el:Element)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption(),colors=['#ed6d79','#4c9fff','#b48bff'];
  const marks=o.series[0].markPoint.data.filter((m:any)=>m.paperTrade).map((m:any)=>({value:m.value,coord:m.coord,price:m.executionPrice,size:m.symbolSize,color:m.itemStyle.color}));
  const lines=c.getZr().storage.getDisplayList().filter((d:any)=>d.type==='line'&&colors.includes(d.style.stroke)&&d.style.lineDash?.join(',')==='3,3').map((d:any)=>({color:d.style.stroke,shape:d.shape}));
  const list=c.getZr().storage.getDisplayList(),rect=(d:any)=>{const r=d.getBoundingRect().clone();r.applyTransform(d.getComputedTransform());return {x:r.x+r.width/2,y:r.y+r.height/2,width:r.width,height:r.height};};
  const symbols=list.filter((d:any)=>colors.includes(d.style.fill)&&rect(d).width>9&&rect(d).width<12).map((d:any)=>({color:d.style.fill,...rect(d)}));
  const ctx=document.createElement('canvas').getContext('2d')!;
  const text=list.filter((d:any)=>d.type==='tspan'&&['B','S','T'].includes(String(d.style.text))).map((d:any)=>{
   ctx.font=d.style.font;ctx.textBaseline=d.style.textBaseline;ctx.textAlign=d.style.textAlign;
   const m=ctx.measureText(d.style.text),x=(d.style.x||0)+(m.actualBoundingBoxRight-m.actualBoundingBoxLeft)/2,y=(d.style.y||0)+(m.actualBoundingBoxDescent-m.actualBoundingBoxAscent)/2,t=d.getComputedTransform()||[1,0,0,1,0,0];
   return {text:d.style.text,font:d.style.font,baseline:d.style.textBaseline,ink:{x:t[0]*x+t[2]*y+t[4],y:t[1]*x+t[3]*y+t[5]},rect:rect(d)};
  });
  return {marks,lines,symbols,text};
 });
 const centered=(r:any)=>{
  expect(r.text).toHaveLength(r.marks.length);
  for(const label of r.text){
   const color=r.marks.find((m:any)=>m.value===label.text).color,symbol=r.symbols.find((s:any)=>s.color===color);
   expect(symbol).toBeDefined();expect(Math.abs(label.ink.x-symbol.x)).toBeLessThan(.2);expect(Math.abs(label.ink.y-symbol.y)).toBeLessThan(.2);
  }
 };
 const minute=page.getByLabel('分时价格及分钟成交量');
 await expect.poll(async()=>(await read(minute)).marks.map((m:any)=>m.value)).toEqual(['B','S']);
 let r=await read(minute);expect(r.marks.map((m:any)=>[m.size,m.color])).toEqual([[10,'#ed6d79'],[10,'#4c9fff']]);
 centered(r);
 expect(r.lines.map((l:any)=>l.color).sort()).toEqual(['#4c9fff','#ed6d79']);
 expect(r.lines.find((l:any)=>l.color==='#ed6d79').shape.y2).toBeGreaterThan(r.lines.find((l:any)=>l.color==='#ed6d79').shape.y1);
 expect(r.lines.find((l:any)=>l.color==='#4c9fff').shape.y2).toBeLessThan(r.lines.find((l:any)=>l.color==='#4c9fff').shape.y1);
 await page.mouse.move(0,0);await minute.screenshot({path:'docs/paper-small-bs-intraday.png'});
 await page.getByRole('button',{name:'日K',exact:true}).click();const daily=page.getByLabel('日K线及成交量');
 await expect.poll(async()=>(await read(daily)).marks.map((m:any)=>m.value)).toEqual(['B','S','T']);
 r=await read(daily);expect(r.marks.map((m:any)=>m.size)).toEqual([10,10,10]);expect(r.marks.map((m:any)=>m.coord[1])).toEqual([2.3,2.5,2.5]);
 centered(r);
 expect(r.lines).toHaveLength(3);expect(r.lines.map((l:any)=>l.color).sort()).toEqual(['#4c9fff','#b48bff','#ed6d79']);
 expect(r.marks[0].price).toBe(2.35);expect(r.marks[1].price).toBe(2.46); // Drawing anchors never replace execution prices.
 const snapshot=await rpc('paper_snapshot',{account});expect(snapshot.fill_count).toBe(4);
 await page.mouse.move(0,0);await page.addStyleTag({content:'.interactive-price-tooltip{visibility:hidden!important}'});await daily.screenshot({path:'docs/paper-small-bst-daily.png'});
 const area=(await daily.boundingBox())!,scroll=await page.evaluate(()=>({x:scrollX,y:scrollY})),left=Math.min(...r.symbols.map((s:any)=>s.x))-14,top=Math.min(...r.symbols.map((s:any)=>s.y))-14;
 await page.screenshot({path:'docs/paper-marker-centered-detail.png',clip:{x:area.x+scroll.x+left,y:area.y+scroll.y+top,width:Math.max(...r.symbols.map((s:any)=>s.x))-left+14,height:Math.max(...r.symbols.map((s:any)=>s.y))-top+14}});
 await page.setViewportSize({width:1000,height:760});await expect.poll(async()=>(await read(daily)).lines.length).toBe(3);
 await expect(async()=>centered(await read(daily))).toPass({timeout:3000});
 // Connectors are recomputed from the date/price coordinates after resize and daily navigation.
 await daily.focus();await page.keyboard.press('ArrowLeft');await expect(page.locator('.linked-minute h3')).toContainText(days[1]);
 expect((await read(daily)).marks.map((m:any)=>m.value)).toEqual(['B','S','T']);
});

test('paper compact fields retain day profit and keep audit details expandable',async({page})=>{
 const code='sh603002',day='2026-10-19',bars=[{time:'09:31',close:'10',volume:100000,complete:true},{time:'09:32',close:'11',volume:100000,complete:true},{time:'09:33',close:'9.5',volume:100000,complete:true}];
 await rpc('__audit_cache',{code,day,data:{date:day,source:'compact-test',previous_close:'9.8',volume_unit:'shares',bars}});
 const a=await rpc('paper_create',{name:'精简字段验证',cash:100000});await rpc('paper_seed',{account:a.id,code,shares:1000,cost:9});await rpc('paper_advance',{account:a.id,code,stamp:day+' 09:31'});
 await page.reload();await page.getByRole('button',{name:'模拟交易',exact:true}).click();const panel=page.getByLabel('历史回放模拟交易');
 await expect(panel.locator('.paper-totals>div>span')).toHaveText(['总资产','可用资金','持仓市值','当日盈亏','累计盈亏']);
 await expect(panel.locator('.paper-totals>div').filter({hasText:'当日盈亏'}).locator('strong')).toHaveText('+200.00');
 await expect(panel.locator('.paper-totals>div').filter({hasText:'累计盈亏'}).locator('strong')).toHaveText('+1,000.00');
 await expect(panel.locator('.paper-positions th')).toHaveText(['股票','持仓 / 可卖','成本价 / 现价','市值','浮动盈亏','操作']);
 await expect(panel.locator('.paper-profit-grid')).toBeHidden();await panel.locator('.paper-profit-details summary').click();await expect(panel.locator('.paper-profit-grid')).toBeVisible();await expect(panel.locator('.paper-profit-grid')).toContainText('累计费用');
 await panel.locator('.paper-profit-details summary').click();
 const stamp=day+' 09:31',q=await rpc('paper_quote',{code,stamp});await rpc('paper_order',{account:a.id,id:'compact-sell',code,stamp,token:q.token,side:'sell',shares:100,limit_price:10});
 await page.getByRole('button',{name:'刷新',exact:true}).click();await expect(panel.locator('.paper-positions')).toContainText('冻结 100 股');
 await page.getByRole('button',{name:'委托记录（1）',exact:true}).click();await expect(panel.locator('.paper-record-table th')).toHaveText(['时间','股票','方向','委托价格','委托 / 已成 / 未成','状态','操作']);
 await expect(panel.locator('.paper-record-details dl')).toBeHidden();await panel.locator('.paper-record-details summary').click();await expect(panel.locator('.paper-record-details dl')).toContainText('compact-sell');await expect(panel.locator('.paper-record-details dl')).toContainText('单边滑点');await panel.locator('.paper-record-details summary').click();
 await rpc('paper_advance',{account:(await rpc('paper_snapshot')).account.id,code:'sh603002',stamp:'2026-10-19 09:32'});await page.getByRole('button',{name:'刷新',exact:true}).click();
 await page.getByRole('button',{name:'成交明细（1）',exact:true}).click();await expect(panel.locator('.paper-record-table th')).toHaveText(['时间','股票','方向','成交价 / 数量','成交金额 / 费用','已实现盈亏']);
 const snapshot=await rpc('paper_snapshot',{account:a.id});expect(snapshot.day_pnl.profit).toBe(119444); // 1000*(11-9.8) less 5.56 yuan sell fees
 await panel.locator('.paper-record-details summary').click();await expect(panel.locator('.paper-record-details dl')).toContainText('印花税');await expect(panel.locator('.paper-record-details dl')).toContainText('过户费');await panel.locator('.paper-record-details summary').click();
 await page.screenshot({path:'docs/paper-compact-fields-local.png',fullPage:true});
 // Missing prior close must be visibly unknown, never a fabricated zero.
 const payload={date:day,source:'compact-test',volume_unit:'shares',bars};await rpc('__audit_cache',{code,day,data:payload});await page.getByRole('button',{name:'刷新',exact:true}).click();
 await expect(panel.locator('.paper-totals>div').filter({hasText:'当日盈亏'}).locator('strong')).toHaveText('暂无');
});

test('paper toolbar hides replay, manual trade, advance and export controls while preserving records',async({page})=>{
 const a=await rpc('paper_create',{cash:12345.67});
 await page.reload();await page.getByRole('button',{name:'模拟交易',exact:true}).click();
 await expect(page.getByLabel('模拟回放分钟')).toHaveCount(0);
 for(const name of ['模拟买入当前股票','模拟卖出当前股票','推进账户时间','导出明细'])await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'持仓明细',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'委托记录（0）',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'成交明细（0）',exact:true})).toBeVisible();
 expect((await rpc('paper_snapshot',{account:a.id})).account.cash).toBe(1234567);
});

test('minimum desktop viewport keeps account fields accessible and failed orders recover',async({page})=>{
 await page.setViewportSize({width:1000,height:680});
 await page.getByRole('button',{name:'模拟交易',exact:true}).click();
 await page.getByLabel('模拟初始资金').fill('3210.98');await page.getByRole('button',{name:'创建模拟账户',exact:true}).click();
 const panel=page.getByLabel('历史回放模拟交易');await expect(panel.locator('.paper-totals')).toContainText('3,210.98');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'small-viewport',volume_unit:'shares',bars:[{time:'09:31',close:'10',volume:100000,complete:true},{time:'09:32',close:'10',volume:100000,complete:true}]}});
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await page.reload();await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19');
 const chart=page.getByLabel('分时价格及分钟成交量');await chart.scrollIntoViewIfNeeded();const xy=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption(),i=o.xAxis[0].data.indexOf('09:31');return c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:31',o.series[0].data[i]]);});const box=(await chart.boundingBox())!;await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});
 const ticket=page.getByRole('dialog');await expect(ticket).toBeVisible();await page.getByLabel('模拟交易股数').fill('100000000');await page.getByRole('button',{name:/^确认(买入|卖出)$/,exact:true}).click();
 await expect(ticket.getByRole('alert')).toContainText('可用资金不足');
 await page.getByLabel('模拟交易股数').fill('100');await page.getByRole('button',{name:/^确认(买入|卖出)$/,exact:true}).click();await expect(ticket).toHaveCount(0);
 const s=await rpc('paper_snapshot');expect(s.order_count).toBe(2);expect(s.fill_count).toBe(0);expect(s.available_cash).toBeGreaterThanOrEqual(0);
 await page.screenshot({path:'docs/paper-acceptance-small-viewport.png',fullPage:true});
});

test('right-click opens buy/sell ticket over intraday without leaving chart and reports acceptance',async({page})=>{
 const code='sh603002',day='2026-10-19';
 await rpc('__audit_cache',{code,day,data:{date:day,source:'context-test',previous_close:'10',volume_unit:'shares',bars:[{time:'09:31',close:'10',volume:100000,complete:true},{time:'09:32',close:'10.1',volume:100000,complete:true},{time:'09:33',close:'9.5',volume:100000,complete:false}]}});
 const a=await rpc('paper_create',{cash:20000});await rpc('paper_seed',{account:a.id,code,shares:1000,cost:9});
 await page.reload();const chart=page.getByLabel('分时价格及分钟成交量');await expect(page.getByLabel('交易日期')).toHaveValue(day);
 const at=async(time:string,price:number,grid=0)=>{await chart.scrollIntoViewIfNeeded();const xy=await chart.evaluate(async(el,arg)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({xAxisIndex:arg.grid,yAxisIndex:arg.grid},[arg.time,arg.price]);},{time,price,grid});const box=(await chart.boundingBox())!;await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});};
 await at('09:32',10.02);
 const ticket=page.getByRole('dialog',{name:'模拟买卖确认'});await expect(ticket).toBeVisible();await expect(ticket).toContainText(day+' 09:32');expect(await ticket.locator('.ticket-details').textContent()).toContain('分时右键委托');await expect(page.getByLabel('模拟委托限价')).toHaveValue('10.02');
 await expect(page.locator('.workspace h1')).toHaveText('自选监控');await expect(page.locator('.detail')).toBeVisible();await expect(page.getByRole('button',{name:'买入',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'卖出',exact:true}).click();await expect(page.getByRole('button',{name:'确认卖出',exact:true})).toBeVisible();await page.getByLabel('模拟交易股数').fill('100');await page.getByLabel('模拟委托限价').fill('10.1');
 await page.screenshot({path:'docs/paper-chart-context-ticket.png'});
 await page.getByRole('button',{name:/^确认(买入|卖出)$/,exact:true}).click();await expect(ticket).toHaveCount(0);await expect(page.locator('.toast')).toContainText('委托已受理：卖出');await expect(page.locator('.workspace h1')).toHaveText('自选监控');
 const s=await rpc('paper_snapshot',{account:a.id});expect(s.order_count).toBe(1);expect(s.fill_count).toBe(0);expect(s.orders[0]).toMatchObject({side:'sell',price:1010,shares:100,stamp:day+' 09:32',status:'open'});
 // Volume area uses the minute's actual price, not the volume coordinate.
 await at('09:32',500,1);await expect(ticket).toBeVisible();await expect(page.getByLabel('模拟委托限价')).toHaveValue('10.1');await page.keyboard.press('Escape');await expect(ticket).toHaveCount(0);
 // No quote or order is invented in unfinished or future minutes.
 await at('14:00',10);await expect(ticket).toHaveCount(0);await expect(page.locator('.chart-trade-hint')).toContainText('未来时间不能委托');
 await at('09:33',10);await expect(ticket).toHaveCount(0);expect((await rpc('paper_snapshot',{account:a.id})).order_count).toBe(1);
});

test('right-click works in linked intraday and provides account setup when no account exists',async({page})=>{
 await page.getByRole('button',{name:'日K',exact:true}).click();const chart=page.locator('.linked-minute').getByLabel('分时价格及分钟成交量');await expect(chart).toBeVisible();
 await chart.scrollIntoViewIfNeeded();const xy=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption(),i=o.xAxis[0].data.indexOf('09:32');return c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:32',o.series[0].data[i]]);});const box=(await chart.boundingBox())!;
 await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});const ticket=page.getByRole('dialog');await expect(ticket).toBeVisible();await expect(page.getByRole('button',{name:/^确认(买入|卖出)$/,exact:true})).toBeDisabled();await expect(page.locator('.workspace h1')).toHaveText('自选监控');
 await page.getByRole('button',{name:'设置模拟账户',exact:true}).click();await expect(ticket).toHaveCount(0);await expect(page.getByLabel('模拟初始资金')).toBeVisible();await expect(page.locator('.workspace h1')).toHaveText('模拟交易');
 expect((await rpc('paper_snapshot')).accounts).toHaveLength(0);
});

test('compact ticket has small footprint, fee-safe fractions, steppers and explicit direction submission',async({page})=>{
 await page.setViewportSize({width:1000,height:680});
 const code='sh603002',day='2026-10-19';
 await rpc('__audit_cache',{code,day,data:{date:day,source:'compact-ticket',volume_unit:'shares',bars:[{time:'09:31',close:'10',volume:100000,complete:true},{time:'09:32',close:'10',volume:100000,complete:true}]}});
 const a=await rpc('paper_create',{cash:2000});await rpc('paper_seed',{account:a.id,code,shares:155,cost:1});await page.reload();
 const chart=page.getByLabel('分时价格及分钟成交量');await chart.scrollIntoViewIfNeeded();const xy=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:31',10]);});const box=(await chart.boundingBox())!;
 await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});
 const ticket=page.getByRole('dialog');await expect(ticket).toBeVisible();await expect(ticket.locator('.ticket-available')).toContainText('可买 100 股');
 const rect=(await ticket.boundingBox())!;expect(rect.width).toBeLessThanOrEqual(350);expect(rect.height).toBeLessThanOrEqual(420);expect(rect.y).toBeGreaterThanOrEqual(0);expect(rect.x+rect.width).toBeLessThanOrEqual(1000);
 expect(Math.abs(rect.x+rect.width/2-500)).toBeLessThan(1);expect(Math.abs(rect.y+rect.height/2-340)).toBeLessThan(1);
 await page.setViewportSize({width:1380,height:900});
 await expect.poll(async()=>{const r=(await ticket.boundingBox())!;return Math.abs(r.x+r.width/2-690)+Math.abs(r.y+r.height/2-450);}).toBeLessThan(2);
 await page.setViewportSize({width:1000,height:680});
 await expect(ticket.locator('.ticket-details>div')).toBeHidden();await expect(page.getByLabel('模拟委托限价')).toBeFocused();
 await page.getByLabel('模拟委托限价').fill('10.00');
 await page.getByRole('button',{name:'提高委托价格',exact:true}).click();await expect(page.getByLabel('模拟委托限价')).toHaveValue('10.01');await page.getByRole('button',{name:'降低委托价格',exact:true}).click();await expect(page.getByLabel('模拟委托限价')).toHaveValue('10.00');
 await ticket.getByRole('button',{name:'全仓',exact:true}).click();await expect(page.getByLabel('模拟交易股数')).toHaveValue('100');
 await page.getByRole('button',{name:'增加委托数量',exact:true}).click();await expect(page.getByLabel('模拟交易股数')).toHaveValue('200');await page.getByRole('button',{name:'减少委托数量',exact:true}).click();await expect(page.getByLabel('模拟交易股数')).toHaveValue('100');
 await page.getByRole('button',{name:'卖出',exact:true}).click();await expect(page.getByRole('button',{name:'确认卖出',exact:true})).toBeVisible();await ticket.getByRole('button',{name:'全仓',exact:true}).click();await expect(page.getByLabel('模拟交易股数')).toHaveValue('155');await expect(ticket.getByRole('button',{name:'1/2仓',exact:true})).toBeDisabled();
 await ticket.getByRole('button',{name:'重填',exact:true}).click();await expect(page.getByLabel('模拟交易股数')).toHaveValue('');await expect(page.getByRole('button',{name:'确认卖出',exact:true})).toBeDisabled();
 await ticket.getByRole('button',{name:'全仓',exact:true}).click();await page.screenshot({path:'docs/paper-compact-ticket-sell.png'});
 await page.getByRole('button',{name:'买入',exact:true}).click();await ticket.getByRole('button',{name:'全仓',exact:true}).click();await page.screenshot({path:'docs/paper-compact-ticket-buy.png'});
 await page.getByRole('button',{name:'确认买入',exact:true}).click();await expect(ticket).toHaveCount(0);const snap=await rpc('paper_snapshot',{account:a.id});expect(snap.orders[0]).toMatchObject({side:'buy',shares:100,status:'open'});expect(snap.available_cash).toBeGreaterThanOrEqual(0);
});

test('current Beijing closed session blocks historical chart orders with visible errors and no ledger mutation',async({page})=>{
 const code='sh603002',day='2026-10-19';await rpc('__audit_cache',{code,day,data:{date:day,source:'wall-clock-test',volume_unit:'shares',bars:[{time:'09:31',close:'10',volume:100000,complete:true}]}});
 const a=await rpc('paper_create',{cash:10000});await page.reload();
 const chart=page.getByLabel('分时价格及分钟成交量');await chart.scrollIntoViewIfNeeded();const xy=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:31',10]);});const box=(await chart.boundingBox())!;
 await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});const ticket=page.getByRole('dialog');await expect(ticket).toBeVisible();await page.getByLabel('模拟交易股数').fill('100');
 for(const [now,reason] of [['2026-10-25T10:00:00+08:00','周末休市'],['2026-10-23T12:00:00+08:00','不在交易时间内'],['2026-10-01T10:00:00+08:00','节假日休市']]){
  await rpc('__audit_clock',{now});await page.getByRole('button',{name:'确认买入',exact:true}).click();await expect(ticket.getByRole('alert')).toContainText(reason);await expect(ticket.getByRole('alert')).toContainText('当前北京时间');
  const s=await rpc('paper_snapshot',{account:a.id});expect(s.order_count).toBe(0);expect(s.fill_count).toBe(0);expect(s.account.cash).toBe(1000000);expect(s.positions).toEqual([]);
 }
 await page.screenshot({path:'docs/paper-closed-session-error.png'});
 await rpc('__audit_clock',{now:'2026-10-23T13:00:00+08:00'});await page.getByRole('button',{name:'确认买入',exact:true}).click();await expect(ticket).toHaveCount(0);expect((await rpc('paper_snapshot',{account:a.id})).order_count).toBe(1);
});

test('intraday buy and sell share one stacked volume bar; unknown stays gray and linked chart matches',async({page})=>{
 const code='sh603002',day='2026-10-23';
 await rpc('__audit_cache',{code,day,data:{date:day,source:'tencent',previous_close:'10',volume_unit:'shares',bars:[{time:'09:31',close:'10',volume:1000,complete:true},{time:'09:32',close:'10.2',volume:1000,complete:true},{time:'09:33',close:'10.1',volume:500,complete:true}]}});
 await rpc('__audit_daily',{code,day,data:{date:day,open:'10',close:'10.1',high:'10.2',low:'9.8',volume:'100000',source:'tencent',volume_unit:'shares'}});
 await rpc('__audit_flow',{code,day,data:{version:1,code,day,fetched_at:'2026-10-23T16:00:00+08:00',buckets:{'09:31':{buy:600,sell:300,neutral:100,unknown:0,total:1000},'09:32':{buy:700,sell:400,neutral:0,unknown:0,total:1100}}}});
 await page.reload();await expect(page.getByLabel('交易日期')).toHaveValue(day);
 const chart=page.getByLabel('分时价格及分钟成交量');
 const inspect=async(locator:any)=>locator.evaluate(async(el:HTMLElement)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const o=e.getInstanceByDom(el).getOption(),i=o.xAxis[0].data.indexOf('09:31'),j=o.xAxis[0].data.indexOf('09:32');return o.series.filter((s:any)=>s.type==='bar').map((s:any)=>({name:s.name,stack:s.stack,color:typeof s.itemStyle.color==='function'?s.itemStyle.color({dataIndex:j}):s.itemStyle.color,first:s.data[i],second:s.data[j]}));});
 await expect.poll(()=>inspect(chart)).toEqual([{name:'买盘量',stack:'minute-volume',color:'#ef6568',first:6,second:0},{name:'卖盘量',stack:'minute-volume',color:'#36b898',first:3,second:0},{name:'中性 / 未分类量',stack:'minute-volume',color:'#718096',first:1,second:0},{name:'总成交量（回退）',stack:'minute-volume',color:'#ef6568',first:0,second:10}]);
 const point=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:31',10]);});const box=(await chart.boundingBox())!;await page.mouse.move(box.x+point[0],box.y+point[1]);await expect(chart.locator('.quote-tooltip')).toContainText('买盘量：6.00 手（60.0%）');await expect(chart.locator('.quote-tooltip')).toContainText('卖盘量：3.00 手（30.0%）');for(const hidden of ['上证：','中性量：','未分类量：','买卖方向：'])await expect(chart.locator('.quote-tooltip')).not.toContainText(hidden);
 await page.screenshot({path:'docs/volume-flow-stacked.png',fullPage:true});
 const expectedBars=await inspect(chart);await page.getByRole('button',{name:'日K',exact:true}).click();await expect.poll(()=>inspect(page.locator('.linked-minute').getByLabel('分时价格及分钟成交量'))).toEqual(expectedBars);
 // Main daily volume keeps the original candle-rise/fall color scheme and one series.
 const bars=await page.getByLabel('日K线及成交量').evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series.filter((s:any)=>s.type==='bar').map((s:any)=>s.name);});expect(bars).toEqual(['成交量（万股）']);
 await page.locator('.stock').filter({hasText:'海优新材'}).click();await expect(page.locator('.volume-flow-caption')).toHaveCount(0);
});

test('public Shanghai sample shows reconciled red green stacks while retaining all original volumes',async({page})=>{
 const {readFileSync}=await import('node:fs');const sample=JSON.parse(readFileSync('tests/ui/fixtures/volume-flow-real.json','utf8'));
 await rpc('__audit_cache',{code:sample.code,day:sample.day,data:sample.minute});await rpc('__audit_flow',{code:sample.code,day:sample.day,data:sample.flow});
 await page.locator('.stock').filter({hasText:'三孚股份'}).click();await expect(page.getByLabel('交易日期')).toHaveValue(sample.day);
 const chart=page.getByLabel('分时价格及分钟成交量');await expect.poll(()=>chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series.find((r:any)=>r.name==='买盘量')?.data.some((n:any)=>n>0);})).toBe(true);await expect(page.locator('.volume-flow-caption')).toHaveCount(0);
 const points=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const o=e.getInstanceByDom(el).getOption(),bars=o.series.filter((s:any)=>s.type==='bar');return o.xAxis[0].data.map((t:string,i:number)=>({time:t,total:bars.reduce((v:number,s:any)=>v+(s.data[i]||0),0)}));});
 for(const p of points){const b=sample.minute.bars.find((b:any)=>b.time===p.time&&((b.time>='09:31'&&b.time<='11:30')||(b.time>='13:01'&&b.time<='15:00')));expect(p.total).toBeCloseTo(b?b.volume/100:0,8);}
 await chart.screenshot({path:'docs/volume-flow-real-chart.png'});
});

test('Shanzi 10:36 and 13:01 show approximate buy sell amounts; 11:30 includes the endpoint trade',async({page})=>{
 const {readFileSync}=await import('node:fs');const sample=JSON.parse(readFileSync('tests/ui/fixtures/volume-flow-shanzi.json','utf8'));
 await rpc('__audit_cache',{code:sample.code,day:sample.day,data:sample.minute});await rpc('__audit_flow',{code:sample.code,day:sample.day,data:sample.flow});
 await page.locator('.stock').filter({hasText:'山子高科'}).click();await expect(page.getByLabel('交易日期')).toHaveValue(sample.day);
 const chart=page.getByLabel('分时价格及分钟成交量');await expect.poll(()=>chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).getOption().series.find((r:any)=>r.name==='买盘量')?.data.some((n:any)=>n>0);})).toBe(true);await expect(page.locator('.volume-flow-caption')).toHaveCount(0);
 const results=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption(),bars=o.series.filter((s:any)=>s.type==='bar');return ['10:36','11:30','13:01'].map(t=>{const i=o.xAxis[0].data.indexOf(t);return {time:t,total:bars.reduce((v:number,s:any)=>v+(s.data[i]||0),0),sell:bars[1].data[i],fallback:bars[3].data[i],point:c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[t,o.series[0].data[i]])};});});
 for(const result of results){expect(result.fallback).toBe(0);expect(result.total).toBeCloseTo(sample.minute.bars.find((b:any)=>b.time===result.time).volume/100,8);}
 expect(results[1].sell).toBe(2863);const box=(await chart.boundingBox())!;
 for(const [index,buy,sell,note] of [[0,'61,346.00','780.00','多1.00手'],[2,'40,439.00','8,762.00','少1.00手']] as const){const point=results[index].point;await page.mouse.move(box.x+point[0],box.y+point[1]);const tip=chart.locator('.quote-tooltip');await expect(tip).toContainText(`买盘量（约）：${buy} 手`);await expect(tip).toContainText(`卖盘量（约）：${sell} 手`);await expect(tip).toContainText(note);}
 await chart.screenshot({path:'docs/volume-flow-shanzi-corrected.png'});
});

test('missing buy sell source keeps total volume in original rise fall colors, including incomplete minutes',async({page})=>{
 const code='sh603002',day='2026-10-23';await rpc('__audit_cache',{code,day,data:{date:day,source:'tencent',previous_close:'10',volume_unit:'shares',bars:[{time:'09:31',close:'10.2',volume:1000,complete:true},{time:'09:32',close:'10.1',volume:700,complete:true},{time:'09:33',close:'10.3',volume:300,complete:false}]}});
 await page.reload();await expect(page.getByLabel('交易日期')).toHaveValue(day);const chart=page.getByLabel('分时价格及分钟成交量');
 const bars=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const o=e.getInstanceByDom(el).getOption(),bs=o.series.filter((s:any)=>s.type==='bar');return ['09:31','09:32','09:33'].map(t=>{const i=o.xAxis[0].data.indexOf(t),s=bs[3];return {values:bs.map((s:any)=>s.data[i]),color:s.itemStyle.color({dataIndex:i}),opacity:s.itemStyle.opacity};});});
 expect(bars).toEqual([{values:[0,0,0,10],color:'#ef6568',opacity:1},{values:[0,0,0,7],color:'#36b898',opacity:1},{values:[0,0,0,3],color:'#ef6568',opacity:1}]);
});

test('Wanxiang limits appear in minute tooltip without a header strip or status row; exact ceiling remains',async({page})=>{
 const {readFileSync}=await import('node:fs');const sample=JSON.parse(readFileSync('tests/ui/fixtures/wanxiang-limit-up.json','utf8'));const code=sample.code,day=sample.minute.date;
 await rpc('add',{code});await rpc('__audit_quote',{code,quote:sample.quote});await rpc('__audit_cache',{code,day,data:{...sample.minute,limit_up:sample.quote.limit_up,limit_down:sample.quote.limit_down}});
 await page.reload();await page.locator('.stock').filter({hasText:'SZ000559'}).click();await expect(page.getByLabel('交易日期')).toHaveValue(day);await expect(page.getByLabel('当日涨跌停价格')).toHaveCount(0);
 const chart=page.getByLabel('分时价格及分钟成交量');const check=await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c.getOption();return {max:o.yAxis[0].max,rightMax:o.yAxis[2].max,rightLabel:o.yAxis[2].axisLabel.formatter(o.yAxis[2].max),line:o.series[0].markLine.data.find((r:any)=>r.name==='涨停'),red:o.series.find((r:any)=>r.name==='涨停走势').lineStyle.color,hasPlateau:o.series.find((r:any)=>r.name==='涨停走势').data.some((n:any)=>n===12.71)};});
 expect(check.max).toBe(12.71);expect(check.rightMax).toBe(12.71);expect(check.rightLabel).toBe('{rise|+10.04%}');expect(check.line.yAxis).toBe(12.71);expect(check.red).toBe('#ef6568');expect(check.hasPlateau).toBe(true);
 await chart.scrollIntoViewIfNeeded();const hit=sample.minute.bars.find((b:any)=>b.time==='10:47');const xy=await chart.evaluate(async(el,b)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).convertToPixel({xAxisIndex:0,yAxisIndex:0},[b.time,+b.close]);},hit);const box=(await chart.boundingBox())!;await page.mouse.move(box.x+xy[0],box.y+xy[1]+2);await expect(chart.locator('.quote-tooltip')).toContainText('涨停：12.71 元（+10.04%）');await expect(chart.locator('.quote-tooltip')).toContainText('跌停：10.40 元（-9.96%）');await expect(chart.locator('.quote-tooltip')).not.toContainText('状态：');await page.mouse.move(10,10);
 await page.locator('.detail').screenshot({path:'docs/wanxiang-limit-up-display.png'});
 await page.getByRole('button',{name:'日K',exact:true}).click();const linked=page.locator('.linked-minute');await expect(linked.getByLabel('当日涨跌停价格')).toHaveCount(0);const linkedMax=await linked.getByLabel('分时价格及分钟成交量').evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);return e.getInstanceByDom(el).getOption().yAxis[0].max;});expect(linkedMax).toBe(12.71);
});

function dailyHistoryFeed(){
 const rows=[];for(let stamp=Date.UTC(2024,0,1);stamp<=Date.UTC(2026,9,26);stamp+=86400000){const d=new Date(stamp);if(d.getUTCDay()===0||d.getUTCDay()===6)continue;const price=10+rows.length/100;rows.push({date:d.toISOString().slice(0,10),open:price.toFixed(2),close:(price+.1).toFixed(2),high:(price+.3).toFixed(2),low:(price-.2).toFixed(2),volume:'100000',volume_unit:'shares',source:'tencent',adjustment:'none'});}return rows;
}
async function dailyWindowState(page:Page){
 return page.getByLabel('日K线及成交量').evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^\"]*echarts\.js[^\"]*)"/)![1]);const c=e.getInstanceByDom(el),o=c?.getOption();if(!o?.xAxis?.[0]?.data?.length)return null;const labels=o.xAxis[0].data,z=o.dataZoom[0],lo=Math.round((labels.length-1)*z.start/100),hi=Math.round((labels.length-1)*z.end/100);return {count:labels.length,visible:hi-lo+1,rendered:c.getModel().getSeriesByIndex(0).getData().count(),first:labels[0],last:labels.at(-1),visibleFirst:labels[lo],visibleLast:labels[hi],selected:document.querySelector('.linked-minute h3')?.textContent?.match(/\d{4}-\d{2}-\d{2}/)?.[0],zoomLock:z.zoomLock};});
}
test('daily entry backfills a short cache to 90 candles; left boundary loads history once and preserves focus',async({page})=>{
 const code='sh600519',feed=dailyHistoryFeed();await rpc('add',{code});await rpc('__audit_daily_feed',{code,rows:feed,delay:.2});await page.reload();await page.locator('.stock').filter({hasText:'贵州茅台'}).click();await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect.poll(()=>dailyWindowState(page)).toMatchObject({visible:90,rendered:90,last:'2026-10-26',selected:'2026-10-26',zoomLock:true});expect(dailyLoadRequests.filter(r=>r.code===code)).toHaveLength(1);
 const initial=(await dailyWindowState(page))!;expect(initial.count).toBeGreaterThan(90);const earlier=feed.filter(r=>r.date<initial.first).at(-1)!.date;
 await selectDailyDate(page,initial.first);const chart=page.getByLabel('日K线及成交量');await chart.focus();await chart.press('ArrowLeft');for(let i=0;i<6;i++)await chart.press('ArrowLeft');
 await expect.poll(()=>dailyWindowState(page)).toMatchObject({visible:90,rendered:90,selected:earlier});expect(dailyLoadRequests.filter(r=>r.code===code)).toHaveLength(2);expect((await dailyWindowState(page))!.count).toBeGreaterThan(initial.count);await expect(chart).toBeFocused();
 await chart.press('ArrowRight');await expect.poll(()=>dailyWindowState(page)).toMatchObject({visible:90,selected:initial.first});expect(dailyLoadRequests.filter(r=>r.code===code)).toHaveLength(2);
 await page.screenshot({path:'docs/daily-90-keyboard-backfill.png'});
 const edge=(await dailyWindowState(page))!.first;await selectDailyDate(page,edge);await chart.focus();await chart.press('ArrowLeft');await expect(page.locator('.daily-load-state')).toBeVisible();await selectDailyDate(page,initial.first);
 await expect(page.locator('.daily-load-state')).toHaveCount(0);await expect.poll(()=>dailyWindowState(page)).toMatchObject({visible:90,rendered:90,selected:initial.first});
});
test('right boundary fills the next batch for an old daily view without jumping to today',async({page})=>{
 const code='sh600519',feed=dailyHistoryFeed(),old='2024-10-25';await rpc('add',{code});await rpc('__audit_daily_feed',{code,rows:feed,delay:.2});await rpc('__audit_cache',{code,day:old,data:{date:old,source:'tencent',bars:[{time:'09:31',close:'10',volume:10000,complete:true}]}});
 await page.reload();await page.locator('.stock').filter({hasText:'贵州茅台'}).click();await page.getByLabel('交易日期').selectOption(old);await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect.poll(()=>dailyWindowState(page)).toMatchObject({visible:90,rendered:90,last:old,selected:old});const before=dailyLoadRequests.filter(r=>r.code===code).length;
 const chart=page.getByLabel('日K线及成交量');await chart.focus();await chart.press('ArrowRight');await expect.poll(()=>dailyWindowState(page)).toMatchObject({visible:90,rendered:90,selected:'2024-10-28'});
 expect(dailyLoadRequests.filter(r=>r.code===code)).toHaveLength(before+1);expect((await dailyWindowState(page))!.last<'2026-10-26').toBe(true);await expect(chart).toBeFocused();
 await chart.press('ArrowRight');await expect.poll(()=>dailyWindowState(page)).toMatchObject({selected:'2024-10-29'});
});

test('short actual daily history stays short without fabricating candles or retry loops',async({page})=>{
 const code='sh600519',feed=dailyHistoryFeed().filter(r=>r.date>='2026-10-16');await rpc('add',{code});await rpc('__audit_daily_feed',{code,rows:feed,delay:.1});await page.reload();await page.locator('.stock').filter({hasText:'贵州茅台'}).click();await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(page.locator('.toast')).toContainText(`仅取得${feed.length}根日K`);await expect.poll(()=>dailyWindowState(page)).toMatchObject({count:feed.length,visible:feed.length,rendered:feed.length});expect(dailyLoadRequests.filter(r=>r.code===code)).toHaveLength(3);
});
test('switching stocks while daily backfill is running cannot replace the newly selected chart',async({page})=>{
 const code='sh600519';await rpc('add',{code});await rpc('__audit_daily_feed',{code,rows:dailyHistoryFeed(),delay:.4});await page.reload();await page.locator('.stock').filter({hasText:'贵州茅台'}).click();await page.getByRole('button',{name:'日K',exact:true}).click();await expect(page.locator('.daily-load-state')).toBeVisible();
 await page.locator('.stock').filter({hasText:'宏昌电子'}).click();await expect(page.locator('.detail h2')).toContainText('宏昌电子');await expect.poll(async()=>(await rpc('chart',{code,kind:'daily'})).length).toBeGreaterThan(90);
 await expect.poll(()=>dailyWindowState(page)).toMatchObject({visible:90,rendered:90,last:'2026-10-16'});await expect(page.locator('.detail h2')).toContainText('宏昌电子');
});
