import {test,expect,type Page,type Locator} from '@playwright/test';
import {mkdirSync} from 'node:fs';

// 股票池「瀑布流分组卡片 + 同义词归并 + 组头单行 + 回测」验收测试（2026-11-11 第四轮）。
// 依据 docs/pool-table/contract.md §12-§12.3 与当前 src/FocusPool.tsx / src/poolTableModel.ts。
// 只断言用户可见行为与稳定 class/aria；不重算业务规则，不依赖真实网络/真实库。
type Json=Record<string,any>;

try{mkdirSync('/tmp/pool-table-verify',{recursive:true});}catch{}
const SHOTS='/tmp/pool-table-verify';

const QUOTES_TIME='2026-11-11T12:45:00+08:00';
const UPDATED_AT='2026-11-11T12:46:00+08:00';

const quote=(price:number,percent:number,time='2026-11-11T12:44:00+08:00',basis:'live'|'last'='live')=>({
  price,percent,time,low:price*0.97,high:price*1.03,basis,fresh:basis==='live',
});
const planA=()=>({buy_low:11.8,buy_high:12.4,chase:13,target1:14.2,target2:15.6,trail:12.6,stop:11.2,
  note:'回踩 11.80–12.40 分批；跌破 11.20 离场。',sell_note:'接近 14.20 分批减半。'});
const planDefault=()=>({buy_low:9.5,buy_high:10,chase:11,stop:9,target1:11,target2:12,trail:9.5,
  note:'回踩 9.50–10.00 可分批；跌破 9.00 离场。',sell_note:'接近 11.00 分批减半。'});
const dayRow=(day:string,price:number,percent:number,options:Json={}):Json=>({
  day,price,percent,high:options.high??price*1.02,low:options.low??price*0.98,
  hit_buy:options.hit_buy??false,hit_stop:options.hit_stop??false,hit_target:options.hit_target??false,
  turnover_rate:options.turnover_rate??null,volume_ratio:options.volume_ratio??null,
});
const fund=(net_yi:number|null,net:number|null=null):Json=>(
  net_yi===null&&net===null?null:{net:net??(net_yi===null?null:net_yi*1e8),net_yi,rate:2,time:QUOTES_TIME}
);

// 默认 = 人形机器人组的「甲机器人」
const makeEntry=(over:Json):Json=>({
  code:'sz000101',name:'甲机器人',added_day:'2026-11-11',added_at:'2026-11-11T11:02:00+08:00',added_price:12.68,
  source:'建仓清单',sector:'人形机器人',role:'低吸候选',state:'可建仓',entry_tag:'可建仓',category:'概念',
  group_name:'人形机器人',groups:['概念','人形机器人'],
  reason:'资金净流入、回踩买点；人形机器人产业订单落地。',zone:'已进入买区',
  updated_at:UPDATED_AT,plan:planA(),quote:quote(13.74,4.2),
  today_percent:4.2,since_add_percent:8.4,distance_to_buy_percent:-1.2,hint:'提示',
  history:[
    dayRow('2026-11-10',13.2,2.4,{turnover_rate:7.2,volume_ratio:2.5,hit_buy:true}),
    dayRow('2026-11-11',13.74,4.2,{turnover_rate:6.5,volume_ratio:2.11}),
  ],
  max_gain_percent:8.4,max_drawdown_percent:-1.2,hold_days:2,
  windows:{'T+1':{n:1,date:'2026-11-10',close:13.2,return_percent:2.5,benchmark_return:1,excess_percent:1.5},'T+3':null,'T+5':null},
  episodes:{total:3,today:1,first_at:'2026-11-09T10:02:00+08:00',last_at:'2026-11-11T11:02:00+08:00'},
  quant:{turnover_rate:6.5,volume_ratio:2.11,amplitude:3.2,float_mcap_yi:123.4},
  tags:{concept:['机器人'],theme:['人形机器人','减速器'],event:['产业订单'],other:['高端制造']},
  driver:{at:'2026-11-11T10:00:00+08:00',text:'方向：人形机器人产业订单落地，核心零部件需求爆发，关注减速器与伺服系统供应链，订单能见度提升至2027年，回调可分批布局，不追高，跌破防守位离场。'},
  driver_short:'人形机器人订单落地，产业加速',
  driver_short_at:'2026-11-11T10:00:00+08:00',
  fund:fund(5.6),
  ...over,
});

