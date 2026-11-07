import {test,expect} from '@playwright/test';
test('模式计划保留原始依据与状态，防守计划只可观察',async({page})=>{
  await page.goto('/');
  const open=()=>page.getByRole('button',{name:'市场机会',exact:true}).click();
  await open();
  const board=page.locator('.mode-journal');
  await expect(board.getByLabel('操作模式')).toBeHidden();
  await board.locator('.mode-advanced > summary').click();
  for(const market of ['试错','防守']){
    await board.getByLabel('市场环境').selectOption(market);
    for(const key of ['evidence','theme','symbol','trigger','expectation','deadline','invalidation','sizing']){
      await board.locator('input[name='+key+']').fill(market+'样例'+key);
    }
    await board.getByLabel('单笔风险预算').fill('100');
    await board.getByRole('button',{name:market==='试错'?'保存盘前计划':'保存观察计划'}).click();
    const card=board.locator('article').filter({hasText:market+'样例symbol'});
    const stages=market==='试错'?['试仓','确认','追加','减仓','失效待退出','退出']:['放弃'];
    if(market==='防守')await expect(card.getByRole('button',{name:'记录试仓'})).toHaveCount(0);
    for(const stage of [...stages,'已复盘']){
      const action=card.getByRole('button',{name:stage==='已复盘'?'保存复盘':'记录'+stage});
      await expect(action).toBeDisabled();
      await card.getByLabel('实际观察或复盘依据').fill(stage+'时的观察');
      await action.click();
      await expect(card.getByRole('heading')).toContainText(stage);
    }
  }
  await page.reload();await open();
  await board.locator('.mode-advanced > summary').click();
  await expect(board.locator('article')).toHaveCount(2);
  const card=board.locator('article').filter({hasText:'试错样例symbol'});
  await card.locator('summary').click();
  await expect(card).toContainText('试错样例invalidation');
  await expect(card).toContainText('减仓时的观察');
});

test('直接列出强势行业及同日代表股，剔除逆势流出和旧报价',async({page})=>{
  await page.clock.setFixedTime(new Date('2026-11-07T12:00:00+08:00'));
  const stamp='2026-11-06T15:01:00+08:00';
  const sector=(name:string,pct:number,net:number,time=stamp)=>({
    name,code:name,change_percent:pct,net_yuan:net,
    representative:{name:name+'代表',code:'sh600001',change_percent:5,time},
  });
  await page.route('**/sector-flow-preview.json',r=>r.fulfill({json:{snapshot:{
    date:'2026-11-06',source:'测试行业',inflow:[],outflow:[],quote_time:stamp,collected_at:stamp,
    sectors:[sector('弱势',-1,90),sector('流出',3,-1),sector('行业甲',1,80),sector('行业乙',2,60),sector('行业丙',3,40,'2026-11-05T15:01:00+08:00')],
  },running:false}}));
  await page.goto('/');
  await page.getByRole('button',{name:'市场机会',exact:true}).click();
  const board=page.getByRole('region',{name:'当天走强的行业和代表股'});
  await expect(board.locator('.decision-pick').nth(1)).toContainText('行业乙代表');
  await expect(page.getByLabel('主导航').getByRole('button',{name:'模拟交易'})).toHaveCount(0);
  await expect(board.locator('.decision-pick')).toHaveCount(3);
  await expect(board).not.toContainText('行业丙代表');
  await expect(board).not.toContainText('弱势');
});

