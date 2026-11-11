import {test,expect,type Page,type Locator} from '@playwright/test';
import {mkdirSync} from 'node:fs';

// 股票池「终端紧凑表格 + 持续跟踪 + 回测」验收测试（2026-11-11 重写）。
// 依据 docs/pool-table/contract.md 与当前 src/FocusPool.tsx / src/poolTableModel.ts。
// 只断言用户可见行为与稳定 class/aria；不重算业务规则，不依赖真实网络/真实库。
type Json=Record<string,any>;

try{mkdirSync('/tmp/pool-table-verify',{recursive:true});}catch{}
const SHOTS='/tmp/pool-table-verify';

const QUOTES_TIME='2026-11-11T10:37:12+08:00';
const UPDATED_AT='2026-11-11T10:37:30+08:00';

const quote=(price:number,percent:number,time='2026-11-11T10:37:00+08:00',basis:'live'|'last'='live')=>({
  price,percent,time,low:price*0.97,high:price*1.03,basis,fresh:basis==='live',
});
const planDefault=()=>({buy_low:9.5,buy_high:10,chase:11,stop:9,target1:11,target2:12,trail:9.5,
  note:'回踩 9.50–10.00 可分批；跌破 9.00 离场。',sell_note:'接近 11.00 分批减半。'});
const planA=()=>({buy_low:11.8,buy_high:12.4,chase:13,target1:14.2,target2:15.6,trail:12.6,stop:11.2,
  note:'回踩 11.80–12.40 分批；跌破 11.20 离场。',sell_note:'接近 14.20 分批减半。'});
const dayRow=(day:string,price:number,percent:number,options:Json={}):Json=>({
  day,price,percent,high:options.high??price*1.02,low:options.low??price*0.98,
  hit_buy:options.hit_buy??false,hit_stop:options.hit_stop??false,hit_target:options.hit_target??false,
  turnover_rate:options.turnover_rate??null,volume_ratio:options.volume_ratio??null,
});
const historyE1=()=>[
  dayRow('2026-11-10',12.9,1.5,{turnover_rate:7.2,volume_ratio:2.5,hit_buy:true}),
  dayRow('2026-11-11',13.09,2.1,{turnover_rate:6.5,volume_ratio:2.11}),
];

const makeEntry=(over:Json):Json=>({
  code:'sz000001',name:'甲科技',added_day:'2026-11-11',added_at:'2026-11-11T09:35:00+08:00',added_price:12.68,
  source:'建仓清单',sector:'半导体',role:'低吸候选',reason:'资金净流入、回踩买点；智能穿戴题材活跃。',
  state:'可建仓',entry_tag:'可建仓',category:'概念',group_name:'智能穿戴',groups:['概念','智能穿戴'],
  updated_at:UPDATED_AT,plan:planA(),quote:quote(13.09,2.1),
  today_percent:2.1,since_add_percent:3.2,distance_to_buy_percent:-1.2,zone:'已进入买区',hint:'提示',
  history:historyE1(),max_gain_percent:6,max_drawdown_percent:-1,hold_days:2,
  windows:{'T+1':{n:1,date:'2026-11-10',close:12.9,return_percent:2.5,benchmark_return:1,excess_percent:1.5},'T+3':null,'T+5':null},
  episodes:{total:3,today:2,first_at:'2026-11-09T10:02:00+08:00',last_at:'2026-11-11T09:35:00+08:00'},
  quant:{turnover_rate:6.5,volume_ratio:2.11,amplitude:3.2,float_mcap_yi:123.4},
  tags:{concept:['智能穿戴'],theme:['AI硬件/算力'],event:['军工订单'],other:['半导体']},
  ...over,
});

