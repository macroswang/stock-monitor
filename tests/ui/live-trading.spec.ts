import {test,expect,Page} from '@playwright/test';
import {spawn,ChildProcessWithoutNullStreams} from 'node:child_process';
import {createInterface} from 'node:readline';
import {plannedQuantity,type QuantityRule} from '../../src/tradingQuantity';
import {amount,sizingEstimate} from '../../src/tradingSizing';

let backend:ChildProcessWithoutNullStreams;
let pending:Array<{resolve:(value:unknown)=>void;reject:(error:Error)=>void}>=[];
async function setup(page:Page,panel:'trading'|'market'='trading'){
 backend=spawn('.venv/bin/python',['-u','tests/trading_ui_backend.py'],{cwd:process.cwd()});
 pending=[];
 createInterface({input:backend.stdout}).on('line',line=>{const next=pending.shift();if(!next)return;const data=JSON.parse(line);data.error?next.reject(Error(data.error)):next.resolve(data.result);});
 backend.stderr.on('data',data=>process.stderr.write(data));
 await page.exposeFunction('testTradingRpc',(method:string,args:Record<string,unknown>)=>new Promise((resolve,reject)=>{pending.push({resolve,reject});backend.stdin.write(JSON.stringify({method,args})+'\n');}));
 await page.addInitScript(()=>{
  const w=window as unknown as {testTradingRpc:(method:string,args:unknown)=>Promise<unknown>;__TAURI_INTERNALS__:unknown;__TAURI_EVENT_PLUGIN_INTERNALS__:unknown;isTauri:boolean};
  let id=0;
  w.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>++id,unregisterCallback:()=>{},invoke:(command:string,args:Record<string,unknown>)=>command==='rpc'?w.testTradingRpc(args.method as string,args.args):Promise.resolve(command==='plugin:autostart|is_enabled'?false:0)};
  w.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
  w.isTauri=true;
 });
 await page.goto('/?panel='+panel);
 if(panel==='trading'){
  await expect(page.getByRole('heading',{name:'自动交易股票'})).toBeVisible();
  await expect(page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'})).toBeVisible();
 }else await expect(page.getByRole('heading',{name:'我的自选',exact:true})).toBeVisible();
}
test.afterEach(()=>{backend?.stdin.end();backend?.kill();for(const p of pending)p.reject(Error('Test ended'));pending=[];});

test('fixed lots and position percentages respect minimums and actual sellable shares',()=>{
 const rule:QuantityRule={buy_mode:'position',sell_mode:'position',buy_lots:1,sell_lots:1,buy_percent:50,sell_percent:25};
 expect(plannedQuantity('sz000981',1200,900,'buy',rule)).toBe(600);
 expect(plannedQuantity('sz000981',1200,900,'sell',rule)).toBe(300);
 expect(plannedQuantity('sz000981',1200,200,'sell',{...rule,sell_percent:50})).toBe(200);
 expect(plannedQuantity('sz000981',199,199,'sell',{...rule,sell_percent:100})).toBe(199);
 expect(plannedQuantity('sh688001',499,499,'buy',rule)).toBe(249);
 expect(plannedQuantity('sz000981',300,300,'buy',{...rule,buy_mode:'lots'})).toBe(100);
 expect(plannedQuantity('sz000981',1000000,1000000,'buy',{...rule,buy_percent:50.01})).toBe(500100);
 expect(plannedQuantity('sz000981',300,300,'buy',{...rule,buy_percent:33.33})).toBe(0);
 expect(plannedQuantity('sz000981',200,200,'sell',{...rule,sell_mode:'lots'})).toBe(100);
});