// 11 只 / 6 组：同义词合并（机器人+人形机器人+工业机器人；光通信+通信设备；商业航天+卫星互联网；半导体+OLED），
// 名称辈/生肖噪声组兜底为「名称辈/生肖」，无任何 token 的进入「其他」；每组数量不限。
const ENTRIES:Json[]=[
  makeEntry({}),
  makeEntry({code:'sz000102',name:'乙减速器',sector:'机器人',added_at:'2026-11-11T10:15:00+08:00',added_price:20.5,
    role:'追涨候选',state:'观察',entry_tag:'观察',quote:quote(19.85,-2.1),today_percent:-2.1,since_add_percent:-3.2,
    max_gain_percent:2,max_drawdown_percent:-4,hold_days:1,
    history:[dayRow('2026-11-10',20.2,-1.1,{turnover_rate:3.1,volume_ratio:1})],
    windows:null,plan:planDefault(),
    episodes:{total:2,today:0,first_at:'2026-11-08T10:31:00+08:00',last_at:'2026-11-11T10:15:00+08:00'},
    quant:{turnover_rate:3.4,volume_ratio:1.03,amplitude:2.1,float_mcap_yi:88.8},
    tags:{concept:['减速器'],theme:[],event:['订单'],other:['机械']},
    driver:null,driver_short:'回踩低吸',driver_short_at:'2026-11-11T12:40:00+08:00',
    fund:fund(3)}),
  makeEntry({code:'sz000103',name:'丙伺服',sector:'工业机器人',added_day:'2026-11-06',added_at:'2026-11-06T14:31:00+08:00',
    added_price:5.62,zone:'等待回踩',quote:quote(5.74,1.5),today_percent:1.5,since_add_percent:2.2,
    role:'低吸候选',state:'观察',entry_tag:'观察',max_gain_percent:3,max_drawdown_percent:-0.8,hold_days:1,plan:planDefault(),
    history:[dayRow('2026-11-06',5.7,1.2,{turnover_rate:1.1,volume_ratio:0.9})],windows:null,
    episodes:{total:1,today:0,first_at:'2026-11-06T14:31:00+08:00',last_at:'2026-11-06T14:31:00+08:00'},
    quant:{turnover_rate:1.2,volume_ratio:0.88,amplitude:1.8,float_mcap_yi:40.2},
    tags:{concept:[],theme:['伺服'],event:[],other:[]},
    reason:'回踩低吸：伺服系统订单增长',driver:null,driver_short:null,driver_short_at:null,fund:null}),
  makeEntry({code:'sz000201',name:'丁光通信',sector:'光通信',added_at:'2026-11-11T09:41:00+08:00',added_price:8.8,
    source:'方向候选',quote:quote(9.25,2.6),today_percent:2.6,since_add_percent:5.1,hold_days:0,
    max_gain_percent:6,max_drawdown_percent:-1,plan:planDefault(),
    history:[dayRow('2026-11-11',9.25,2.6,{turnover_rate:4.6,volume_ratio:3.2})],
    windows:{'T+1':null,'T+3':null,'T+5':null},
    episodes:{total:1,today:1,first_at:'2026-11-11T09:41:00+08:00',last_at:'2026-11-11T09:41:00+08:00'},
    quant:{turnover_rate:4.6,volume_ratio:3.2,amplitude:5.5,float_mcap_yi:66.6},
    tags:{concept:['光通信'],theme:['光通信模块'],event:[],other:['通信']},
    driver:null,driver_short:'光通信股今早逆市走高',driver_short_at:'2026-11-11T10:30:00+08:00',fund:fund(1.2)}),
  makeEntry({code:'sz000202',name:'戊通信',sector:'通信设备',added_day:'2026-11-07',added_at:'2026-11-07T10:02:00+08:00',
    added_price:14.2,source:'方向候选',role:'追涨候选',zone:'等待回踩',quote:quote(13.92,-1.3),
    today_percent:-1.3,since_add_percent:-2,hold_days:2,max_gain_percent:1,max_drawdown_percent:-3,plan:planDefault(),
    history:[dayRow('2026-11-07',14.2,-1,{turnover_rate:3,volume_ratio:1.1})],windows:null,
    episodes:{total:2,today:0,first_at:'2026-11-05T10:31:00+08:00',last_at:'2026-11-07T10:02:00+08:00'},
    quant:{turnover_rate:3.1,volume_ratio:1.2,amplitude:4.2,float_mcap_yi:77.7},
    // 泛化 token「通信」的归组回归断言见「同义词分组回归」用例（修复前会被商业航天组的长关键词吸走）
    tags:{concept:['通信'],theme:[],event:[],other:['通信设备']},
    reason:'板块上涨且资金净流入；通信设备订单增长',
    driver:null,driver_short:'板块上涨、资金净流入',driver_short_at:'2026-11-11T12:10:00+08:00',fund:fund(-0.4)}),
  makeEntry({code:'sz000301',name:'己航天',sector:'商业航天',added_at:'2026-11-11T09:35:00+08:00',added_price:30.1,
    source:'炒作雷达',role:'观察候选',quote:quote(31.9,3.3),today_percent:3.3,since_add_percent:6,hold_days:1,
    max_gain_percent:8,max_drawdown_percent:-2,plan:planDefault(),
    history:[dayRow('2026-11-11',31.9,3.3,{turnover_rate:2.5,volume_ratio:1.1})],windows:null,
    episodes:{total:1,today:1,first_at:'2026-11-11T09:35:00+08:00',last_at:'2026-11-11T09:35:00+08:00'},
    quant:{turnover_rate:2.3,volume_ratio:0.8,amplitude:4.4,float_mcap_yi:210.5},
    tags:{concept:['商业航天'],theme:['卫星互联网'],event:[],other:['军工']},
    driver:{at:'2026-11-11T11:30:00+08:00',text:'方向：卫星互联网订单确认，发射排期密集'},
    driver_short:null,driver_short_at:null,fund:fund(2.5)}),
  makeEntry({code:'sz000302',name:'庚卫星',sector:'卫星互联网',added_day:'2026-11-10',added_at:'2026-11-10T13:01:00+08:00',
    added_price:9.86,source:'炒作雷达',role:'观察候选',zone:'等待回踩',quote:quote(9.75,-0.9),
    today_percent:-0.9,since_add_percent:-1.1,hold_days:2,max_gain_percent:1,max_drawdown_percent:-2.5,plan:planDefault(),
    history:[dayRow('2026-11-10',9.86,-0.5,{turnover_rate:9.1,volume_ratio:2})],windows:null,
    episodes:{total:1,today:0,first_at:'2026-11-10T13:01:00+08:00',last_at:'2026-11-10T13:01:00+08:00'},
    quant:{turnover_rate:9.9,volume_ratio:null,amplitude:7.1,float_mcap_yi:55.5},
    tags:{concept:['卫星通信'],theme:[],event:[],other:[]},
    driver:null,driver_short:null,driver_short_at:null,fund:null}),
  makeEntry({code:'sz000401',name:'辛半导体',sector:'半导体',added_day:'2026-11-10',added_at:'2026-11-10T09:35:00+08:00',
    added_price:10.2,source:'方向候选',quote:quote(10.65,3.1),today_percent:3.1,since_add_percent:4.4,hold_days:1,
    max_gain_percent:5,max_drawdown_percent:-1,plan:planDefault(),
    history:[dayRow('2026-11-10',10.2,2,{turnover_rate:7.5,volume_ratio:1.4})],windows:null,
    episodes:{total:3,today:0,first_at:'2026-11-08T10:31:00+08:00',last_at:'2026-11-10T09:35:00+08:00'},
    quant:{turnover_rate:7.8,volume_ratio:1.5,amplitude:3.3,float_mcap_yi:99.9},
    tags:{concept:['半导体'],theme:['芯片'],event:[],other:['电子']},
    driver:null,driver_short:'大摩高喊抄底半导体：资金回流',driver_short_at:'2026-11-11T10:20:00+08:00',fund:fund(-1.5)}),
  makeEntry({code:'sz000402',name:'壬OLED',sector:'OLED',added_day:'2026-11-09',added_at:'2026-11-09T13:01:00+08:00',
    added_price:15.5,source:'炒作雷达',role:'观察候选',zone:'等待回踩',quote:quote(15.19,-2),
    today_percent:-2,since_add_percent:-5.5,hold_days:3,max_gain_percent:0.5,max_drawdown_percent:-6,plan:planDefault(),
    history:[dayRow('2026-11-09',15.5,-1.5,{turnover_rate:4,volume_ratio:1.9})],windows:null,
    episodes:{total:2,today:0,first_at:'2026-11-07T09:41:00+08:00',last_at:'2026-11-09T13:01:00+08:00'},
    quant:{turnover_rate:4.2,volume_ratio:2,amplitude:4.4,float_mcap_yi:44.4},
    tags:{concept:['印制电路板'],theme:['OLED'],event:[],other:[]},
    driver:null,driver_short:'芯片股午后逆市拉升',driver_short_at:'2026-11-11T11:50:00+08:00',fund:fund(-0.5)}),
  makeEntry({code:'sz000501',name:'癸东方',sector:'东方',category:'名称辈',group_name:'东方',groups:['名称辈'],
    added_day:'2026-11-08',added_at:'2026-11-08T09:41:00+08:00',added_price:8.8,source:'炒作雷达',role:'观察候选',
    zone:'等待回踩',quote:quote(8.6,-1),today_percent:-1,since_add_percent:-2.3,hold_days:3,
    max_gain_percent:0.5,max_drawdown_percent:-4,plan:planDefault(),
    history:[dayRow('2026-11-08',8.8,-1,{turnover_rate:4,volume_ratio:1.9})],windows:null,
    episodes:{total:1,today:0,first_at:'2026-11-08T09:41:00+08:00',last_at:'2026-11-08T09:41:00+08:00'},
    quant:{turnover_rate:4.2,volume_ratio:2,amplitude:4.4,float_mcap_yi:44.4},
    tags:{concept:[],theme:['东方'],event:[],other:['名称辈']},
    reason:'东方系名称辈观察；只观察，不追高',
    driver:null,driver_short:null,driver_short_at:null,fund:null}),
  makeEntry({code:'sz000601',name:'子其他',sector:'',category:'其他',group_name:'其他',groups:['其他'],
    added_day:'2026-11-03',added_at:'2026-11-03T11:02:00+08:00',added_price:6.66,source:'炒作雷达',role:'观察候选',
    zone:'等待回踩',quote:null,today_percent:null,since_add_percent:null,hold_days:null,
    max_gain_percent:null,max_drawdown_percent:null,plan:planDefault(),history:[],windows:null,
    episodes:{total:1,today:0,first_at:'2026-11-03T11:02:00+08:00',last_at:'2026-11-03T11:02:00+08:00'},
    quant:{turnover_rate:null,volume_ratio:null,amplitude:null,float_mcap_yi:null},
    tags:{concept:[],theme:[],event:[],other:[]},
    reason:'',driver:null,driver_short:null,driver_short_at:null,fund:fund(0.5)}),
];

// ===== pool_backtest mock（契约 §1.3 / §2.2，沿用回测口径） =====
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
          case 'paper_quote':return {code:params.args?.code,name:'甲机器人',stamp:params.args?.stamp,price:1268,volume:0,source:'测试',token:'t',order_mode:'paper'};
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

