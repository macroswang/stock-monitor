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
  await expect(board).toContainText('本期已走强的代表股是行业乙的行业乙代表');
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
          case 'daily_outlook':return {issue:{ideas:[candidate],themes:[{code:'topic_fresh',name:'新型传感器',members:[]}],directory:{new_dlhy:'电力行业'},exclusions:{topic_fresh:'只有一家相关公司，继续等。'},published_at:time,quote_date:date,coverage:{industry:2,concept:0}},
            day:date,batch:time,sectors:{new_dlhy:{change:1,net:100,time}},quotes:stocks.map(s=>({...s,price:'10.2',previous_close:'10',day_low:'9.9',timestamp:time}))};
          default:throw Error('测试未提供 '+args.method);
        }
      }
    }});
  },{date,time,stocks,candidate,sectors});
  await page.goto('/');
  await page.getByRole('button',{name:'市场机会',exact:true}).click();
  const today=page.getByRole('region',{name:'当天走强的行业和代表股'});
  const future=page.getByRole('region',{name:'未来几天的建仓候选'});
  await expect(today).toContainText('乐山电力因当天涨幅超过行业而列为代表股');
  await expect(today).toContainText('建仓候选 · 长江电力 · 可考虑建仓');
  await expect(today).toContainText('继续等。其他行业未列入本期重点建仓候选');
  await expect(future).toContainText('可考虑建仓 · 首选 长江电力');
  await expect(future).toContainText('乐山电力当天涨 4.00%');
  await expect(future.locator('article')).toHaveCount(1);
  await future.getByText('查某个方向为什么没入选').click();
  await future.getByPlaceholder('输入名称查询本期结果').fill('传感器');
  await expect(future).toContainText('新型传感器 · 未入选');
  await expect(future).toContainText('只有一家相关公司，继续等。');
  await expect(future.locator('article')).toHaveCount(1);
});
