import {openSimulation} from './fixtures/open-simulation';
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
async function manualTicket(page:Page){
 await rpc('e2e_repeat');
 const {chart}=await markers(page);await chart.scrollIntoViewIfNeeded();
 const xy=await chart.evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);
  const instance=e.getInstanceByDom(el),option=instance.getOption(),prices=option.series[0].data.filter((p:any)=>typeof p==='number'),i=option.series[0].data.findIndex((p:any,j:number)=>j>3&&typeof p==='number');
  // Click inside the price grid; a point exactly on its top border can round
  // outside the grid when the browser converts fractional client pixels.
  return instance.convertToPixel({xAxisIndex:0,yAxisIndex:0},[option.xAxis[0].data[i],(Math.min(...prices)+Math.max(...prices))/2]);
 });
 const box=(await chart.boundingBox())!;await page.mouse.click(box.x+xy[0],box.y+xy[1],{button:'right'});
 const ticket=page.getByRole('dialog');await expect(ticket).toHaveAttribute('aria-label','真实买卖确认');
 await expect(ticket.getByRole('switch',{name:'真实委托'})).toHaveAttribute('aria-checked','true');return ticket;
}
test.afterEach(()=>{backend?.stdin.end();backend?.kill();for(const p of pending)p.reject(Error('Test ended'));pending=[];});
test.setTimeout(45000);

test('tickets default to real on every open without submitting or selecting simulation automatically',async({page},info)=>{
 await setup(page);const ticket=await manualTicket(page);await expect(ticket.getByLabel('真实委托券商账户')).toHaveValue('');
 await expect(ticket.getByLabel('真实委托限价')).toBeFocused();
 await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeDisabled();
 await ticket.screenshot({path:info.outputPath('default-real-ticket.png')});
 await ticket.getByRole('switch',{name:'真实委托'}).click();await expect(ticket).toHaveAttribute('aria-label','模拟买卖确认');await page.keyboard.press('Escape');await expect(ticket).toHaveCount(0);
 await manualTicket(page);const state=await rpc('e2e_state');expect(state.orders.zhangle).toEqual([]);expect(state.orders.ths).toEqual([]);expect((await rpc('paper_snapshot')).orders).toEqual([]);
 expect(await rpc('broker_requests',{id:'e2e-a'})).toEqual([]);expect(await rpc('broker_requests',{id:'e2e-b'})).toEqual([]);
});

test('a holding-entry real ticket initializes its price from the delayed quote when no point price was supplied',async({page})=>{
 await setup(page);await rpc('e2e_repeat');await markers(page);
 const account=await rpc('paper_create',{cash:10000});await rpc('paper_seed',{account:account.id,code:'sz000981',shares:100,cost:'2.00'});
 await openSimulation(page);const row=page.locator('.paper-positions tbody tr').filter({hasText:'山子高科'});await expect(row).toBeVisible();
 await page.evaluate(()=>{const w=window as any,original=w.testTradingRpc;w.testTradingRpc=async(method:string,args:any)=>{const result=await original(method,args);if(method==='paper_quote'){w.defaultRealQuote=result.price/100;await new Promise(r=>setTimeout(r,300));}return result;};});
 await row.getByRole('button',{name:'买入',exact:true}).click();const ticket=page.getByRole('dialog');await expect(ticket).toHaveAttribute('aria-label','真实买卖确认');
 await expect.poll(()=>page.evaluate(()=> (window as any).defaultRealQuote||0)).toBeGreaterThan(0);
 await expect(ticket.getByLabel('真实委托限价')).toHaveValue(String(await page.evaluate(()=> (window as any).defaultRealQuote)));
 expect((await rpc('e2e_state')).orders.zhangle).toEqual([]);expect((await rpc('paper_snapshot')).orders).toEqual([]);
});