const groupsLoc=(page:Page)=>page.locator('.pt-group');
const columnsLoc=(page:Page)=>page.locator('.pt-groups > .pt-group-col');
const waitGroups=async(page:Page,count=6)=>{
  await expect(groupsLoc(page)).toHaveCount(count,{timeout:15000});
};
const groupOf=(page:Page,label:string)=>page.locator('.pt-group').filter({hasText:label+' — '});
const groupLabels=async(page:Page)=>groupsLoc(page).evaluateAll(elements=>elements.map(element=>element.getAttribute('aria-label')));
const groupTitles=async(page:Page)=>(await groupsLoc(page).locator('.pt-group-title').allInnerTexts()).map(text=>text.trim());
const columnLabels=async(page:Page)=>columnsLoc(page).evaluateAll(columns=>columns.map(column=>[...column.querySelectorAll('.pt-group')].map(group=>group.getAttribute('aria-label'))));
const columnTitles=async(page:Page)=>columnsLoc(page).evaluateAll(columns=>columns.map(column=>[...column.querySelectorAll('.pt-group')].map(group=>{
  const title=group.querySelector('.pt-group-title');
  return (title?.textContent||'').trim();
})));
const columnFundValues=async(page:Page)=>columnsLoc(page).evaluateAll(columns=>columns.map(column=>[...column.querySelectorAll('.pt-group')].map(group=>{
  const text=(group.querySelector('.pt-group-stats .pt-group-stat:nth-child(3) b')?.textContent||'').trim();
  const match=text.match(/^([+-]?\d+\.\d{2})亿/);
  return match?parseFloat(match[1]):null;
})));
const firstColumnFundTexts=async(page:Page)=>columnsLoc(page).evaluateAll(columns=>columns.map(column=>{
  const group=column.querySelector('.pt-group');
  return (group?.querySelector('.pt-group-stats .pt-group-stat:nth-child(3) b')?.textContent||'').trim();
}));
const firstNameOf=async(group:Locator)=>(await group.locator('.pt-row').first().locator('.pt-name-text').innerText()).trim();
const rowCellsIn=async(group:Locator,name:string)=>{
  const row=group.locator('.pt-row').filter({hasText:name});
  await expect(row).toHaveCount(1);
  const cells=(await row.locator('.pt-cell').allInnerTexts()).map(text=>text.trim());
  cells[1]=(await row.locator('.pt-name-text').innerText()).trim();
  return cells;
};
const inlineOverflowProblems=async(page:Page)=>page.locator('.pt-group').evaluateAll(groups=>{
  const problems:string[]=[];
  for(const group of groups){
    for(const span of group.querySelectorAll('.pt-head > span')){
      if(span.scrollWidth>span.clientWidth+1)problems.push('表头省略:'+(span.textContent||''));
    }
    for(const cell of group.querySelectorAll('.pt-cell.pt-num')){
      if(cell.scrollWidth>cell.clientWidth+1)problems.push('数值省略:'+(cell.textContent||''));
    }
    for(const name of group.querySelectorAll('.pt-name-text')){
      if(name.scrollWidth>name.clientWidth+1)problems.push('名称省略:'+(name.textContent||''));
    }
  }
  return problems;
});
const waitRpc=async(page:Page,predicate:(call:{method:string;args:Json})=>boolean,timeout=10000)=>{
  await expect.poll(async()=>{
    const calls=await page.evaluate(()=>((window as any).__poolCalls)||[]);
    return calls.some(call=>predicate(call));
  },{timeout}).toBe(true);
};
const rpcCalls=async(page:Page)=>page.evaluate(()=>((window as any).__poolCalls)||[]);
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

