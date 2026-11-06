import {test,expect,Page} from '@playwright/test';
import {spawn,ChildProcessWithoutNullStreams} from 'node:child_process';
import {createInterface} from 'node:readline';
import {writeFileSync} from 'node:fs';

// Real React UI + App + SQLite + signal engine + broker journal + native page
// parsers + reconciliation. Only Android / broker responses are simulated.
let backend:ChildProcessWithoutNullStreams;
let pending:Array<{resolve:(value:any)=>void;reject:(error:Error)=>void}>=[];
function rpc(method:string,args:Record<string,unknown>={}):Promise<any>{
 return new Promise((resolve,reject)=>{pending.push({resolve,reject});backend.stdin.write(JSON.stringify({method,args})+'\n');});
}
async function setup(page:Page){
 backend=spawn('.venv/bin/python',['-u','tests/automatic_e2e_backend.py'],{cwd:process.cwd()});pending=[];
 createInterface({input:backend.stdout}).on('line',line=>{const next=pending.shift();if(!next)return;const data=JSON.parse(line);data.error?next.reject(Error(data.error)):next.resolve(data.result);});
 backend.stderr.on('data',data=>process.stderr.write(data));
 await page.exposeFunction('testTradingRpc',rpc);
 await page.addInitScript(()=>{
  const w=window as any;let id=0;
  w.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>++id,unregisterCallback:()=>{},invoke:(command:string,args:any)=>command==='rpc'?w.testTradingRpc(args.method,args.args):Promise.resolve(command==='plugin:autostart|is_enabled'?false:0)};
  w.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};w.isTauri=true;
 });
 await page.goto('/?panel=trading');
 await expect(page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'987***002 山子高科 自动卖出'})).toBeChecked();
 await page.getByRole('button',{name:'启动实盘执行',exact:true}).click();
 await expect(page.getByText('自动执行运行中',{exact:true})).toBeVisible();
}
async function records(page:Page){
 await page.getByRole('tab',{name:'执行记录',exact:true}).click();
 await page.getByRole('button',{name:'刷新',exact:true}).click();
 return page.locator('.trading-runs tbody tr');
}
async function markers(page:Page){
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await page.locator('.stocks .stock').filter({has:page.locator('strong',{hasText:'山子高科'})}).click();
 const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});await expect(chart).toBeVisible();
 return {chart,read:()=>chart.evaluate(async el=>{
  const s=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(s.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);
  return e.getInstanceByDom(el)?.getOption().series.find((s:any)=>s.name==='自动委托')?.data.map((d:any)=>({label:d.label.formatter,...d.autoTrade}))||[];
 })};
}
test.afterEach(()=>{backend?.stdin.end();backend?.kill();for(const p of pending)p.reject(Error('Test ended'));pending=[];});
test.setTimeout(45000);

test('E2E: confirmed bottom/top routes two accounts through native submission, B/S and partial/full fills',async({page},info)=>{
 await setup(page);
 const buy=await rpc('e2e_feed',{kind:'bottom'});
 expect(buy.isolated).toBe(true);expect(buy.real_device_io).toBe(false);
 expect(buy.orders.zhangle).toMatchObject([{side:'buy',code:'000981',quantity:100,price:'2.24',order_id:'800001'}]);
 expect(buy.orders.ths).toMatchObject([{side:'buy',code:'000981',quantity:200,price:'2.24',order_id:'900001'}]);
 expect(buy.runs.map((r:any)=>r.status)).toEqual(['accepted','accepted']);
 const rows=await records(page);await expect(rows).toHaveCount(2);
 await expect(rows.filter({hasText:'123***001'})).toContainText('买入 100股 × 2.24元');
 await expect(rows.filter({hasText:'987***002'})).toContainText('买入 200股 × 2.24元');
 const repeat=await rpc('e2e_repeat');expect(repeat.orders).toEqual(buy.orders);
 await rpc('e2e_reconcile',{fraction:.5});await page.getByRole('button',{name:'刷新',exact:true}).click();
 await expect(rows.filter({hasText:'123***001'})).toContainText('部分成交');await expect(rows.filter({hasText:'123***001'})).toContainText('已成交 50 股');
 const filledBuy=await rpc('e2e_reconcile',{fraction:1});await page.getByRole('button',{name:'刷新',exact:true}).click();
 await expect(rows.filter({hasText:'987***002'})).toContainText('已成交 200 股');
 expect(filledBuy.chart.points.find((p:any)=>p.account_id==='e2e-b').fill_price).toBe('2.24');
 // ZL's native order reader does not expose execution average; never invent it.
 expect(filledBuy.chart.points.find((p:any)=>p.account_id==='e2e-a').fill_price).toBeNull();
 const sell=await rpc('e2e_feed',{kind:'top'});
 expect(sell.orders.zhangle[1]).toMatchObject({side:'sell',quantity:100,price:'2.27',order_id:'800002'});
 expect(sell.orders.ths[1]).toMatchObject({side:'sell',quantity:200,price:'2.27',order_id:'900002'});
 await rpc('e2e_reconcile',{fraction:.5});const settled=await rpc('e2e_reconcile',{fraction:1});
 expect(settled.runs.map((r:any)=>r.status)).toEqual(['filled','filled','filled','filled']);
 expect((await rpc('e2e_repeat')).orders).toEqual(settled.orders);
 const plot=await markers(page);await expect.poll(async()=>(await plot.read()).map((p:any)=>p.label).sort()).toEqual(['B','B','S','S']);
 const marks=await plot.read();
 expect(marks.filter((p:any)=>p.account_id==='e2e-a').map((p:any)=>p.quantity)).toEqual([100,100]);
 expect(marks.filter((p:any)=>p.account_id==='e2e-b').map((p:any)=>p.quantity)).toEqual([200,200]);
 expect(marks.find((p:any)=>p.label==='S'&&p.account_id==='e2e-b').fill_price).toBe('2.27');
 await page.screenshot({path:info.outputPath('isolated-e2e-bs.png'),fullPage:true});
 writeFileSync(info.outputPath('isolated-e2e-report.json'),JSON.stringify({boundary:'SIMULATED_EXTERNAL_BROKERS_NO_REAL_ORDERS',buy,settled,marks},null,2));
});