test('a single synchronized source fixes the ticket account and submits only to that account',async({page},info)=>{
 await setup(page);await rpc('e2e_keep_sources',{code:'sz000981',accounts:['e2e-b']});await page.reload();
 const ticket=await manualTicket(page);await expect(ticket.getByRole('combobox',{name:'真实委托券商账户'})).toHaveCount(0);
 await expect(ticket.getByLabel('真实委托券商账户')).toContainText('987***002');
 await expect(ticket.getByRole('checkbox')).toHaveCount(0);await expect(ticket.getByRole('switch',{name:'真实委托'})).toHaveAttribute('aria-checked','true');
 await expect(ticket.getByText('图表参考',{exact:false})).toHaveCount(0);await expect(ticket.getByText('费用以券商为准')).toHaveCount(0);
 await ticket.getByLabel('真实委托限价').fill('2.24');await ticket.getByLabel('真实委托股数').fill('1000');
 await expect(ticket.locator('.ticket-buy .ticket-estimate')).toHaveText('委托金额 2,240.00 元');
 await page.setViewportSize({width:1280,height:800});const box=(await ticket.boundingBox())!;expect(box.width).toBeLessThanOrEqual(350);expect(box.height).toBeLessThanOrEqual(430);
 await ticket.screenshot({path:info.outputPath('fixed-source-ticket.png')});
 await ticket.getByRole('button',{name:'确认买入',exact:true}).click();await expect(ticket).toHaveCount(0);
 const state=await rpc('e2e_state');expect(state.orders.zhangle).toEqual([]);expect(state.orders.ths).toMatchObject([{side:'buy',quantity:1000,price:'2.24'}]);
 expect(await rpc('broker_requests',{id:'e2e-a'})).toEqual([]);expect(await rpc('broker_requests',{id:'e2e-b'})).toHaveLength(1);
});

test('multiple synchronized sources exclude unrelated accounts and still show the amount before selection',async({page})=>{
 await setup(page);await page.evaluate(()=>{
  const w=window as any,original=w.testTradingRpc;
  w.testTradingRpc=async(method:string,args:any)=>{const result=await original(method,args);return method==='broker_accounts'?[...result,{...result[0],id:'unrelated',account_masked:'000***999'}]:result;};
 });
 const ticket=await manualTicket(page),accounts=ticket.getByRole('combobox',{name:'真实委托券商账户'});
 await expect(accounts.locator('option')).toHaveCount(3);expect(await accounts.locator('option').evaluateAll(items=>items.map(e=>(e as HTMLOptionElement).value))).toEqual(['','e2e-a','e2e-b']);
 await ticket.getByLabel('真实委托限价').fill('30.01');await ticket.getByLabel('真实委托股数').fill('1000');
 await expect(ticket.locator('.ticket-buy .ticket-estimate')).toHaveText('委托金额 30,010.00 元');await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeDisabled();
 await accounts.selectOption('e2e-a');await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeEnabled();
 expect((await rpc('e2e_state')).orders.zhangle).toEqual([]);
});

test('a stock without synchronized sources can choose an account while amounts depend only on price and quantity',async({page})=>{
 await setup(page);await rpc('e2e_keep_sources',{code:'sz000981',accounts:[]});await page.reload();const ticket=await manualTicket(page);
 const accounts=ticket.getByRole('combobox',{name:'真实委托券商账户'});await expect(accounts.locator('option')).toHaveCount(3);
 await ticket.getByLabel('真实委托限价').fill('9.96');await ticket.getByLabel('真实委托股数').fill('1000');
 await expect(ticket.locator('.ticket-buy .ticket-estimate')).toHaveText('委托金额 9,960.00 元');await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeDisabled();
 await accounts.selectOption('e2e-a');await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeEnabled();
 await ticket.getByLabel('真实委托限价').fill('');await expect(ticket.locator('.ticket-buy .ticket-estimate')).toHaveText('委托金额 待填写');await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeDisabled();
});