// ===== 1. 瀑布流 + 同义词分组 + 无「其他方向」 + 组间资金倒序 =====
test('瀑布流分组：两列瀑布/间距 8px、同义词归并为 6 组且无「其他方向」、组间按资金倒序',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitGroups(page);
  // 同义词合并：机器人/人形机器人/工业机器人 → 人形机器人；光通信+通信设备 → 通信光通信；
  // 商业航天+卫星互联网 → 商业航天；半导体+OLED → 半导体电子；噪声只进「名称辈/生肖」；空标签进「其他」。
  // JS masonry 列优先 DOM 顺序：左列 [人形机器人, 其他, 半导体电子]，右列 [商业航天, 通信光通信, 名称辈/生肖]
  expect(await groupLabels(page)).toEqual([
    '分组 人形机器人','分组 其他','分组 半导体电子','分组 商业航天','分组 通信光通信','分组 名称辈/生肖',
  ]);
  expect(await groupTitles(page)).toEqual([
    '人形机器人 — 3 只','其他 — 1 只','半导体电子 — 2 只','商业航天 — 2 只','通信光通信 — 2 只','名称辈/生肖 — 1 只',
  ]);
  const human=groupOf(page,'人形机器人');
  const humanNames=(await human.locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(humanNames).toEqual(['丙伺服','乙减速器','甲机器人'].sort());
  const commNames=(await groupOf(page,'通信光通信').locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(commNames).toEqual(['丁光通信','戊通信'].sort());
  const spaceNames=(await groupOf(page,'商业航天').locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(spaceNames).toEqual(['庚卫星','己航天'].sort());
  await expect(groupOf(page,'名称辈/生肖').locator('.pt-name-text')).toHaveText('癸东方');
  await expect(groupOf(page,'其他').locator('.pt-name-text')).toHaveText('子其他');
  // 不再有「其他方向」/is-other 跨列逻辑
  await expect(page.locator('.pt-group.is-other')).toHaveCount(0);
  await expect(page.getByText('其他方向',{exact:true})).toHaveCount(0);
  await expect(page.getByText('其他方向',{exact:false})).toHaveCount(0);

  // 标题条/页脚
  await expect(page.locator('.pt-title')).toHaveText('股票池 - 11');
  await expect(page.locator('.pt-title-status')).toContainText('行情 12:45:00 · 实时');
  await expect(page.locator('.pt-title-status')).toContainText('上涨 5 / 下跌 5');
  await expect(page.locator('.pt-footer')).toContainText('显示 11 / 共 11 只 · 6 个方向');

  // JS masonry：两个显式列容器（非 CSS columns/inline-block），首行左=资金 Top1、右=资金 Top2
  await expect(columnsLoc(page)).toHaveCount(2);
  expect(await columnLabels(page)).toEqual([
    ['分组 人形机器人','分组 其他','分组 半导体电子'],
    ['分组 商业航天','分组 通信光通信','分组 名称辈/生肖'],
  ]);
  expect(await columnTitles(page)).toEqual([
    ['人形机器人 — 3 只','其他 — 1 只','半导体电子 — 2 只'],
    ['商业航天 — 2 只','通信光通信 — 2 只','名称辈/生肖 — 1 只'],
  ]);
  const columns=columnsLoc(page);
  await expect(columns.nth(0).locator('.pt-group').first()).toHaveAttribute('aria-label','分组 人形机器人');
  await expect(columns.nth(1).locator('.pt-group').first()).toHaveAttribute('aria-label','分组 商业航天');
  // mock 组资金 Top1/Top2 = 人形机器人 +8.60亿 / 商业航天 +2.50亿
  expect(await firstColumnFundTexts(page)).toEqual(['+8.60亿','+2.50亿']);
  // 两列等宽（差<=2px）；列间距 8px；卡片无 margin、同列卡片垂直间距 ≈8px
  const columnMetrics=await page.evaluate(()=>[...document.querySelectorAll('.pt-group-col')].map(column=>{
    const cards=[...column.querySelectorAll('.pt-group')].map(card=>card.getBoundingClientRect());
    const gaps:number[]=[];
    for(let index=1;index<cards.length;index+=1)gaps.push(Math.round(cards[index].top-cards[index-1].bottom));
    return {
      width:column.getBoundingClientRect().width,
      gap:getComputedStyle(column).gap,
      margins:[...column.querySelectorAll('.pt-group')].map(card=>getComputedStyle(card).margin),
      gaps,
    };
  }));
  expect(columnMetrics.length).toBe(2);
  expect(Math.abs(columnMetrics[0].width-columnMetrics[1].width)).toBeLessThanOrEqual(2);
  expect(columnMetrics[0].width).toBeGreaterThan(500);
  for(const metric of columnMetrics){
    expect(metric.gap).toBe('8px');
    for(const margin of metric.margins)expect(margin).toBe('0px');
    for(const gap of metric.gaps)expect(Math.abs(gap-8)).toBeLessThanOrEqual(1);
  }
  // 同一列内后续组的资金不大于前一组（缺失 — 视为最小）
  const columnFunds=await columnFundValues(page);
  expect(columnFunds.length).toBe(2);
  for(const funds of columnFunds){
    for(let index=1;index<funds.length;index+=1){
      const previous=funds[index-1]??-Infinity;
      const current=funds[index]??-Infinity;
      expect(current).toBeLessThanOrEqual(previous);
    }
  }
});

// ===== 2. 组头严格单行 + 统计 + 驱动短句 =====
test('组头：严格单行（height<28/nowrap/overflow hidden）、统计、具体新闻驱动优先与短句兜底',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitGroups(page);
  const human=groupOf(page,'人形机器人');
  const head=human.locator('.pt-group-head');
  const headStyle=await head.evaluate(element=>{
    const style=getComputedStyle(element);
    return {height:element.getBoundingClientRect().height,whiteSpace:style.whiteSpace,flexWrap:style.flexWrap,overflow:style.overflow};
  });
  expect(headStyle.whiteSpace).toBe('nowrap');
  expect(headStyle.flexWrap).toBe('nowrap');
  expect(headStyle.overflow).toBe('hidden');
  expect(headStyle.height).toBeLessThan(28);
  expect(headStyle.height).toBeGreaterThan(20);
  await expect(human.locator('.pt-group-title')).toHaveText('人形机器人 — 3 只');
  const stats=head.locator('.pt-group-stats');
  await expect(stats.locator('.pt-group-stat')).toHaveCount(3);
  await expect(stats.locator('.pt-group-stat').nth(0)).toHaveText('上涨 2/下跌 1');
  await expect(stats.locator('.pt-group-stat').nth(0).locator('b.pt-up')).toHaveText('2');
  await expect(stats.locator('.pt-group-stat').nth(0).locator('b.pt-down')).toHaveText('1');
  const inBuy=stats.locator('.pt-group-stat').nth(1);
  await expect(inBuy).toHaveText('当前符合 2');
  await expect(inBuy).toHaveAttribute('title','现价处于计划买区、当前仍符合入选条件，不代表建议买入');
  await expect(stats.locator('.pt-group-stat').nth(2)).toHaveText('资金净流入 +8.60亿');
  await expect(stats.locator('.pt-group-stat').nth(2).locator('b')).toHaveClass(/pt-up/);
  // 驱动：即使组内存在更晚的泛化短句（乙减速器 12:40「回踩低吸」），也优先具体新闻短句
  const driver=human.locator('.pt-group-driver');
  await expect(driver).toHaveText('驱动：人形机器人订单落地，产业加速');
  const driverText=driver.locator('.pt-driver-text');
  await expect(driverText).toHaveText('人形机器人订单落地，产业加速');
  await expect(driver).toHaveAttribute('title','人形机器人订单落地，产业加速');
  expect((await driverText.innerText()).length).toBeLessThanOrEqual(40);

  // 其它组统计/驱动
  const spaceStats=groupOf(page,'商业航天').locator('.pt-group-stats');
  await expect(spaceStats.locator('.pt-group-stat').nth(0)).toHaveText('上涨 1/下跌 1');
  await expect(spaceStats.locator('.pt-group-stat').nth(1)).toHaveText('当前符合 1');
  await expect(spaceStats.locator('.pt-group-stat').nth(2)).toHaveText('资金净流入 +2.50亿');
  await expect(groupOf(page,'商业航天').locator('.pt-group-driver')).toHaveText('驱动：卫星互联网订单确认，发射排期密集');

  const comm=groupOf(page,'通信光通信');
  await expect(comm.locator('.pt-group-stats .pt-group-stat').nth(1)).toHaveText('当前符合 1');
  await expect(comm.locator('.pt-group-stats .pt-group-stat').nth(2)).toHaveText('资金净流入 +0.80亿');
  await expect(comm.locator('.pt-group-driver')).toHaveText('驱动：光通信股今早逆市走高');

  const semi=groupOf(page,'半导体电子');
  await expect(semi.locator('.pt-group-stats .pt-group-stat').nth(2)).toHaveText('资金净流入 -2.00亿');
  await expect(semi.locator('.pt-group-stats .pt-group-stat').nth(2).locator('b')).toHaveClass(/pt-down/);
  // 同一组内两条短句：带新闻关键词+标点的「大摩…」优先于更晚的「芯片股午后逆市拉升」
  await expect(semi.locator('.pt-group-driver')).toHaveText('驱动：大摩高喊抄底半导体：资金回流');

  // 噪声组只有泛化短句时回退展示
  await expect(groupOf(page,'名称辈/生肖').locator('.pt-group-stats .pt-group-stat').nth(2)).toHaveText('资金净流入 —');
  await expect(groupOf(page,'名称辈/生肖').locator('.pt-group-driver')).toHaveText('驱动：只观察不追高');
  // 无驱动 → —
  await expect(groupOf(page,'其他').locator('.pt-group-driver')).toHaveText('驱动：—');
  await expect(groupOf(page,'其他').locator('.pt-group-stats .pt-group-stat').nth(2)).toHaveText('资金净流入 +0.50亿');
});

// ===== 2b. 同义词分组回归：泛化 token 不被更靠前分组的长关键词吸走 =====
test('分组回归：泛化 token 通信/能源/电机 归入正确组，不被商业航天/光伏新能源/人形机器人吸走',async({page})=>{
  const regressionEntries:Json[]=[
    makeEntry({code:'sz000701',name:'通信样本',sector:'',category:'概念',group_name:'',groups:[],
      added_day:'2026-11-11',added_at:'2026-11-11T10:00:00+08:00',added_price:10.1,quote:quote(10.2,1.2),
      today_percent:1.2,since_add_percent:1.2,zone:'等待回踩',plan:planDefault(),history:[],windows:null,
      episodes:{total:1,today:1,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'},
      quant:{turnover_rate:3.1,volume_ratio:1.1,amplitude:2,float_mcap_yi:50},
      reason:'通信设备订单增长',tags:{concept:['通信'],theme:[],event:[],other:[]},driver:null,driver_short:null,driver_short_at:null,fund:fund(1)}),
    makeEntry({code:'sz000702',name:'能源样本',sector:'',category:'题材',group_name:'',groups:[],
      added_day:'2026-11-11',added_at:'2026-11-11T10:05:00+08:00',added_price:8.2,quote:quote(8.3,2.1),
      today_percent:2.1,since_add_percent:2.1,zone:'等待回踩',plan:planDefault(),history:[],windows:null,
      episodes:{total:1,today:1,first_at:'2026-11-11T10:05:00+08:00',last_at:'2026-11-11T10:05:00+08:00'},
      quant:{turnover_rate:2.2,volume_ratio:1.2,amplitude:3,float_mcap_yi:60},
      reason:'电力需求回升',tags:{concept:[],theme:['能源'],event:[],other:[]},driver:null,driver_short:null,driver_short_at:null,fund:fund(2)}),
    makeEntry({code:'sz000703',name:'电机样本',sector:'',category:'概念',group_name:'',groups:[],
      added_day:'2026-11-11',added_at:'2026-11-11T10:10:00+08:00',added_price:6.6,quote:quote(6.7,3.2),
      today_percent:3.2,since_add_percent:3.2,zone:'等待回踩',plan:planDefault(),history:[],windows:null,
      episodes:{total:1,today:1,first_at:'2026-11-11T10:10:00+08:00',last_at:'2026-11-11T10:10:00+08:00'},
      quant:{turnover_rate:1.5,volume_ratio:0.9,amplitude:2,float_mcap_yi:40},
      reason:'家电电机订单增长',tags:{concept:['电机'],theme:[],event:[],other:[]},driver:null,driver_short:null,driver_short_at:null,fund:fund(3)}),
  ];
  await boot(page,{entries:regressionEntries});
  await waitGroups(page,3);
  // 组间按资金倒序：电机 +3.00 > 能源 +2.00 > 通信 +1.00
  expect((await groupLabels(page)).sort()).toEqual(['分组 家电电机','分组 能源电力','分组 通信光通信'].sort());
  expect((await groupTitles(page)).sort()).toEqual(['家电电机 — 1 只','能源电力 — 1 只','通信光通信 — 1 只'].sort());
  await expect(groupOf(page,'通信光通信').locator('.pt-name-text')).toHaveText('通信样本');
  await expect(groupOf(page,'能源电力').locator('.pt-name-text')).toHaveText('能源样本');
  await expect(groupOf(page,'家电电机').locator('.pt-name-text')).toHaveText('电机样本');
  // 修复前会被更靠前分组的长关键词吸走：通信→商业航天、能源→光伏新能源、电机→人形机器人
  const labels=await groupLabels(page);
  for(const wrong of ['商业航天','光伏新能源','人形机器人']){
    expect(labels).not.toContain('分组 '+wrong);
    await expect(page.getByText(wrong,{exact:false})).toHaveCount(0);
  }
});

// ===== 2c. 分组修复：同标签归并（名称辈/生肖 fallback 先于 sector 概念；标签命中优先） =====
test('分组修复：同「东方」标签的股票同组到名称辈/生肖，游戏标签归传媒娱乐且不含东方股',async({page})=>{
  const groupFixEntries:Json[]=[
    makeEntry({code:'sz000801',name:'大东方',sector:'快手概念',category:'名称辈',group_name:'',groups:[],
      added_day:'2026-11-11',added_at:'2026-11-11T10:20:00+08:00',added_price:5.2,quote:quote(5.3,1.1),
      today_percent:1.1,since_add_percent:1.1,zone:'等待回踩',plan:planDefault(),history:[],windows:null,
      episodes:{total:1,today:1,first_at:'2026-11-11T10:20:00+08:00',last_at:'2026-11-11T10:20:00+08:00'},
      quant:{turnover_rate:2.1,volume_ratio:1.1,amplitude:2,float_mcap_yi:30},
      tags:{concept:[],theme:['东方'],event:[],other:[]},reason:'东方系名称辈观察',
      driver:null,driver_short:null,driver_short_at:null,fund:fund(1)}),
    makeEntry({code:'sz000802',name:'京东方A',sector:'东方',category:'名称辈',group_name:'',groups:[],
      added_day:'2026-11-11',added_at:'2026-11-11T10:25:00+08:00',added_price:4.1,quote:quote(4.2,0.8),
      today_percent:0.8,since_add_percent:0.8,zone:'等待回踩',plan:planDefault(),history:[],windows:null,
      episodes:{total:1,today:1,first_at:'2026-11-11T10:25:00+08:00',last_at:'2026-11-11T10:25:00+08:00'},
      quant:{turnover_rate:1.8,volume_ratio:1,amplitude:2,float_mcap_yi:20},
      tags:{concept:[],theme:['东方'],event:[],other:[]},reason:'面板行业需求回升',
      driver:null,driver_short:null,driver_short_at:null,fund:fund(2)}),
    makeEntry({code:'sz000803',name:'游戏样本',sector:'游戏Ⅱ',category:'概念',group_name:'',groups:[],
      added_day:'2026-11-11',added_at:'2026-11-11T10:30:00+08:00',added_price:6.8,quote:quote(7,1.8),
      today_percent:1.8,since_add_percent:1.8,zone:'等待回踩',plan:planDefault(),history:[],windows:null,
      episodes:{total:1,today:1,first_at:'2026-11-11T10:30:00+08:00',last_at:'2026-11-11T10:30:00+08:00'},
      quant:{turnover_rate:3.2,volume_ratio:1.3,amplitude:3,float_mcap_yi:50},
      tags:{concept:['网络游戏'],theme:['IP'],event:[],other:[]},reason:'游戏版号获批',
      driver:null,driver_short:null,driver_short_at:null,fund:fund(2.5)}),
  ];
  await boot(page,{entries:groupFixEntries});
  await waitGroups(page,2);
  // A/B 虽 sector 分别为 快手概念/东方，但 theme「东方」命中名称辈/生肖 fallback（先于 sector 概念匹配）；
  // C 的 theme「IP」/concept「网络游戏」命中传媒娱乐。
  expect((await groupLabels(page)).sort()).toEqual(['分组 名称辈/生肖','分组 传媒娱乐'].sort());
  expect((await groupTitles(page)).sort()).toEqual(['名称辈/生肖 — 2 只','传媒娱乐 — 1 只'].sort());
  const nameGroup=groupOf(page,'名称辈/生肖');
  const mediaGroup=groupOf(page,'传媒娱乐');
  const nameNames=(await nameGroup.locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(nameNames).toEqual(['京东方A','大东方'].sort());
  await expect(mediaGroup.locator('.pt-name-text')).toHaveText('游戏样本');
  // 传媒娱乐组不得包含带「东方」标签的 A/B
  const mediaNames=(await mediaGroup.locator('.pt-name-text').allInnerTexts()).map(text=>text.trim());
  expect(mediaNames).not.toContain('大东方');
  expect(mediaNames).not.toContain('京东方A');
  await expect(page.locator('.pt-footer')).toContainText('显示 3 / 共 3 只 · 2 个方向');
});

// ===== 3. 卡片 10 列：代码 6 位/名称完整/换手无 %/右对齐/不省略/徽标 =====
test('卡片 10 列：代码 6 位、名称不省略、换手无 %、数值右对齐文本左对齐、表头与数值不省略、×N 徽标',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitGroups(page);
  const human=groupOf(page,'人形机器人');
  const heads=human.locator('.pt-head > span');
  await expect(heads).toHaveCount(10);
  const labels=(await human.locator('.pt-head [role="columnheader"]').allInnerTexts()).map(text=>text.replace(/[▾▴]/g,'').trim());
  expect(labels).toEqual(['代码','名称','入选时间','入选价格','现价','入选后涨幅','今日涨幅','量比','换手(%)','相关概念·题材']);
  await expect(human.getByRole('table',{name:'人形机器人 标的'})).toBeVisible();

  const jia=await rowCellsIn(human,'甲机器人');
  expect(jia).toEqual(['000101','甲机器人','11-11 11:02','12.68','13.74','+8.40%','+4.20%','2.11','6.50','人形机器人 / 减速器 / 机器人']);
  const jiaRow=human.locator('.pt-row').filter({hasText:'甲机器人'});
  await expect(jiaRow.locator('.pt-code')).toHaveAttribute('title','sz000101');
  await expect(jiaRow.locator('.pt-cell').nth(5)).toHaveClass(/pt-up/);
  await expect(jiaRow.locator('.pt-cell').nth(6)).toHaveClass(/pt-up/);
  await expect(jiaRow.locator('.pt-cell').nth(9)).toHaveAttribute('title','人形机器人 · 减速器 · 机器人 · 产业订单 · 高端制造');
  const jiaBadge=jiaRow.locator('.pt-count-badge');
  await expect(jiaBadge).toHaveText('×3');
  await expect(jiaBadge).toHaveAttribute('aria-label','入选 3 天');
  await expect(jiaBadge).toHaveAttribute('title','累计 3 天 · 今日已入选 · 首次 2026-11-09 10:02 · 最近 2026-11-11 11:02');

  const yi=await rowCellsIn(human,'乙减速器');
  expect(yi[3]).toBe('20.50');
  expect(yi[5]).toBe('-3.20%');
  expect(yi[6]).toBe('-2.10%');
  expect(yi[9]).toBe('减速器 / 订单 / 机械');
  await expect(human.locator('.pt-row').filter({hasText:'乙减速器'}).locator('.pt-count-badge')).toHaveText('×2');
  await expect(human.locator('.pt-row').filter({hasText:'乙减速器'}).locator('.pt-cell').nth(5)).toHaveClass(/pt-down/);

  // 代码：全部 6 位数字，title 保留完整 code
  const codes=await page.locator('.pt-code').evaluateAll(elements=>elements.map(element=>({text:(element.textContent||'').trim(),title:element.getAttribute('title')})));
  for(const code of codes){
    expect(code.text).toMatch(/^\d{6}$/);
    expect(code.title).toMatch(/^(sh|sz|bj)\d{6}$/);
    expect(code.text).toBe((code.title||'').slice(2));
  }
  // 换手行内去掉 %，title 说明单位
  const turnovers=await page.locator('.pt-cell.pt-col-turnover').evaluateAll(elements=>elements.map(element=>({text:(element.textContent||'').trim(),title:element.getAttribute('title')})));
  for(const turnover of turnovers){
    expect(turnover.text).not.toContain('%');
    expect(turnover.text).toMatch(/^(\d+\.\d{2}|—)$/);
    expect(turnover.title).toBe('换手率(%)');
  }
  // 名称完整不省略
  const nameOverflow=await page.locator('.pt-name-text').evaluateAll(elements=>elements.filter(element=>element.scrollWidth>element.clientWidth+1).map(element=>element.textContent));
  expect(nameOverflow).toEqual([]);

  // 对齐：数值列表头/单元格右对齐，文本列左对齐
  const headClasses=await heads.evaluateAll(elements=>elements.map(element=>element.className));
  const headJustify=await heads.evaluateAll(elements=>elements.map(element=>getComputedStyle(element).justifyContent));
  const numIndexes=[0,3,4,5,6,7,8];
  for(const index of numIndexes){
    expect(headClasses[index]).toContain('pt-head-num');
    expect(headJustify[index]).toBe('flex-end');
  }
  for(const index of [1,2,9]){
    expect(headClasses[index]).not.toContain('pt-head-num');
    expect(headJustify[index]).toBe('normal');
  }
  const numAlign=await page.locator('.pt-cell.pt-num').evaluateAll(elements=>elements.map(element=>getComputedStyle(element).textAlign));
  for(const align of numAlign)expect(align).toBe('right');
  expect(await human.locator('.pt-row').first().locator('.pt-time').evaluate(element=>getComputedStyle(element).textAlign)).not.toBe('right');
  expect(await human.locator('.pt-row').first().locator('.pt-col-tags').evaluate(element=>getComputedStyle(element).textAlign)).not.toBe('right');

  // 所有表头与数值不省略
  expect(await inlineOverflowProblems(page)).toEqual([]);
});

// ===== 4. 组内排序（组间顺序固定按资金） =====
test('组内排序：默认入选时间降序，6 个表头/下拉升降序只影响组内且组间资金顺序不变',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitGroups(page);
  const labelsBefore=await groupLabels(page);
  const human=groupOf(page,'人形机器人');
  await expect(human.locator('.pt-head > span').nth(2)).toHaveAttribute('aria-sort','descending');
  expect(await firstNameOf(human)).toBe('甲机器人');
  expect(await firstNameOf(groupOf(page,'商业航天'))).toBe('己航天');
  expect(await firstNameOf(groupOf(page,'其他'))).toBe('子其他');
  expect(await human.getByRole('button',{name:/^按.+排序$/}).count()).toBe(6);

  await human.getByRole('button',{name:'按入选后涨幅排序'}).click();
  await expect(human.locator('.pt-head > span').nth(5)).toHaveAttribute('aria-sort','descending');
  await expect(groupOf(page,'商业航天').locator('.pt-head > span').nth(5)).toHaveAttribute('aria-sort','descending');
  expect(await firstNameOf(human)).toBe('甲机器人');
  expect(await groupLabels(page)).toEqual(labelsBefore);
  await human.getByRole('button',{name:'按入选后涨幅排序'}).click();
  await expect(human.locator('.pt-head > span').nth(5)).toHaveAttribute('aria-sort','ascending');
  expect(await firstNameOf(human)).toBe('乙减速器');

  await human.getByRole('button',{name:'按入选价格排序'}).click();
  await expect(human.locator('.pt-head > span').nth(3)).toHaveAttribute('aria-sort','descending');
  expect(await firstNameOf(human)).toBe('乙减速器');
  await human.getByRole('button',{name:'按入选价格排序'}).click();
  expect(await firstNameOf(human)).toBe('丙伺服');

  await human.getByRole('button',{name:'按量比排序'}).click();
  expect(await firstNameOf(human)).toBe('甲机器人');
  await human.getByRole('button',{name:'按量比排序'}).click();
  expect(await firstNameOf(human)).toBe('丙伺服');

  await human.getByRole('button',{name:'按换手(%)排序'}).click();
  expect(await firstNameOf(human)).toBe('甲机器人');
  await human.getByRole('button',{name:'按换手(%)排序'}).click();
  expect(await firstNameOf(human)).toBe('丙伺服');

  const sortOptions=(await page.getByLabel('排序',{exact:true}).locator('option').allInnerTexts()).map(text=>text.trim());
  expect(sortOptions).toContain('入选天数 ↓');
  expect(sortOptions).toContain('入选天数 ↑');
  await page.getByLabel('排序',{exact:true}).selectOption('episodes-asc');
  expect(await firstNameOf(human)).toBe('丙伺服');
  expect(await groupLabels(page)).toEqual(labelsBefore);
  await page.getByLabel('排序',{exact:true}).selectOption('added-desc');
  expect(await firstNameOf(human)).toBe('甲机器人');
});

// ===== 5. 筛选 chips 重新分组、空组消失 =====
test('筛选 chips：今日入选/多次入选后重新分组、空组消失、清除筛选恢复',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const chips=page.getByRole('group',{name:'入选筛选'});
  const all=chips.getByRole('button',{name:'全部 11'});
  const today=chips.getByRole('button',{name:'今日入选 4'});
  const multi=chips.getByRole('button',{name:'多次入选 5'});
  await expect(all).toHaveAttribute('aria-pressed','true');
  await expect(today).toBeVisible();
  await expect(multi).toBeVisible();

  await today.click();
  await expect(today).toHaveAttribute('aria-pressed','true');
  await waitGroups(page,3);
  expect((await groupLabels(page)).sort()).toEqual(['分组 人形机器人','分组 商业航天','分组 通信光通信'].sort());
  expect((await groupTitles(page)).sort()).toEqual(['人形机器人 — 2 只','商业航天 — 1 只','通信光通信 — 1 只'].sort());
  await expect(page.locator('.pt-footer')).toContainText('显示 4 / 共 11 只 · 3 个方向');
  await expect(page.locator('.pt-row')).toHaveCount(4);
  await expect(page.getByRole('button',{name:'清除筛选'})).toBeVisible();
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page);
  await expect(all).toHaveAttribute('aria-pressed','true');

  await multi.click();
  await waitGroups(page,3);
  expect((await groupTitles(page)).sort()).toEqual(['人形机器人 — 2 只','通信光通信 — 1 只','半导体电子 — 2 只'].sort());
  await expect(page.locator('.pt-footer')).toContainText('显示 5 / 共 11 只 · 3 个方向');
  await expect(page.locator('.pt-row')).toHaveCount(5);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page);
});