const ENTRIES:Json[]=[
  makeEntry({}),
  makeEntry({code:'sz000002',name:'乙材料',added_day:'2026-11-10',added_at:'2026-11-10T14:31:00+08:00',added_price:20.5,
    source:'方向候选',sector:'化工',role:'追涨候选',state:'观察',entry_tag:'观察',category:'行业',group_name:'化工',groups:['行业'],
    quote:quote(20.19,-0.8),today_percent:-0.8,since_add_percent:-1.5,hold_days:1,max_gain_percent:2,max_drawdown_percent:-3,
    windows:null,history:[dayRow('2026-11-10',20.5,0.5,{turnover_rate:3.1,volume_ratio:1})],
    episodes:{total:2,today:0,first_at:'2026-11-08T10:31:00+08:00',last_at:'2026-11-10T14:31:00+08:00'},
    quant:{turnover_rate:3.4,volume_ratio:1.03,amplitude:2.1,float_mcap_yi:88.8},
    tags:{concept:['锂电池','储能'],theme:['新能源'],event:[],other:['化工']}}),
  makeEntry({code:'sz000003',name:'丙电子',added_day:'2026-11-09',added_at:'2026-11-09T10:02:00+08:00',added_price:9.86,
    source:'炒作雷达',sector:'固态电池',role:'观察候选',state:'观察',entry_tag:'观察',category:'题材',group_name:'固态电池',groups:['题材'],
    plan:null,quote:quote(9.86,0),today_percent:0,since_add_percent:0,hold_days:2,max_gain_percent:null,max_drawdown_percent:null,
    windows:null,history:[],
    episodes:{total:1,today:0,first_at:'2026-11-09T10:02:00+08:00',last_at:'2026-11-09T10:02:00+08:00'},
    quant:{turnover_rate:9.9,volume_ratio:null,amplitude:null,float_mcap_yi:null},
    tags:{concept:[],theme:[],event:[],other:[]}}),
  makeEntry({code:'sz000004',name:'丁能源',added_day:'2026-11-11',added_at:'2026-11-11T10:37:00+08:00',added_price:5.62,
    source:'建仓清单',sector:'电力',role:'低吸候选',state:'可建仓',entry_tag:'可建仓',category:'事件',group_name:'电力改革',groups:['事件'],
    quote:quote(5.69,1.2),today_percent:1.2,since_add_percent:1.2,hold_days:0,max_gain_percent:1.2,max_drawdown_percent:-0.5,
    windows:{'T+1':null,'T+3':null,'T+5':null},
    history:[dayRow('2026-11-11',5.69,1.2,{turnover_rate:1.2,volume_ratio:0.88})],
    episodes:{total:1,today:1,first_at:'2026-11-11T10:37:00+08:00',last_at:'2026-11-11T10:37:00+08:00'},
    quant:{turnover_rate:1.2,volume_ratio:0.88,amplitude:1.8,float_mcap_yi:40.2},
    tags:{concept:['光伏'],theme:[],event:['项目中标'],other:['电力']}}),
  makeEntry({code:'sz000005',name:'戊智能',added_day:'2026-11-06',added_at:'2026-11-06T11:02:00+08:00',added_price:30.1,
    source:'方向候选',sector:'机器人',role:'龙头',state:'观察',entry_tag:'观察',category:'概念',group_name:'机器人',groups:['概念','机器人'],
    quote:quote(32.63,-2.2),today_percent:-2.2,since_add_percent:8.4,hold_days:5,max_gain_percent:12,max_drawdown_percent:-4,
    windows:{'T+1':{n:1,date:'2026-11-09',close:31.2,return_percent:-1.2,benchmark_return:0.4,excess_percent:-1.6},'T+3':null,'T+5':null},
    history:[dayRow('2026-11-08',31.5,-1),dayRow('2026-11-09',32.63,-2.2)],
    episodes:{total:4,today:0,first_at:'2026-11-06T11:02:00+08:00',last_at:'2026-11-09T10:02:00+08:00'},
    quant:{turnover_rate:2.3,volume_ratio:0.8,amplitude:5.5,float_mcap_yi:210.5},
    tags:{concept:['机器人','减速器','工业母机'],theme:['AI硬件/算力'],event:['行业展会'],other:['机械设备']}}),
  makeEntry({code:'sz000006',name:'己汽车',added_day:'2026-11-05',added_at:'2026-11-05T08:11:00+08:00',added_price:14.2,
    source:'炒作雷达',sector:'汽车',role:'观察候选',state:'观察',entry_tag:'观察',category:'题材',group_name:'汽车',groups:['题材'],
    plan:planDefault(),quote:null,today_percent:null,since_add_percent:null,hold_days:null,max_gain_percent:null,max_drawdown_percent:null,
    windows:null,history:[],
    episodes:{total:1,today:0,first_at:'2026-11-05T08:11:00+08:00',last_at:'2026-11-05T08:11:00+08:00'},
    quant:{turnover_rate:null,volume_ratio:null,amplitude:null,float_mcap_yi:null},
    tags:{concept:[],theme:[],event:[],other:[]}}),
  makeEntry({code:'sz000007',name:'庚医药',added_day:'2026-11-04',added_at:'2026-11-04T15:01:00+08:00',added_price:10.2,
    source:'建仓清单',sector:'医药生物',role:'低吸候选',state:'观察',entry_tag:'观察',category:'概念',group_name:'创新药',groups:['概念'],
    quote:quote(9.85,0.4),today_percent:0.4,since_add_percent:-4.2,hold_days:3,max_gain_percent:2,max_drawdown_percent:-5,
    windows:{'T+1':{n:1,date:'2026-11-09',close:9.9,return_percent:-2.9,benchmark_return:0.4,excess_percent:-3.3},'T+3':null,'T+5':null},
    history:[dayRow('2026-11-09',9.9,-0.8,{turnover_rate:8.1,volume_ratio:1.6})],
    episodes:{total:2,today:0,first_at:'2026-11-04T15:01:00+08:00',last_at:'2026-11-08T10:31:00+08:00'},
    quant:{turnover_rate:7.8,volume_ratio:1.5,amplitude:4.4,float_mcap_yi:66.6},
    tags:{concept:['创新药'],theme:['医药'],event:[],other:['医药生物']}}),
  makeEntry({code:'sz000008',name:'辛传媒',added_day:'2026-11-03',added_at:'2026-11-03T13:01:00+08:00',added_price:8.8,
    source:'方向候选',sector:'文化传媒',role:'观察候选',state:'观察',entry_tag:'观察',category:'事件',group_name:'短剧',groups:['事件'],
    quote:quote(8.9,0),today_percent:0,since_add_percent:1.1,hold_days:4,max_gain_percent:3,max_drawdown_percent:-2,
    windows:{'T+1':{n:1,date:'2026-11-09',close:8.85,return_percent:0.6,benchmark_return:0.4,excess_percent:0.2},'T+3':null,'T+5':null},
    history:[dayRow('2026-11-09',8.9,0,{turnover_rate:4.9,volume_ratio:3.4})],
    episodes:{total:3,today:0,first_at:'2026-11-03T13:01:00+08:00',last_at:'2026-11-09T13:01:00+08:00'},
    quant:{turnover_rate:4.6,volume_ratio:3.2,amplitude:6.1,float_mcap_yi:55.5},
    tags:{concept:['短剧','AIGC'],theme:['传媒'],event:[],other:['文化传媒']}}),
];

// ===== pool_backtest mock（契约 §1.3 / §2.2） =====
const btRow=(over:Json):Json=>({
  code:'sz000001',name:'甲科技',source:'建仓清单',category:'概念',
  first_day:'2026-11-11',first_price:12.68,first_percent:3.2,episodes:3,
  latest_day:'2026-11-11',latest_price:13.09,since_percent:3.2,
  returns:{'T+1':{date:'2026-11-12',ret_percent:2.5,bench_percent:1.3,excess_percent:1.2},'T+3':null,'T+5':null},
  pending:['T+3'],missing:['T+5'],
  ...over,
});
const BACKTEST_ROWS:Json[]=[
  btRow({}),
  btRow({code:'sz000002',name:'乙材料',first_day:'2026-11-10',first_price:20.5,first_percent:-1.4,episodes:2,source:'方向候选',
    returns:{'T+1':{date:'2026-11-11',ret_percent:-0.6,bench_percent:0.2,excess_percent:-0.8},
      'T+3':{date:'2026-11-12',ret_percent:1.1,bench_percent:0.3,excess_percent:0.8},'T+5':null},
    pending:['T+5'],missing:[]}),
  btRow({code:'sz000003',name:'丙电子',first_day:'2026-11-09',first_price:9.86,first_percent:0,episodes:1,source:'炒作雷达',
    returns:{'T+1':null,'T+3':null,'T+5':null},pending:['T+1','T+3','T+5'],missing:[]}),
  btRow({code:'sz000004',name:'丁能源',first_day:'2026-11-06',first_price:5.62,first_percent:8.5,episodes:3,source:'建仓清单',
    returns:{'T+1':{date:'2026-11-09',ret_percent:1.2,bench_percent:0.6,excess_percent:0.6},'T+3':null,'T+5':null},
    pending:['T+5'],missing:['T+3']}),
  btRow({code:'sz000005',name:'戊智能',first_day:'2026-11-04',first_price:30.1,first_percent:5,episodes:1,source:'方向候选',
    returns:{'T+1':{date:'2026-11-05',ret_percent:-1.1,bench_percent:-0.6,excess_percent:-0.5},'T+3':null,'T+5':null},
    pending:['T+3','T+5'],missing:[]}),
  btRow({code:'sz000006',name:'己汽车',first_day:'2026-11-11',first_price:14.2,first_percent:0.8,episodes:2,source:'炒作雷达',
    returns:{'T+1':{date:'2026-11-12',ret_percent:0.9,bench_percent:0.5,excess_percent:0.4},'T+3':null,'T+5':null},
    pending:['T+3','T+5'],missing:[]}),
];
const BACKTEST_DATA:Json={
  rows:BACKTEST_ROWS,
  coverage:{rows:6,with_returns:5,bench:'上证指数',daily_codes:106,episode_issues:50,episode_range:'2026-11-09~2026-11-11',note:'历史回放样本。'},
};