test('an unavailable unique source never falls back to another brokerage account',async({page})=>{
 await setup(page);await rpc('e2e_keep_sources',{code:'sz000981',accounts:['e2e-a']});await page.reload();
 await page.evaluate(()=>{const w=window as any,original=w.testTradingRpc;w.testTradingRpc=async(method:string,args:any)=>{const result=await original(method,args);return method==='broker_accounts'?result.map((a:any)=>a.id==='e2e-a'?{...a,enabled:false}:a):result;};});
 const ticket=await manualTicket(page);await expect(ticket.getByLabel('真实委托券商账户')).toContainText('123***001');
 await expect(ticket.getByRole('combobox',{name:'真实委托券商账户'})).toHaveCount(0);await expect(ticket.getByText('来源账户已停用或暂不支持下单，请核对证券账户。')).toBeVisible();
 await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeDisabled();expect((await rpc('e2e_state')).orders.zhangle).toEqual([]);expect((await rpc('e2e_state')).orders.ths).toEqual([]);
});

test('real ticket capacity and fractions use only the selected broker and recompute when price changes',async({page},info)=>{
 await setup(page);await page.evaluate(()=>{
  const w=window as any,original=w.testTradingRpc;w.capacityMethods=[];
  w.testTradingRpc=async(method:string,args:any)=>{w.capacityMethods.push(method);const result=await original(method,args);if(method!=='trading_view')return result;
   return {...result,accounts:result.accounts.map((a:any)=>({...a,funds:{...a.funds,available:a.id==='e2e-a'?'5,973.01':'1,000.00'}})),positions:result.positions.map((p:any)=>({...p,sellable:p.account_id==='e2e-a'?900:155}))};};
 });
 const ticket=await manualTicket(page),accounts=ticket.getByLabel('真实委托券商账户'),price=ticket.getByLabel('真实委托限价'),shares=ticket.getByLabel('真实委托股数'),capacity=ticket.getByLabel('可买卖数量',{exact:true});
 await accounts.selectOption('e2e-a');await price.fill('2.24');await expect(capacity).toContainText('2,600 股');
 await expect(capacity).not.toContainText('试算');await expect(shares).toHaveValue('2600');
 await price.fill('3.00');await expect(shares).toHaveValue('1900');await price.fill('2.24');await expect(shares).toHaveValue('2600');
 await ticket.screenshot({path:info.outputPath('default-buy-quantity.png')});
 for(const [label,value] of [['全仓','2600'],['1/2仓','1300'],['1/3仓','800'],['1/4仓','600']]){await ticket.getByRole('button',{name:label,exact:true}).click();await expect(shares).toHaveValue(value);}
 await price.fill('3.00');await expect(capacity).toContainText('1,900 股');await expect(shares).toHaveValue('600');
 await accounts.selectOption('e2e-b');await price.fill('2.24');await expect(capacity).toContainText('400 股');await expect(shares).toHaveValue('400');
 await ticket.getByRole('button',{name:'卖出',exact:true}).click();await expect(capacity).toContainText('155 股');await expect(shares).toHaveValue('155');
 await ticket.getByRole('button',{name:'全仓',exact:true}).click();await expect(shares).toHaveValue('155');await expect(ticket.getByRole('button',{name:'1/2仓',exact:true})).toBeDisabled();
 await accounts.selectOption('e2e-a');await expect(capacity).toContainText('900 股');await ticket.getByRole('button',{name:'1/3仓',exact:true}).click();await expect(shares).toHaveValue('300');
 await ticket.screenshot({path:info.outputPath('capacity-and-fractions.png')});
 expect(await page.evaluate(()=> (window as any).capacityMethods.filter((m:string)=>['trading_sync','broker_submit'].includes(m)))).toEqual([]);
 const state=await rpc('e2e_state');expect(state.orders.zhangle).toEqual([]);expect(state.orders.ths).toEqual([]);
});