test('same stock in different accounts keeps switches, ratios and drafts separate',async({page})=>{
 await setup(page);
 const buyA=page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'}),buyB=page.getByRole('checkbox',{name:'987***002 山子高科 自动买入'});
 await buyA.check();await expect(buyA).toBeChecked();await expect(buyB).not.toBeChecked();
 const accountA=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 await accountA.getByRole('button',{name:'配置规则'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog).toContainText('123***001');await expect(dialog).not.toContainText('987***002');
 await expect(dialog.getByLabel('单笔金额上限（元）',{exact:true})).toHaveCount(0);
 await expect(dialog.getByLabel('该股每日买入上限（元）',{exact:true})).toHaveCount(0);
 await dialog.getByLabel('买入数量方式').selectOption('position');
 await dialog.getByLabel('买入持仓比例（%）').fill('25');
 await dialog.getByRole('button',{name:'保存规则'}).click();await expect(dialog).not.toBeVisible();
 await expect(accountA).toContainText('当前持仓的 25%');
 const accountB=page.getByRole('region',{name:/同花顺（银河证券） · 987/});
 await expect(accountB).toContainText('每次 1 手');
 await accountA.getByRole('button',{name:'试算买入'}).click();
 await expect(page.getByRole('status')).toContainText('300股');await expect(page.getByRole('status')).toContainText('123***001');
 await page.getByRole('button',{name:'启动试运行',exact:true}).click();
 await expect(page.getByText('自动执行运行中',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'暂停全部自动交易'}).click();
 await expect(page.getByText('自动执行已暂停',{exact:true})).toBeVisible();
});

test('a watchlist-only stock can be assigned to one account without inventing a holding',async({page})=>{
 await setup(page);
 await page.getByRole('combobox',{name:'管理证券账户'}).selectOption('test-a');
 await page.getByRole('button',{name:'添加自选股'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByLabel('选择自选股证券账户')).toHaveValue('test-a');
 await dialog.getByLabel('选择自动交易自选股').selectOption('sh603938');
 await dialog.getByRole('button',{name:'添加',exact:true}).click();
 await expect(dialog).not.toBeVisible();
 const accountA=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 const row=accountA.getByRole('row').filter({hasText:'三孚股份'});
 await expect(row).toContainText('自选股配置');await expect(row).toContainText('待持仓同步');
 await row.getByRole('checkbox',{name:'123***001 三孚股份 自动买入'}).check();
 await row.getByRole('button',{name:'试算买入'}).click();
 await expect(page.getByRole('status')).toContainText('三孚股份');await expect(page.getByRole('status')).toContainText('100股');
 await page.getByRole('combobox',{name:'管理证券账户'}).selectOption('test-b');
 await expect(page.getByRole('region',{name:/同花顺（银河证券） · 987/}).getByRole('button',{name:'三孚股份',exact:true})).toHaveCount(0);
});

test('watchlist sources and automatic order entries are exclusive in the same left-hand position',async({page})=>{
 await setup(page,'market');
 const state=()=>page.evaluate(()=> (window as any).testTradingRpc('trading_view',{}));
 const before=await state();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 const stocks=page.locator('.stocks .stock');
 const synced=page.locator('.stocks').getByRole('button',{name:/账户同步来源$/});
 await expect(synced).toHaveCount(1);
 await expect(page.locator('.stocks').getByRole('button',{name:/ 自动下单$/})).toHaveCount((await stocks.count())-1);
 for(const stock of await stocks.all()){
  await expect(stock.locator('button.trading-source')).toHaveCount(1);
  await expect(stock.locator('.stock-right button')).toHaveCount(0);
  await expect(stock.locator('div').first().locator('button.trading-source')).toHaveCount(1);
 }
 await expect(page.getByRole('button',{name:'山子高科 自动下单',exact:true})).toHaveCount(0);
 await page.setViewportSize({width:1280,height:800});
 await page.screenshot({path:'outputs/watchlist-auto-order-entry.png'});
 await page.getByRole('button',{name:'三孚股份 自动下单',exact:true}).click();
 let dialog=page.getByRole('dialog');
 await expect(dialog).toContainText('三孚股份 · SH603938');
 await expect(dialog.getByLabel('选择自选股证券账户')).toHaveValue('');
 await expect(dialog.getByRole('button',{name:'配置规则',exact:true})).toBeDisabled();
 await dialog.getByLabel('选择自选股证券账户').selectOption('test-b');
 await page.screenshot({path:'outputs/watchlist-auto-order-account.png'});
 await dialog.getByRole('button',{name:'配置规则',exact:true}).click();
 dialog=page.getByRole('dialog');
 await expect(dialog).toContainText('三孚股份 · 自动交易');await expect(dialog).toContainText('987***002');
 await expect(dialog).toContainText('待持仓同步');
 await expect(dialog.getByLabel('自动买入',{exact:true})).not.toBeChecked();
 await expect(dialog.getByLabel('交易方式')).toHaveValue('independent');
 await dialog.getByLabel('自动买入',{exact:true}).check();
 await dialog.getByLabel('每次买入手数（手）').fill('2');
 await page.screenshot({path:'outputs/watchlist-auto-order-rule.png'});
 await dialog.getByRole('button',{name:'保存规则'}).click();await expect(dialog).not.toBeVisible();
 const after=await state(),target=after.positions.find((p:any)=>p.account_id==='test-b'&&p.code==='sh603938');
 expect(target.rule.buy_enabled).toBe(true);expect(target.rule.buy_lots).toBe(2);expect(target.position_verified).toBe(false);
 expect(after.positions.some((p:any)=>p.account_id==='test-a'&&p.code==='sh603938')).toBe(false);
 expect(after.settings).toEqual(before.settings);expect(after.runs).toEqual(before.runs);
 await expect(page.getByRole('combobox',{name:'管理证券账户'})).toHaveValue('test-b');
});

test('synced watchlist stocks retain their original management route and running rules',async({page})=>{
 await setup(page);
 const state=()=>page.evaluate(()=> (window as any).testTradingRpc('trading_view',{}));
 await page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'}).check();
 await page.getByRole('region',{name:/华泰涨乐通 · 123/}).getByRole('button',{name:'配置规则'}).click();
 await page.getByRole('dialog').getByLabel('每次买入手数（手）').fill('7');
 await page.getByRole('dialog').getByRole('button',{name:'保存规则'}).click();
 await page.getByRole('button',{name:'启动试运行',exact:true}).click();
 await expect(page.getByText('自动执行运行中',{exact:true})).toBeVisible();
 const before=await state();
 for(const accountId of ['test-a','test-b']){
  await page.getByRole('button',{name:'自选监控',exact:true}).click();
  await expect(page.getByRole('button',{name:'山子高科 自动下单',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'山子高科 账户同步来源',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('combobox',{name:'管理证券账户'}).selectOption(accountId);
  await page.getByRole('region',{name:accountId==='test-a'?/华泰涨乐通 · 123/:/同花顺（银河证券） · 987/}).getByRole('button',{name:'配置规则'}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByLabel('每次买入手数（手）')).toHaveValue(accountId==='test-a'?'7':'1');
  if(accountId==='test-a')await expect(dialog.getByLabel('自动买入',{exact:true})).toBeChecked();
  else await expect(dialog.getByLabel('自动买入',{exact:true})).not.toBeChecked();
  await dialog.getByRole('button',{name:'取消',exact:true}).click();
 }
 const after=await state();expect(after.settings).toEqual(before.settings);
 expect(after.positions).toEqual(before.positions);expect(after.runs).toEqual(before.runs);
 await expect(page.getByText('自动执行运行中',{exact:true})).toBeVisible();
});

test('cancelling watchlist setup never enables a rule or starts execution',async({page})=>{
 await setup(page);
 const state=()=>page.evaluate(()=> (window as any).testTradingRpc('trading_view',{}));
 const before=await state();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await page.getByRole('button',{name:'三孚股份 自动下单',exact:true}).click();
 await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
 expect((await state()).positions).toEqual(before.positions);
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await page.getByRole('button',{name:'三孚股份 自动下单',exact:true}).click();
 await page.getByRole('dialog').getByLabel('选择自选股证券账户').selectOption('test-a');
 await page.getByRole('dialog').getByRole('button',{name:'配置规则',exact:true}).click();
 await expect(page.getByRole('dialog')).toContainText('三孚股份 · 自动交易');
 await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
 const after=await state(),target=after.positions.find((p:any)=>p.account_id==='test-a'&&p.code==='sh603938');
 expect(target.rule.buy_enabled).toBe(false);expect(target.rule.sell_enabled).toBe(false);expect(target.rule.paired_enabled).toBe(false);
 expect(after.settings).toEqual(before.settings);expect(after.runs).toEqual(before.runs);
});

test('watchlist setup without a bound account leads to the existing securities account page',async({page})=>{
 await setup(page);
 await page.evaluate(async()=>{for(const id of ['test-a','test-b'])await (window as any).testTradingRpc('broker_account_delete',{id});});
 await page.getByRole('button',{name:'刷新',exact:true}).click();
 await expect(page.getByText('先连接你的证券账户',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await page.getByRole('button',{name:'三孚股份 自动下单',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog).toContainText('请先');
 await expect(dialog.getByRole('button',{name:'配置规则',exact:true})).toBeDisabled();
 await dialog.getByRole('button',{name:'添加证券账户',exact:true}).click();
 await expect(dialog).not.toBeVisible();
 await expect(page.getByRole('tab',{name:'证券账户',exact:true})).toHaveAttribute('aria-selected','true');
});

test('code confirmation is account-scoped and wrong code never creates association',async({page})=>{
 await setup(page);
 await page.getByRole('button',{name:'确认代码',exact:true}).click();
 const dialog=page.getByRole('dialog');await expect(dialog).toContainText('987***002');
 await dialog.getByLabel('持仓股票代码').fill('000981');
 await dialog.getByRole('button',{name:'核对并关联'}).click();
 await expect(dialog.getByRole('alert')).toContainText('不一致');
 await dialog.getByLabel('持仓股票代码').fill('603002');
 await dialog.getByRole('button',{name:'核对并关联'}).click();
 await expect(dialog).not.toBeVisible();
 const accountB=page.getByRole('region',{name:/同花顺（银河证券） · 987/});
 await expect(accountB.getByRole('button',{name:'宏昌电子',exact:true})).toBeVisible();
 const accountA=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 await expect(accountA.getByRole('button',{name:'宏昌电子',exact:true})).toHaveCount(0);
 await page.getByRole('combobox',{name:'管理证券账户'}).selectOption('test-b');
 await page.getByRole('button',{name:'同步当前账户'}).click();
 await expect(page.getByRole('status')).toContainText('同步完成');
 await expect(page.getByRole('button',{name:'宏昌电子',exact:true})).toBeVisible();
});

test('holdings provenance leads from watchlist to management; dialogs fit compact screens',async({page})=>{
 await setup(page);
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await expect(page.getByRole('button',{name:'山子高科 账户同步来源'})).toContainText('2账户');
 await page.getByRole('button',{name:'山子高科 账户同步来源'}).click();
 await expect(page.getByRole('heading',{name:'自动交易股票'})).toBeVisible();
 await page.setViewportSize({width:1100,height:800});
 await page.getByRole('region',{name:/华泰涨乐通 · 123/}).getByRole('button',{name:'配置规则'}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
 const box=await page.getByRole('dialog').boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(1100);
 const save=await page.getByRole('dialog').getByRole('button',{name:'保存规则'}).boundingBox();
 expect(save!.y).toBeGreaterThanOrEqual(0);expect(save!.y+save!.height).toBeLessThanOrEqual(800);
 await page.screenshot({path:'outputs/live-trading-rule-dialog.png',fullPage:false});
 await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
 await page.setViewportSize({width:1440,height:1050});
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:'outputs/live-trading-management.png',fullPage:true});
});

test('broker report refresh settles only its bound account and distinguishes automatic evidence',async({page})=>{
 await setup(page);
 await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc('test_seed_reports',{}));
 await page.getByRole('tab',{name:'执行记录',exact:true}).click();
 await page.getByRole('button',{name:'刷新',exact:true}).click();
 const a=page.getByRole('row').filter({hasText:'123***001'}),b=page.getByRole('row').filter({hasText:'987***002'});
 await a.getByRole('button',{name:'刷新券商回报',exact:true}).click();
 await expect(a).toContainText('券商回报自动核实');await expect(a).toContainText('fixture-test-a');await expect(a).toContainText('已成交 100 股');
 await expect(b).toContainText('已受理');await expect(b).not.toContainText('券商回报自动核实');
 await page.screenshot({path:'outputs/trading-order-reconciliation.png',fullPage:true});
 await expect(page.getByText('自动执行已暂停',{exact:true})).toBeVisible();
});

test('execution records expose receipts without manual verification tasks or missing-number prompts',async({page})=>{
 await setup(page);
 await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc('test_seed_unknown',{}));
 await page.getByRole('tab',{name:'执行记录',exact:true}).click();await page.getByRole('button',{name:'刷新',exact:true}).click();
 const b=page.getByRole('row').filter({hasText:'987***002'});
 await expect(b).toContainText('未收到明确回执');await expect(b).toContainText('不影响后续新信号');
 await expect(b.getByRole('button',{name:'补充编号并核实'})).toHaveCount(0);
 await expect(b.getByRole('button',{name:'核实结果',exact:true})).toHaveCount(0);
 await expect(b.getByRole('button',{name:'刷新券商回报'})).toHaveCount(0);
 await expect(page.getByText('待核实',{exact:false})).toHaveCount(0);
});

test('automation follows the labelled chart top/bottom signals rather than Q1 filtering',async({page})=>{
 await setup(page);
 await expect(page.getByText('信号源：图中已确认的顶／底',{exact:false})).toBeVisible();
 await page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'}).check();
 await page.getByRole('button',{name:'启动试运行',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('底买、顶卖');
 await expect(page.getByRole('status')).toContainText('不补下历史信号');
 await expect(page.getByRole('status')).not.toContainText('Q1');
});


test('fixed-hand drafts persist without money limits and changing mode shows the matching quantity',async({page})=>{
 await setup(page);
 const a=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 await a.getByRole('button',{name:'配置规则'}).click();let dialog=page.getByRole('dialog');
 await expect(a).not.toContainText('每日最多');
 await expect(dialog.getByLabel('最大不利价格偏离（%）')).toHaveCount(0);
 await expect(dialog).not.toContainText('含预留');
 await dialog.getByLabel('每次买入手数（手）').fill('20');
 await expect(dialog.getByRole('region',{name:'买入结果试算'})).toContainText('每次买入 2,000 股');
 await expect(dialog.getByLabel('该股每日最多执行次数')).not.toBeVisible();
 await dialog.getByRole('button',{name:'保存规则'}).click();await expect(dialog).not.toBeVisible();
 await a.getByRole('button',{name:'试算买入'}).click();await expect(page.getByRole('status')).toContainText('2000股');
 await a.getByRole('button',{name:'配置规则'}).click();dialog=page.getByRole('dialog');
 await expect(dialog.getByLabel('每次买入手数（手）')).toHaveValue('20');
 await dialog.getByLabel('卖出数量方式').selectOption('position');
 await dialog.getByLabel('卖出持仓比例（%）').fill('50');
 await expect(dialog.getByRole('region',{name:'卖出结果试算'})).toContainText('每次卖出 600 股');
 await page.screenshot({path:'outputs/simple-quantity-rule-dialog.png',fullPage:false});
 await dialog.getByRole('button',{name:'保存规则'}).click();
 await expect(a).toContainText('当前持仓的 50%');
});

test('paired T rule exposes one shared lot size and a fee-aware net-profit gate',async({page})=>{
 await setup(page);
 const a=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 await a.getByRole('button',{name:'配置规则'}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByLabel('交易方式').selectOption('paired_t');
 await dialog.getByLabel('启用成对T').check();
 await dialog.getByLabel('成对T每轮手数（手）').fill('23');
 await dialog.getByLabel('最低净收益（元）').fill('20');
 await dialog.getByText('手续费与滑点参数').click();
 await dialog.getByLabel('佣金（万分）').fill('2');
 await dialog.getByLabel('单边最低佣金（元）').fill('5');
 await expect(dialog).toContainText('一轮完成后可继续下一轮，不限制每日轮次');
 await page.screenshot({path:'outputs/paired-t-rule-dialog.png',fullPage:false});
 await dialog.getByRole('button',{name:'保存规则'}).click();
 await expect(a.getByRole('checkbox',{name:'123***001 山子高科 成对T'})).toBeChecked();
 await expect(a).toContainText('每轮 23 手');
 await expect(a).toContainText('净收益至少 20 元');
 await expect(a).toContainText('不会独立买入');
});

test('paired cycle can be disabled and manually closed with an explicit settlement note',async({page})=>{
 await setup(page);
 await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc('test_seed_paired_review',{}));
 await page.getByRole('button',{name:'刷新',exact:true}).click();
 const a=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 await a.getByRole('checkbox',{name:'123***001 山子高科 成对T'}).uncheck();
 await expect(a.getByRole('checkbox',{name:'123***001 山子高科 成对T'})).not.toBeChecked();
 const cycle=page.getByRole('region',{name:'sz000981 成对T周期'});
 await expect(cycle).toContainText('历史回报读取失败');
 await cycle.getByText('人工结案',{exact:true}).click();
 const close=cycle.getByRole('button',{name:'确认结案'});await expect(close).toBeDisabled();
 await cycle.getByLabel('sz000981 结案依据').fill('已在券商核对并处理剩余仓位');
 await cycle.getByRole('checkbox').check();await close.click();
 await expect(cycle).toHaveCount(0);
 await expect(page.getByRole('status')).toContainText('已记录人工结案');
});

test('missing execution average is enriched through the existing verification API',async({page})=>{
 await setup(page);
 await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc('test_seed_paired_missing_average',{}));
 await page.getByRole('button',{name:'刷新',exact:true}).click();
 const cycle=page.getByRole('region',{name:'sz000981 成对T周期'});
 await expect(cycle).toContainText('需人工处理');
 await cycle.getByText('首腿卖出 · 人工核实',{exact:true}).click();
 await expect(cycle.getByLabel('券商委托号',{exact:true})).toBeDisabled();
 await expect(cycle.getByLabel('累计成交股数',{exact:true})).toBeDisabled();
 await cycle.getByLabel('成交均价',{exact:true}).fill('2.14');
 await cycle.getByLabel('核实依据',{exact:true}).fill('已核对券商成交明细均价');
 await cycle.getByRole('checkbox',{name:'已在券商逐项核对本笔委托和成交明细'}).check();
 await cycle.getByRole('button',{name:'保存核实结果'}).click();
 await expect(cycle).toContainText('等待回补');
 await expect(cycle.getByText('首腿卖出 · 人工核实',{exact:true})).toHaveCount(0);
});

test('sizing explains the screenshot rounding, cash needs and position impact',()=>{
 const rule:QuantityRule={buy_mode:'lots',sell_mode:'position',buy_lots:1,sell_lots:1,buy_percent:50,sell_percent:50};
 const buy=sizingEstimate('sh603938',300,300,'buy',rule,29.36,'13,361.69','22,170.69');
 expect(buy.quantity).toBe(100);expect(buy.value).toBeCloseTo(2936);
 expect(buy.required).toBeCloseTo(2936);expect(buy.cashAfter).toBeCloseTo(10425.69);
 expect(buy.maxBuyQuantity).toBe(400);expect(buy.positionAfter).toBe(400);
 const sell=sizingEstimate('sh603938',300,300,'sell',rule,29.36,'13,361.69','22,170.69');
 expect(sell.requested).toBe(150);expect(sell.quantity).toBe(100);
 expect(sell.effectivePercent).toBeCloseTo(100/3);expect(sell.positionAfter).toBe(200);
 expect(sell.cashAfter).toBeCloseTo(16297.69);
 const capped=sizingEstimate('sh603938',300,50,'sell',{...rule,sell_percent:100},29.36,'13361.69',undefined);
 expect(capped.quantity).toBe(50);expect(capped.positionAfter).toBe(250);
 const tooMany=sizingEstimate('sh603938',300,300,'sell',{...rule,sell_mode:'lots',sell_lots:4},29.36,0,0);
 expect(tooMany.quantity).toBe(0);expect(tooMany.blockedReason).toContain('超过可卖');
 expect(sizingEstimate('sh603938',300,300,'buy',rule,29.36,'2,935',undefined).blockedReason).toContain('资金不足');
 for(const missing of [undefined,null,'','--','not-a-number']){
  expect(amount(missing)).toBeNull();
  const s=sizingEstimate('sh603938',300,300,'buy',rule,29.36,missing,undefined);
  expect(s.cashAfter).toBeNull();expect(s.maxBuyQuantity).toBeNull();expect(s.blockedReason).toContain('尚未读到');
 }
 expect(sizingEstimate('sh603938',300,300,'buy',rule,29.36,'0',undefined).maxBuyQuantity).toBe(0);
 expect(sizingEstimate('sh603938',300,300,'buy',rule,undefined,'10000',undefined).value).toBeNull();
 const small=sizingEstimate('sh603938',300,300,'sell',{...rule,sell_percent:25},29.36,0,0);
 expect(small.quantity).toBe(0);expect(small.blockedReason).toContain('最低 100 股');
 expect(sizingEstimate('sh688001',499,499,'buy',{...rule,buy_mode:'position'},10,'1,800',undefined).maxBuyQuantity).toBe(0);
 expect(sizingEstimate('sh688001',499,499,'buy',{...rule,buy_mode:'position'},10,'2,502.47',undefined).maxBuyQuantity).toBe(250);
 for(const price of [1.01,2.13,5.02,10.3,20.59,29.36]){
  const cash=Math.ceil((price*700)*100)/100;
  const maximum=sizingEstimate('sh603938',300,300,'buy',rule,price,cash,undefined).maxBuyQuantity!;
  expect(maximum).toBe(700);
  const maxPlan=sizingEstimate('sh603938',300,300,'buy',{...rule,buy_lots:maximum/100},price,cash,undefined);
  expect(maxPlan.required!).toBeLessThanOrEqual(cash);
  expect(sizingEstimate('sh603938',300,300,'buy',{...rule,buy_lots:maximum/100+1},price,cash,undefined).blockedReason).toContain('资金不足');
 }
});

test('draft sizing updates instantly, compares quantities and uses only the selected account cash',async({page})=>{
 await setup(page);
 const a=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 const b=page.getByRole('region',{name:/同花顺（银河证券） · 987/});
 await expect(a).toContainText('25,000');await expect(b).toContainText('1,000');
 await a.getByRole('button',{name:'配置规则'}).click();
 let dialog=page.getByRole('dialog');
 const sell=dialog.getByRole('region',{name:'卖出结果试算'});
 await dialog.getByLabel('卖出数量方式').selectOption('position');
 await dialog.getByLabel('卖出持仓比例（%）').fill('12.5');
 await expect(sell).toContainText('1,200 股 × 12.5% = 150 股');
 await expect(sell).toContainText('向下取整为 100 股');
 await expect(sell).toContainText('8.33%');await expect(sell).toContainText('1,200 → 1,100 股');
 await dialog.getByLabel('买入数量快捷比较').getByRole('button',{name:'50%',exact:true}).click();
 const buy=dialog.getByRole('region',{name:'买入结果试算'});
 await expect(buy).toContainText('每次买入 600 股');await expect(buy).toContainText('1,278 元');
 await expect(buy).not.toContainText('资金不足');
 await page.setViewportSize({width:1440,height:1100});
 await page.screenshot({path:'outputs/sizing-impact-rule-dialog.png',fullPage:false});
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 await b.getByRole('button',{name:'配置规则'}).click();dialog=page.getByRole('dialog');
 await dialog.getByLabel('每次买入手数（手）').fill('5');
 await expect(dialog.getByRole('region',{name:'买入结果试算'})).toContainText('该数量资金不足');
 await expect(dialog.getByRole('region',{name:'买入结果试算'})).toContainText('最多可买 4 手');
 await expect(dialog).not.toContainText('25,000');
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 // Comparing and cancelling drafts never persists new quantities or toggles.
 await b.getByRole('button',{name:'配置规则'}).click();
 await expect(page.getByRole('dialog').getByLabel('每次买入手数（手）')).toHaveValue('1');
});

test('one execution button switches state and feedback dismisses within five seconds without polling revival',async({page})=>{
 await page.clock.install();await setup(page);
 const toggle=page.getByRole('button',{name:/^(启动试运行|启动实盘执行|暂停全部自动交易)$/});
 await expect(toggle).toHaveCount(1);
 await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc('test_seed_notice',{}));
 await page.getByRole('button',{name:'刷新',exact:true}).click();
 const migration=page.getByText('测试：原买卖开关已保留，自动执行已暂停。',{exact:true});
 await expect(migration).toBeVisible();
 await page.clock.fastForward(4900);await expect(migration).toBeVisible();
 await page.clock.fastForward(150);await expect(migration).toHaveCount(0);
 await page.clock.fastForward(6000);await expect(migration).toHaveCount(0);
 await page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'}).check();
 const info=page.getByRole('status').filter({hasText:'自动买入已开启'});await expect(info).toBeVisible();
 await page.clock.fastForward(5050);await expect(info).toHaveCount(0);
 await expect(toggle).toHaveText('启动试运行');await toggle.click();
 await expect(toggle).toHaveText('暂停全部自动交易');await expect(toggle).toHaveAttribute('aria-pressed','true');
 await toggle.click();await expect(toggle).toHaveText('启动试运行');await expect(toggle).toHaveAttribute('aria-pressed','false');
});

test('compact rules fit a 1280 by 800 window and navigation uses consistent SVG icons',async({page})=>{
 await setup(page);await page.setViewportSize({width:1280,height:800});
 for(const name of ['自选监控','大盘广度','市场机会','股票池','自动交易','模拟交易','数据管理','设置与通知']){
  await expect(page.getByRole('button',{name,exact:true}).locator('svg')).toHaveCount(1);
 }
 await page.getByRole('region',{name:/华泰涨乐通 · 123/}).getByRole('button',{name:'配置规则'}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByLabel('卖出数量方式').selectOption('position');
 await dialog.getByLabel('卖出持仓比例（%）').fill('12.5');
 await expect(dialog.getByText('每次卖出 100 股',{exact:true})).toBeVisible();
 const size=await dialog.evaluate(el=>({scroll:el.scrollHeight,client:el.clientHeight}));
 expect(size.scroll).toBeLessThanOrEqual(size.client+1);
 const save=await dialog.getByRole('button',{name:'保存规则'}).boundingBox();expect(save!.y+save!.height).toBeLessThan(800);
 await page.screenshot({path:'outputs/compact-rule-1280x800.png',fullPage:false});
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 await page.screenshot({path:'outputs/compact-trading-1280x800.png',fullPage:false});
});

test('account page shows clean cards and adds accounts through a labelled modal',async({page})=>{
 await setup(page);await page.getByRole('tab',{name:'证券账户',exact:true}).click();
 const panel=page.getByRole('region',{name:'证券账户管理'});
 await expect(panel.locator('.broker-account-card')).toHaveCount(2);
 await expect(panel.getByText('文件权限 600',{exact:false})).toHaveCount(0);
 await expect(panel.getByRole('button',{name:'测试登录'})).toHaveCount(0);
 await expect(panel.getByLabel('客户号')).toHaveCount(0);
 await expect(panel.getByRole('button',{name:'真实提交'})).not.toBeVisible();
 await page.setViewportSize({width:1280,height:800});
 await page.screenshot({path:'outputs/broker-accounts-clean.png',fullPage:false});
 await panel.getByRole('button',{name:'＋ 添加账户',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.getByLabel('券商').selectOption('ths');
 await dialog.getByLabel('银河资金账号',{exact:true}).fill('4455667788');
 await dialog.getByLabel('备注',{exact:true}).fill('新增测试账户');
 await dialog.getByLabel('交易密码',{exact:true}).fill('fixture-new-only');
 await page.screenshot({path:'outputs/broker-add-account.png',fullPage:false});
 await dialog.getByRole('button',{name:'添加账户',exact:true}).click();
 await expect(dialog).not.toBeVisible();await expect(panel.locator('.broker-account-card')).toHaveCount(3);
 await expect(panel).toContainText('新增测试账户');
 const rows=await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<Array<{id:string;label:string;password_saved:boolean}>>}).testTradingRpc('broker_accounts',{}));
 expect(rows.find(r=>r.label==='新增测试账户')?.password_saved).toBe(true);
});

test('managing one account preserves its identity and checks only that account',async({page})=>{
 await setup(page);await page.getByRole('tab',{name:'证券账户',exact:true}).click();
 const b=page.getByRole('article',{name:'同花顺（银河证券） 987***002'});
 await b.getByRole('button',{name:'管理',exact:true}).click();
 let dialog=page.getByRole('dialog');await expect(dialog).toContainText('987***002');
 await expect(dialog.getByLabel('交易密码',{exact:true})).toHaveValue('');
 await dialog.getByLabel('备注',{exact:true}).fill('银河常用');
 await dialog.getByRole('button',{name:'保存更改',exact:true}).click();
 await expect(dialog).not.toBeVisible();await expect(b).toContainText('银河常用');
 await b.getByRole('button',{name:'管理',exact:true}).click();dialog=page.getByRole('dialog');
 await dialog.getByRole('button',{name:'检查连接',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'连接正常'})).toContainText('连接正常，账户已核对');
 await expect(page.getByRole('status').filter({hasText:'连接正常'})).not.toContainText('account_verified');
 const checks=await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<string[]>}).testTradingRpc('test_broker_checks',{}));
 expect(checks).toEqual(['test-b']);
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 await b.getByRole('button',{name:'查看持仓',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'管理证券账户'})).toHaveValue('test-b');
 await expect(page.getByRole('region',{name:/同花顺（银河证券） · 987/})).toBeVisible();
});