type BootOptions={
  entries?:Json[];
  backtest?:Json;
  trading?:boolean;
  failPoolTimes?:number;
  failBacktestTimes?:number;
  delayPoolMs?:number;
};

// Tauri rpc mock：pool / pool_backtest 为主，其余为主应用启动所需的最小响应。
async function boot(page:Page,options:BootOptions={}):Promise<Locator>{
  const config={
    entries:options.entries??ENTRIES,
    backtest:options.backtest??BACKTEST_DATA,
    trading:options.trading!==false,
    quotesTime:QUOTES_TIME,
    updatedAt:UPDATED_AT,
    failPoolTimes:options.failPoolTimes??0,
    failBacktestTimes:options.failBacktestTimes??0,
    delayPoolMs:options.delayPoolMs??0,
  };
  await page.addInitScript((config:Json)=>{
    try{
      localStorage.removeItem('stock-monitor-pool-terminal-v1');
      localStorage.removeItem('stock-monitor-pool-view');
      localStorage.removeItem('stock-monitor-pool-filters-v2');
    }catch{}
    const w=window as any;
    w.__poolCalls=[];
    let poolFailures=Number(config.failPoolTimes||0);
    let backtestFailures=Number(config.failBacktestTimes||0);
    const clone=(value:any)=>JSON.parse(JSON.stringify(value));
    Object.assign(window,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
      metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
      async invoke(command:string,params:{method:string;args?:Record<string,unknown>}){
        if(command!=='rpc')return 0;
        w.__poolCalls.push({method:params.method,args:params.args??{}});
        switch(params.method){
          case 'snapshot':return {watch:[],events:[],config:{monitor:false},now:config.updatedAt,market_open:false,data_dir:'/tmp',rule:'r1'};
          case 'market':case 'market_overview':case 'index_minute':return {quotes:[],minute:null};
          case 'daily_outlook':return {issue:null,quotes:[],sectors:{},day:null,batch:null,schedule:''};
          case 'sector_flow':return {snapshot:null,running:false,error:''};
          case 'pool':{
            if(poolFailures>0){poolFailures-=1;throw Error('行情服务不可用');}
            if(config.delayPoolMs)await new Promise(resolve=>setTimeout(resolve,config.delayPoolMs));
            return {updated_at:config.updatedAt,quotes_time:config.quotesTime,trading:config.trading,error:'',
              entries:clone(config.entries),filtered_total:config.entries.length,has_more:false,offset:0,limit:200,
              benchmark:'上证指数',archived_count:0};
          }
          case 'pool_backtest':{
            if(backtestFailures>0){backtestFailures-=1;throw Error('回测服务不可用');}
            return clone(config.backtest);
          }
          case 'stock_search':return [{code:'sh601318',name:'中国平安',initials:'ZGPA'}];
          case 'pool_add':case 'pool_remove':case 'pool_sync':return {ok:true};
          case 'add_job':return {code:params.args?.code};
          case 'paper_sync':return {accounts:[],account:null,positions:[],orders:[],fills:[],order_count:0,fill_count:0};
          case 'paper_quote':return {code:params.args?.code,name:'甲科技',stamp:params.args?.stamp,price:1268,volume:0,source:'测试',token:'t',order_mode:'paper'};
          case 'paper_chart':return {points:[]};
          case 'trading_chart':return {code:'',day:'',accounts:[],points:[]};
          case 'chart':return [];
          case 'history':return {daily:[],days:[],events:[],source:{}};
          case 'volume_flow':return {code:params.args?.code,day:'',status:'unavailable',minutes:[],message:''};
          case 'events':case 'messages':return {items:[],total:0};
          case 'config':return {};
          case 'sources':return null;
          default:throw Error('测试未提供 '+params.method);
        }
      }
    }});
  },config);
  await page.goto('/');
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  const root=page.getByRole('region',{name:'股票池'});
  await expect(root).toBeVisible({timeout:15000});
  return root;
}

const tableRows=(page:Page)=>page.locator('.pt-row');
const waitRows=async(page:Page,count=ENTRIES.length)=>{
  await expect(tableRows(page)).toHaveCount(count,{timeout:15000});
};
const rowOf=(page:Page,name:string)=>page.locator('.pt-row').filter({hasText:name});
const rowCells=async(page:Page,name:string)=>{
  const row=rowOf(page,name);
  await expect(row).toHaveCount(1);
  return (await row.locator('.pt-cell').allInnerTexts()).map(text=>text.trim());
};
const firstRowName=async(page:Page)=>(await page.locator('.pt-row').first().locator('.pt-cell').nth(1).innerText()).trim();
const headButton=(page:Page,label:string)=>page.getByRole('button',{name:'按'+label+'排序'});
const rpcCalls=async(page:Page)=>page.evaluate(()=>((window as any).__poolCalls)||[]);
const waitRpc=async(page:Page,predicate:(call:{method:string;args:Json})=>boolean,timeout=10000)=>{
  await expect.poll(async()=>{
    const calls=await rpcCalls(page);
    return calls.some(call=>predicate(call));
  },{timeout}).toBe(true);
};
const noHorizontalOverflow=async(page:Page)=>{
  const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,body:document.body.scrollWidth}));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client+1);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.client+1);
};
const openBacktest=async(page:Page)=>{
  await page.getByRole('button',{name:'回测',exact:true}).click();
  const panel=page.getByRole('region',{name:'入选回测'});
  await expect(panel).toBeVisible();
  return panel;
};

// ===== 1. 标题条 =====
test('标题条：股票池 - N、行情时间/实时、上涨/下跌统计',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  await expect(page.locator('.pt-title')).toHaveText('股票池 - 8');
  const status=page.locator('.pt-title-status');
  await expect(status).toContainText('行情 10:37:12 · 实时');
  await expect(status).toContainText('上涨 3 / 下跌 2');
  await expect(status.locator('b.pt-up')).toHaveText('3');
  await expect(status.locator('b.pt-down')).toHaveText('2');
  await expect(page.locator('.pt-readonly')).toHaveCount(0);
  await expect(page.locator('.pt-footer')).toContainText('显示 8 / 共 8 只');
  await expect(page.locator('.pt-footer')).toContainText('不自动下单');
});