test('missing brokerage capacity stays unknown and explicit refresh uses only the selected account',async({page})=>{
 await setup(page);await page.evaluate(()=>{
  const w=window as any,original=w.testTradingRpc;w.capacitySyncs=[];w.capacityFresh=false;
  w.testTradingRpc=async(method:string,args:any)=>{if(method==='trading_sync'){w.capacitySyncs.push(args.account_id);w.capacityFresh=true;}const result=await original(method,args);return method==='trading_view'&&!w.capacityFresh?{...result,accounts:result.accounts.map((a:any)=>({...a,funds:{},sync_status:'never'})),positions:[]}:result;};
 });
 const ticket=await manualTicket(page);await ticket.getByLabel('真实委托券商账户').selectOption('e2e-b');
 await expect(ticket.getByLabel('可买卖数量',{exact:true})).toContainText('待同步');await expect(ticket.getByRole('button',{name:'全仓',exact:true})).toBeDisabled();
 await expect(ticket.getByLabel('真实委托股数')).toHaveValue('');
 await ticket.getByRole('button',{name:'同步可买卖数量'}).click();await expect(ticket.getByLabel('可买卖数量',{exact:true})).toContainText('股');await expect(ticket.getByRole('button',{name:'全仓',exact:true})).toBeEnabled();
 expect(await page.evaluate(()=> (window as any).capacitySyncs)).toEqual(['e2e-b']);expect((await rpc('e2e_state')).orders.ths).toEqual([]);
});

test('a submitted default quantity stays frozen when refreshed funds change after an unknown receipt',async({page})=>{
 await setup(page);await page.evaluate(()=>{
  const w=window as any,original=w.testTradingRpc;w.defaultCash='5973.01';
  w.testTradingRpc=async(method:string,args:any)=>{const result=await original(method,args);return method==='trading_view'?{...result,accounts:result.accounts.map((a:any)=>({...a,funds:{...a.funds,available:w.defaultCash}}))}:result;};
 });
 const ticket=await manualTicket(page);await ticket.getByLabel('真实委托券商账户').selectOption('e2e-a');await ticket.getByLabel('真实委托限价').fill('2.24');await expect(ticket.getByLabel('真实委托股数')).toHaveValue('2600');
 await rpc('e2e_fault',{broker:'zhangle',kind:'lose_receipt'});await ticket.getByRole('button',{name:'确认买入',exact:true}).click();await expect(ticket.getByRole('status')).toContainText('未收到明确回执');
 await page.evaluate(()=>{(window as any).defaultCash='1000';});await ticket.getByRole('switch',{name:'真实委托'}).click();await ticket.getByRole('switch',{name:'真实委托'}).click();
 await expect(ticket.getByLabel('可买卖数量',{exact:true})).toContainText('400 股');await expect(ticket.getByLabel('真实委托股数')).toHaveValue('2600');await expect(ticket.getByRole('button',{name:'确认买入',exact:true})).toBeDisabled();
 expect((await rpc('e2e_state')).orders.zhangle).toMatchObject([{quantity:2600}]);expect(await rpc('broker_requests',{id:'e2e-a'})).toHaveLength(1);
});

test('a complete empty holding shows zero sellable while an incomplete snapshot stays unknown',async({page})=>{
 await setup(page);await page.evaluate(()=>{
  const w=window as any,original=w.testTradingRpc;w.capacityComplete=true;
  w.testTradingRpc=async(method:string,args:any)=>{const result=await original(method,args);return method==='trading_view'?{...result,accounts:result.accounts.map((a:any)=>({...a,sync_status:w.capacityComplete?'complete':'partial'})),positions:result.positions.map((p:any)=>({...p,position_verified:false,sellable:0}))}:result;};
 });
 const ticket=await manualTicket(page);await ticket.getByLabel('真实委托券商账户').selectOption('e2e-a');await ticket.getByRole('button',{name:'卖出',exact:true}).click();
 await expect(ticket.getByLabel('可买卖数量',{exact:true})).toContainText('0 股');await expect(ticket.getByRole('button',{name:'全仓',exact:true})).toBeDisabled();
 await page.evaluate(()=>{(window as any).capacityComplete=false;});
 await ticket.getByRole('switch',{name:'真实委托'}).click();await ticket.getByRole('switch',{name:'真实委托'}).click();
 await expect(ticket.getByLabel('可买卖数量',{exact:true})).toContainText('待同步');await expect(ticket.getByRole('button',{name:'全仓',exact:true})).toBeDisabled();expect((await rpc('e2e_state')).orders.zhangle).toEqual([]);
});