test('E2E: wrong account blocks only that account while the other account submits',async({page})=>{
 await setup(page);await rpc('e2e_fault',{broker:'zhangle',kind:'wrong_account'});
 const state=await rpc('e2e_feed',{kind:'bottom'});
 expect(state.orders.zhangle).toHaveLength(0);expect(state.orders.ths).toHaveLength(1);
 expect(state.runs.find((r:any)=>r.account_id==='e2e-a').status).toBe('skipped');
 expect(state.runs.find((r:any)=>r.account_id==='e2e-b').status).toBe('accepted');
 expect((await rpc('e2e_repeat')).orders.ths).toHaveLength(1);
 const rows=await records(page);await expect(rows.filter({hasText:'123***001'})).toContainText('账号不一致');
});

test('E2E: accepted unfilled buy and sell immediately show B/S for both accounts',async({page},info)=>{
 await setup(page);
 const buy=await rpc('e2e_feed',{kind:'bottom'});
 expect(buy.runs.map((r:any)=>r.status)).toEqual(['accepted','accepted']);
 expect([...buy.orders.zhangle,...buy.orders.ths].every((r:any)=>r.filled===0)).toBe(true);
 const plot=await markers(page);
 await expect.poll(async()=>(await plot.read()).map((p:any)=>p.label)).toEqual(['B','B']);
 const sell=await rpc('e2e_feed',{kind:'top'});
 expect(sell.runs.map((r:any)=>r.status)).toEqual(['accepted','accepted','accepted','accepted']);
 expect([...sell.orders.zhangle,...sell.orders.ths].every((r:any)=>r.filled===0)).toBe(true);
 await expect.poll(async()=>(await plot.read()).map((p:any)=>p.label).sort()).toEqual(['B','B','S','S']);
 expect((await plot.read()).every((p:any)=>p.fill_price==null)).toBe(true);
 expect((await rpc('e2e_repeat')).orders).toEqual(sell.orders);
 writeFileSync(info.outputPath('accepted-unfilled-markers.json'),JSON.stringify({boundary:'SIMULATED_EXTERNAL_BROKERS_NO_REAL_ORDERS',state:sell,marks:await plot.read()},null,2));
});

test('E2E: a temporary chart refresh failure retains B/S within the same stock and date',async({page})=>{
 await setup(page);await rpc('e2e_feed',{kind:'bottom'});
 const plot=await markers(page);
 await expect.poll(async()=>(await plot.read()).length).toBe(2);
 const before=await plot.read();
 await rpc('e2e_chart_fault',{enabled:true});
 await expect.poll(()=>rpc('e2e_chart_failures'),{timeout:12000}).toBeGreaterThan(0);
 expect(await plot.read()).toEqual(before);
 await page.getByRole('button',{name:'自动交易',exact:true}).click();
 await rpc('add',{code:'sh603938'});
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await page.locator('.stocks .stock').filter({hasText:'603938'}).click();
 await expect.poll(async()=>(await plot.read()).length).toBe(0);
 await page.locator('.stocks .stock').filter({hasText:'000981'}).click();
 await expect(plot.chart).toBeVisible();
 await expect.poll(()=>plot.read()).toEqual(before);
});

test('E2E: unknown automatic attempts retain B/S and do not block a different fresh signal',async({page})=>{
 await setup(page);await rpc('e2e_fault',{broker:'zhangle',kind:'lose_receipt'});
 const state=await rpc('e2e_feed',{kind:'bottom'});
 expect(state.orders.zhangle).toHaveLength(1);expect(state.runs.find((r:any)=>r.account_id==='e2e-a').status).toBe('unknown');
 expect((await rpc('e2e_repeat')).orders.zhangle).toHaveLength(1);
 const top=await rpc('e2e_feed',{kind:'top'});expect(top.orders.zhangle).toHaveLength(2);
 const plot=await markers(page);await expect.poll(async()=>(await plot.read()).length).toBe(4);
 const marks=await plot.read();expect(marks.filter((m:any)=>m.account_id==='e2e-a')).toHaveLength(2);expect(marks.filter((m:any)=>m.account_id==='e2e-a').every((m:any)=>m.status==='unknown')).toBe(true);expect(marks.filter((m:any)=>m.account_id==='e2e-b')).toHaveLength(2);
});