// ===== 2. 14 列表格与格式 =====
test('表格：14 列、时间/价格/收益/量比/换手格式与红涨绿跌、无行情行',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const heads=page.locator('.pt-head > span');
  await expect(heads).toHaveCount(14);
  const labels=await page.locator('.pt-head [role="columnheader"]').allInnerTexts();
  expect(labels.map(text=>text.trim())).toEqual(['代码','名称','入选时间▾','入选价格','入选收益','现价','涨幅','量比','换手','概念','题材','事件','行业/方向','入选次数']);
  const table=page.getByRole('table',{name:'股票池跟踪表'});
  await expect(table).toBeVisible();

  const jia=await rowCells(page,'甲科技');
  expect(jia).toEqual(['sz000001','甲科技','11-11 09:35','12.68','+3.20%','13.09','+2.10%','2.11','6.50%','智能穿戴','AI硬件/算力','军工订单','半导体','3']);
  const jiaRow=rowOf(page,'甲科技');
  await expect(jiaRow.locator('.pt-cell').nth(4)).toHaveClass(/pt-up/);
  await expect(jiaRow.locator('.pt-cell').nth(6)).toHaveClass(/pt-up/);
  await expect(jiaRow.locator('.pt-cell').nth(13)).toHaveAttribute('title','累计 3 次 · 今日 2 次 · 首次 2026-11-09 10:02 · 最近 2026-11-11 09:35');

  const yi=await rowCells(page,'乙材料');
  expect(yi[3]).toBe('20.50');
  expect(yi[4]).toBe('-1.50%');
  expect(yi[6]).toBe('-0.80%');
  await expect(rowOf(page,'乙材料').locator('.pt-cell').nth(4)).toHaveClass(/pt-down/);
  await expect(rowOf(page,'乙材料').locator('.pt-cell').nth(6)).toHaveClass(/pt-down/);

  const bing=await rowCells(page,'丙电子');
  expect(bing[4]).toBe('0.00%');
  expect(bing[6]).toBe('0.00%');
  expect(bing[7]).toBe('—');
  expect(bing[9]).toBe('—');
  await expect(rowOf(page,'丙电子').locator('.pt-cell').nth(4)).toHaveClass(/pt-flat/);
  await expect(rowOf(page,'丙电子').locator('.pt-cell').nth(9)).toHaveClass(/is-empty/);

  const ji=await rowCells(page,'己汽车');
  expect(ji[4]).toBe('—');
  expect(ji[5]).toBe('—');
  expect(ji[6]).toBe('—');
  expect(ji[7]).toBe('—');
  expect(ji[8]).toBe('—');
  await expect(rowOf(page,'己汽车').locator('.pt-cell').nth(5)).toHaveAttribute('title','行情待取得');

  // 标签 title 全量、单元格只显示前两个
  const wu=rowOf(page,'戊智能');
  await expect(wu.locator('.pt-cell').nth(9)).toHaveText('机器人 / 减速器');
  await expect(wu.locator('.pt-cell').nth(9)).toHaveAttribute('title','机器人 · 减速器 · 工业母机');
  await expect(wu.locator('.pt-cell').nth(2)).toHaveText('11-06 11:02');
});

// ===== 3. 排序 =====
test('排序：默认时间降序，7 个可排序列点击升降序且首行变化',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const timeHeader=page.locator('.pt-head > span').nth(2);
  await expect(timeHeader).toHaveAttribute('aria-sort','descending');
  expect(await firstRowName(page)).toBe('丁能源');
  await expect(page.getByRole('button',{name:'按入选时间排序'})).toHaveText('入选时间▾');
  expect(await page.getByRole('button',{name:/排序$/}).count()).toBe(7);

  await headButton(page,'入选时间').click();
  await expect(timeHeader).toHaveAttribute('aria-sort','ascending');
  expect(await firstRowName(page)).toBe('辛传媒');
  await expect(page.getByRole('button',{name:'按入选时间排序'})).toHaveText('入选时间▴');
  await headButton(page,'入选时间').click();
  expect(await firstRowName(page)).toBe('丁能源');

  const cases:[string,string,string][]=[
    ['入选价格','戊智能','丁能源'],
    ['入选收益','戊智能','庚医药'],
    ['涨幅','甲科技','戊智能'],
    ['量比','辛传媒','戊智能'],
    ['换手','丙电子','丁能源'],
    ['入选次数','戊智能','丙电子'],
  ];
  for(const [label,descFirst,ascFirst] of cases){
    await headButton(page,label).click();
    expect(await firstRowName(page)).toBe(descFirst);
    await headButton(page,label).click();
    expect(await firstRowName(page)).toBe(ascFirst);
  }
  // 排序下拉与表头排序一致（下拉只覆盖时间/收益的升降序组合）
  await headButton(page,'入选收益').click();
  await expect(page.getByLabel('排序',{exact:true})).toHaveValue('since-desc');
  expect(await firstRowName(page)).toBe('戊智能');
  await headButton(page,'入选收益').click();
  await expect(page.getByLabel('排序',{exact:true})).toHaveValue('since-asc');
  expect(await firstRowName(page)).toBe('庚医药');
});

// ===== 4. 筛选 chips =====
test('筛选：全部/今日入选/多次入选 chips 与清除筛选',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const chips=page.getByRole('group',{name:'入选筛选'});
  const all=chips.getByRole('button',{name:'全部 8'});
  const today=chips.getByRole('button',{name:'今日入选 2'});
  const multi=chips.getByRole('button',{name:'多次入选 5'});
  await expect(all).toHaveAttribute('aria-pressed','true');
  await expect(today).toBeVisible();
  await expect(multi).toBeVisible();
  await today.click();
  await expect(today).toHaveAttribute('aria-pressed','true');
  await waitRows(page,2);
  await expect(page.locator('.pt-footer')).toContainText('显示 2 / 共 8 只');
  const todayNames=await page.locator('.pt-row .pt-name').allInnerTexts();
  expect(todayNames.map(text=>text.trim()).sort()).toEqual(['丁能源','甲科技']);
  await expect(page.getByRole('button',{name:'清除筛选'})).toBeVisible();
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitRows(page);
  await expect(all).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('button',{name:'清除筛选'})).toHaveCount(0);
  await multi.click();
  await waitRows(page,5);
  const multiNames=(await page.locator('.pt-row .pt-name').allInnerTexts()).map(text=>text.trim()).sort();
  expect(multiNames).toEqual(['乙材料','庚医药','戊智能','甲科技','辛传媒'].sort());
});