test('manual real buy uses the selected account and existing gateway without a paper account or changing automatic rules',async({page},info)=>{
 await setup(page);await page.getByRole('button',{name:'暂停全部自动交易'}).click();
 const before=await rpc('trading_view');expect((await rpc('paper_snapshot')).accounts).toHaveLength(0);
 const ticket=await manualTicket(page);
 await expect(ticket.getByLabel('真实委托券商账户')).toHaveValue('');
 const submit=ticket.getByRole('button',{name:'确认买入'});await expect(submit).toBeDisabled();
 await ticket.getByLabel('真实委托券商账户').selectOption('e2e-a');
 await ticket.getByLabel('真实委托限价').fill('2.24');await ticket.getByLabel('真实委托股数').fill('2300');
 await expect(submit).toBeEnabled();await expect(ticket.getByRole('checkbox')).toHaveCount(0);
 await page.screenshot({path:info.outputPath('manual-real-buy.png')});await submit.click();
 await expect(ticket).toHaveCount(0);await expect(page.locator('.toast')).toContainText('待手动同步成交');
 const state=await rpc('e2e_state');expect(state.orders.zhangle).toMatchObject([{side:'buy',code:'000981',quantity:2300,price:'2.24'}]);expect(state.orders.ths).toEqual([]);
 const requests=await rpc('broker_requests',{id:'e2e-a'});expect(requests).toHaveLength(1);expect(requests[0].status).toBe('unknown');expect(requests[0].request_id).not.toMatch(/^auto_/);
 const plot=await markers(page);await expect.poll(plot.read).toMatchObject([{label:'B',source:'manual',status:'unknown',order_price:'2.24'}]);
 const after=await rpc('trading_view');expect(after.settings).toEqual(before.settings);expect(after.positions.map((p:any)=>p.rule)).toEqual(before.positions.map((p:any)=>p.rule));expect(after.runs).toEqual(before.runs);
 const paper=await rpc('paper_snapshot');expect(paper.accounts).toHaveLength(0);expect(paper.orders).toEqual([]);
 // A newly opened ticket always defaults to real; simulation remains selectable.
 const reopened=await manualTicket(page);await reopened.getByRole('switch',{name:'真实委托'}).click();await expect(reopened).toHaveAttribute('aria-label','模拟买卖确认');
});