test('E2E: UI and snapshot RPC stay responsive while a broker operation is waiting',async({page},info)=>{
 await setup(page);await rpc('e2e_hold_native');const job=await rpc('e2e_feed_async',{kind:'bottom'});
 await expect.poll(async()=>{const s=await rpc('e2e_state');return s.runs.some((r:any)=>r.status==='processing');}).toBe(true);
 const start=Date.now();const rows=await records(page);await expect(rows).toHaveCount(2);
 await page.getByRole('tab',{name:'持仓与策略',exact:true}).click();
 await page.getByRole('textbox',{name:'搜索股票'}).fill('山子');
 const elapsedMs=Date.now()-start;expect(elapsedMs).toBeLessThan(2000);
 writeFileSync(info.outputPath('ui-responsive.json'),JSON.stringify({scenario:'native broker wait; refresh, switch tabs and search',elapsedMs,limitMs:2000}));
 await rpc('e2e_release_native');
 await expect.poll(async()=>(await rpc('job',{job:job.job})).status).toBe('done');
 const done=await rpc('e2e_state');expect(done.orders.zhangle).toHaveLength(1);expect(done.orders.ths).toHaveLength(1);
});

test('E2E: missing Galaxy receipt recovers a unique filled contract and displays B without resubmission',async({page},info)=>{
 await setup(page);await rpc('e2e_fault',{broker:'ths',kind:'lose_receipt'});
 await rpc('e2e_fault',{broker:'ths',kind:'orders_unavailable'});
 const state=await rpc('e2e_feed',{kind:'bottom'});
 expect(state.orders.ths).toHaveLength(1);
 expect(state.runs.find((r:any)=>r.account_id==='e2e-b').status).toBe('unknown');
 const filled=await rpc('e2e_reconcile',{fraction:1});
 expect(filled.runs.find((r:any)=>r.account_id==='e2e-b').status).toBe('filled');
 expect(filled.chart.points.find((p:any)=>p.account_id==='e2e-b')).toMatchObject({order_id:'900001',filled:200,fill_price:'2.24'});
 expect((await rpc('e2e_repeat')).orders.ths).toHaveLength(1);
 const plot=await markers(page);
 await expect.poll(async()=>(await plot.read()).filter((p:any)=>p.account_id==='e2e-b').map((p:any)=>p.label)).toEqual(['B']);
 await page.getByRole('button',{name:'自动交易',exact:true}).click();
 const rows=await records(page);await expect(rows.filter({hasText:'987***002'})).toContainText('已成交 200 股');
 await page.screenshot({path:info.outputPath('recovered-contract-record.png'),fullPage:true});
});

test('E2E: lost Galaxy receipts recover unfilled and partial B/S from today orders without broker IDs or resubmission',async({page},info)=>{
 await setup(page);await rpc('e2e_fault',{broker:'ths',kind:'lose_receipt'});
 const lost=await rpc('e2e_feed',{kind:'bottom'});
 expect(lost.runs.find((r:any)=>r.account_id==='e2e-b').status).toBe('unknown');
 const accepted=await rpc('e2e_reconcile',{fraction:0});
 expect(accepted.chart.points.find((p:any)=>p.account_id==='e2e-b')).toMatchObject({status:'accepted',order_id:'',filled:0,order_price:'2.24',fill_price:null});
 const plot=await markers(page);
 await expect.poll(async()=>(await plot.read()).map((p:any)=>p.label)).toEqual(['B','B']);
 await rpc('e2e_feed',{kind:'top'});
 const acceptedSell=await rpc('e2e_reconcile',{fraction:0});
 expect(acceptedSell.chart.points.filter((p:any)=>p.account_id==='e2e-b').map((p:any)=>p.status)).toEqual(['accepted','accepted']);
 await expect.poll(async()=>(await plot.read()).map((p:any)=>p.label).sort()).toEqual(['B','B','S','S']);
 const partial=await rpc('e2e_reconcile',{fraction:.5});
 expect(partial.chart.points.filter((p:any)=>p.account_id==='e2e-b').map((p:any)=>[p.status,p.filled,p.order_id])).toEqual([['partial',100,''],['partial',100,'']]);
 expect((await rpc('e2e_repeat')).orders.ths).toHaveLength(2);
 expect((await plot.read()).filter((p:any)=>p.account_id==='e2e-b').map((p:any)=>p.label).sort()).toEqual(['B','S']);
 writeFileSync(info.outputPath('lost-receipt-native-order.json'),JSON.stringify({boundary:'SIMULATED_EXTERNAL_BROKERS_NO_REAL_ORDERS',accepted:acceptedSell,partial,marks:await plot.read()},null,2));
 await page.screenshot({path:info.outputPath('lost-receipt-native-bs.png'),fullPage:true});
});