// ===== 5. 时间范围筛选 =====
test('筛选：时间范围 今日/近3日/近5日/全部时间',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const period=page.getByLabel('时间范围');
  await expect(period).toHaveValue('all');
  const options=await period.locator('option').allInnerTexts();
  expect(options.map(text=>text.trim())).toEqual(['全部时间','今日','近3日','近5日']);
  await period.selectOption('today');
  await waitRows(page,2);
  expect((await page.locator('.pt-row .pt-time').allInnerTexts()).map(text=>text.trim())).toEqual(['11-11 10:37','11-11 09:35']);
  await period.selectOption('3d');
  await waitRows(page,4);
  await period.selectOption('5d');
  await waitRows(page,6);
  await expect(page.locator('.pt-footer')).toContainText('显示 6 / 共 8 只');
  await period.selectOption('all');
  await waitRows(page);
});

// ===== 6. 搜索 / 空结果 / 清除 =====
test('搜索：代码/名称/标签命中，空结果提示与清除筛选',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const search=page.getByLabel('搜索代码/名称/标签');
  await search.fill('军工');
  await waitRows(page,1);
  expect(await firstRowName(page)).toBe('甲科技');
  await search.fill('机器人');
  await waitRows(page,1);
  expect(await firstRowName(page)).toBe('戊智能');
  await search.fill('sz000007');
  await waitRows(page,1);
  expect(await firstRowName(page)).toBe('庚医药');
  await search.fill('不存在的标签');
  await expect(page.locator('.pt-empty')).toHaveText('当前筛选条件下没有标的。点「清除筛选」恢复。');
  await expect(page.locator('.pt-table')).toHaveCount(0);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitRows(page);
  await expect(search).toHaveValue('');
  await expect(page.getByRole('button',{name:'清除筛选'})).toHaveCount(0);
});

// ===== 7. 行展开详情 =====
test('详情：行点击展开，含入选信息/计划/入选统计/窗口表现/逐日快照/操作',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const row=rowOf(page,'甲科技');
  await expect(row).toHaveAttribute('aria-expanded','false');
  await expect(row).toHaveAttribute('aria-controls','pt-detail-sz000001');
  await row.click();
  await expect(row).toHaveAttribute('aria-expanded','true');
  await expect(row).toHaveClass(/is-open/);
  const detail=page.getByRole('region',{name:'详情 甲科技'});
  await expect(detail).toBeVisible();
  await expect(detail).toHaveAttribute('id','pt-detail-sz000001');
  for(const heading of ['入选信息','计划与关键价位','入选统计','窗口表现','逐日快照','操作']){
    await expect(detail.getByRole('heading',{name:new RegExp(heading)})).toBeVisible();
  }
  // 入选信息
  await expect(detail.locator('.pt-detail-strong')).toContainText('资金净流入、回踩买点；智能穿戴题材活跃。');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'来源'})).toContainText('建仓清单');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'方向'})).toContainText('半导体 · 低吸候选');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'入选'})).toContainText('2026-11-11 09:35 · 入选价格 12.68');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'跟进'})).toContainText('已跟踪 2 个交易日');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'跟进'})).toContainText('最大浮盈 +6.00%');
  await expect(detail.locator('.pt-detail-tags')).toContainText('概念 智能穿戴 · 题材 AI硬件/算力 · 事件 军工订单 · 其他 半导体');
  // 计划与关键价位
  await expect(detail).toContainText('11.80–12.40');
  await expect(detail).toContainText('13.00');
  await expect(detail).toContainText('11.20');
  await expect(detail).toContainText('14.20');
  await expect(detail).toContainText('15.60');
  await expect(detail).toContainText('12.60');
  await expect(detail).toContainText('回踩 11.80–12.40 分批；跌破 11.20 离场。');
  await expect(detail).toContainText('接近 14.20 分批减半。');
  // 入选统计
  await expect(detail.locator('.pt-kv > div').filter({hasText:'累计'})).toContainText('3 次 · 今日 2 次');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'首次'})).toContainText('2026-11-09 10:02');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'最近'})).toContainText('2026-11-11 09:35');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'量比/换手'})).toContainText('2.11 / 6.50%');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'振幅/流通'})).toContainText('3.20% / 123.4亿');
  // 窗口表现
  const windowTable=detail.locator('table.pt-mini').first();
  await expect(windowTable.locator('thead th')).toHaveText(['窗口','日期','收益','超额']);
  const windowCells=(await windowTable.locator('tbody tr').first().locator('td').allInnerTexts()).map(text=>text.trim());
  expect(windowCells).toEqual(['T+1','11-10','+2.50%','+1.50%']);
  await expect(windowTable.locator('tbody tr').first().locator('td').nth(2)).toHaveClass(/pt-up/);
  // 逐日快照
  const historyTable=detail.locator('table.pt-mini').nth(1);
  await expect(historyTable.locator('thead th')).toHaveText(['日期','收盘','涨跌','量比','换手','买','损','标']);
  const historyCells=(await historyTable.locator('tbody tr').first().locator('td').allInnerTexts()).map(text=>text.trim());
  expect(historyCells).toEqual(['11-10','12.90','+1.50%','2.50','7.20%','✓','—','—']);
  await expect(historyTable.locator('tbody tr').first().locator('td').nth(5)).toHaveClass(/pt-hit/);
  // 操作
  await expect(detail.getByRole('button',{name:'买入',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'卖出',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'K线',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'加自选',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'删除',exact:true})).toBeEnabled();
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/03-detail-1440.png'});
});

// ===== 8. 键盘展开 + 单行展开 =====
test('详情：键盘 Enter 展开/收起，同一时间只展开一行',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const first=page.locator('.pt-row').first();
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region',{name:'详情 丁能源'})).toBeVisible();
  await expect(first).toHaveAttribute('aria-expanded','true');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region',{name:'详情 丁能源'})).toHaveCount(0);
  await expect(first).toHaveAttribute('aria-expanded','false');
  await rowOf(page,'甲科技').click();
  await expect(page.getByRole('region',{name:'详情 甲科技'})).toBeVisible();
  await rowOf(page,'乙材料').click();
  await expect(page.getByRole('region',{name:'详情 乙材料'})).toBeVisible();
  await expect(page.getByRole('region',{name:'详情 甲科技'})).toHaveCount(0);
});

