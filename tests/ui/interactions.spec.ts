import {test,expect,Page} from '@playwright/test';
import {spawn,ChildProcessWithoutNullStreams} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {turningShapes} from '../../src/turningShapes';
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
 await page.addInitScript(()=>{if(!sessionStorage.getItem('__audit-turning-version-initialized')){localStorage.setItem('stock-monitor-turning-version','v1');sessionStorage.setItem('__audit-turning-version-initialized','true');}(window as any).isTauri=true;(window as any).__TAURI_INTERNALS__={invoke:(cmd:string,args:any)=>(window as any).__auditRpc(cmd,args)};});
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

test('daily left boundary expands using local cached history and retains selected date',async({page})=>{
 await page.getByRole('button',{name:'日K',exact:true}).click();
 const before=await page.getByLabel('区间交易日').getByRole('button').first().innerText();
 await page.getByLabel('区间交易日').getByRole('button').first().click();
 await page.getByLabel('日K线及成交量').focus();await page.getByLabel('日K线及成交量').press('ArrowLeft');
 await expect(page.locator('.linked-minute h3')).not.toContainText(before.slice(0,10));
 const day=await page.locator('.linked-minute h3').innerText();expect(day<before.slice(0,10)).toBeTruthy();
 await expect(page.locator('.chart-caption')).toContainText('本地缓存优先');
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/0.4.0/history.png',fullPage:true});
});

test('messages retain content, mark read, survive reload and link to matching intraday',async({page})=>{
 const e={key:'2026-10-16|603002|09:31',symbol:'603002',trading_date:'2026-10-16',candidate_time:'09:31',confirmation_label:'09:33',event_label:'09:33',volumes:[4384500,1461000,1957000],kind:'TWO_MINUTE_CONFIRMATION',observed_at:'2026-10-16T09:33:05+08:00'};
 await rpc('__audit_event',e);await rpc('__audit_event',e);
 await page.getByRole('button',{name:/消息中心/}).click();await expect(page.locator('.message-item')).toHaveCount(1);
 await expect(page.locator('.message-item')).toContainText('宏昌电子');await expect(page.locator('.message-item')).toContainText('438.45');await expect(page.locator('.message-item')).toContainText('万股');
 await page.getByRole('button',{name:'全部标为已读'}).click();await expect(page.locator('.message-item.unread')).toHaveCount(0);
 await page.reload();await page.getByRole('button',{name:/消息中心/}).click();await expect(page.locator('.message-item')).toHaveCount(1);await expect(page.locator('.message-item.unread')).toHaveCount(0);
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/0.4.0/messages.png',fullPage:true});
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
 await expect(page.getByRole('checkbox',{name:/缩量顶补漏/})).toHaveCount(0);await expect(page.getByLabel('底顶观察版本')).toHaveCount(0);
 await expect(page.locator('.average-caption')).toContainText('Q1筛选未改');
 const show=async(time:string)=>chart.evaluate(async(el,time)=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el);c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:c.getOption().xAxis[0].data.indexOf(time)});},time);
 await show(example.expected[0].time);const tooltip=chart.locator('.quote-tooltip');
 await expect(tooltip).toContainText('底形态：');await expect(tooltip).toContainText('Q1质量：入选');for(const hidden of ['Q1冻结版','确认依据：','研究滑点：','信号间隔：','验证状态：'])await expect(tooltip).not.toContainText(hidden);await expect(tooltip).toContainText('候选点：09:57');await expect(tooltip).toContainText('确认时间：09:59');
 await expect(tooltip).toContainText('不保证到达');await expect(tooltip).toContainText('基准触发：09:50');
 expect(await tooltip.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await chart.evaluate(async el=>{const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);const c=e.getInstanceByDom(el),m=c.getOption().series[0].markPoint.data.find((m:any)=>m.value==='底形态');c.trigger('click',{componentType:'markPoint',data:m});});
 await show(example.expected[0].time);await expect(tooltip).toContainText('基准触发：09:50');
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
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/0.4.0/coverage.png',fullPage:true});
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
 await chart.locator('.quote-tooltip').screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/compact-trade-tooltip.png'});
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
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/watch-quotes-local.png',fullPage:true});
 await rpc('__audit_quote',{code:'sh603002',quote:{price:'9',timestamp:'2026-10-19T14:31:00+08:00'}});
 await expect(stock.getByLabel('涨跌幅').locator('strong')).toHaveText('—',{timeout:10000});
 await expect(stock.getByLabel('涨跌额').locator('strong')).toHaveText('—');await expect(stock.getByLabel('振幅').locator('strong')).toHaveText('—');
});

test('tooltip body does not block mouse tracking',async({page})=>{
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 const chart=page.getByLabel('分时价格及分钟成交量');const box=(await chart.boundingBox())!;
 await page.mouse.move(box.x+box.width*.35,box.y+150);
 const tooltip=chart.locator('.quote-tooltip');await expect(tooltip).toBeVisible();
 const rect=(await tooltip.boundingBox())!;
 // Move into the text body of the displayed tooltip; the chart beneath must still track.
 const x=rect.x+Math.min(25,rect.width/3),y=rect.y+15;
 const expected=await chart.evaluate(async(el,args)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);const c=e.getInstanceByDom(el);
  const converted=c.convertFromPixel({gridIndex:0},[args.x,args.y]);const index=Math.round(Array.isArray(converted)?converted[0]:converted);return c.getOption().xAxis[0].data[index];
 },{x:x-box.x,y:y-box.y});
 const before=await tooltip.locator(':scope>div').first().textContent();expect(expected).not.toBe(before);
 await page.mouse.move(x,y);await expect(tooltip.locator(':scope>div').first()).toHaveText(expected,{timeout:1000});
 await expect(chart.locator('input')).toHaveCount(0);
 for(const fraction of [.2,.55,.85,.4,.75,.25]){
  const target=await chart.evaluate(async(el,f)=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text());const url=source.match(/from "([^"]*echarts\.js[^"]*)"/)![1];const e=await import(url);const c=e.getInstanceByDom(el);const labels=c.getOption().xAxis[0].data;const index=Math.round((labels.length-1)*f);return {xy:c.convertToPixel({seriesIndex:0},[labels[index],10]),time:labels[index]};
  },fraction);
  await page.mouse.move(box.x+target.xy[0],box.y+150);
  await expect(tooltip.locator(':scope>div').first()).toHaveText(target.time,{timeout:500});
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
  return {labels:o.xAxis.map((a:any)=>a.data),prices:o.series[0].data,volume:o.series.at(-1).data.map((d:any)=>d.value),end:o.dataZoom[0].end,point:c.convertToPixel({seriesIndex:0},['09:33',11])};
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
 await page.screenshot({path:'../../outputs/guanliang-q1-freeze-20261025/ui/ui/watchlist-equal-height-local.png',fullPage:true});
});
