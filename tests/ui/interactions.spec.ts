import {test,expect,Page} from '@playwright/test';
import {spawn,ChildProcessWithoutNullStreams} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
let process:ChildProcessWithoutNullStreams;let directory:string;
let waiting:{resolve:(r:any)=>void;reject:(e:Error)=>void}[]=[];
async function rpc(method:string,args:Record<string,unknown>={}){if(process.stdin.writableEnded)return null;return new Promise<any>((resolve,reject)=>{waiting.push({resolve,reject});process.stdin.write(JSON.stringify({method,args})+'\n');});}
test.beforeEach(async({page})=>{
 directory=await mkdtemp(join(tmpdir(),'stock-ui-audit-'));
 process=spawn('.venv/bin/python',['tests/ui/rpc_fixture.py'],{env:{...global.process.env,PYTHONPATH:global.process.cwd(),STOCK_MONITOR_DATA:directory},stdio:'pipe'});
 waiting=[];
 createInterface({input:process.stdout}).on('line',line=>{const reply=JSON.parse(line),p=waiting.shift();if(reply.ok)p?.resolve(reply.data);else p?.reject(Error(reply.error));});
 process.stderr.on('data',chunk=>console.error(String(chunk)));
 await page.exposeFunction('__auditRpc',async(cmd:string,args:any)=>{
  if(cmd==='plugin:autostart|is_enabled')return false;
  if(cmd==='rpc'){
   if(args.method==='chart'&&args.args.code==='sh603002')await new Promise(r=>setTimeout(r,220));
   return rpc(args.method,args.args);
  }
  return true;
 });
 await page.addInitScript(()=>{(window as any).isTauri=true;(window as any).__TAURI_INTERNALS__={invoke:(cmd:string,args:any)=>(window as any).__auditRpc(cmd,args)};});
 await page.goto('/');await expect(page.locator('.stock')).toHaveCount(12);
});
test.afterEach(async({page})=>{await page.close();process.stdin.end();await new Promise(resolve=>process.once('exit',resolve));await rm(directory,{recursive:true,force:true});});

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
 const chart=page.locator('.chart');const box=(await chart.boundingBox())!;await page.mouse.move(box.x+65.2,box.y+80);
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
 await page.getByRole('button',{name:/触发记录/}).click();
 await expect(page.getByRole('columnheader',{name:'三分钟量（万股）'})).toBeVisible();
 const row=page.locator('tbody tr').filter({hasText:'宏昌电子'});await expect(row).toContainText('603002');
 await expect(row).toContainText('438.45 / 146.10 / 195.70');await expect(row).toContainText('腾讯行情');
 await page.screenshot({path:'docs/0.4.0/records.png',fullPage:true});
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
 await page.screenshot({path:'docs/0.4.0/intraday.png',fullPage:true});
});

test('daily left boundary expands using local cached history and retains selected date',async({page})=>{
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const before=await page.getByLabel('区间交易日').getByRole('button').first().innerText();
 await page.getByLabel('区间交易日').getByRole('button').first().click();
 await page.getByLabel('日K线及成交量').focus();await page.getByLabel('日K线及成交量').press('ArrowLeft');
 await expect(page.locator('.linked-minute h3')).not.toContainText(before.slice(0,10));
 const day=await page.locator('.linked-minute h3').innerText();expect(day<before.slice(0,10)).toBeTruthy();
 await expect(page.locator('.chart-caption')).toContainText('本地缓存优先');
 await page.screenshot({path:'docs/0.4.0/history.png',fullPage:true});
});

