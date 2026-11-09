import {test,expect} from '@playwright/test';

// 预览样本固定为测试内联 fixture，不依赖 public/opportunity-preview.json 的具体数值。
const previewFixture={
  preview_note:'测试预览样本（浏览器只读）',
  issue:{screen_version:9,horizon:'未来 1–3 个交易日',verdict:'分化震荡 · 精选方向',bias:'试错',position:'总仓 3–4 成，单方向 ≤1.5 成',
    published_at:'2026-11-06T16:20:00+08:00',quote_date:'2026-11-06',
    focus:{sector:'测试方向甲',sector_code:'new_t1',state:'可考虑建仓',why:'测试定调：方向甲条件满足。',
      candidate:{code:'sh600001',name:'测试候选甲'},window:'下一交易日 9:45–10:30',
      summary:'首选 测试方向甲 · 测试候选甲：测试定调：方向甲条件满足。'},
    pulse:{
      market:{indices:[{code:'sh000001',name:'上证指数',price:3987.62,percent:0.71,change:28.15,ma5:3941.20,ma10:3902.44,ma20:3859.73,
        above_ma5:true,above_ma20:true,high20:4021.36,low20:3812.55,volume:512000000000,volume_ratio:1.12,support:3941.20,resistance:4021.36,
        stamp:'2026-11-06T15:00:00+08:00'}],
        breadth:{date:'2026-11-06',status:'closed',advance:3421,decline:1568,flat:142,advancing_percent:66.67,trin:0.91,
          amount_yuan:1986000000000,amount_5d_avg:1824000000000,amount_ratio:1.09,days_used:5},
        signals:['上证收于 3987.62，站上 MA5 3941.20。']},
      capital:{industry:{inflow:[{code:'new_t1',name:'测试行业甲',net_yuan:1000000000,change_percent:1.2}],
          outflow:[{code:'new_yh',name:'测试行业乙',net_yuan:-500000000,change_percent:-0.5}],measure:'买卖方向净额',date:'2026-11-06'},
        concept:null,persistent:[{code:'new_t1',name:'测试行业甲',sector_kind:'行业',net_yuan:1000000000,net_5d:2000000000,days:3,change_percent:1.2}],history_days:3},
      sentiment:{limit_up:{today:50,yesterday:40,attempt:70,sealed_rate:0.71,open_num:20},
        limit_down:{today:4,yesterday:6,attempt:10,sealed_rate:0.4,open_num:6},max_board:5,max_board_name:'测试高标',
        ladder:[{boards:5,count:1}],non_consecutive:35,yesterday_performance:null,
        hot_reasons:[{name:'测试原因',count:8,codes:['sh600000']}],
        trend:[{date:'2026-11-06',limit_up:50,limit_down:4,sealed_rate:0.71,max_board:5}],temperature:'分化'},
      hotspots:{news:[{time:'2026-11-06T14:32:00+08:00',title:'测试新闻标题',url:'https://example.com/news',region:'domestic',match:'测试原因'}],
        reasons:[{name:'测试原因',count:8,stocks:[{code:'sh600000',name:'测试股份'}]}]}
    },
    top_picks:[
      {code:'sh600001',name:'测试候选甲',role:'低吸候选',sector:'测试方向甲',sector_code:'new_t1',sector_kind:'行业',rank:1,
        state:'可考虑建仓',why:'测试定调：方向甲条件满足。',price:10.2,percent:1.0,boards:0,limit_tag:null,
        buy_low:9.9,buy_high:10.2,chase:10.5,stop:9.0,target1:10.8,target2:11.4,trail:9.8,
        note:'回踩 9.90–10.20 可分批；跌破 9.00 离场。',sell_note:'接近 10.80（+5.9%）分批减半；收盘跌破 9.80（均线）或 9.00（防守位）离场；持有 1–3 个交易日。',
        window:'下一交易日 9:45–10:30',sizing:'1 成以内',trigger:'市场下跌家数≤2/3；板块当日上涨；候选涨幅<5%；同行至少 1 只上涨'},
      {code:'sz300001',name:'测试候选乙',role:'低吸候选',sector:'测试方向乙',sector_code:'gn_t2',sector_kind:'概念',rank:2,
        state:'继续等',why:'测试继续等：候选涨幅超限。',price:6.3,percent:6.1,boards:1,limit_tag:'涨停',
        buy_low:5.8,buy_high:6.2,chase:6.5,stop:5.2,target1:6.9,target2:7.4,trail:5.8,
        note:'回踩 5.80–6.20 可分批；跌破 5.20 离场。',sell_note:'接近 6.90（+9.5%）分批减半；收盘跌破 5.80（均线）或 5.20（防守位）离场；持有 1–3 个交易日。',
        window:'下一交易日 9:45–10:30',sizing:'0.5–1 成',trigger:'市场下跌家数≤2/3；板块当日上涨；板块资金净流入；候选涨幅<5%'}
    ],
    radar_summary:'识别 1 个 · 启动初期 1 个 · 名称/玄学 0 个',
    radar:[{theme:'测试炒作',kind:'事件/题材',stage:'启动初期',stage_note:'今日首批涨停出现，尚未形成连续梯队',
      signals:['今日涨停 2 家','近 72 小时新闻 3 条'],limit_up_today:2,limit_up_prev:0,limit_up_5d:2,max_board:1,news_count:3,
      net_yuan:null,change:null,verdict:'可小仓试错（≤0.5 成）',risk:'测试风险：新闻热度不等于订单或业绩。',
      watch:['次日出现 2 家以上连板再加仓'],
      stocks:[{code:'sh600005',name:'测试雷达股',role:'龙头',price:5.1,percent:9.9,boards:1,limit_tag:'涨停',reason:'测试原因',levels:null,
        entry:{buy_low:5.0,buy_high:5.0,stop:4.7,chase:5.3,target1:5.5,target2:5.9,trail:null,
          note:'回踩 5.00 可分批；跌破 4.70 离场。',sell_note:'接近 5.50（+8.0%）分批减半；跌破 4.70 离场；持有 1–3 个交易日。'}}],
      evidence:[{label:'新闻',value:'测试冰雪经济政策预期升温',source:'测试来源'}]}],
    playbooks:[{name:'修复延续',conditions:['测试条件一'],action:'测试动作',position:'5–6 成',active:false},
      {name:'高低切 / 分化',conditions:['测试条件二'],action:'只做低吸，不做连板接力。',position:'3–4 成',active:true},
      {name:'补跌防守',conditions:['测试条件三'],action:'空仓观察',position:'≤2 成',active:false}],
    timetable:[{time:'9:30–10:00',focus:'开盘 30 分钟',rule:'测试规则：上证不跌破 MA5。'}],
    risk:['公开数据统计与研究，不构成投资建议。'],
    warnings:['测试数据缺口：近 5 日资金只有 2 个采集日。'],
    coverage:{industry:10,concept:20},
    exclusions:{gn_robot:'测试未入选原因：资金净流出 3.00 亿元。'},
    directory:{gn_robot:'机器人'},
    directions:[
      {rank:1,sector:'测试方向甲',sector_code:'new_t1',sector_kind:'行业',change:1.2,net:1000000000,net_5d:null,net_5d_days:null,
        score:6.5,state:'可考虑建仓',why:'测试定调：方向甲条件满足。',opportunity:'测试机会：方向甲回踩可低吸。',
        logic:['测试逻辑：板块上涨 1.20%。'],risk:'测试风险：跌破 9.00 元放弃。',
        candidate:{code:'sh600001',name:'测试候选甲'},peers:[{code:'sh600002',name:'测试同行甲'},{code:'sh600003',name:'测试同行乙'}],
        stocks:[{code:'sh600001',name:'测试候选甲',role:'低吸候选',price:10.2,percent:1.0,amount_yuan:100000000,low:9.9,
            boards:0,limit_tag:null,reason:null,levels:{ma5:10.0,ma10:9.8,ma20:9.5,high20:10.8,low20:9.0},
            entry:{buy_low:9.9,buy_high:10.2,stop:9.0,chase:10.5,target1:10.8,target2:11.4,trail:9.8,
              note:'回踩 9.90–10.20 可分批；跌破 9.00 离场。',
              sell_note:'接近 10.80（+5.9%）分批减半；收盘跌破 9.80（均线）或 9.00（防守位）离场；持有 1–3 个交易日。'}},
          {code:'sh600002',name:'测试同行甲',role:'龙头',price:11.5,percent:2.0,amount_yuan:200000000,low:11.0,
            boards:null,limit_tag:null,reason:null,levels:null,entry:null}],
        timing:{window:'下一交易日 9:45–10:30',triggers:['测试触发条件：现价站上 10.00。'],invalidation:['测试失效条件：跌破 9.00。'],
          gates:[{kind:'candidate_pct_max',value:5}]},
        evidence:[{label:'资金',value:'测试净流入 10.00 亿元。',source:'测试来源'}]},
      {rank:2,sector:'测试方向乙',sector_code:'gn_t2',sector_kind:'概念',change:0.5,net:500000000,net_5d:1000000000,net_5d_days:3,
        score:5.2,state:'继续等',why:'测试继续等：候选涨幅超限。',opportunity:'测试机会：方向乙等待回踩。',
        logic:['测试逻辑：概念上涨 0.50%。'],risk:'测试风险：跌破 5.20 元放弃。',
        candidate:{code:'sz300001',name:'测试候选乙'},peers:[{code:'sh600002',name:'测试同行甲'},{code:'sz300002',name:'测试同行丙'}],
        stocks:[{code:'sz300001',name:'测试候选乙',role:'低吸候选',price:6.3,percent:6.1,amount_yuan:80000000,low:5.9,
            boards:1,limit_tag:'涨停',reason:'测试原因',levels:{ma5:5.8,ma10:5.5,ma20:5.2,high20:6.5,low20:4.8},
            entry:{buy_low:5.8,buy_high:6.2,stop:5.2,chase:6.5,target1:6.9,target2:7.4,trail:5.8,
              note:'回踩 5.80–6.20 可分批；跌破 5.20 离场。',
              sell_note:'接近 6.90（+9.5%）分批减半；收盘跌破 5.80（均线）或 5.20（防守位）离场；持有 1–3 个交易日。'}},
          {code:'sz300002',name:'测试同行丙',role:'中军',price:8.8,percent:-0.5,amount_yuan:60000000,low:8.6,
            boards:null,limit_tag:null,reason:null,levels:null,entry:null}],
        timing:{window:'下一交易日 9:45–10:30',triggers:['测试触发条件：回踩 6.00。'],invalidation:['测试失效条件：跌破 5.20。'],
          gates:[{kind:'candidate_pct_max',value:5}]},
        evidence:[]}
    ]},
  quotes:[],sectors:{},day:'2026-11-06',batch:'2026-11-06T15:31:00+08:00',schedule:'',completed_slot:null
};

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