test('historical receipts do not require manual resolution before unbinding',async({page})=>{
 await setup(page);
 await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc('test_seed_reports',{}));
 await page.getByRole('tab',{name:'证券账户',exact:true}).click();
 const b=page.getByRole('article').filter({hasText:'987***002'});
 await b.getByRole('button',{name:'管理',exact:true}).click();const dialog=page.getByRole('dialog');
 await dialog.getByRole('button',{name:'解除绑定',exact:true}).click();
 await dialog.getByRole('button',{name:'确认解除绑定',exact:true}).click();
 await expect(dialog).not.toBeVisible();await expect(page.locator('.broker-account-card')).toHaveCount(1);
});

test('confirmed unbinding removes only the chosen local binding',async({page})=>{
 await setup(page);await page.getByRole('tab',{name:'证券账户',exact:true}).click();
 const b=page.getByRole('article',{name:'同花顺（银河证券） 987***002'});
 await b.getByRole('button',{name:'管理',exact:true}).click();const dialog=page.getByRole('dialog');
 await dialog.getByRole('button',{name:'解除绑定',exact:true}).click();
 await dialog.getByRole('button',{name:'确认解除绑定',exact:true}).click();
 await expect(dialog).not.toBeVisible();await expect(page.locator('.broker-account-card')).toHaveCount(1);
 await expect(page.getByRole('article',{name:'华泰涨乐通 123***001'})).toBeVisible();
});