// ===== 9. 详情操作：K线/买入跳转、加自选 =====
test('详情操作：K线跳自选监控、买入跳模拟交易、加自选调用 add_job',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  await rowOf(page,'甲科技').click();
  const detail=page.getByRole('region',{name:'详情 甲科技'});
  await detail.getByRole('button',{name:'K线',exact:true}).click();
  await expect(page.locator('.workspace-heading h1')).toHaveText('自选监控');
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  await expect(page.getByRole('region',{name:'详情 甲科技'})).toBeVisible();
  await page.getByRole('region',{name:'详情 甲科技'}).getByRole('button',{name:'买入',exact:true}).click();
  await expect(page.locator('.workspace-heading h1')).toHaveText('模拟交易');
  await waitRpc(page,call=>call.method==='paper_sync');
  // 买入在模拟交易面板打开人工委托票据（模态），先关闭再回到股票池
  const closeTicket=page.getByRole('button',{name:'关闭真实委托'});
  await expect(closeTicket).toBeVisible({timeout:5000});
  await closeTicket.click();
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  await expect(page.getByRole('region',{name:'详情 甲科技'})).toBeVisible();
  await page.getByRole('region',{name:'详情 甲科技'}).getByRole('button',{name:'加自选',exact:true}).click();
  await waitRpc(page,call=>call.method==='add_job'&&call.args.code==='sz000001');
  await expect(page.locator('.pt-notice')).toHaveText('已请求加入自选：甲科技。');
});

// ===== 10. 删除二次确认 =====
test('详情删除：window.confirm 取消不调用，确认后调用 pool_remove',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  await rowOf(page,'甲科技').click();
  const detail=page.getByRole('region',{name:'详情 甲科技'});
  await expect(detail).toBeVisible();
  const dialogs:string[]=[];
  page.on('dialog',async dialog=>{
    dialogs.push(dialog.message());
    if(dialogs.length===1)await dialog.dismiss();
    else await dialog.accept();
  });
  await detail.getByRole('button',{name:'删除',exact:true}).click();
  await expect.poll(()=>dialogs.length).toBe(1);
  expect(dialogs[0]).toContain('确定从股票池删除 甲科技（sz000001）？');
  expect((await rpcCalls(page)).some(call=>call.method==='pool_remove')).toBe(false);
  await detail.getByRole('button',{name:'删除',exact:true}).click();
  await waitRpc(page,call=>call.method==='pool_remove'&&call.args.code==='sz000001');
  await expect(page.locator('.pt-notice')).toHaveText('已从股票池删除 甲科技');
  await expect(page.getByRole('region',{name:'详情 甲科技'})).toHaveCount(0);
});

// ===== 11. 回测面板摘要与口径 =====
test('回测面板：开关、摘要（T+1·n）、覆盖文案与口径说明',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const toggle=page.getByRole('button',{name:'回测',exact:true});
  await expect(toggle).toHaveAttribute('aria-pressed','false');
  expect((await rpcCalls(page)).some(call=>call.method==='pool_backtest')).toBe(false);
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed','true');
  const panel=page.getByRole('region',{name:'入选回测'});
  await expect(panel).toBeVisible();
  await waitRpc(page,call=>call.method==='pool_backtest');
  await expect(panel.locator('.pt-bt-summary')).toHaveText('样本 6 · 上涨占比（T+1·n=5） 60.0% · 平均收益 +0.58% · 平均超额 +0.18% · 已出结果 5 / 未到期 1 / 缺数据 0');
  await expect(panel.locator('.pt-bt-badge')).toHaveCount(0);
  const filters=panel.getByRole('group',{name:'回测筛选'});
  await expect(filters).toContainText('筛选后 6 / 全部 6');
  await expect(filters).toContainText('样本区间至 11-11');
  await expect(panel.getByLabel('回测入选时间')).toHaveValue('all');
  await expect(panel.getByLabel('回测入选次数')).toHaveValue('all');
  await expect(panel.getByLabel('回测入选涨幅')).toHaveValue('all');
  await expect(panel.getByLabel('回测来源')).toHaveValue('全部');
  const note=panel.locator('.pt-bt-note');
  await expect(note).toContainText('T+N = 首次入选日之后第 N 个交易日收盘 / 入选价格 − 1');
  await expect(note).toContainText('回测覆盖 6 只 · 有收益 5 只 · 基准 上证指数 · 本机日K覆盖 106 只 · 统计范围 50 期研判（2026-11-09~2026-11-11）');
  await expect(note).toContainText('未到期/缺数据不按 0 计');
  await expect(note).toContainText('不构成投资建议');
  await expect(note).toContainText('不自动下单');
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/04-backtest-1440.png'});
  await toggle.click();
  await expect(page.getByRole('region',{name:'入选回测'})).toHaveCount(0);
});

// ===== 12. 回测筛选联动 =====
test('回测筛选：入选时间/次数/涨幅/来源四项联动与重置',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const panel=await openBacktest(page);
  const filters=panel.getByRole('group',{name:'回测筛选'});
  const detailRows=()=>panel.locator('table.pt-bt-detail tbody tr');
  const filtered=()=>filters.innerText();
  await expect(detailRows()).toHaveCount(6);
  await panel.getByLabel('回测入选次数').selectOption('1');
  await expect(detailRows()).toHaveCount(2);
  await expect(filters).toContainText('筛选后 2 / 全部 6');
  await expect(detailRows().first()).toContainText('丙电子');
  await panel.getByRole('button',{name:'重置',exact:true}).click();
  await expect(detailRows()).toHaveCount(6);
  await panel.getByLabel('回测入选涨幅').selectOption('lt0');
  await expect(detailRows()).toHaveCount(1);
  await expect(detailRows().first()).toContainText('乙材料');
  await panel.getByRole('button',{name:'重置',exact:true}).click();
  await panel.getByLabel('回测来源').selectOption('炒作雷达');
  await expect(detailRows()).toHaveCount(2);
  const radarNames=(await detailRows().locator('td:nth-child(2)').allInnerTexts()).map(text=>text.trim()).sort();
  expect(radarNames).toEqual(['丙电子','己汽车'].sort());
  await panel.getByRole('button',{name:'重置',exact:true}).click();
  await panel.getByLabel('回测入选时间').selectOption('today');
  await expect(detailRows()).toHaveCount(2);
  await panel.getByLabel('回测入选时间').selectOption('3d');
  await expect(detailRows()).toHaveCount(4);
  await panel.getByLabel('回测入选时间').selectOption('5d');
  await expect(detailRows()).toHaveCount(5);
  await panel.getByLabel('回测入选时间').selectOption('all');
  await expect(detailRows()).toHaveCount(6);
  expect(await filtered()).toContain('筛选后 6 / 全部 6');
});