// ===== 6. 时间范围筛选重新分组 =====
test('时间范围：近3日/近5日/今日筛选后重新分组并隐藏空组',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const period=page.getByLabel('时间范围');
  const options=(await period.locator('option').allInnerTexts()).map(text=>text.trim());
  expect(options).toEqual(['全部时间','今日','近3日','近5日']);
  await period.selectOption('3d');
  await waitGroups(page,4);
  expect((await groupTitles(page)).sort()).toEqual(['人形机器人 — 2 只','商业航天 — 2 只','通信光通信 — 1 只','半导体电子 — 2 只'].sort());
  await expect(page.locator('.pt-footer')).toContainText('显示 7 / 共 11 只 · 4 个方向');
  await period.selectOption('5d');
  await waitGroups(page,5);
  expect((await groupTitles(page)).sort()).toEqual(['人形机器人 — 3 只','商业航天 — 2 只','通信光通信 — 2 只','半导体电子 — 2 只','名称辈/生肖 — 1 只'].sort());
  await expect(page.locator('.pt-footer')).toContainText('显示 10 / 共 11 只 · 5 个方向');
  await period.selectOption('today');
  await waitGroups(page,3);
  expect((await groupTitles(page)).sort()).toEqual(['人形机器人 — 2 只','商业航天 — 1 只','通信光通信 — 1 只'].sort());
  await period.selectOption('all');
  await waitGroups(page);
  await expect(page.locator('.pt-footer')).toContainText('显示 11 / 共 11 只 · 6 个方向');
});