test('adding an already-bound account requires using manage instead of overwriting credentials',async({page})=>{
 await setup(page);await page.getByRole('tab',{name:'证券账户',exact:true}).click();
 await page.getByRole('button',{name:'＋ 添加账户',exact:true}).click();const dialog=page.getByRole('dialog');
 await dialog.getByLabel('券商').selectOption('ths');await dialog.getByLabel('银河资金账号').fill('9876542002');
 await dialog.getByLabel('交易密码',{exact:true}).fill('fixture-unused-password');
 await dialog.getByRole('button',{name:'添加账户',exact:true}).click();
 await expect(dialog.getByRole('alert')).toContainText('该账户已绑定');
 await expect(page.locator('.broker-account-card')).toHaveCount(2);
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 await page.getByRole('article',{name:'同花顺（银河证券） 987***002'}).getByRole('button',{name:'管理',exact:true}).click();
 await expect(page.getByRole('dialog').getByRole('button',{name:'检查连接',exact:true})).toHaveCount(1);
 await expect(page.getByRole('dialog').getByRole('button',{name:'重新登录',exact:true})).toHaveCount(0);
});


test('global and account pause remain available while holdings sync is running',async({page})=>{
 await setup(page);
 const rpc=(m:string)=>page.evaluate(method=>(window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc(method,{}),m);
 await page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'}).check();
 await page.getByRole('button',{name:'启动试运行',exact:true}).click();
 await rpc('test_hold_sync');
 await page.getByRole('button',{name:'一键同步全部持仓',exact:true}).click();
 await expect(page.getByText('正在逐个核验账户并同步持仓…',{exact:true})).toBeVisible();
 const accountA=page.getByRole('region',{name:/华泰涨乐通 · 123/});
 await expect(accountA.getByRole('button',{name:'暂停账户',exact:true})).toBeEnabled();
 await accountA.getByRole('button',{name:'暂停账户',exact:true}).click();
 await expect(accountA.getByText('账户已暂停',{exact:true})).toBeVisible();
 const pause=page.getByRole('button',{name:'暂停全部自动交易',exact:true});
 await expect(pause).toBeEnabled();await pause.click();
 await expect(page.getByText('自动执行已暂停',{exact:true})).toBeVisible();
 await rpc('test_release_sync');
 await expect(page.getByRole('button',{name:'一键同步全部持仓',exact:true})).toBeEnabled();
 await expect(page.getByText('自动执行已暂停',{exact:true})).toBeVisible();
});

test('cancelling startup prevents its delayed sync from starting execution later',async({page})=>{
 await setup(page);
 const rpc=(m:string)=>page.evaluate(method=>(window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc(method,{}),m);
 await page.getByRole('checkbox',{name:'123***001 山子高科 自动买入'}).check();
 await rpc('test_hold_sync');
 await page.getByRole('button',{name:'启动试运行',exact:true}).click();
 const cancel=page.getByRole('button',{name:'取消启动',exact:true});await expect(cancel).toBeEnabled();await cancel.click();
 await rpc('test_release_sync');
 await expect(page.getByRole('button',{name:'启动试运行',exact:true})).toBeEnabled();
 await expect(page.getByText('自动执行已暂停',{exact:true})).toBeVisible();
});


test('stock detail has no execution notice while exact evidence remains in execution records',async({page})=>{
 await setup(page);
 await page.getByRole('region',{name:/华泰涨乐通 · 123/}).getByRole('button',{name:'配置规则'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByText('更多设置',{exact:true})).toHaveCount(0);
 await expect(dialog.getByLabel('最大不利价格偏离（%）',{exact:true})).toHaveCount(0);
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 await page.evaluate(()=> (window as unknown as {testTradingRpc:(m:string,a:unknown)=>Promise<unknown>}).testTradingRpc('test_seed_price_checks',{}));
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await page.locator('.stock').filter({hasText:'山子高科'}).click();
 await expect(page.getByRole('button',{name:'查看该股票的自动交易执行详情',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'自动交易',exact:true}).click();
 await page.getByRole('tab',{name:'执行记录',exact:true}).click();
 await page.getByRole('button',{name:'刷新',exact:true}).click();
 const row=page.getByRole('row').filter({hasText:'29.04'});
 await expect(row).toContainText('123***001');await expect(row).toContainText('已跳过');await expect(row).not.toContainText('987***002');
 await row.locator('.trading-price-audit summary').click();
 for(const text of ['参考 29.04 元 → 校验 28.89 元','不利偏离 0.517% / 上限 0.5%','本次最低卖价 28.90 元','持仓核验 24.3秒','目标股票'])await expect(row).toContainText(text);
 await page.screenshot({path:'outputs/adverse-price-execution-details.png'});
});