test('messages retain content, mark read, survive reload and link to matching intraday',async({page})=>{
 const e={key:'2026-10-16|603002|09:31',symbol:'603002',trading_date:'2026-10-16',candidate_time:'09:31',confirmation_label:'09:33',event_label:'09:33',volumes:[4384500,1461000,1957000],kind:'TWO_MINUTE_CONFIRMATION',observed_at:'2026-10-16T09:33:05+08:00'};
 await rpc('__audit_event',e);await rpc('__audit_event',e);
 await page.getByRole('button',{name:/消息中心/}).click();await expect(page.locator('.message-item')).toHaveCount(1);
 await expect(page.locator('.message-item')).toContainText('宏昌电子');await expect(page.locator('.message-item')).toContainText('438.45');await expect(page.locator('.message-item')).toContainText('万股');
 await page.getByRole('button',{name:'全部标为已读'}).click();await expect(page.locator('.message-item.unread')).toHaveCount(0);
 await page.reload();await page.getByRole('button',{name:/消息中心/}).click();await expect(page.locator('.message-item')).toHaveCount(1);await expect(page.locator('.message-item.unread')).toHaveCount(0);
 await page.screenshot({path:'docs/0.4.0/messages.png',fullPage:true});
 await page.getByRole('button',{name:'查看对应分时'}).click();await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');await expect(page.locator('.detail h2')).toContainText('宏昌电子');
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
 await expect(page.getByLabel('区间交易日').getByRole('button').filter({hasText:'2026-10-15'})).toBeVisible();
 await page.getByLabel('区间交易日').getByRole('button').filter({hasText:'2026-10-15'}).click();
 await expect(page.locator('.history-status')).toContainText('缺少当日可靠涨停价');
 await page.getByLabel('历史涨停价').fill('17.89');await page.getByRole('button',{name:'保存参考价并回放'}).click();
 await expect(page.locator('.history-status')).toContainText('完整分钟量回放');await expect(page.locator('.day-signals')).toContainText('438.45');
 expect((await rpc('messages')).total).toBe(0);
});

test('intraday average is shown from turnover data and removed daily toolbar stays absent',async({page})=>{
 const old=await rpc('chart',{code:'sh603002',kind:'minute'});const data=old[0].data;
 data.bars=data.bars.map((b:any)=>({...b,average:'15.4321'}));
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-16',data});
 await page.reload();await expect(page.locator('.average-caption')).toContainText('累计成交额');
 const chart=page.getByLabel('分时价格及分钟成交量');const box=(await chart.boundingBox())!;
 await expect(async()=>{await page.mouse.move(box.x+65.2,box.y+80);await expect(chart.locator('.quote-tooltip')).toContainText('均价：15.43 元');}).toPass();
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(page.locator('.daily-navigation')).toHaveCount(0);await expect(page.getByRole('button',{name:'← 上一交易日',exact:true})).toHaveCount(0);
});

test('old daily selection explains missing intraday and can return to available history',async({page})=>{
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await page.getByLabel('区间交易日').getByRole('button').first().click();
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
 await page.screenshot({path:'docs/0.4.0/coverage.png',fullPage:true});
 await day.click();await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-09');
 await expect(page.locator('.day-signals')).toContainText('规则回放暂未认证');
 expect((await rpc('messages')).total).toBe(0);
});