test('同一行业的代表股与候选股分别说明，未入选行业只显示等待',async({page})=>{
  const time='2026-11-06T10:15:00+08:00', date=time.slice(0,10);
  await page.clock.setFixedTime(new Date(time));
  const stocks=[{name:'长江电力',code:'sh600900',low:9},{name:'同行甲',code:'sh600001',low:9},{name:'同行乙',code:'sh600002',low:9}];
  const candidate={sector:'电力运营',sector_code:'new_dlhy',stocks,allow_entry:true,reason:'长江电力回落后上涨，两只同行上涨。',risk:'等同行确认。'};
  const sectors=[{code:'new_dlhy',name:'电力行业'},{code:'new_other',name:'其他行业'}].map((r,index)=>({...r,change_percent:1,net_yuan:100,representative:{
    code:index?'sh600003':'sh600644',name:index?'另一代表':'乐山电力',change_percent:4,time
  }}));
  await page.addInitScript(({date,time,stocks,candidate,sectors})=>{
    Object.assign(window,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
      metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
      async invoke(command:string,args:{method:string}){
        if(command!=='rpc')return 0;
        switch(args.method){
          case 'snapshot':return {watch:[],events:[],config:{},now:time,market_open:true};
          case 'market':case 'market_overview':return {quotes:[],minute:null};
          case 'sector_flow':return {snapshot:{date,sectors,quote_time:time}};
          case 'breadth':return {days:[{date,advance:2,decline:1,flat:1,advancing_percent:50,suspended:0,missing:0,covered:4,expected:4,
            first_quote:time,last_quote:time,collected_at:time,status:'provisional'}]};
          case 'daily_outlook':{
            const extra=[{name:'领涨甲',code:'sz300008'},{name:'旧报价',code:'sz300009'},{name:'未上涨',code:'sz300010'}];
            const quote=(s:{code:string},price:string,timestamp=time)=>({...s,price,previous_close:'10',day_low:'9.9',timestamp});
            return {issue:{ideas:[{...candidate,core_members:[...stocks,...extra]},{...candidate,sector:'新概念',sector_code:'gn_new',core_members:extra.slice(2)},{...candidate,sector:'并列方向',sector_code:'topic_tie',sector_kind:'题材',core_members:stocks}],themes:[{code:'topic_fresh',name:'新型传感器',members:[]}],directory:{new_dlhy:'电力行业'},exclusions:{topic_fresh:'只有一家相关公司，继续等。'},published_at:time,quote_date:date,coverage:{industry:2,concept:0}},
            day:date,batch:time,sectors:{new_dlhy:{change:1,net:100,time}},quotes:[...stocks.map(s=>quote(s,'10.2')),quote(extra[0],'12'),quote(extra[1],'13',time.replace('10:15','09:45')),quote(extra[2],'9.99')]};}
          default:throw Error('测试未提供 '+args.method);
        }
      }
    }});
  },{date,time,stocks,candidate,sectors});
  await page.goto('/');
  await page.getByRole('button',{name:'市场机会',exact:true}).click();
  const today=page.getByRole('region',{name:'当天走强的行业和代表股'});
  const future=page.getByRole('region',{name:'未来几天的建仓候选'});
  await expect(today).toContainText('乐山电力当天跑赢行业；建仓候选为长江电力');
  await expect(today.locator('.decision-pick').first()).toContainText('可考虑建仓');
  await expect(today.locator('.decision-pick').nth(1)).toContainText('继续等 · 未入选');
  await expect(future).toContainText('可考虑建仓 · 首选 长江电力');
  const rising=future.getByRole('region',{name:'上涨核心股'});
  await expect(rising.locator('tbody tr')).toHaveCount(4);
  await expect(rising.locator('tbody tr').first()).toContainText('领涨甲');
  await expect(rising.locator('tbody tr').first()).toContainText('+20.00%');
  await expect(rising).not.toContainText('旧报价');
  await expect(rising.locator('tbody tr').first().locator('.leader-role')).toHaveText('领涨');
  await expect(rising.locator('tbody tr').filter({hasText:'长江电力'}).locator('.candidate-role')).toHaveText('建仓候选');
  await expect(rising.locator('.role-explanation')).toContainText('策略不追涨幅达 5%');
  await expect(rising.locator('.entry-status')).toHaveText('可考虑建仓');
  const before=await rising.boundingBox(), left=await future.locator('.direction-pane').boundingBox();
  expect(left!.y).toBe(before!.y);expect(left!.height).toBe(before!.height);
  const scroll=await rising.locator('.riser-scroll').elementHandle();
  await future.locator('.outlook-evidence summary').click();
  await expect(future.locator('.outlook-evidence')).toContainText('长江电力回落后上涨');
  await future.locator('.outlook-item').nth(1).click();
  await expect(rising).toContainText('已核对的核心股中暂无上涨');
  await expect(rising).not.toContainText('领涨甲');
  await expect(rising.locator('.entry-status')).toHaveText('继续等');
  expect(await rising.boundingBox()).toEqual(before);
  expect(await scroll!.evaluate(e=>e.isConnected)).toBe(true);
  await future.getByRole('button',{name:'题材',exact:true}).click();
  await expect(rising.locator('.leader-role')).toHaveCount(3);
  await expect(rising.locator('.role-explanation')).toContainText('长江电力既是本期建仓候选，也并列领涨');
  await page.setViewportSize({width:1000,height:680});
  await expect(rising).toBeVisible();
  const dimensions=await rising.evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth}));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width+1);
  await future.getByRole('button',{name:'全部',exact:true}).click();
  await future.getByText('查某个方向为什么没入选').click();
  await future.getByPlaceholder('输入名称查询本期结果').fill('传感器');
  await expect(future).toContainText('新型传感器 · 未入选');
  await expect(future).toContainText('只有一家相关公司，继续等。');
  await expect(future.locator('.outlook-item')).toHaveCount(3);
});