test('manual real sell freezes its intent while sending and cannot submit twice',async({page})=>{
 await setup(page);const ticket=await manualTicket(page);
 await ticket.getByLabel('真实委托券商账户').selectOption('e2e-b');await ticket.getByRole('button',{name:'卖出',exact:true}).click();
 await ticket.getByLabel('真实委托限价').fill('2.24');await ticket.getByLabel('真实委托股数').fill('200');
 await ticket.getByLabel('真实委托限价').fill('2.25');await expect(ticket.getByRole('checkbox')).toHaveCount(0);
 await rpc('e2e_hold_native');
 const submit=ticket.getByRole('button',{name:'确认卖出'});await submit.evaluate((el:HTMLButtonElement)=>{el.click();el.click();});
 await expect(ticket.getByRole('button',{name:'提交中…'})).toBeDisabled();await expect(ticket.getByLabel('真实委托券商账户')).toBeDisabled();
 await expect(ticket.getByRole('switch',{name:'真实委托'})).toBeDisabled();await expect(ticket.getByRole('button',{name:'关闭真实委托'})).toBeDisabled();
 await rpc('e2e_release_native');await expect(ticket).toHaveCount(0);
 const state=await rpc('e2e_state');expect(state.orders.zhangle).toEqual([]);expect(state.orders.ths).toMatchObject([{side:'sell',quantity:200,price:'2.25'}]);
 expect(await rpc('broker_requests',{id:'e2e-b'})).toHaveLength(1);
 const plot=await markers(page);await expect.poll(plot.read).toMatchObject([{label:'S',source:'manual',order_price:'2.25'}]);
 // Existing bottom-signal automation remains functional after a manual order.
 const automatic=await rpc('e2e_feed',{kind:'bottom'});expect(automatic.orders.zhangle).toHaveLength(1);expect(automatic.orders.ths).toHaveLength(2);
 expect(automatic.runs.map((r:any)=>r.status)).toEqual(['accepted','accepted']);
});

test('manual order closes and shows B without reading the receipt, then manual sync corrects its position',async({page})=>{
 await setup(page);await page.getByRole('button',{name:'暂停全部自动交易'}).click();
 await page.clock.install({time:new Date('2026-11-04T09:55:00+08:00')});
 await rpc('e2e_fault',{broker:'ths',kind:'lose_receipt'});const ticket=await manualTicket(page);
 await ticket.getByLabel('真实委托券商账户').selectOption('e2e-b');await ticket.getByLabel('真实委托限价').fill('2.24');await ticket.getByLabel('真实委托股数').fill('100');
 await ticket.getByRole('button',{name:'确认买入'}).click();await expect(ticket).toHaveCount(0);
 const plot=await markers(page);await expect.poll(plot.read).toMatchObject([{label:'B',source:'manual',status:'unknown',order_price:'2.24'}]);
 expect((await rpc('e2e_state')).orders.ths).toHaveLength(1);
 await rpc('e2e_manual_fill',{broker:'ths',price:'2.23'});await rpc('e2e_repeat');
 await page.getByRole('button',{name:'同步券商成交',exact:true}).click();
 await expect.poll(plot.read).toMatchObject([{label:'B',source:'broker_cache',fill_price:2.23,ordered_at:'2026-11-04T09:56:00+08:00'}]);
 expect((await rpc('e2e_state')).orders.ths).toHaveLength(1);
});

test('manual real order verifies the chosen brokerage account before native submission',async({page})=>{
 await setup(page);await rpc('e2e_fault',{broker:'zhangle',kind:'wrong_account'});const ticket=await manualTicket(page);
 await ticket.getByLabel('真实委托券商账户').selectOption('e2e-a');await ticket.getByLabel('真实委托限价').fill('2.24');await ticket.getByLabel('真实委托股数').fill('100');
 await ticket.getByRole('button',{name:'确认买入'}).click();
 await expect(ticket.getByRole('status')).toContainText('提交前已停止');await expect(ticket.getByRole('status')).toContainText('账号不一致');
 expect((await rpc('e2e_state')).orders.zhangle).toEqual([]);expect((await rpc('broker_requests',{id:'e2e-a'}))[0].status).toBe('failed');
 await expect(ticket.getByRole('checkbox')).toHaveCount(0);
});