test('index cards replace old summary and chart keyboard focus has no enclosing outline',async({page})=>{
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

test('latest trigger is default; manual anchor stays selected and restores latest across dates',async({page})=>{
 const bars=['100','99','98','110','108','105'].map((close,i)=>({time:`09:${31+i}`,close,volume:100,complete:true}));
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'tencent',bars}});
 for(const [candidate_time,confirmation_label] of [['09:31','09:33'],['09:34','09:36']])await rpc('__audit_event',{key:`2026-10-19|603002|${candidate_time}`,symbol:'603002',trading_date:'2026-10-19',candidate_time,confirmation_label,event_label:confirmation_label,volumes:[300,100,100],kind:'TWO_MINUTE_CONFIRMATION'});
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-19',{timeout:10000});
 const chart=page.getByLabel('分时价格及分钟成交量');
 await expect(page.locator('.trigger-comparison')).toContainText('已选触发：09:34 · 110.00 元');
 await expect(page.getByRole('button',{name:'买点研究',exact:false})).toHaveCount(0);
 await expect(page.getByRole('region',{name:'做T价差参考'})).toHaveCount(0);
 const point=async(time:string,price:number)=>chart.evaluate(async(el,args)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];
  const echarts=await import(url);const instance=echarts.getInstanceByDom(el);
  return instance.convertToPixel({seriesIndex:0},[args.time,args.price]) as number[];
 },{time,price});
 const clickMark=async(time:string,price:number)=>{
  const xy=await point(time,price);const box=(await chart.boundingBox())!;
  await page.mouse.click(box.x+xy[0],box.y+xy[1]-18);
 };
 const hover=async(time:string,price:number)=>{
  const xy=await point(time,price);const box=(await chart.boundingBox())!;
  await page.mouse.move(box.x+xy[0],box.y+80);
 };
 await expect(async()=>{await clickMark('09:31',100);await expect(page.locator('.trigger-comparison')).toContainText('已选触发：09:31 · 100.00 元');}).toPass();
 await hover('09:33',98);await expect(chart.locator('.quote-tooltip')).toContainText('相对触发涨跌幅：-2.00%');
 await hover('09:34',110);await expect(chart.locator('.quote-tooltip')).toContainText('相对触发涨跌幅：+10.00%');
 await clickMark('09:34',110);await expect(page.locator('.trigger-comparison')).toContainText('已选触发：09:34 · 110.00 元');
 await hover('09:36',105);await expect(chart.locator('.quote-tooltip')).toContainText('相对触发涨跌幅：-4.55%');
 await page.screenshot({path:'docs/trigger-hover-local.png',fullPage:true});
 await page.getByRole('button',{name:'恢复最近触发'}).click();await hover('09:33',98);
 await expect(chart.locator('.quote-tooltip')).toContainText('相对触发涨跌幅：-10.91%');
 await clickMark('09:31',100);await page.getByLabel('交易日期').selectOption('2026-10-16');
 await expect(page.locator('.trigger-comparison')).not.toContainText('100.00 元');
 await page.getByLabel('交易日期').selectOption('2026-10-19');await expect(page.locator('.trigger-comparison')).toContainText('已选触发：09:34 · 110.00 元');
 await rpc('__audit_cache',{code:'sh603002',day:'2026-10-19',data:{date:'2026-10-19',source:'tencent',bars:[...bars,...['120','115','112'].map((close,i)=>({time:`09:${37+i}`,close,volume:100,complete:true}))]}});
 await rpc('__audit_event',{key:'2026-10-19|603002|09:37',symbol:'603002',trading_date:'2026-10-19',candidate_time:'09:37',confirmation_label:'09:39',event_label:'09:39',volumes:[300,100,100],kind:'TWO_MINUTE_CONFIRMATION'});
 await expect(page.locator('.trigger-comparison')).toContainText('已选触发：09:37 · 120.00 元',{timeout:10000});
});

test('watch list shows quote change percent and amplitude, with missing fields explicit',async({page})=>{
 await rpc('__audit_quote',{code:'sh603002',quote:{price:'10.50',previous_close:'10',high:'10.8',low:'9.8',change:'5',timestamp:'2026-10-19T14:30:00+08:00'}});
 const stock=page.locator('.stock').filter({hasText:'宏昌电子'});
 await expect(stock.getByLabel('涨跌额').locator('strong')).toHaveText('+0.50',{timeout:10000});
 await expect(stock.getByLabel('涨跌幅').locator('strong')).toHaveText('+5.00%');await expect(stock.getByLabel('振幅').locator('strong')).toHaveText('10.00%');
 await expect(page.getByRole('button',{name:/买点研究/})).toHaveCount(0);
 await page.screenshot({path:'docs/watch-quotes-local.png',fullPage:true});
 await rpc('__audit_quote',{code:'sh603002',quote:{price:'9',timestamp:'2026-10-19T14:31:00+08:00'}});
 await expect(stock.getByLabel('涨跌幅').locator('strong')).toHaveText('—',{timeout:10000});
 await expect(stock.getByLabel('涨跌额').locator('strong')).toHaveText('—');await expect(stock.getByLabel('振幅').locator('strong')).toHaveText('—');
});