// ===== 13. 回测分桶表 =====
test('回测分桶表：表头、条数合计=筛选后行数、样本≤条数',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const panel=await openBacktest(page);
  const blocks=panel.locator('.pt-bt-block');
  await expect(blocks).toHaveCount(3);
  const titles=await blocks.locator('h5').allInnerTexts();
  expect(titles.map(text=>text.trim())).toEqual(['按入选次数','按入选涨幅','按入选时间（最近10个入选日）']);
  for(let index=0;index<3;index+=1){
    await expect(blocks.nth(index).locator('thead th')).toHaveText(['分桶','条数','样本','上涨占比','平均收益','平均超额']);
  }
  const cellTexts=async(block:Locator,rowIndex:number)=>{
    const row=block.locator('tbody tr').nth(rowIndex);
    return (await row.locator('td').allInnerTexts()).map(text=>text.trim());
  };
  const episodes=blocks.nth(0);
  await expect(episodes.locator('tbody tr')).toHaveCount(3);
  expect(await cellTexts(episodes,0)).toEqual(['1 次','2','1','0.0%','-1.10%','-0.50%']);
  expect(await cellTexts(episodes,1)).toEqual(['2 次','2','2','50.0%','+0.15%','-0.20%']);
  expect(await cellTexts(episodes,2)).toEqual(['3 次及以上','2','2','100.0%','+1.85%','+0.90%']);
  const percent=blocks.nth(1);
  await expect(percent.locator('tbody tr')).toHaveCount(5);
  expect(await cellTexts(percent,0)).toEqual(['< 0%','1','1','0.0%','-0.60%','-0.80%']);
  expect(await cellTexts(percent,1)).toEqual(['0–3%','2','1','100.0%','+0.90%','+0.40%']);
  expect(await cellTexts(percent,2)).toEqual(['3–7%','2','2','50.0%','+0.70%','+0.35%']);
  expect(await cellTexts(percent,3)).toEqual(['7% 以上','1','1','100.0%','+1.20%','+0.60%']);
  expect(await cellTexts(percent,4)).toEqual(['缺数据','0','0','—','—','—']);
  const byDay=blocks.nth(2);
  await expect(byDay.locator('tbody tr')).toHaveCount(5);
  expect(await cellTexts(byDay,0)).toEqual(['11-11','2','2','100.0%','+1.70%','+0.80%']);
  // 条数合计 = 当前筛选后明细行数；每个分桶 样本<=条数
  const detailCount=await panel.locator('table.pt-bt-detail tbody tr').count();
  for(const block of [episodes,percent,byDay]){
    const rows=block.locator('tbody tr');
    let sum=0;
    for(let index=0;index<await rows.count();index+=1){
      const cells=await cellTexts(block,index);
      const rowCount=Number(cells[1]);
      const sample=Number(cells[2]);
      sum+=rowCount;
      expect(sample).toBeLessThanOrEqual(rowCount);
    }
    expect(sum).toBe(detailCount);
  }
  // 筛选后分桶合计同步
  await panel.getByLabel('回测入选次数').selectOption('3+');
  await expect(panel.locator('table.pt-bt-detail tbody tr')).toHaveCount(2);
  const filteredSum=(await episodes.locator('tbody tr td:nth-child(2)').allInnerTexts()).map(Number).reduce((sum,value)=>sum+value,0);
  expect(filteredSum).toBe(2);
});

// ===== 14. 回测明细 =====
test('回测明细：T+1/T+3/T+5 未到期/缺数据/涨跌样式、入选时涨幅正负',async({page})=>{
  await boot(page,{});
  await waitRows(page);
  const panel=await openBacktest(page);
  const table=panel.locator('table.pt-bt-detail');
  await expect(table.locator('thead th')).toHaveText(['代码','名称','首次入选','入选价格','入选次数','入选时涨幅','T+1','T+3','T+5']);
  const rows=table.locator('tbody tr');
  await expect(rows).toHaveCount(6);
  const cellsOf=async(index:number)=>(await rows.nth(index).locator('td').allInnerTexts()).map(text=>text.trim());
  expect(await cellsOf(0)).toEqual(['sz000001','甲科技','11-11','12.68','3','+3.20%','+2.50%','未到期','缺数据']);
  await expect(rows.nth(0).locator('td').nth(5)).toHaveClass(/pt-up/);
  await expect(rows.nth(0).locator('td').nth(6)).toHaveClass(/pt-up/);
  await expect(rows.nth(0).locator('td').nth(7)).toHaveClass(/pt-pending/);
  await expect(rows.nth(0).locator('td').nth(8)).toHaveClass(/pt-missing/);
  expect(await cellsOf(1)).toEqual(['sz000006','己汽车','11-11','14.20','2','+0.80%','+0.90%','未到期','未到期']);
  expect(await cellsOf(2)).toEqual(['sz000002','乙材料','11-10','20.50','2','-1.40%','-0.60%','+1.10%','未到期']);
  await expect(rows.nth(2).locator('td').nth(5)).toHaveClass(/pt-down/);
  await expect(rows.nth(2).locator('td').nth(6)).toHaveClass(/pt-down/);
  await expect(rows.nth(2).locator('td').nth(7)).toHaveClass(/pt-up/);
  expect(await cellsOf(3)).toEqual(['sz000003','丙电子','11-09','9.86','1','0.00%','未到期','未到期','未到期']);
  expect(await cellsOf(4)).toEqual(['sz000004','丁能源','11-06','5.62','3','+8.50%','+1.20%','缺数据','未到期']);
  expect(await cellsOf(5)).toEqual(['sz000005','戊智能','11-04','30.10','1','+5.00%','-1.10%','未到期','未到期']);
  await expect(rows.nth(5).locator('td').nth(6)).toHaveClass(/pt-down/);
  await expect(rows.nth(0).locator('td').nth(6)).toHaveAttribute('title',/2026-11-12/);
});

// ===== 15. 回测错误态 =====
test('回测错误态：role=alert 错误条与重试恢复',async({page})=>{
  await boot(page,{failBacktestTimes:1});
  await waitRows(page);
  const panel=await openBacktest(page);
  const alert=panel.locator('.pt-error');
  await expect(alert).toBeVisible();
  await expect(alert).toHaveAttribute('role','alert');
  await expect(alert).toContainText('回测服务不可用');
  await alert.getByRole('button',{name:'重试',exact:true}).click();
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  await expect(panel.locator('.pt-error')).toHaveCount(0);
});

// ===== 16. 加载态 =====
test('加载态：读取中提示，数据到达后渲染表格',async({page})=>{
  await boot(page,{delayPoolMs:1200});
  await expect(page.locator('.pt-empty')).toContainText('股票池读取中…',{timeout:5000});
  await expect(page.locator('.pt-row')).toHaveCount(8,{timeout:15000});
  await expect(page.locator('.pt-empty')).toHaveCount(0);
});