// ===== 7. 搜索 / 空结果 / 清除 =====
test('搜索：标签命中的股票重新分组（单只组保留），空结果提示与清除筛选',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const search=page.getByLabel('搜索代码/名称/标签');
  await search.fill('光通信');
  await waitGroups(page,1);
  expect(await groupLabels(page)).toEqual(['分组 通信光通信']);
  expect(await groupTitles(page)).toEqual(['通信光通信 — 1 只']);
  await expect(page.locator('.pt-row .pt-name-text')).toHaveText('丁光通信');
  await search.fill('卫星');
  await waitGroups(page,1);
  expect(await groupLabels(page)).toEqual(['分组 商业航天']);
  expect(await page.locator('.pt-row')).toHaveCount(2);
  await search.fill('不存在的标签');
  await expect(page.locator('.pt-empty')).toHaveText('当前筛选条件下没有标的。点「清除筛选」恢复。');
  await expect(page.locator('.pt-group')).toHaveCount(0);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page);
  await expect(search).toHaveValue('');
  await expect(page.getByRole('button',{name:'清除筛选'})).toHaveCount(0);
});

// ===== 8. 行展开详情 =====
test('详情：行点击展开，含入选信息/计划/入选统计/窗口表现/逐日快照/操作',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const human=groupOf(page,'人形机器人');
  const row=human.locator('.pt-row').filter({hasText:'甲机器人'});
  await expect(row).toHaveAttribute('aria-expanded','false');
  await expect(row).toHaveAttribute('aria-controls','pt-detail-sz000101');
  await row.click();
  await expect(row).toHaveAttribute('aria-expanded','true');
  const detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail).toBeVisible();
  await expect(detail).toHaveAttribute('id','pt-detail-sz000101');
  for(const heading of ['入选信息','计划与关键价位','入选统计','窗口表现','逐日快照','操作']){
    await expect(detail.getByRole('heading',{name:new RegExp(heading)})).toBeVisible();
  }
  await expect(detail.locator('.pt-detail-strong')).toContainText('资金净流入、回踩买点；人形机器人产业订单落地。');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'来源'})).toContainText('建仓清单');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'方向'})).toContainText('人形机器人 · 低吸候选');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'入选价格'})).toContainText('2026-11-11 11:02 · 入选价格 12.68');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'状态'})).toContainText('已进入买区');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'跟进'})).toContainText('已跟踪 2 个交易日');
  await expect(detail.locator('.pt-detail-tags')).toContainText('概念 机器人 · 题材 人形机器人 · 减速器 · 事件 产业订单 · 其他 高端制造');
  for(const text of ['11.80–12.40','13.00','11.20','14.20','15.60','12.60','回踩 11.80–12.40 分批；跌破 11.20 离场。']){
    await expect(detail).toContainText(text);
  }
  await expect(detail.locator('.pt-kv > div').filter({hasText:'累计'})).toContainText('3 天 · 今日已入选');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'首次'})).toContainText('2026-11-09 10:02');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'量比/换手'})).toContainText('2.11 / 6.50%');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'振幅/流通'})).toContainText('3.20% / 123.4亿');
  const windowTable=detail.locator('table.pt-mini').first();
  await expect(windowTable.locator('thead th')).toHaveText(['窗口','日期','收益','超额']);
  const windowCells=(await windowTable.locator('tbody tr').first().locator('td').allInnerTexts()).map(text=>text.trim());
  expect(windowCells).toEqual(['T+1','11-10','+2.50%','+1.50%']);
  await expect(windowTable.locator('tbody tr').first().locator('td').nth(2)).toHaveClass(/pt-up/);
  const historyTable=detail.locator('table.pt-mini').nth(1);
  await expect(historyTable.locator('thead th')).toHaveText(['日期','收盘','涨跌','量比','换手','买','损','标']);
  const historyCells=(await historyTable.locator('tbody tr').first().locator('td').allInnerTexts()).map(text=>text.trim());
  expect(historyCells).toEqual(['11-10','13.20','+2.40%','2.50','7.20%','✓','—','—']);
  await expect(detail.getByRole('button',{name:'买入',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'卖出',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'K线',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'加自选',exact:true})).toBeEnabled();
  await expect(detail.getByRole('button',{name:'删除',exact:true})).toBeEnabled();
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/03-detail-1440.png'});
  // 今日未入选的股票：累计行文案为「N 天 · 今日未入选」
  await row.click();
  await human.locator('.pt-row').filter({hasText:'乙减速器'}).click();
  const notToday=page.getByRole('region',{name:'详情 乙减速器'});
  await expect(notToday).toBeVisible();
  await expect(notToday.locator('.pt-kv > div').filter({hasText:'累计'})).toContainText('2 天 · 今日未入选');
});