test('市场机会首屏聚焦：优先行、建仓清单与方向详情',async({page})=>{
  await page.clock.setFixedTime(new Date('2026-11-08T12:00:00+08:00'));
  await page.route('**/opportunity-preview.json',route=>route.fulfill({json:previewFixture}));
  await page.goto('/');
  await page.getByRole('button',{name:'市场机会',exact:true}).click();
  const root=page.getByRole('region',{name:'市场机会研判'});
  await expect(root).toBeVisible();
  await expect(root).toContainText('分化震荡 · 精选方向');
  await expect(root.locator('.mo-focus-line')).toContainText('首选 测试方向甲 · 测试候选甲');
  await expect(root).toContainText('预览：静态状态，非实时核对');
  const picks=page.getByRole('region',{name:'建仓清单'});
  await expect(picks).toBeVisible();
  await expect(picks.locator('.mo-pick-row')).toHaveCount(2);
  await expect(picks).toContainText('买点区间');
  await expect(picks).toContainText('止损');
  await expect(picks).toContainText('止盈目标');
  const first=picks.locator('.mo-pick-row').first();
  await expect(first).toContainText('测试候选甲');
  await expect(first).toContainText('9.90–10.20');
  await expect(first).toContainText('9.00');
  await expect(first).toContainText('10.80');
  await expect(first).toContainText('+5.9%');
  await expect(first).toContainText('1 成以内');
  await expect(first).toContainText('9:45–10:30');
  await expect(first).toContainText('市场下跌家数≤2/3');
  expect(await first.getAttribute('title')).toContain('卖出：');
  const radar=page.getByRole('region',{name:'炒作雷达'});
  await expect(radar).toBeVisible();
  await expect(radar.locator('.mo-radar-row')).toHaveCount(1);
  await expect(radar).toContainText('测试炒作');
  await expect(radar).toContainText('启动初期');
  await expect(radar).toContainText('可小仓试错（≤0.5 成）');
  await radar.locator('.mo-radar-row').click();
  await expect(radar.locator('.mo-radar-detail')).toContainText('测试风险');
  await expect(radar.locator('.mo-radar-detail')).toContainText('5.00');
  await expect(radar.locator('.mo-radar-detail')).toContainText('≤0.5 成或只观察');
  const detail=page.getByRole('region',{name:'方向详情'});
  await expect(detail.locator('.mo-tab')).toHaveCount(2);
  await expect(detail.locator('.mo-tab').first()).toHaveAttribute('aria-pressed','true');
  await expect(detail).toContainText('测试方向甲');
  await expect(detail).toContainText('卖出提示');
  // 首屏不展示市场背景四卡，默认折叠
  await expect(page.locator('details.mo-fold-market')).not.toHaveAttribute('open','');
  await expect(page.getByRole('region',{name:'市场温度'})).toBeHidden();
  await expect(page.getByRole('region',{name:'行动计划'})).toBeHidden();
  await picks.locator('.mo-pick-row').filter({hasText:'测试候选乙'}).click();
  await expect(detail.locator('.mo-tab').nth(1)).toHaveAttribute('aria-pressed','true');
  await expect(detail).toContainText('测试方向乙');
  await expect(detail).toContainText('测试候选乙');
  await expect(detail).toContainText('跌破 5.20 离场');
  // 展开折叠区：市场背景与方向排名/数据覆盖
  await page.locator('details.mo-fold-market > summary').click();
  await expect(page.getByRole('region',{name:'市场温度'})).toBeVisible();
  await expect(page.getByRole('region',{name:'热点题材'})).toContainText('测试新闻标题');
  await page.locator('details.mo-fold-action > summary').click();
  await expect(page.getByRole('region',{name:'行动计划'})).toContainText('修复延续');
  await page.locator('details.mo-fold-rank > summary').click();
  const coverage=page.getByRole('region',{name:'数据覆盖'});
  await expect(page.getByRole('region',{name:'方向排名'})).toBeVisible();
  await expect(coverage).toContainText('测试数据缺口：近 5 日资金只有 2 个采集日。');
  await coverage.getByText('查某个方向为什么没入选').click();
  await coverage.getByPlaceholder('输入名称查询本期结果').fill('机器人');
  await expect(coverage).toContainText('测试未入选原因：资金净流出 3.00 亿元。');
  const advanced=page.locator('.mode-advanced');
  await expect(advanced).toContainText('详细交易计划');
  await advanced.locator(':scope > summary').click();
  await expect(advanced).toContainText('BAOBAOLI 模式计划');
});

test('预览样本缺失时显示研判空态',async({page})=>{
  await page.clock.setFixedTime(new Date('2026-11-08T12:00:00+08:00'));
  await page.route('**/opportunity-preview.json',route=>route.abort());
  await page.goto('/');
  await page.getByRole('button',{name:'市场机会',exact:true}).click();
  await expect(page.getByRole('region',{name:'市场机会研判'})).toContainText('今日研判尚未生成');
});