// ===== 17. 主表错误态 =====
test('错误态：role=alert 错误条与重试恢复',async({page})=>{
  await boot(page,{failPoolTimes:1});
  const alert=page.locator('.pt-error');
  await expect(alert).toBeVisible({timeout:15000});
  await expect(alert).toHaveAttribute('role','alert');
  await expect(alert).toContainText('行情服务不可用');
  await expect(page.locator('.pt-title-status')).toContainText('行情 — · 读取中');
  await expect(page.locator('.pt-row')).toHaveCount(0);
  await alert.getByRole('button',{name:'重试',exact:true}).click();
  await waitRows(page);
  await expect(page.locator('.pt-error')).toHaveCount(0);
  await expect(page.locator('.pt-title-status')).toContainText('行情 10:37:12 · 实时');
});

// ===== 18. 空池空态 =====
test('空态：股票池为空时给出引导',async({page})=>{
  await boot(page,{entries:[]});
  const empty=page.locator('.pt-empty');
  await expect(empty).toBeVisible({timeout:15000});
  await expect(empty).toHaveText('股票池还没有标的。市场机会中可考虑建仓的标的、方向候选与题材启动信号会自动加入，也可点「添加」手动添加。');
  await expect(page.locator('.pt-title')).toHaveText('股票池 - 0');
  await expect(page.locator('.pt-row')).toHaveCount(0);
  await expect(page.locator('.pt-table')).toHaveCount(0);
  await expect(page.locator('.pt-footer')).toContainText('显示 0 / 共 0 只');
});

// ===== 19. 快照状态 =====
test('行情状态：休市快照显示“行情 HH:MM:SS · 快照”',async({page})=>{
  await boot(page,{trading:false});
  await waitRows(page);
  await expect(page.locator('.pt-title-status')).toContainText('行情 10:37:12 · 快照');
});

// ===== 20. 响应式 =====
test('响应式：1440/1000 无整页横滚，1000 容器横滚并隐藏题材/事件/行业方向三列',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitRows(page);
  await noHorizontalOverflow(page);
  const headCells=page.locator('.pt-head > span');
  await expect(headCells).toHaveCount(14);
  for(let index=0;index<14;index+=1)await expect(headCells.nth(index)).toBeVisible();
  await expect(page.locator('.pt-head > span.pt-col-theme')).toBeVisible();
  await expect(page.locator('.pt-head > span.pt-col-event')).toBeVisible();
  await expect(page.locator('.pt-head > span.pt-col-other')).toBeVisible();
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/01-table-1440.png'});

  await page.setViewportSize({width:1000,height:980});
  await noHorizontalOverflow(page);
  const scroll=page.locator('.pt-scroll');
  const scrollable=await scroll.evaluate(element=>({scrollWidth:element.scrollWidth,clientWidth:element.clientWidth}));
  expect(scrollable.scrollWidth).toBeGreaterThan(scrollable.clientWidth);
  await expect(page.locator('.pt-head > span.pt-col-theme')).toBeHidden();
  await expect(page.locator('.pt-head > span.pt-col-event')).toBeHidden();
  await expect(page.locator('.pt-head > span.pt-col-other')).toBeHidden();
  const visibleHeads=page.locator('.pt-head > span:visible');
  await expect(visibleHeads).toHaveCount(11);
  await expect(rowOf(page,'甲科技').locator('.pt-cell.pt-col-theme')).toBeHidden();
  await expect(rowOf(page,'甲科技').locator('.pt-cell.pt-col-event')).toBeHidden();
  await expect(rowOf(page,'甲科技').locator('.pt-cell.pt-col-other')).toBeHidden();
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/02-table-1000.png'});
  // 1000 下详情单列
  await rowOf(page,'甲科技').click();
  await expect(page.getByRole('region',{name:'详情 甲科技'})).toBeVisible();
  const detailColumns=await page.locator('.pt-detail-grid').evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length);
  expect(detailColumns).toBe(1);
  await noHorizontalOverflow(page);
  // 1000 下回测分桶单列且无整页横滚
  const panel=await openBacktest(page);
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  const bucketColumns=await panel.locator('.pt-bt-buckets').evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length);
  expect(bucketColumns).toBe(1);
  await noHorizontalOverflow(page);
});

// ===== 21. 只读预览 =====
test('只读预览：route 两个静态 JSON 渲染，交易/添加/删除禁用',async({page})=>{
  await page.route('**/pool-preview.json',async route=>{
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
      updated_at:UPDATED_AT,quotes_time:QUOTES_TIME,trading:false,error:'',
      entries:ENTRIES,filtered_total:ENTRIES.length,has_more:false,offset:0,limit:200,benchmark:'上证指数',archived_count:0,
    })});
  });
  await page.route('**/pool-backtest-preview.json',async route=>{
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(BACKTEST_DATA)});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  const root=page.getByRole('region',{name:'股票池'});
  await expect(root).toBeVisible();
  await waitRows(page);
  expect(await page.evaluate(()=>(window as any).__TAURI_INTERNALS__)).toBeUndefined();
  await expect(page.locator('.pt-readonly')).toHaveText('只读预览');
  await expect(page.locator('.pt-title-status')).toContainText('行情 10:37:12 · 快照');
  await expect(page.getByRole('button',{name:'添加',exact:true})).toBeDisabled();
  await rowOf(page,'甲科技').click();
  const detail=page.getByRole('region',{name:'详情 甲科技'});
  await expect(detail).toBeVisible();
  for(const label of ['买入','卖出','加自选','删除']){
    await expect(detail.getByRole('button',{name:label,exact:true})).toBeDisabled();
  }
  await expect(detail.getByRole('button',{name:'K线',exact:true})).toBeEnabled();
  await expect(detail.locator('.pt-muted').filter({hasText:'只读预览'})).toContainText('只读预览：添加/删除/自选/交易请在桌面客户端操作。');
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/05-preview-readonly.png'});
  const panel=await openBacktest(page);
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  await expect(panel.locator('.pt-bt-badge')).toHaveText('回放/历史样本');
  await expect(panel.locator('.pt-bt-note')).toContainText('不构成投资建议');
  expect((await rpcCalls(page)).length).toBe(0);
});

// ===== 22. console 无 error =====
test('console：浏览表格/排序/筛选/详情/回测无 console error 与 pageerror',async({page})=>{
  const consoleErrors:string[]=[];
  const pageErrors:string[]=[];
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
  page.on('pageerror',error=>pageErrors.push(String(error)));
  await boot(page,{});
  await waitRows(page);
  await headButton(page,'入选收益').click();
  await page.getByRole('group',{name:'入选筛选'}).getByRole('button',{name:'今日入选 2'}).click();
  await waitRows(page,2);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitRows(page);
  await rowOf(page,'甲科技').click();
  await expect(page.getByRole('region',{name:'详情 甲科技'})).toBeVisible();
  await rowOf(page,'甲科技').click();
  const panel=await openBacktest(page);
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  await panel.getByLabel('回测入选次数').selectOption('2');
  await expect(panel.locator('table.pt-bt-detail tbody tr')).toHaveCount(2);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