// ===== 9. 键盘展开 + 单行展开 =====
test('详情：键盘 Enter 展开/收起，同一时间只展开一行',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const human=groupOf(page,'人形机器人');
  const first=human.locator('.pt-row').first();
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region',{name:'详情 甲机器人'})).toBeVisible();
  await expect(first).toHaveAttribute('aria-expanded','true');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region',{name:'详情 甲机器人'})).toHaveCount(0);
  await human.locator('.pt-row').filter({hasText:'甲机器人'}).click();
  await expect(page.getByRole('region',{name:'详情 甲机器人'})).toBeVisible();
  await groupOf(page,'商业航天').locator('.pt-row').first().click();
  await expect(page.getByRole('region',{name:'详情 己航天'})).toBeVisible();
  await expect(page.getByRole('region',{name:'详情 甲机器人'})).toHaveCount(0);
});

// ===== 10. 详情操作：K线/买入/加自选 =====
test('详情操作：K线跳自选监控、买入跳模拟交易、加自选调用 add_job',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  await groupOf(page,'人形机器人').locator('.pt-row').filter({hasText:'甲机器人'}).click();
  let detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail).toBeVisible();
  await detail.getByRole('button',{name:'K线',exact:true}).click();
  await expect(page.locator('.workspace-heading h1')).toHaveText('自选监控');
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail).toBeVisible();
  await detail.getByRole('button',{name:'买入',exact:true}).click();
  await expect(page.locator('.workspace-heading h1')).toHaveText('模拟交易');
  await waitRpc(page,call=>call.method==='paper_sync');
  const closeTicket=page.getByRole('button',{name:'关闭真实委托'});
  await expect(closeTicket).toBeVisible({timeout:5000});
  await closeTicket.click();
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail).toBeVisible();
  await detail.getByRole('button',{name:'加自选',exact:true}).click();
  await waitRpc(page,call=>call.method==='add_job'&&call.args.code==='sz000101');
  await expect(page.locator('.pt-notice')).toHaveText('已请求加入自选：甲机器人。');
});

// ===== 11. 删除二次确认 =====
test('详情删除：window.confirm 取消不调用，确认后调用 pool_remove',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  await groupOf(page,'人形机器人').locator('.pt-row').filter({hasText:'甲机器人'}).click();
  const detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail).toBeVisible();
  const dialogs:string[]=[];
  page.on('dialog',async dialog=>{
    dialogs.push(dialog.message());
    if(dialogs.length===1)await dialog.dismiss();
    else await dialog.accept();
  });
  await detail.getByRole('button',{name:'删除',exact:true}).click();
  await expect.poll(()=>dialogs.length).toBe(1);
  expect(dialogs[0]).toContain('确定从股票池删除 甲机器人（sz000101）？');
  expect((await rpcCalls(page)).some(call=>call.method==='pool_remove')).toBe(false);
  await detail.getByRole('button',{name:'删除',exact:true}).click();
  await waitRpc(page,call=>call.method==='pool_remove'&&call.args.code==='sz000101');
  await expect(page.locator('.pt-notice')).toHaveText('已从股票池删除 甲机器人');
  await expect(page.getByRole('region',{name:'详情 甲机器人'})).toHaveCount(0);
});

// ===== 12. 回测面板摘要与口径 =====
test('回测面板：开关、摘要（T+1·n）、覆盖文案与口径说明',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
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
  const episodeFilter=panel.getByLabel('回测入选天数');
  await expect(episodeFilter).toHaveValue('all');
  expect((await episodeFilter.locator('option').allInnerTexts()).map(text=>text.trim())).toEqual(['全部天数','1 天','2 天','3 天及以上']);
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

// ===== 13. 回测筛选联动 =====
test('回测筛选：入选时间/次数/涨幅/来源四项联动与重置',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const panel=await openBacktest(page);
  const filters=panel.getByRole('group',{name:'回测筛选'});
  const detailRows=()=>panel.locator('table.pt-bt-detail tbody tr');
  await expect(detailRows()).toHaveCount(6);
  await panel.getByLabel('回测入选天数').selectOption('1');
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
  expect(await filters.innerText()).toContain('筛选后 6 / 全部 6');
});

// ===== 14. 回测分桶表 =====
test('回测分桶表：表头、条数合计=筛选后行数、样本≤条数',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const panel=await openBacktest(page);
  const blocks=panel.locator('.pt-bt-block');
  await expect(blocks).toHaveCount(3);
  const titles=(await blocks.locator('h5').allInnerTexts()).map(text=>text.trim());
  expect(titles).toEqual(['按入选天数','按入选涨幅','按入选时间（最近10个入选日）']);
  for(let index=0;index<3;index+=1){
    await expect(blocks.nth(index).locator('thead th')).toHaveText(['分桶','条数','样本','上涨占比','平均收益','平均超额']);
  }
  const cellTexts=async(block:Locator,rowIndex:number)=>{
    const row=block.locator('tbody tr').nth(rowIndex);
    return (await row.locator('td').allInnerTexts()).map(text=>text.trim());
  };
  const episodes=blocks.nth(0);
  await expect(episodes.locator('tbody tr')).toHaveCount(3);
  expect(await cellTexts(episodes,0)).toEqual(['1 天','2','1','0.0%','-1.10%','-0.50%']);
  expect(await cellTexts(episodes,1)).toEqual(['2 天','2','2','50.0%','+0.15%','-0.20%']);
  expect(await cellTexts(episodes,2)).toEqual(['3 天及以上','2','2','100.0%','+1.85%','+0.90%']);
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
  await panel.getByLabel('回测入选天数').selectOption('3+');
  await expect(panel.locator('table.pt-bt-detail tbody tr')).toHaveCount(2);
  const filteredSum=(await episodes.locator('tbody tr td:nth-child(2)').allInnerTexts()).map(Number).reduce((sum,value)=>sum+value,0);
  expect(filteredSum).toBe(2);
});