test('manual real order with an interrupted IPC response keeps the same intent and cannot be resent',async({page})=>{
 await setup(page);const ticket=await manualTicket(page);
 await ticket.getByLabel('真实委托券商账户').selectOption('e2e-a');await ticket.getByLabel('真实委托限价').fill('2.24');await ticket.getByLabel('真实委托股数').fill('100');
 await page.evaluate(()=>{
  const w=window as any,original=w.testTradingRpc;let lost=false;
  w.testTradingRpc=(method:string,args:any)=>{if(method==='job'&&!lost){lost=true;return Promise.reject(Error('隔离测试：IPC 回执中断'));}return original(method,args);};
 });
 await ticket.getByRole('button',{name:'确认买入'}).click();
 await expect(ticket.getByRole('alert')).toContainText('结果待核实');await expect(ticket.getByRole('button',{name:'确认买入'})).toBeDisabled();
 await expect.poll(async()=> (await rpc('broker_requests',{id:'e2e-a'}))[0]?.status).toBe('unknown');
 expect((await rpc('e2e_state')).orders.zhangle).toHaveLength(1);expect(await rpc('broker_requests',{id:'e2e-a'})).toHaveLength(1);
 await expect(ticket).toBeVisible();
});

test('mode switching preserves the unknown real intent and cannot unlock another submission',async({page})=>{
 await setup(page);const ticket=await manualTicket(page);
 await ticket.getByLabel('真实委托券商账户').selectOption('e2e-a');await ticket.getByLabel('真实委托限价').fill('2.24');await ticket.getByLabel('真实委托股数').fill('100');
 await page.evaluate(()=>{const w=window as any,original=w.testTradingRpc;let lost=false;w.testTradingRpc=(method:string,args:any)=>method==='job'&&!lost?(lost=true,Promise.reject(Error('IPC 回执中断'))):original(method,args);});
 await ticket.getByRole('button',{name:'确认买入'}).click();
 await expect(ticket.getByRole('alert')).toContainText('结果待核实');
 const original=await rpc('broker_requests',{id:'e2e-a'});
 await ticket.getByRole('switch',{name:'真实委托'}).click();
 await expect(ticket.getByRole('button',{name:'买入',exact:true})).toHaveAttribute('aria-pressed','true');
 await ticket.getByRole('button',{name:'卖出',exact:true}).click();
 await ticket.getByRole('switch',{name:'真实委托'}).click();
 await expect(ticket.getByRole('alert')).toContainText('结果待核实');
 await expect(ticket.getByLabel('真实委托券商账户')).toHaveValue('e2e-a');
 await expect(ticket.getByRole('button',{name:'确认买入'})).toBeDisabled();
 expect(await rpc('broker_requests',{id:'e2e-a'})).toEqual(original);expect((await rpc('e2e_state')).orders.zhangle).toHaveLength(1);
});

test('mode switching keeps simulation and real drafts separate without sending either order',async({page})=>{
 await setup(page);const ticket=await manualTicket(page);
 await ticket.getByRole('switch',{name:'真实委托'}).click();
 await ticket.getByLabel('模拟委托限价').fill('2.20');await ticket.getByLabel('模拟交易股数').fill('300');
 await ticket.getByRole('switch',{name:'真实委托'}).click();
 await ticket.getByLabel('真实委托券商账户').selectOption('e2e-b');await ticket.getByRole('button',{name:'卖出',exact:true}).click();
 await ticket.getByLabel('真实委托限价').fill('2.25');await ticket.getByLabel('真实委托股数').fill('200');
 await ticket.getByRole('switch',{name:'真实委托'}).click();
 await expect(ticket.getByRole('button',{name:'买入',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(ticket.getByLabel('模拟委托限价')).toHaveValue('2.20');await expect(ticket.getByLabel('模拟交易股数')).toHaveValue('300');
 await ticket.getByRole('switch',{name:'真实委托'}).click();
 await expect(ticket.getByLabel('真实委托券商账户')).toHaveValue('e2e-b');await expect(ticket.getByRole('button',{name:'卖出',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(ticket.getByLabel('真实委托限价')).toHaveValue('2.25');await expect(ticket.getByLabel('真实委托股数')).toHaveValue('200');
 expect(await rpc('broker_requests',{id:'e2e-a'})).toEqual([]);expect(await rpc('broker_requests',{id:'e2e-b'})).toEqual([]);expect((await rpc('paper_snapshot')).orders).toEqual([]);
});

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