// ===== 15. 回测明细 =====
test('回测明细：T+1/T+3/T+5 未到期/缺数据/涨跌样式、入选时涨幅正负',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const panel=await openBacktest(page);
  const table=panel.locator('table.pt-bt-detail');
  await expect(table.locator('thead th')).toHaveText(['代码','名称','首次入选','入选价格','入选天数','入选时涨幅','T+1','T+3','T+5']);
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

// ===== 16. 回测错误态 =====
test('回测错误态：role=alert 错误条与重试恢复',async({page})=>{
  await boot(page,{failBacktestTimes:1});
  await waitGroups(page);
  const panel=await openBacktest(page);
  const alert=panel.locator('.pt-error');
  await expect(alert).toBeVisible();
  await expect(alert).toHaveAttribute('role','alert');
  await expect(alert).toContainText('回测服务不可用');
  await alert.getByRole('button',{name:'重试',exact:true}).click();
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  await expect(panel.locator('.pt-error')).toHaveCount(0);
});

// ===== 17. 加载态 =====
test('加载态：读取中提示，数据到达后渲染分组',async({page})=>{
  await boot(page,{delayPoolMs:1200});
  await expect(page.locator('.pt-empty')).toContainText('股票池读取中…',{timeout:5000});
  await waitGroups(page);
  await expect(page.locator('.pt-empty')).toHaveCount(0);
});

// ===== 18. 主错误态 =====
test('错误态：role=alert 错误条与重试恢复',async({page})=>{
  await boot(page,{failPoolTimes:1});
  const alert=page.locator('.pt-error');
  await expect(alert).toBeVisible({timeout:15000});
  await expect(alert).toHaveAttribute('role','alert');
  await expect(alert).toContainText('行情服务不可用');
  await expect(page.locator('.pt-title-status')).toContainText('行情 — · 读取中');
  await expect(page.locator('.pt-row')).toHaveCount(0);
  await alert.getByRole('button',{name:'重试',exact:true}).click();
  await waitGroups(page);
  await expect(page.locator('.pt-error')).toHaveCount(0);
  await expect(page.locator('.pt-title-status')).toContainText('行情 12:45:00 · 实时');
});

// ===== 19. 空池空态 =====
test('空态：股票池为空时给出引导',async({page})=>{
  await boot(page,{entries:[]});
  const empty=page.locator('.pt-empty');
  await expect(empty).toBeVisible({timeout:15000});
  await expect(empty).toHaveText('股票池还没有标的。市场机会中可考虑建仓的标的、方向候选与题材启动信号会自动加入，也可点「添加」手动添加。');
  await expect(page.locator('.pt-title')).toHaveText('股票池 - 0');
  await expect(page.locator('.pt-group')).toHaveCount(0);
  await expect(page.locator('.pt-footer')).toContainText('显示 0 / 共 0 只 · 0 个方向');
});

// ===== 20. 快照状态 =====
test('行情状态：休市快照显示“行情 HH:MM:SS · 快照”',async({page})=>{
  await boot(page,{trading:false});
  await waitGroups(page);
  await expect(page.locator('.pt-title-status')).toContainText('行情 12:45:00 · 快照');
});

// ===== 21. 响应式 =====
test('响应式：1440 JS masonry 两列（首行 Top1/Top2、等宽、间距 8px）；1000 单列仍 10 列全可见且无整页横滚',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitGroups(page);
  await noHorizontalOverflow(page);
  // 1440：两个显式列容器，首行左=资金 Top1、右=资金 Top2；两列等宽、列内卡片间距 8px
  await expect(columnsLoc(page)).toHaveCount(2);
  expect(await firstColumnFundTexts(page)).toEqual(['+8.60亿','+2.50亿']);
  const columnMetrics1440=await page.evaluate(()=>[...document.querySelectorAll('.pt-group-col')].map(column=>{
    const cards=[...column.querySelectorAll('.pt-group')].map(card=>card.getBoundingClientRect());
    const gaps:number[]=[];
    for(let index=1;index<cards.length;index+=1)gaps.push(Math.round(cards[index].top-cards[index-1].bottom));
    return {width:column.getBoundingClientRect().width,gap:getComputedStyle(column).gap,gaps};
  }));
  const widths=columnMetrics1440.map(metric=>metric.width);
  expect(Math.abs(widths[0]-widths[1])).toBeLessThanOrEqual(2);
  expect(widths[0]).toBeGreaterThan(500);
  for(const metric of columnMetrics1440){
    expect(metric.gap).toBe('8px');
    for(const gap of metric.gaps)expect(Math.abs(gap-8)).toBeLessThanOrEqual(1);
  }
  // 组内顺序：同一列后续组资金不高于前一组（缺失 — 视为最小）
  const columnFunds1440=await columnFundValues(page);
  for(const funds of columnFunds1440){
    for(let index=1;index<funds.length;index+=1){
      expect(funds[index]??-Infinity).toBeLessThanOrEqual(funds[index-1]??-Infinity);
    }
  }
  const human=groupOf(page,'人形机器人');
  await expect(human.locator('.pt-head > span')).toHaveCount(10);
  for(let index=0;index<10;index+=1)await expect(human.locator('.pt-head > span').nth(index)).toBeVisible();
  const headHeight1440=await human.locator('.pt-group-head').evaluate(element=>element.getBoundingClientRect().height);
  expect(headHeight1440).toBeLessThan(28);
  const innerScroll1440=await groupsLoc(page).evaluateAll(groups=>groups.map(group=>{
    const scroller=group.querySelector(':scope > .pt-scroll') as HTMLElement;
    return {scrollWidth:scroller.scrollWidth,clientWidth:scroller.clientWidth};
  }));
  for(const item of innerScroll1440)expect(item.scrollWidth).toBeLessThanOrEqual(item.clientWidth+1);
  expect(await inlineOverflowProblems(page)).toEqual([]);
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/01-masonry-1440.png'});

  // 1000：单列（matchMedia 1108 断点触发重排），10 列仍全部可见
  await page.setViewportSize({width:1000,height:980});
  await expect(columnsLoc(page)).toHaveCount(1,{timeout:5000});
  await noHorizontalOverflow(page);
  await expect(human.locator('.pt-head > span')).toHaveCount(10);
  for(let index=0;index<10;index+=1)await expect(human.locator('.pt-head > span').nth(index)).toBeVisible();
  const headHeight1000=await human.locator('.pt-group-head').evaluate(element=>element.getBoundingClientRect().height);
  expect(headHeight1000).toBeLessThan(28);
  const innerScroll1000=await groupsLoc(page).evaluateAll(groups=>groups.map(group=>{
    const scroller=group.querySelector(':scope > .pt-scroll') as HTMLElement;
    return {scrollWidth:scroller.scrollWidth,clientWidth:scroller.clientWidth};
  }));
  for(const item of innerScroll1000)expect(item.scrollWidth).toBeLessThanOrEqual(item.clientWidth+1);
  expect(await inlineOverflowProblems(page)).toEqual([]);
  // 单列时组顺序 = 全局资金倒序
  const singleColumnLabels=await columnLabels(page);
  expect(singleColumnLabels.length).toBe(1);
  expect(singleColumnLabels[0]).toEqual(['分组 人形机器人','分组 商业航天','分组 通信光通信','分组 其他','分组 半导体电子','分组 名称辈/生肖']);
  await expect(human.locator('.pt-row').first().locator('.pt-count-badge')).toBeVisible();
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/02-masonry-1000.png'});

  // 1000 下详情/回测仍单列，均无整页横滚
  await human.locator('.pt-row').filter({hasText:'甲机器人'}).click();
  await expect(page.getByRole('region',{name:'详情 甲机器人'})).toBeVisible();
  const detailColumns=await page.locator('.pt-detail-grid').evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length);
  expect(detailColumns).toBe(1);
  await noHorizontalOverflow(page);
  const panel=await openBacktest(page);
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  const bucketColumns=await panel.locator('.pt-bt-buckets').evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length);
  expect(bucketColumns).toBe(1);
  await noHorizontalOverflow(page);
});

// ===== 22. 只读预览 =====
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
  await waitGroups(page);
  expect(await page.evaluate(()=>(window as any).__TAURI_INTERNALS__)).toBeUndefined();
  await expect(page.locator('.pt-readonly')).toHaveText('只读预览');
  await expect(page.locator('.pt-title-status')).toContainText('行情 12:45:00 · 快照');
  await expect(page.getByRole('button',{name:'添加',exact:true})).toBeDisabled();
  await groupOf(page,'人形机器人').locator('.pt-row').filter({hasText:'甲机器人'}).click();
  const detail=page.getByRole('region',{name:'详情 甲机器人'});
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

// ===== 23. console 无 error =====
test('console：瀑布流浏览/排序/筛选/详情/回测无 console error 与 pageerror',async({page})=>{
  const consoleErrors:string[]=[];
  const pageErrors:string[]=[];
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
  page.on('pageerror',error=>pageErrors.push(String(error)));
  await boot(page,{});
  await waitGroups(page);
  await groupOf(page,'人形机器人').getByRole('button',{name:'按入选后涨幅排序'}).click();
  await page.getByRole('group',{name:'入选筛选'}).getByRole('button',{name:'今日入选 4'}).click();
  await waitGroups(page,3);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page);
  await groupOf(page,'人形机器人').locator('.pt-row').first().click();
  await expect(page.getByRole('region',{name:'详情 甲机器人'})).toBeVisible();
  await groupOf(page,'人形机器人').locator('.pt-row').first().click();
  const panel=await openBacktest(page);
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  await panel.getByLabel('回测入选天数').selectOption('2');
  await expect(panel.locator('table.pt-bt-detail tbody tr')).toHaveCount(2);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
