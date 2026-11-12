import {test,expect,type Page,type Locator} from '@playwright/test';
import {existsSync,mkdirSync,readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {auditGrouping,entryTime,groupKey,NOISE_TOKENS,relatedTagsOf,relatedTagsText,rowCounts,type Entry} from '../../src/poolTableModel';

// 股票池「瀑布流分组卡片 + 同义词归并 + 组头单行 + 回测」验收测试（2026-11-11 第四轮）。
// 依据 docs/pool-table/contract.md §12-§12.3 与当前 src/FocusPool.tsx / src/poolTableModel.ts。
// 只断言用户可见行为与稳定 class/aria；不重算业务规则，不依赖真实网络/真实库。
type Json=Record<string,any>;

try{mkdirSync('/tmp/pool-table-verify',{recursive:true});}catch{}
const SHOTS='/tmp/pool-table-verify';

// 置顶相关用例：每个用例首次导航前清空置顶 localStorage；同一用例内 reload 时保留（用于持久化断言）
test.beforeEach(async({page})=>{
  await page.addInitScript(()=>{
    try{
      if(!sessionStorage.getItem('pool-test-pin-inited')){
        localStorage.removeItem('stock-monitor-pool-pinned-v1');
        sessionStorage.setItem('pool-test-pin-inited','1');
      }
    }catch{}
  });
});

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
const makeEntry=(over:Json):Json=>{
  const entry:Json={
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
  };
  // 默认补 selection（契约第九轮）：first_at 取 added_at 以保持既有入选时间列/排序；
  // 测试可用 over.selection 覆盖（09:25 映射、today/last_day 口径等）。
  if(over.selection===undefined){
    const episodes=entry.episodes;
    const lastAt=episodes&&typeof episodes==='object'&&typeof episodes.last_at==='string'?episodes.last_at:(entry.added_at??null);
    const total=episodes&&typeof episodes==='object'&&typeof episodes.total==='number'?episodes.total:1;
    const today=episodes&&typeof episodes==='object'&&typeof episodes.today==='number'?(episodes.today>0?1:0):0;
    entry.selection={
      first_at:entry.added_at??null,
      first_day:entry.added_day,
      last_at:lastAt,
      last_day:lastAt&&lastAt.length>=10?lastAt.slice(0,10):entry.added_day,
      days:total,
      today,
    };
  }
  return entry;
};

// 11 只 / 6 组：同义词合并（机器人+人形机器人+工业机器人；光通信+通信设备；商业航天+卫星互联网；半导体+OLED），
// 首标签（theme→concept→event→other，跳过噪声）即组键：命中同义词→规范组名，未命中→标签本身；无标签才回退 sector，全空进「其他」。每组数量不限。
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
  emptyChart?:boolean;
  today?:string;
  calendarToday?:string;
  quotesTime?:string;
  messages?:Json[];
};

// Tauri rpc mock：pool / pool_backtest 为主，其余为主应用启动所需的最小响应。
async function boot(page:Page,options:BootOptions={}):Promise<Locator>{
  const config={
    entries:options.entries??ENTRIES,
    backtest:options.backtest??BACKTEST_DATA,
    trading:options.trading!==false,
    quotesTime:options.quotesTime??QUOTES_TIME,
    updatedAt:UPDATED_AT,
    failPoolTimes:options.failPoolTimes??0,
    failBacktestTimes:options.failBacktestTimes??0,
    delayPoolMs:options.delayPoolMs??0,
    emptyChart:Boolean(options.emptyChart),
    today:options.today??'2026-11-11',
    calendarToday:options.calendarToday??options.today??'2026-11-11',
    messages:options.messages??[],
  };
  await page.addInitScript((config:Json)=>{
    try{
      localStorage.removeItem('stock-monitor-pool-terminal-v1');
      localStorage.removeItem('stock-monitor-pool-terminal-v2');
      localStorage.removeItem('stock-monitor-pool-view');
      localStorage.removeItem('stock-monitor-pool-filters-v2');
    }catch{}
    const w=window as any;
    w.__poolCalls=[];
    // 行详情内嵌图表所需的最小行情：分时 4 根 + 日K 60 根（可被 emptyChart 覆盖分时）
    const minuteBars=[
      {time:'09:30',close:'10.00',volume:100,complete:true,average:'10.00'},
      {time:'09:31',close:'10.01',volume:120,complete:true,average:'10.005'},
      {time:'09:32',close:'10.02',volume:90,complete:true,average:'10.01'},
      {time:'09:33',close:'10.03',volume:80,complete:true,average:'10.015'},
      {time:'09:34',close:'10.04',volume:70,complete:true,average:'10.02'},
    ];
    const dailyRows=(()=>{
      const base=new Date(Date.UTC(2026,10,11));
      return Array.from({length:60},(_,index)=>{
        const day=new Date(base);day.setUTCDate(day.getUTCDate()-(59-index));
        const value=(9.5+index*0.01).toFixed(2);
        return {date:day.toISOString().slice(0,10),open:value,close:(Number(value)+0.05).toFixed(2),
          high:(Number(value)+0.1).toFixed(2),low:(Number(value)-0.1).toFixed(2),volume:String(1000+index)};
      });
    })();
    let poolFailures=Number(config.failPoolTimes||0);
    let backtestFailures=Number(config.failBacktestTimes||0);
    const clone=(value:any)=>JSON.parse(JSON.stringify(value));
    Object.assign(window,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
      metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
      async invoke(command:string,params:{method:string;args?:Record<string,unknown>}){
        if(command!=='rpc')return 0;
        w.__poolCalls.push({method:params.method,args:params.args??{}});
        switch(params.method){
          case 'snapshot':return {watch:[{code:'sh603002',name:'甲科技',enabled:1,health:'正常',candidates:[],quote:null,broker_sources:[]}],events:[],config:{monitor:false},now:config.updatedAt,market_open:false,data_dir:'/tmp',rule:'r1'};
          case 'market':case 'market_overview':case 'index_minute':return {quotes:[],minute:null};
          case 'daily_outlook':return {issue:null,quotes:[],sectors:{},day:null,batch:null,schedule:''};
          case 'sector_flow':return {snapshot:null,running:false,error:''};
          case 'pool':{
            if(poolFailures>0){poolFailures-=1;throw Error('行情服务不可用');}
            if(config.delayPoolMs)await new Promise(resolve=>setTimeout(resolve,config.delayPoolMs));
            const offset=Number(params.args?.offset||0),limit=Number(params.args?.limit||200);
            return {updated_at:config.updatedAt,quotes_time:config.quotesTime,today:config.today,calendar_today:config.calendarToday,trading:config.trading,error:'',
              entries:clone(config.entries.slice(offset,offset+limit)),filtered_total:config.entries.length,has_more:offset+limit<config.entries.length,offset,limit,
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
          case 'chart':{
            const kind=params.args?.kind;
            if(kind==='minute')return config.emptyChart?[]:[{day:'2026-11-11',data:{bars:minuteBars,previous_close:'10'}}];
            if(kind==='daily')return [{day:'2026-11-11',data:dailyRows[dailyRows.length-1]}];
            return [];
          }
          case 'history':return {code:params.args?.code,daily:dailyRows,days:[],events:[],source:{},minute_days:[]};
          case 'minute_ensure':return {job:'mock-minute'};
          case 'daily_load':return {job:'mock-daily'};
          case 'job':return {status:'done',result:null};
          case 'volume_flow':return {code:params.args?.code,day:'',status:'unavailable',minutes:[],message:''};
          case 'events':return {items:[],total:0};
          case 'messages':{
            const items=config.messages.filter((m:Json)=>(!params.args?.unread||!m.read_at)&&(!params.args?.category||
              (params.args.category==='pool_alert'?m.payload.kind==='POOL_ALERT':m.category===params.args.category&&m.payload.kind!=='POOL_ALERT')));
            return {items:clone(items),total:items.length};
          }
          case 'message_read':{
            for(const m of config.messages)if(params.args?.all||params.args?.id===m.id)m.read_at=config.updatedAt;
            return {ok:true};
          }
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
  const text=(group.querySelector('.pt-group-stats .pt-group-stat:nth-child(2) b')?.textContent||'').trim();
  const match=text.match(/^([+-]?\d+\.\d{2})亿/);
  return match?parseFloat(match[1]):null;
})));
const firstColumnFundTexts=async(page:Page)=>columnsLoc(page).evaluateAll(columns=>columns.map(column=>{
  const group=column.querySelector('.pt-group');
  return (group?.querySelector('.pt-group-stats .pt-group-stat:nth-child(2) b')?.textContent||'').trim();
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
  // 商业航天+卫星互联网 → 商业航天；半导体+OLED → 半导体电子；首标签「东方」未命中同义词表 → 组名直接用「东方」；空标签进「其他」。
  // JS masonry 列优先 DOM 顺序：左列 [人形机器人, 其他, 半导体电子]，右列 [商业航天, 通信光通信, 东方]
  expect(await groupLabels(page)).toEqual([
    '分组 人形机器人','分组 其他','分组 半导体电子','分组 商业航天','分组 通信光通信','分组 东方',
  ]);
  expect(await groupTitles(page)).toEqual([
    '人形机器人 — 3 只','其他 — 1 只','半导体电子 — 2 只','商业航天 — 2 只','通信光通信 — 2 只','东方 — 1 只',
  ]);
  const human=groupOf(page,'人形机器人');
  const humanNames=(await human.locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(humanNames).toEqual(['丙伺服','乙减速器','甲机器人'].sort());
  const commNames=(await groupOf(page,'通信光通信').locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(commNames).toEqual(['丁光通信','戊通信'].sort());
  const spaceNames=(await groupOf(page,'商业航天').locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(spaceNames).toEqual(['庚卫星','己航天'].sort());
  await expect(groupOf(page,'东方').locator('.pt-name-text')).toHaveText('癸东方');
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
    ['分组 商业航天','分组 通信光通信','分组 东方'],
  ]);
  expect(await columnTitles(page)).toEqual([
    ['人形机器人 — 3 只','其他 — 1 只','半导体电子 — 2 只'],
    ['商业航天 — 2 只','通信光通信 — 2 只','东方 — 1 只'],
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
  expect(headStyle.height).toBeLessThan(40);
  expect(headStyle.height).toBeGreaterThan(20);
  // 仍为单行：组名/统计/驱动/置顶按钮顶边基本对齐（无换行）
  const headRows=await head.evaluate(element=>{const boxes=['.pt-group-title','.pt-group-stats','.pt-group-driver','.pt-pin'].map(selector=>element.querySelector(selector)?.getBoundingClientRect().top??-1);return {tops:boxes,height:element.getBoundingClientRect().height};});
  for(const top of headRows.tops.slice(1))expect(Math.abs(top-headRows.tops[0])).toBeLessThanOrEqual(6);
  await expect(human.locator('.pt-group-title')).toHaveText('人形机器人 — 3 只');
  const stats=head.locator('.pt-group-stats');
  // 组头不再有「当前符合」统计：只剩 上涨/下跌、资金净流入
  await expect(stats.locator('.pt-group-stat')).toHaveCount(2);
  await expect(head).not.toContainText('当前符合');
  await expect(stats.locator('.pt-group-stat').nth(0)).toHaveText('上涨 2/下跌 1');
  await expect(stats.locator('.pt-group-stat').nth(0).locator('b.pt-up')).toHaveText('2');
  await expect(stats.locator('.pt-group-stat').nth(0).locator('b.pt-down')).toHaveText('1');
  await expect(stats.locator('.pt-group-stat').nth(1)).toHaveText('资金净流入 +8.60亿');
  await expect(stats.locator('.pt-group-stat').nth(1).locator('b')).toHaveClass(/pt-up/);
  // 组头末尾置顶按钮：svg + aria-label/aria-pressed
  const pin=head.locator('.pt-pin');
  await expect(pin).toHaveCount(1);
  await expect(pin.locator('svg')).toHaveCount(1);
  await expect(pin).toHaveAttribute('aria-label','置顶 人形机器人');
  await expect(pin).toHaveAttribute('aria-pressed','false');
  // 新 pin 样式：20×20、圆角 6、1px 边框、svg viewBox 24 且 12×12
  const pinStyle=await pin.evaluate(element=>{
    const style=getComputedStyle(element);
    const svg=element.querySelector('svg');
    return {width:style.width,height:style.height,radius:style.borderRadius,borderWidth:style.borderTopWidth,
      viewBox:svg?.getAttribute('viewBox'),svgWidth:svg?.getAttribute('width'),svgHeight:svg?.getAttribute('height')};
  });
  expect(pinStyle.width).toBe('20px');
  expect(pinStyle.height).toBe('20px');
  expect(pinStyle.radius).toBe('6px');
  expect(pinStyle.borderWidth).toBe('1px');
  expect(pinStyle.viewBox).toBe('0 0 24 24');
  expect(pinStyle.svgWidth).toBe('12');
  expect(pinStyle.svgHeight).toBe('12');
  // 驱动：即使组内存在更晚的泛化短句（乙减速器 12:40「回踩低吸」），也优先具体新闻短句
  const driver=human.locator('.pt-group-driver');
  await expect(driver).toHaveText('驱动：人形机器人订单落地，产业加速');
  const driverText=driver.locator('.pt-driver-text');
  await expect(driverText).toHaveText('人形机器人订单落地，产业加速');
  await expect(driver).toHaveAttribute('title','人形机器人订单落地，产业加速');
  expect((await driverText.innerText()).length).toBeLessThanOrEqual(40);
  expect((await driverText.innerText()).endsWith('…')).toBe(false);

  // 其它组统计/驱动（资金净流入显示数值）
  const spaceStats=groupOf(page,'商业航天').locator('.pt-group-stats');
  await expect(spaceStats.locator('.pt-group-stat')).toHaveCount(2);
  await expect(spaceStats.locator('.pt-group-stat').nth(0)).toHaveText('上涨 1/下跌 1');
  await expect(spaceStats.locator('.pt-group-stat').nth(1)).toHaveText('资金净流入 +2.50亿');
  await expect(groupOf(page,'商业航天').locator('.pt-group-driver')).toHaveText('驱动：卫星互联网订单确认，发射排期密集');
  expect((await groupOf(page,'商业航天').locator('.pt-driver-text').innerText()).endsWith('…')).toBe(false);

  const comm=groupOf(page,'通信光通信');
  await expect(comm.locator('.pt-group-stats .pt-group-stat')).toHaveCount(2);
  await expect(comm.locator('.pt-group-stats .pt-group-stat').nth(1)).toHaveText('资金净流入 +0.80亿');
  await expect(comm.locator('.pt-group-driver')).toHaveText('驱动：光通信股今早逆市走高');

  const semi=groupOf(page,'半导体电子');
  await expect(semi.locator('.pt-group-stats .pt-group-stat').nth(1)).toHaveText('资金净流入 -2.00亿');
  await expect(semi.locator('.pt-group-stats .pt-group-stat').nth(1).locator('b')).toHaveClass(/pt-down/);
  // 驱动相关性：半导体组的关键词为「半导体电子 / 芯片 / OLED」，「大摩高喊抄底半导体」不含关键词→不作为组头驱动；含「芯片」的短句保留
  await expect(semi.locator('.pt-group-driver')).toHaveText('驱动：芯片股午后逆市拉升');
  expect((await semi.locator('.pt-driver-text').innerText()).endsWith('…')).toBe(false);

  // 无同义词命中的标签组（东方）只有泛化短句时回退展示
  await expect(groupOf(page,'东方').locator('.pt-group-stats .pt-group-stat').nth(1)).toHaveText('资金净流入 —');
  await expect(groupOf(page,'东方').locator('.pt-group-driver')).toHaveText('驱动：只观察不追高');
  // 无驱动 → —
  await expect(groupOf(page,'其他').locator('.pt-group-driver')).toHaveText('驱动：—');
  await expect(groupOf(page,'其他').locator('.pt-group-stats .pt-group-stat').nth(1)).toHaveText('资金净流入 +0.50亿');
  // 每个组头都有置顶按钮
  await expect(page.locator('.pt-group .pt-pin')).toHaveCount(6);
  for(const group of await groupsLoc(page).all()){
    await expect(group.locator('.pt-group-head .pt-pin')).toHaveCount(1);
  }
  // 组头资金净流入 = 组内成员 fund.net_yi 之和（缺失不计，2 位小数；无有效值显示 —）
  const fundByFullName=new Map<string,number|null>();
  for(const entry of ENTRIES){
    const net=entry.fund&&typeof entry.fund.net_yi==='number'?entry.fund.net_yi:null;
    fundByFullName.set(String(entry.name),net);
  }
  for(const label of ['人形机器人','商业航天','通信光通信','其他','半导体电子','东方']){
    const group=groupOf(page,label);
    const memberNames=await group.locator('.pt-row .pt-name').evaluateAll(elements=>elements.map(element=>element.getAttribute('title')));
    let sum=0;
    let seen=false;
    for(const name of memberNames){
      const value=fundByFullName.get(name||'');
      if(typeof value==='number'){sum+=value;seen=true;}
    }
    const total=Math.round(sum*100)/100;
    const expected=seen?(total>0?'+':'')+total.toFixed(2)+'亿':'—';
    await expect(group.locator('.pt-group-stats .pt-group-stat').nth(1).locator('b')).toHaveText(expected);
  }
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

// ===== 2c. 分组修复：同一标签必须同组（首标签即组键；未命中同义词直接用标签作组名） =====
test('分组修复：首标签优先——东方同组、2027 羊年（跨年）不被通信/商业航天吸走、IP 归传媒娱乐',async({page})=>{
  const makeCase=(code:string,name:string,sector:string,theme:string[],concept:string[],netYi:number,reasonText:string)=>makeEntry({
    code,name,sector,category:'概念',group_name:'',groups:[],
    added_day:'2026-11-11',added_at:'2026-11-11T10:20:00+08:00',added_price:5.2,quote:quote(5.3,1.1),
    today_percent:1.1,since_add_percent:1.1,zone:'等待回踩',plan:planDefault(),history:[],windows:null,
    episodes:{total:1,today:1,first_at:'2026-11-11T10:20:00+08:00',last_at:'2026-11-11T10:20:00+08:00'},
    quant:{turnover_rate:2.1,volume_ratio:1.1,amplitude:2,float_mcap_yi:30},
    tags:{concept,theme,event:[],other:[]},reason:reasonText,
    driver:null,driver_short:null,driver_short_at:null,fund:fund(netYi),
  });
  const groupFixEntries:Json[]=[
    // A：theme「东方」+ sector「快手概念」→ 组「东方」（不是传媒娱乐）
    makeCase('sz000801','大东方','快手概念',['东方'],[],1,'东方系名称辈观察'),
    // B：theme「东方」+ sector「东方」→ 同组「东方」
    makeCase('sz000802','京东方A','东方',['东方'],[],2,'面板行业需求回升'),
    // C：theme「IP」→ 命中同义词表 → 传媒娱乐
    makeCase('sz000803','游戏样本','游戏Ⅱ',['IP'],['网络游戏'],2.5,'游戏版号获批'),
    // D：theme「2027 羊年（跨年）」+ sector「通信设备」→ 新组「2027 羊年（跨年）」，不得混入通信光通信
    makeCase('sz000804','盛洋科技','通信设备',['2027 羊年（跨年）'],[],1.5,'跨年题材活跃'),
    // E：theme「2027 羊年（跨年）」+ concept「商业航天」→ 同组「2027 羊年（跨年）」，不得混入商业航天
    makeCase('sz000805','阳光照明','商业航天',['2027 羊年（跨年）'],['商业航天'],0.5,'跨年题材活跃'),
  ];
  await boot(page,{entries:groupFixEntries});
  await waitGroups(page,3);
  // 组资金：东方 1+2=3.00 > 传媒娱乐 2.50 > 2027 羊年（跨年）1.5+0.5=2.00
  const labels=await groupLabels(page);
  expect(labels.sort()).toEqual(['分组 东方','分组 传媒娱乐','分组 2027 羊年（跨年）'].sort());
  expect((await groupTitles(page)).sort()).toEqual(['东方 — 2 只','传媒娱乐 — 1 只','2027 羊年（跨年） — 2 只'].sort());
  const eastGroup=groupOf(page,'东方');
  const mediaGroup=groupOf(page,'传媒娱乐');
  const goatGroup=groupOf(page,'2027 羊年（跨年）');
  const eastNames=(await eastGroup.locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(eastNames).toEqual(['京东方','大东方'].sort());
  // 名称展示去掉尾部字母，title/aria 保留完整原名
  await expect(eastGroup.locator('.pt-name[title="京东方A"] .pt-name-text')).toHaveText('京东方');
  await expect(eastGroup.locator('.pt-name[title="京东方A"]')).toHaveAttribute('aria-label','京东方A');
  await expect(mediaGroup.locator('.pt-name-text')).toHaveText('游戏样本');
  const goatNames=(await goatGroup.locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(goatNames).toEqual(['盛洋科技','阳光照明'].sort());
  // 东方/羊年股票不得被 sector 概念吸走：不存在通信光通信、商业航天组
  expect(labels).not.toContain('分组 通信光通信');
  expect(labels).not.toContain('分组 商业航天');
  // 阳光照明的「商业航天」只出现在相关概念·题材列，分组仍为 2027 羊年（跨年）
  await expect(goatGroup.locator('.pt-row').filter({hasText:'阳光照明'}).locator('.pt-col-tags')).toContainText('商业航天');
  // 传媒娱乐只含 C，不含带「东方」标签的 A/B
  const mediaNames=(await mediaGroup.locator('.pt-name-text').allInnerTexts()).map(text=>text.trim());
  expect(mediaNames).not.toContain('大东方');
  expect(mediaNames).not.toContain('京东方');
  await expect(page.locator('.pt-footer')).toContainText('显示 5 / 共 5 只 · 3 个方向');
});

// ===== 2d. 全量分组一致性审计（真实 public/pool-preview.json，173 只） =====
test('全量分组一致性：真实预览 auditGrouping=[]、相关标签无噪声、首标签映射唯一，次要标签不吸走股票',async()=>{
  const rootDir=test.info().config.rootDir||process.cwd();
  const candidates=[
    resolve(rootDir,'../public/pool-preview.json'),
    resolve(rootDir,'public/pool-preview.json'),
    resolve(process.cwd(),'public/pool-preview.json'),
    resolve(process.cwd(),'Code/stock-monitor/public/pool-preview.json'),
  ];
  const previewPath=candidates.find(file=>existsSync(file));
  expect(previewPath,'public/pool-preview.json 应存在').toBeTruthy();
  const data=JSON.parse(readFileSync(previewPath as string,'utf8')) as {entries:Entry[];today?:string|null};
  const entries=data.entries;
  // selection/alert 数据完备性（真实 preview）：selection 全量存在、无 00:0x 半截时间、今日提醒存在
  const withSelection=entries.filter(entry=>entry.selection&&typeof entry.selection==='object');
  expect(withSelection.length).toBe(entries.length);
  const badSelectionTime=withSelection.filter(entry=>typeof entry.selection?.first_at==='string'&&entry.selection.first_at.includes('T00:0')).map(entry=>entry.code);
  expect(badSelectionTime).toEqual([]);
  const previewToday=typeof data.today==='string'&&data.today?data.today.slice(0,10):'';
  if(previewToday){
    const alertsToday=entries.filter(entry=>entry.alert&&entry.alert.day===previewToday);
    expect(alertsToday.length).toBeGreaterThan(0);
    expect(String(alertsToday[0].alert?.label||'')).not.toBe('');
    // 真实 preview 全量计数（本轮验收口径：190 只 / 今日入选 38 / 多次入选 57 / 今日提醒 58）
    const previewCounts=rowCounts(entries,previewToday);
    expect(previewCounts.all).toBe(entries.length);
    expect(previewCounts.all).toBe(190);
    expect(previewCounts.today).toBe(38);
    expect(previewCounts.multi).toBe(57);
    expect(previewCounts.alert).toBe(2);
  }
  expect(Array.isArray(entries)).toBe(true);
  expect(entries.length).toBeGreaterThan(100);

  // 1) 全量审计：每只 groupKey == 其「表格显示的第一个有效标签」的规范映射；同一首个标签不得分到两个组
  expect(auditGrouping(entries)).toEqual([]);

  // 2) 相关概念·题材不得出现噪声标签（精确匹配）
  const noisy:string[]=[];
  for(const entry of entries){
    for(const tag of relatedTagsOf(entry))if(NOISE_TOKENS.includes(tag))noisy.push(entry.code+'='+tag);
  }
  expect(noisy).toEqual([]);
  // 相关标签为空时 relatedTagsText 回退 sector（非噪声）或 —
  for(const entry of entries){
    if(relatedTagsOf(entry).length)continue;
    const sector=String(entry.sector||'').trim();
    const expected=sector&&!NOISE_TOKENS.includes(sector)?sector:'—';
    expect(relatedTagsText(entry)).toBe(expected);
  }
  // 同一首个标签 → 唯一组（显式再校验一次，便于定位 same-tag-split）
  const tagToGroup=new Map<string,string>();
  for(const entry of entries){
    const firstTag=relatedTagsOf(entry)[0]||'';
    if(!firstTag)continue;
    const group=groupKey(entry);
    const previous=tagToGroup.get(firstTag);
    if(previous===undefined)tagToGroup.set(firstTag,group);
    else expect(group).toBe(previous);
  }
  expect(tagToGroup.size).toBeGreaterThan(0);

  // 3) 次要标签不再把股票吸走（直接调用模型，覆盖通用首标签规则）
  const tagsEntry=(tags:Json,sector:string)=>groupKey({tags,sector} as unknown as Entry);
  expect(tagsEntry({theme:['2027 羊年（跨年）'],concept:['商业航天'],event:[],other:[]},'商业航天')).toBe('2027 羊年（跨年）');
  expect(tagsEntry({theme:['2027 羊年（跨年）'],concept:[],event:[],other:[]},'通信设备')).toBe('2027 羊年（跨年）');
  expect(tagsEntry({theme:['东方'],concept:[],event:[],other:[]},'快手概念')).toBe('东方');
  expect(tagsEntry({theme:['IP'],concept:['网络游戏'],event:[],other:[]},'游戏Ⅱ')).toBe('传媒娱乐');
});

// ===== 2f. 分组规则回归：物理AI 独立、最长关键词、噪声 token 跳过 =====
test('分组规则回归：物理AI 独立成组、大模型/AI漫剧→传媒娱乐、汽车相关→汽车产业链、PCB→半导体电子、专精特新/百元股不作组键',async({page})=>{
  const make=(code:string,name:string,theme:string[],concept:string[],sector='')=>makeEntry({code,name,sector,category:'概念',group_name:'',groups:[],
    tags:{concept,theme,event:[],other:[]},added_day:'2026-11-11',added_at:'2026-11-11T10:00:00+08:00',
    quote:quote(10,1),today_percent:1,since_add_percent:1,plan:planDefault(),history:[],windows:null,
    episodes:{total:1,today:1,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'},
    quant:{turnover_rate:2,volume_ratio:1.2,amplitude:2,float_mcap_yi:30},
    driver:null,driver_short:null,driver_short_at:null,fund:fund(1)});
  const entries:Json[]=[
    make('sz000b01','物理样本',['物理AI'],[],'AI算力'),
    make('sz000b02','大模样本',['大模型'],[],'AI算力'),
    make('sz000b03','漫剧样本',['AI漫剧'],[],'传媒'),
    make('sz000b04','汽电样本',['汽车电子'],[]),
    make('sz000b05','后视样本',['电子后视镜'],[]),
    make('sz000b06','轮毂样本',['轮毂电机'],[]),
    make('sz000b07','零件样本',['汽车零部件'],[]),
    make('sz000b08','PCB样本',['PCB'],[]),
    make('sz000b09','专精样本',['专精特新'],['半导体']),
    make('sz000b10','百元样本',['百元股'],[],'汽车零部件'),
  ];
  await boot(page,{entries});
  await waitGroups(page,4);
  const labels=await groupLabels(page);
  expect(labels.sort()).toEqual(['分组 物理AI','分组 传媒娱乐','分组 汽车产业链','分组 半导体电子'].sort());
  expect(labels).not.toContain('分组 AI算力');
  const namesIn=async(label:string)=>(await groupOf(page,label).locator('.pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();
  expect(await namesIn('物理AI')).toEqual(['物理样本']);
  expect(await namesIn('传媒娱乐')).toEqual(['大模样本','漫剧样本'].sort());
  expect(await namesIn('汽车产业链')).toEqual(['汽电样本','后视样本','轮毂样本','零件样本','百元样本'].sort());
  expect(await namesIn('半导体电子')).toEqual(['PCB样本','专精样本'].sort());
});

// ===== 2g. 组头驱动相关性：成员次要题材新闻不得成为组头驱动 =====
test('组头驱动相关性：成员次要题材新闻不成为组头驱动，相关新闻保留，无相关候选回退泛化短句',async({page})=>{
  const make=(code:string,name:string,tag:string,driverShort:string,genericReason='')=>makeEntry({code,name,sector:'',category:'概念',group_name:'',groups:[],
    tags:{concept:[tag],theme:[],event:[],other:[]},added_day:'2026-11-11',added_at:'2026-11-11T10:00:00+08:00',
    quote:quote(10,1),today_percent:1,since_add_percent:1,plan:planDefault(),history:[],windows:null,
    episodes:{total:1,today:1,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'},
    quant:{turnover_rate:2,volume_ratio:1.2,amplitude:2,float_mcap_yi:30},
    reason:genericReason,driver:null,driver_short:driverShort||null,driver_short_at:'2026-11-11T10:00:00+08:00',fund:fund(1)});
  const entries:Json[]=[
    make('sz000c01','化工样本甲','化工','具身智能产业订单爆发'),
    make('sz000c02','化工样本乙','化工','','板块上涨且资金净流入；化工品涨价'),
    make('sz000c03','算力样本甲','AI算力','OpenAI发布新一代模型'),
    make('sz000c04','算力样本乙','AI算力','','回踩低吸：算力需求增长'),
    make('sz000c05','羊年样本甲','2027 羊年（跨年）','AI漫剧打开增长空间'),
    make('sz000c06','羊年样本乙','2027 羊年（跨年）','','只观察，不追高'),
    make('sz000c07','光通信样本','光通信','光通信股今早逆市走高'),
    make('sz000c08','传媒样本','短剧','短剧与AI漫剧打开公司增长空间'),
  ];
  await boot(page,{entries});
  await waitGroups(page,5);
  // 无关新闻不得成为组头驱动，回退到泛化短句
  await expect(groupOf(page,'化工材料').locator('.pt-group-driver')).toHaveText('驱动：板块上涨、资金净流入');
  await expect(groupOf(page,'AI算力').locator('.pt-group-driver')).toHaveText('驱动：回踩低吸');
  await expect(groupOf(page,'2027 羊年（跨年）').locator('.pt-group-driver')).toHaveText('驱动：只观察不追高');
  // 相关新闻保留
  await expect(groupOf(page,'通信光通信').locator('.pt-group-driver')).toHaveText('驱动：光通信股今早逆市走高');
  await expect(groupOf(page,'传媒娱乐').locator('.pt-group-driver')).toHaveText('驱动：短剧与AI漫剧打开公司增长空间');
  // 无关新闻文本不得出现在组头驱动
  for(const label of ['化工材料','AI算力','2027 羊年（跨年）']){
    const text=await groupOf(page,label).locator('.pt-group-driver').innerText();
    expect(text).not.toContain('具身智能');
    expect(text).not.toContain('OpenAI');
    expect(text).not.toContain('AI漫剧');
  }
});

// ===== 2e. 组置顶：pin 按钮、顺序、localStorage、刷新持久化、取消与筛选 =====
test('组置顶：点击 .pt-pin 置顶到最前并保持点击顺序、localStorage 持久化、取消置顶与筛选保留记录',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitGroups(page);
  const columns=columnsLoc(page);
  const firstIn=(columnIndex:number)=>columns.nth(columnIndex).locator('.pt-group').first();
  await expect(firstIn(0)).toHaveAttribute('aria-label','分组 人形机器人');
  await expect(firstIn(1)).toHaveAttribute('aria-label','分组 商业航天');
  const storage=()=>page.evaluate(()=>localStorage.getItem('stock-monitor-pool-pinned-v1'));

  // 初始：无置顶，置顶按钮 aria-pressed=false
  const comm=groupOf(page,'通信光通信');
  const commPin=comm.locator('.pt-group-head .pt-pin');
  await expect(commPin).toHaveCount(1);
  await expect(commPin).toHaveAttribute('aria-label','置顶 通信光通信');
  await expect(commPin).toHaveAttribute('aria-pressed','false');
  await commPin.click();
  // 置顶后排到最前（第一列首卡=置顶组），按钮态/localStorage 更新，行未被展开
  await expect(firstIn(0)).toHaveAttribute('aria-label','分组 通信光通信');
  await expect(commPin).toHaveAttribute('aria-pressed','true');
  await expect(commPin).toHaveAttribute('aria-label','取消置顶 通信光通信');
  expect(await storage()).toBe(JSON.stringify(['通信光通信']));
  await expect(page.locator('.pt-detail')).toHaveCount(0);

  // 再置顶第二组：保持点击顺序（第一列首卡=第一个置顶，第二列首卡=第二个置顶）
  const semiPin=groupOf(page,'半导体电子').locator('.pt-group-head .pt-pin');
  await semiPin.click();
  await expect(firstIn(0)).toHaveAttribute('aria-label','分组 通信光通信');
  await expect(firstIn(1)).toHaveAttribute('aria-label','分组 半导体电子');
  expect(await storage()).toBe(JSON.stringify(['通信光通信','半导体电子']));
  await expect(groupOf(page,'通信光通信').locator('.pt-pin')).toHaveAttribute('aria-pressed','true');
  await expect(groupOf(page,'半导体电子').locator('.pt-pin')).toHaveAttribute('aria-pressed','true');

  // 刷新页面后仍置顶（localStorage 持久化）
  await page.reload();
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  await waitGroups(page);
  await expect(firstIn(0)).toHaveAttribute('aria-label','分组 通信光通信');
  await expect(firstIn(1)).toHaveAttribute('aria-label','分组 半导体电子');
  await expect(groupOf(page,'通信光通信').locator('.pt-pin')).toHaveAttribute('aria-pressed','true');
  expect(await storage()).toBe(JSON.stringify(['通信光通信','半导体电子']));

  // 取消一个置顶：剩余置顶仍在前
  await groupOf(page,'通信光通信').locator('.pt-pin').click();
  await expect(firstIn(0)).toHaveAttribute('aria-label','分组 半导体电子');
  expect(await storage()).toBe(JSON.stringify(['半导体电子']));
  await expect(groupOf(page,'通信光通信').locator('.pt-pin')).toHaveAttribute('aria-pressed','false');

  // 筛选掉置顶组：按钮不显示但记录保留；清除筛选后恢复置顶
  const search=page.getByLabel('搜索代码/名称/标签');
  await search.fill('卫星');
  await waitGroups(page,1);
  await expect(page.locator('.pt-pin')).toHaveCount(1);
  await expect(page.locator('.pt-pin[aria-label="取消置顶 半导体电子"]')).toHaveCount(0);
  expect(await storage()).toBe(JSON.stringify(['半导体电子']));
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page);
  await expect(firstIn(0)).toHaveAttribute('aria-label','分组 半导体电子');
  await expect(groupOf(page,'半导体电子').locator('.pt-pin')).toHaveAttribute('aria-pressed','true');
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
  expect(labels).toEqual(['代码','名称','现价','入选时间','入选价格','入选后涨幅','今日涨幅','量比','换手(%)','相关概念·题材']);
  // 名称列宽 72px；入选后涨幅列宽 61px；现价列表头/单元格 padding-right≈7px
  const columnTracks=await human.locator('.pt-head').evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean));
  expect(columnTracks[1]).toBe('72px');
  const nameWidth=await human.locator('.pt-row').first().locator('.pt-name').evaluate(element=>element.getBoundingClientRect().width);
  expect(Math.abs(nameWidth-72)).toBeLessThanOrEqual(2);
  expect(await human.locator('.pt-head > span').nth(2).evaluate(element=>getComputedStyle(element).paddingRight)).toBe('7px');
  expect(await human.locator('.pt-row').first().locator('.pt-cell.pt-col-price').evaluate(element=>getComputedStyle(element).paddingRight)).toBe('7px');
  await expect(human.getByRole('table',{name:'人形机器人 标的'})).toBeVisible();

  const jia=await rowCellsIn(human,'甲机器人');
  expect(jia).toEqual(['000101','甲机器人','13.74','11-11 11:02','12.68','+8.40%','+4.20%','2.11','6.50','人形机器人 / 减速器 / 机器人']);
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
  expect(yi[2]).toBe('19.85');
  expect(yi[4]).toBe('20.50');
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
  const numIndexes=[0,2,4,5,6,7,8];
  for(const index of numIndexes){
    expect(headClasses[index]).toContain('pt-head-num');
    expect(headJustify[index]).toBe('flex-end');
  }
  for(const index of [1,3,9]){
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

// ===== 3b. 名称展示：去尾部字母，title/aria 保留原名，名称列 72px 不省略 =====
test('名称展示：displayName 去尾部 -W/-U/全角字母，title/aria 保留完整原名，名称列 72px 且不省略',async({page})=>{
  const cases:[string,string,string][]=[
    ['sz000a01','奥比中光-W','奥比中光'],
    ['sz000a02','宇树科技-W','宇树科技'],
    ['sz000a03','埃夫特-U','埃夫特'],
    ['sz000a04','京东方Ａ','京东方'],
  ];
  const entries=cases.map((item,index)=>makeEntry({code:item[0],name:item[1],sector:'名称测试'+index,group_name:'',groups:[],
    tags:{concept:['名称测试'+index],theme:[],event:[],other:[]},category:'概念',
    added_day:'2026-11-11',added_at:'2026-11-11T10:00:00+08:00',quote:quote(10,1),today_percent:1,since_add_percent:1,
    plan:planDefault(),history:[],windows:null,
    episodes:{total:1,today:1,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'},
    quant:{turnover_rate:2,volume_ratio:1.2,amplitude:2,float_mcap_yi:30},
    driver:null,driver_short:null,driver_short_at:null,fund:fund(1)}));
  await boot(page,{entries});
  await waitGroups(page,4);
  const rendered=await page.locator('.pt-name').evaluateAll(elements=>elements.map(element=>({
    title:element.getAttribute('title'),
    aria:element.getAttribute('aria-label'),
    text:(element.querySelector('.pt-name-text')?.textContent||'').trim(),
  })));
  expect(rendered.length).toBe(4);
  for(const [,full,shown] of cases){
    const item=rendered.find(row=>row.title===full);
    expect(item).toBeTruthy();
    expect(item!.aria).toBe(full);
    expect(item!.text).toBe(shown);
  }
  const overflow=await page.locator('.pt-name-text').evaluateAll(elements=>elements.filter(element=>element.scrollWidth>element.clientWidth+1).map(element=>element.textContent));
  expect(overflow).toEqual([]);
  const tracks=await groupOf(page,'名称测试0').locator('.pt-head').evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean));
  expect(tracks[1]).toBe('72px');
});

// ===== 4. 组内排序（组间顺序固定按资金） =====
test('组内排序：默认入选时间降序，6 个表头/下拉升降序只影响组内且组间资金顺序不变',async({page})=>{
  await page.setViewportSize({width:1440,height:980});
  await boot(page,{});
  await waitGroups(page);
  const labelsBefore=await groupLabels(page);
  const human=groupOf(page,'人形机器人');
  await expect(human.locator('.pt-head > span').nth(3)).toHaveAttribute('aria-sort','descending');
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
  await expect(human.locator('.pt-head > span').nth(4)).toHaveAttribute('aria-sort','descending');
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
test('今日入选保持原有再次入选口径，多次入选和清除筛选正常',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const chips=page.getByRole('group',{name:'入选筛选'});
  await expect(chips.locator('button')).toHaveCount(4);
  await chips.getByRole('button',{name:'今日入选 3'}).click();
  await expect(page.locator('.pt-row')).toHaveCount(3);
  await expect(chips.getByRole('button',{name:'今日入选 3'})).toHaveAttribute('title',/不要求今天是首次入选/);
  await page.getByLabel('时间范围').selectOption('today');
  await expect(page.locator('.pt-row')).toHaveCount(3);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page);
  await chips.getByRole('button',{name:'多次入选 5'}).click();
  await expect(page.locator('.pt-row')).toHaveCount(5);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await expect(page.locator('.pt-row')).toHaveCount(11);
});


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
  expect((await groupTitles(page)).sort()).toEqual(['人形机器人 — 3 只','商业航天 — 2 只','通信光通信 — 2 只','半导体电子 — 2 只','东方 — 1 只'].sort());
  await expect(page.locator('.pt-footer')).toContainText('显示 10 / 共 11 只 · 5 个方向');
  await period.selectOption('today');
  await waitGroups(page,3);
  expect((await groupTitles(page)).sort()).toEqual(['人形机器人 — 2 只','商业航天 — 1 只','通信光通信 — 1 只'].sort());
  await period.selectOption('all');
  await waitGroups(page);
  await expect(page.locator('.pt-footer')).toContainText('显示 11 / 共 11 只 · 6 个方向');
});

// ===== 6b. 时间范围「今日」与「今日入选」一致（盘前 anchor 优先 data.today，按最近一次入选日过滤） =====
test('时间范围今日命中今日入选行：anchor 优先 data.today（盘前 quotes_time 为上一交易日）、近3日/5日按 last_at 过滤',async({page})=>{
  const baseEntry=(over:Json)=>makeEntry(Object.assign({
    sector:'测试方向',category:'概念',group_name:'',groups:[],
    tags:{concept:['测试方向'],theme:[],event:[],other:[]},
    quote:quote(10,1),today_percent:1,since_add_percent:1,plan:planDefault(),history:[],windows:null,
    quant:{turnover_rate:2,volume_ratio:1.2,amplitude:2,float_mcap_yi:30},
    driver:null,driver_short:null,driver_short_at:null,fund:fund(1),
  },over));
  const entries:Json[]=[
    // 今日再次入选：首次入选日更早(11-11)，最近一次入选日=今日 11-12（盘前 08:05）
    baseEntry({code:'sz000d01',name:'今日样本',added_day:'2026-11-11',added_at:'2026-11-11T10:00:00+08:00',
      tags:{concept:['测试方向A'],theme:[],event:[],other:[]},
      episodes:{total:2,today:1,first_at:'2026-11-09T10:00:00+08:00',last_at:'2026-11-12T08:05:00+08:00'}}),
    // 最近一次入选日=11-11（若错误地用 quotes_time 11-11 作 anchor，则「今日」会误收该行）
    baseEntry({code:'sz000d02',name:'前日样本',added_day:'2026-11-09',added_at:'2026-11-09T10:00:00+08:00',
      tags:{concept:['测试方向B'],theme:[],event:[],other:[]},
      episodes:{total:1,today:0,first_at:'2026-11-09T10:00:00+08:00',last_at:'2026-11-11T14:00:00+08:00'}}),
    // 最近一次入选日=10-20，超出近3日/近5日范围（排除样本）
    baseEntry({code:'sz000d03',name:'远日样本',added_day:'2026-11-03',added_at:'2026-11-03T10:00:00+08:00',
      tags:{concept:['测试方向C'],theme:[],event:[],other:[]},
      episodes:{total:1,today:0,first_at:'2026-10-20T10:00:00+08:00',last_at:'2026-10-20T10:00:00+08:00'}}),
  ];
  // 盘前场景：quotes_time 仍是上一交易日 11-11，而后端 today=11-12
  await boot(page,{entries,today:'2026-11-12',quotesTime:'2026-11-11T15:00:00+08:00'});
  await waitGroups(page,3);
  const chips=page.getByRole('group',{name:'入选筛选'});
  await expect(chips.getByRole('button',{name:'今日入选 1'})).toBeVisible();
  const period=page.getByLabel('时间范围');
  const rows=()=>page.locator('.pt-row');
  const names=async()=>(await page.locator('.pt-row .pt-name-text').allInnerTexts()).map(text=>text.trim()).sort();

  // 单独「时间范围=今日」→ 命中今日再次入选行（修复前为 0 行）
  await period.selectOption('today');
  await expect(rows()).toHaveCount(1);
  expect(await names()).toEqual(['今日样本']);
  await expect(page.locator('.pt-footer')).toContainText('显示 1 / 共 3 只');
  // 今日入选 chip + 时间范围今日 → 同一行
  await chips.getByRole('button',{name:'今日入选 1'}).click();
  await expect(rows()).toHaveCount(1);
  expect(await names()).toEqual(['今日样本']);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page,3);

  // 近3日：按 last_at 判断 → 今日样本(11-12)、前日样本(11-11)保留；远日样本(10-20)排除
  await period.selectOption('3d');
  await expect(rows()).toHaveCount(2);
  expect(await names()).toEqual(['前日样本','今日样本'].sort());
  // 近5日：同样按 last_at 排除远日样本
  await period.selectOption('5d');
  await expect(rows()).toHaveCount(2);
  expect(await names()).toEqual(['前日样本','今日样本'].sort());
  await period.selectOption('all');
  await waitGroups(page,3);
});

// ===== 6c. 有效入选时间 selection：09:25 映射、回退、过滤口径与详情 =====
test('入选时间 selection：09:25 映射不显示 00:05、无 selection 回退、chip/时间范围/详情按 selection 口径',async({page})=>{
  const mk=(over:Json)=>makeEntry(Object.assign({
    sector:'选测方向',category:'概念',group_name:'',groups:[],
    tags:{concept:['选测方向'],theme:[],event:[],other:[]},
    quote:quote(10,1),today_percent:1,since_add_percent:1,plan:planDefault(),history:[],windows:null,
    quant:{turnover_rate:2,volume_ratio:1.2,amplitude:2,float_mcap_yi:30},
    driver:null,driver_short:null,driver_short_at:null,fund:fund(1),
  },over));
  const entries:Json[]=[
    // Z1：added_at=00:05，但有效入选时间 selection.first_at=09:25；episodes.today=0 而 selection.today=1（chip 以 selection 为准）
    mk({code:'sz000e01',name:'有效样本',added_day:'2026-11-12',added_at:'2026-11-12T00:05:00+08:00',
      tags:{concept:['选测方向A'],theme:[],event:[],other:[]},
      selection:{first_at:'2026-11-12T09:25:00+08:00',first_day:'2026-11-12',last_at:'2026-11-12T09:25:00+08:00',last_day:'2026-11-12',days:5,today:1},
      episodes:{total:3,today:0,first_at:'2026-11-09T14:31:00+08:00',last_at:'2026-11-12T09:25:00+08:00'}}),
    // Z2：selection.today=0 而 episodes.today=1 → 不计入今日入选
    mk({code:'sz000e02',name:'口径样本',added_day:'2026-11-11',added_at:'2026-11-11T10:00:00+08:00',
      tags:{concept:['选测方向B'],theme:[],event:[],other:[]},
      selection:{first_at:'2026-11-11T10:00:00+08:00',first_day:'2026-11-11',last_at:'2026-11-11T10:00:00+08:00',last_day:'2026-11-11',days:1,today:0},
      episodes:{total:1,today:1,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'}}),
    // Z3：selection.last_day=11-09（近3日排除），added_day=11-10 本在范围内 → 证明时间范围按 selection
    mk({code:'sz000e03',name:'远日样本',added_day:'2026-11-10',added_at:'2026-11-10T10:00:00+08:00',
      tags:{concept:['选测方向C'],theme:[],event:[],other:[]},
      selection:{first_at:'2026-11-09T10:00:00+08:00',first_day:'2026-11-09',last_at:'2026-11-09T10:00:00+08:00',last_day:'2026-11-09',days:1,today:0},
      episodes:{total:1,today:0,first_at:'2026-11-09T10:00:00+08:00',last_at:'2026-11-09T10:00:00+08:00'}}),
    // Z4：无 selection → first_at 回退 episodes.first_at=11-11 10:00；last_day 回退 episodes.last_at=11-11（今日 anchor=11-12 应排除）
    mk({code:'sz000e04',name:'回退样本',added_day:'2026-11-12',added_at:'2026-11-12T08:05:00+08:00',
      tags:{concept:['选测方向D'],theme:[],event:[],other:[]},selection:null,
      episodes:{total:1,today:0,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'}}),
  ];
  // 盘前：quotes_time 仍是上一交易日 11-11，后端 today=11-12
  await boot(page,{entries,today:'2026-11-12',quotesTime:'2026-11-11T15:00:00+08:00'});
  await waitGroups(page,4);
  const z1=page.locator('.pt-row').filter({has:page.locator('.pt-name[title="有效样本"]')});
  const z4=page.locator('.pt-row').filter({has:page.locator('.pt-name[title="回退样本"]')});
  const timeCell=z1.locator('.pt-time');
  await expect(timeCell).toHaveText('11-12 09:25');
  await expect(timeCell).toHaveAttribute('title','入选 2026-11-12 09:25');
  await expect(timeCell).toHaveAttribute('aria-label','入选时间 2026-11-12 09:25');
  await expect(z1).not.toContainText('00:05');
  await expect(z4.locator('.pt-time')).toHaveText('11-11 10:00');
  await expect(z4.locator('.pt-time')).toHaveAttribute('title','入选 2026-11-11 10:00');
  // 连 episodes.first_at 都没有时回退 added_at（模型级）
  expect(entryTime({added_day:'2026-11-12',added_at:'2026-11-12T08:05:00+08:00'} as unknown as Entry)).toBe('11-12 08:05');
  // chip 今日入选 = selection.today：Z1 计入、Z2 不计入 → 1
  const chips=page.getByRole('group',{name:'入选筛选'});
  await expect(chips.getByRole('button',{name:'今日入选 1'})).toBeVisible();
  await chips.getByRole('button',{name:'今日入选 1'}).click();
  await expect(page.locator('.pt-row')).toHaveCount(1);
  await page.getByLabel('时间范围').selectOption('today');
  await expect(page.locator('.pt-row')).toHaveCount(1);
  await expect(page.locator('.pt-row .pt-name-text')).toHaveText('有效样本');
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page,4);
  // 时间范围今日：anchor=data.today=11-12 → 仅 Z1；Z4(last_day 11-11) 不被误收
  await page.getByLabel('时间范围').selectOption('today');
  await expect(page.locator('.pt-row')).toHaveCount(1);
  await expect(page.locator('.pt-row .pt-name-text')).toHaveText('有效样本');
  // 近3日按 selection.last_day：Z3(11-09) 排除（若按 added_day=11-10 会保留）
  await page.getByLabel('时间范围').selectOption('3d');
  await expect(page.locator('.pt-row')).toHaveCount(3);
  expect((await page.locator('.pt-row .pt-name-text').allInnerTexts()).map(text=>text.trim()).sort()).toEqual(['回退样本','口径样本','有效样本'].sort());
  await page.getByLabel('时间范围').selectOption('5d');
  await expect(page.locator('.pt-row')).toHaveCount(4);
  // 详情：累计天数=selection.days(5，而非 episodes.total=3)、首次/最近=selection 时间
  await page.getByLabel('时间范围').selectOption('all');
  await z1.click();
  const detail=page.getByRole('region',{name:'详情 有效样本'});
  await expect(detail.locator('.pt-kv > div').filter({hasText:'累计'})).toContainText('5 天 · 今日已入选');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'首次'})).toContainText('2026-11-12 09:25');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'最近'})).toContainText('2026-11-12 09:25');
  await expect(z1.locator('.pt-count-badge')).toHaveText('×3');
});

// ===== 6d. 今日提醒 alert：无行内铃铛、行标记/动态计数/筛选说明/详情提醒行 =====
test('今日提醒严格按当天首次加入筛选，历史重选或历史通知不混入，今日入选逻辑不变',async({page})=>{
  const mk=(code:string,added:string,over:Json={})=>makeEntry({code,name:code,
    added_at:added,added_day:added.slice(0,10),
    episodes:{total:1,today:0,first_at:added,last_at:added},...over});
  const entries=[
    mk('sz100001','2026-11-12T00:05:00+08:00',{added_day:'2026-11-11',
      episodes:{total:1,today:1,first_at:'2026-11-12T00:05:00+08:00',last_at:'2026-11-12T00:05:00+08:00'}}),
    mk('sz100002','2026-11-11T10:00:00+08:00',{
      episodes:{total:2,today:1,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-12T10:00:00+08:00'},
      alert:{day:'2026-11-12',kind:'buy_zone',label:'进入买区',at:'2026-11-12T09:34:00+08:00'}}),
    mk('sz100003','2026-11-10T10:00:00+08:00',{
      alert:{day:'2026-11-12',kind:'stop_break',label:'跌破防守位',at:'2026-11-12T09:35:00+08:00'}}),
    mk('sz100004','2026-11-12',{source:'手动',episodes:null,selection:null}),
    mk('sz100005','2026-11-13T00:05:00+08:00'),
    mk('sz100006','2026-11-11T16:10:00Z'),
    mk('sz100007','2026-11-12T00:10:00+09:00'),
  ];
  await boot(page,{entries,today:'2026-11-12',quotesTime:'2026-11-11T15:00:00+08:00'});
  const chips=page.getByRole('group',{name:'入选筛选'});
  await expect(chips.getByRole('button',{name:'今日入选 2'})).toBeVisible();
  await chips.getByRole('button',{name:'今日入选 2'}).click();
  await expect(page.locator('.pt-code')).toHaveText(['100001','100002']);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await page.getByLabel('时间范围').selectOption('3d');
  await chips.getByRole('button',{name:/^今日提醒 /}).click();
  await expect(page.locator('.pt-row')).toHaveCount(3);
  expect((await page.locator('.pt-code').allTextContents()).sort()).toEqual(['100001','100004','100006']);
  await expect(chips.getByRole('button',{name:'今日提醒 3'})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByLabel('时间范围')).toHaveValue('all');
  await expect(page.getByLabel('时间范围')).toBeDisabled();
  await expect(page.locator('.pt-filter-note')).toContainText('仅显示 2026-11-12 首次加入');
  for(const stamp of await page.locator('.pt-time').allTextContents())expect(stamp).toMatch(/^11-12/);
  await expect(page.getByRole('button',{name:'按入池时间排序'})).toBeVisible();
  await expect(page.getByRole('button',{name:'消息中心',exact:true})).toHaveCount(0);
  await expect(page.locator('.pt-alert-line')).toHaveCount(0);
  await expect(page.getByText(/已定位通知股票/)).toHaveCount(0);
  await page.screenshot({path:SHOTS+'/today-added-only.png',fullPage:true});
});

test('今日提醒按自然日而非上个交易日筛选',async({page})=>{
  await boot(page,{today:'2026-11-13',calendarToday:'2026-11-15',entries:[
    makeEntry({code:'sz100011',added_day:'2026-11-13',added_at:'2026-11-13T10:00:00+08:00'}),
    makeEntry({code:'sz100012',added_day:'2026-11-15',added_at:'2026-11-15T10:00:00+08:00'}),
  ]});
  await page.getByRole('button',{name:'今日提醒 1'}).click();
  await expect(page.locator('.pt-row')).toHaveCount(1);
  await expect(page.locator('.pt-code')).toHaveText('100012');
});

test('超过200只的股票池继续读取下一页，今日入选和当天首次加入筛选不漏尾页',async({page})=>{
  const entries=Array.from({length:201},(_,index)=>makeEntry({code:'sz'+String(100000+index),name:'测试'+index,added_at:index===200?'2026-11-11T10:00:00+08:00':'2026-11-10T10:00:00+08:00',
    episodes:{total:1,today:index===200?1:0,first_at:'2026-11-11T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'},
    tags:{concept:['分页方向'],theme:[],event:[],other:[]},
    alert:index===200?{day:'2026-11-11',kind:'buy_zone',label:'进入买区',at:'2026-11-11T09:34:00+08:00'}:null}));
  await boot(page,{entries});
  await expect(page.locator('.pt-row')).toHaveCount(201);
  await page.getByRole('button',{name:'今日入选 1'}).click();
  await expect(page.locator('.pt-row')).toHaveCount(1);
  await expect(page.locator('.pt-row')).toContainText('测试200');
  await page.getByRole('button',{name:'今日提醒 1'}).click();
  await expect(page.locator('.pt-row')).toHaveCount(1);
  await expect(page.locator('.pt-row')).toContainText('测试200');
  await waitRpc(page,call=>call.method==='pool'&&call.args.offset===200);
});

test('搜索：标签命中的股票重新分组（单只组保留），空结果提示与清除筛选',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const search=page.getByLabel('搜索代码/名称/标签');
  const chips=page.getByRole('group',{name:'入选筛选'});
  await search.fill('光通信');
  await waitGroups(page,1);
  expect(await groupLabels(page)).toEqual(['分组 通信光通信']);
  expect(await groupTitles(page)).toEqual(['通信光通信 — 1 只']);
  await expect(page.locator('.pt-row .pt-name-text')).toHaveText('丁光通信');
  // chips 数字跟随搜索动态变化
  await expect(chips.getByRole('button',{name:'全部 1'})).toBeVisible();
  await expect(chips.getByRole('button',{name:'今日入选 1'})).toBeVisible();
  await expect(chips.getByRole('button',{name:'多次入选 0'})).toBeVisible();
  await search.fill('卫星');
  await waitGroups(page,1);
  expect(await groupLabels(page)).toEqual(['分组 商业航天']);
  expect(await page.locator('.pt-row')).toHaveCount(2);
  await expect(chips.getByRole('button',{name:'全部 2'})).toBeVisible();
  await expect(chips.getByRole('button',{name:'今日入选 1'})).toBeVisible();
  await expect(chips.getByRole('button',{name:'多次入选 0'})).toBeVisible();
  await search.fill('不存在的标签');
  await expect(page.locator('.pt-empty')).toHaveText('当前筛选条件下没有标的。点「清除筛选」恢复。');
  await expect(page.locator('.pt-group')).toHaveCount(0);
  await expect(chips.getByRole('button',{name:'全部 0'})).toBeVisible();
  await page.getByRole('button',{name:'清除筛选'}).click();
  await waitGroups(page);
  await expect(search).toHaveValue('');
  await expect(page.getByRole('button',{name:'清除筛选'})).toHaveCount(0);
  await expect(chips.getByRole('button',{name:'全部 11'})).toBeVisible();
});

// ===== 8. 行详情内嵌图表：tabs/默认分时/日K/周K/放大缩小/请求不重复 =====
test('股票池展开分时持续取新数据，切走和收起后停止刷新',async({page})=>{
  await page.clock.install({time:new Date('2026-11-12T14:00:00+08:00')});
  await boot(page,{today:'2026-11-12'});
  await page.evaluate(()=>{
    const w=window as any,original=w.__TAURI_INTERNALS__.invoke;
    w.poolMinuteRefreshes=0;
    w.__TAURI_INTERNALS__.invoke=async(command:string,params:any)=>{
      if(command==='rpc'&&params.method==='minute_ensure'&&params.args.code==='sz000101'&&params.args.refresh===true)w.poolMinuteRefreshes++;
      const result=await original(command,params);
      if(command==='rpc'&&params.method==='chart'&&params.args.code==='sz000101'&&params.args.kind==='minute'&&w.poolMinuteRefreshes){
        const bars=[...result[0].data.bars,{time:'13:01',close:'14.56',volume:100,complete:true}];
        if(w.poolMinuteRefreshes>=2)bars.push({time:'13:02',close:'14.58',volume:200,complete:true});
        if(w.poolMinuteComplete)bars.push({time:'15:00',close:'14.60',volume:300,complete:true});
        return [{day:'2026-11-12',data:{...result[0].data,bars}}];
      }
      return result;
    };
  });
  const row=page.locator('.pt-row').filter({has:page.locator('.pt-name[title="甲机器人"]')});
  await row.click();
  const detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail.locator('.scp-state')).toContainText('至 13:01');
  await page.clock.runFor(6500);
  await expect(detail.locator('.scp-state')).toContainText('至 13:02');
  const value=await detail.locator('.chart').evaluate(async el=>{
    const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);
    const option=e.getInstanceByDom(el).getOption();return option.series.find((s:any)=>s.name==='价格').data[option.xAxis[0].data.indexOf('13:02')];
  });
  expect(value).toBe(14.58);
  await page.getByRole('button',{name:'自选监控',exact:true}).click();
  const before=await page.evaluate(()=>(window as any).poolMinuteRefreshes);
  await page.clock.runFor(13000);
  expect(await page.evaluate(()=>(window as any).poolMinuteRefreshes)).toBe(before);
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).poolMinuteRefreshes)).toBeGreaterThan(before);
  await page.evaluate(()=>{(window as any).poolMinuteComplete=true;});
  await page.clock.runFor(6500);
  await expect(detail.locator('.scp-state')).toContainText('至 15:00');
  const complete=await page.evaluate(()=>(window as any).poolMinuteRefreshes);
  await page.clock.runFor(13000);
  expect(await page.evaluate(()=>(window as any).poolMinuteRefreshes)).toBe(complete);
  await row.click();
  const closed=await page.evaluate(()=>(window as any).poolMinuteRefreshes);
  await page.clock.runFor(13000);
  expect(await page.evaluate(()=>(window as any).poolMinuteRefreshes)).toBe(closed);
});

test('股票池分时午休、收盘及节假日周末暂停，到交易时间自动恢复',async({page})=>{
  await page.clock.install({time:new Date('2026-09-30T11:29:50+08:00')});
  await boot(page,{});
  await page.locator('.pt-row').filter({has:page.locator('.pt-name[title="甲机器人"]')}).click();
  const count=async()=>(await rpcCalls(page)).filter(call=>call.method==='minute_ensure'&&call.args.code==='sz000101'&&call.args.refresh===true).length;
  const at=async(stamp:string)=>page.clock.fastForward(await page.evaluate(value=>Date.parse(value)-Date.now(),stamp));
  await expect.poll(count).toBeGreaterThan(0);
  await at('2026-09-30T11:30:00+08:00');
  const lunch=await count();
  await at('2026-09-30T12:59:59+08:00');
  expect(await count()).toBe(lunch);
  await at('2026-09-30T13:00:00+08:00');
  await expect.poll(count).toBeGreaterThan(lunch);
  await at('2026-09-30T15:00:00+08:00');
  const close=await count();
  await at('2026-10-07T14:00:00+08:00');
  expect(await count()).toBe(close);
  await at('2026-10-08T09:19:59+08:00');
  expect(await count()).toBe(close);
  await at('2026-10-08T09:20:00+08:00');
  await expect.poll(count).toBeGreaterThan(close);
  await at('2026-10-09T15:00:00+08:00');
  const weekend=await count();
  await at('2026-10-11T14:00:00+08:00');
  expect(await count()).toBe(weekend);
  await at('2026-10-12T09:20:00+08:00');
  await expect.poll(count).toBeGreaterThan(weekend);
});

test('详情图表：分时实时刷新、日K与周K复用缓存、切换与放大正常',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const human=groupOf(page,'人形机器人');
  await human.locator('.pt-row').filter({hasText:'甲机器人'}).click();
  const detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail).toBeVisible();
  const panel=detail.locator('section.stock-chart-panel[aria-label="行情图表 甲机器人"]');
  await expect(panel).toBeVisible();
  await expect(detail.locator('.pt-detail-chart')).toBeVisible();

  const tablist=panel.locator('.tabs[role="tablist"]');
  await expect(tablist).toHaveCount(1);
  const tabs=tablist.getByRole('tab');
  await expect(tabs).toHaveCount(3);
  expect((await tabs.allInnerTexts()).map(text=>text.trim())).toEqual(['分时','日K','周K']);
  await expect(tablist.getByRole('tab',{name:'分时'})).toHaveAttribute('aria-selected','true');
  await expect(tablist.getByRole('tab',{name:'日K'})).toHaveAttribute('aria-selected','false');

  // 默认分时
  await expect(panel.locator('.scp-chart .chart')).toBeVisible({timeout:10000});
  await expect(panel.locator('.scp-chart .chart')).toHaveAttribute('aria-label','分时价格及分钟成交量');
  await expect(panel.locator('.scp-state')).toContainText('分时 2026-11-11');

  // 切日K/周K
  await tablist.getByRole('tab',{name:'日K'}).click();
  await expect(tablist.getByRole('tab',{name:'日K'})).toHaveAttribute('aria-selected','true');
  await expect(tablist.getByRole('tab',{name:'分时'})).toHaveAttribute('aria-selected','false');
  await expect(panel.locator('.scp-chart .chart')).toHaveAttribute('aria-label','日K线及成交量',{timeout:10000});
  await expect(panel.locator('.scp-state')).toContainText('日K 60根');
  await tablist.getByRole('tab',{name:'周K'}).click();
  await expect(tablist.getByRole('tab',{name:'周K'})).toHaveAttribute('aria-selected','true');
  await expect(panel.locator('.scp-chart .chart')).toHaveAttribute('aria-label','周K线及成交量',{timeout:10000});

  // 放大/缩小
  const expand=panel.getByRole('button',{name:'放大图表'});
  await expect(expand).toHaveAttribute('aria-pressed','false');
  await expect(panel).not.toHaveClass(/is-expanded/);
  await expand.click();
  await expect(panel).toHaveClass(/is-expanded/);
  const collapse=panel.getByRole('button',{name:'缩小图表'});
  await expect(collapse).toHaveAttribute('aria-pressed','true');
  await expect(panel.locator('.scp-chart .chart')).toHaveAttribute('aria-label','周K线及成交量');
  await collapse.click();
  await expect(panel).not.toHaveClass(/is-expanded/);
  await expect(panel.getByRole('button',{name:'放大图表'})).toHaveAttribute('aria-pressed','false');

  // 日K/周K复用一次 history；分时在实时模式下允许刷新。
  await tablist.getByRole('tab',{name:'分时'}).click();
  await tablist.getByRole('tab',{name:'日K'}).click();
  await tablist.getByRole('tab',{name:'分时'}).click();
  const calls=await rpcCalls(page);
  const minuteCalls=calls.filter(call=>call.method==='chart'&&call.args.code==='sz000101'&&call.args.kind==='minute');
  const historyCalls=calls.filter(call=>call.method==='history'&&call.args.code==='sz000101');
  expect(minuteCalls.length).toBeGreaterThanOrEqual(1);
  expect(historyCalls.length).toBe(1);
  expect(calls.filter(call=>call.method==='minute_ensure'&&call.args.code==='sz000101').every(call=>call.args.refresh===true)).toBe(true);
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/03-detail-1440.png'});
});

// ===== 9. 详情精简：保留计划/理由/标签/入选统计/窗口徽标/操作，删除旧区块 =====
test('详情精简：保留计划与关键价位/入选理由/完整标签/入选统计/窗口徽标/操作，无入选信息/逐日快照/振幅流通/量比换手/K线按钮',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  const human=groupOf(page,'人形机器人');
  const row=human.locator('.pt-row').filter({hasText:'甲机器人'});
  await row.click();
  const detail=page.getByRole('region',{name:'详情 甲机器人'});
  await expect(detail).toBeVisible();
  await expect(detail.locator('.pt-detail-chart')).toBeVisible();
  for(const heading of ['计划与关键价位','入选理由','入选统计','当前状态','窗口表现','操作']){ 
    await expect(detail.getByRole('heading',{name:new RegExp(heading)})).toBeVisible();
  }
  // 已删除的旧区块
  for(const removed of ['入选信息','逐日快照']){
    await expect(detail.getByRole('heading',{name:new RegExp(removed)})).toHaveCount(0);
  }
  await expect(detail.locator('.pt-detail-strong')).toHaveCount(0);
  await expect(detail.locator('table.pt-mini')).toHaveCount(0);
  // 计划与关键价位
  for(const text of ['11.80–12.40','13.00','11.20','14.20','15.60','12.60','回踩 11.80–12.40 分批；跌破 11.20 离场。']){
    await expect(detail).toContainText(text);
  }
  // 入选理由 + 完整标签
  await expect(detail.locator('.pt-detail-reason')).toContainText('资金净流入、回踩买点；人形机器人产业订单落地。');
  await expect(detail.locator('.pt-detail-tags')).toContainText('概念 机器人 · 题材 人形机器人 · 减速器 · 事件 产业订单 · 其他 高端制造');
  // 入选统计：累计天数/今日/首次/最近
  await expect(detail.locator('.pt-kv > div').filter({hasText:'累计'})).toContainText('3 天 · 今日已入选');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'首次'})).toContainText('2026-11-11 11:02');
  await expect(detail.locator('.pt-kv > div').filter({hasText:'最近'})).toContainText('2026-11-11 11:02');
  const kvJoined=(await detail.locator('.pt-kv').allInnerTexts()).join(' ');
  for(const removed of ['来源','方向','状态','跟进','量比/换手','振幅/流通']){
    expect(kvJoined).not.toContain(removed);
  }
  // 当前符合：甲机器人 zone=已进入买区但现价 13.74 不在计划买区 11.80–12.40 → 否
  const current=detail.locator('.pt-current');
  await expect(current).toBeVisible();
  await expect(current.locator('b')).toHaveText('当前符合：否');
  await expect(current.locator('span')).toContainText('现价不在计划买区');
  await expect(current.locator('em')).toHaveText('不代表买入建议');
  await expect(current).not.toHaveClass(/is-match/);
  // 窗口表现：3 个 pt-win-badge（T+1 有值，T+3/T+5 待积累）
  const badges=detail.locator('.pt-win-badge');
  await expect(badges).toHaveCount(3);
  expect((await badges.allInnerTexts()).map(text=>text.replace(/\s+/g,' ').trim())).toEqual(['T+1 +2.50% 超额 +1.50%','T+3 待积累','T+5 待积累']);
  await expect(badges.nth(0)).toHaveAttribute('title','T+1 收益 +2.50% · 超额 +1.50%');
  await expect(badges.nth(1)).toHaveAttribute('title','T+3 尚未到期/待积累');
  // 操作按钮：买入/卖出/加自选/删除；无 K线
  for(const label of ['买入','卖出','加自选','删除']){
    await expect(detail.getByRole('button',{name:label,exact:true})).toBeEnabled();
  }
  await expect(detail.getByRole('button',{name:'K线',exact:true})).toHaveCount(0);
  // 今日未入选的股票：累计行文案为「N 天 · 今日未入选」
  await row.click();
  await human.locator('.pt-row').filter({hasText:'乙减速器'}).click();
  const notToday=page.getByRole('region',{name:'详情 乙减速器'});
  await expect(notToday).toBeVisible();
  await expect(notToday.locator('.pt-kv > div').filter({hasText:'累计'})).toContainText('2 天 · 今日未入选');
});

// ===== 10. 分时空态：提示并降级查看日K =====
test('详情图表：分时无数据时显示提示文案，可降级查看日K',async({page})=>{
  await boot(page,{emptyChart:true});
  await waitGroups(page);
  await groupOf(page,'人形机器人').locator('.pt-row').filter({hasText:'甲机器人'}).click();
  const panel=page.locator('.pt-detail section.stock-chart-panel[aria-label="行情图表 甲机器人"]');
  await expect(panel).toBeVisible();
  await expect(panel.locator('.scp-message')).toContainText('该股暂无可用的分时数据（可稍后重试或查看日K）。',{timeout:10000});
  const calls=await rpcCalls(page);
  expect(calls.some(call=>call.method==='minute_ensure'&&call.args.code==='sz000101')).toBe(true);
  expect(calls.some(call=>call.method==='job')).toBe(true);
  await panel.locator('.tabs[role="tablist"]').getByRole('tab',{name:'日K'}).click();
  await expect(panel.locator('.scp-chart .chart')).toHaveAttribute('aria-label','日K线及成交量',{timeout:10000});
  await expect(panel.locator('.scp-message')).toHaveCount(0);
});

// ===== 10b. 行详情「当前符合」判定 =====
test('详情当前符合：是=已进入买区+现价在买区+未破止损；否显示 zone/hint；均标注不代表买入建议',async({page})=>{
  const entries:Json[]=[
    makeEntry({code:'sz000901',name:'符合样本',sector:'测试方向A',group_name:'测试方向A',groups:[],
      tags:{concept:['测试方向A'],theme:[],event:[],other:[]},zone:'已进入买区',hint:'提示A',
      quote:quote(10,1.2),today_percent:1.2,since_add_percent:1.2,plan:planDefault(),
      history:[],windows:null,
      episodes:{total:1,today:1,first_at:'2026-11-09T10:00:00+08:00',last_at:'2026-11-11T10:00:00+08:00'},
      quant:{turnover_rate:2,volume_ratio:1.2,amplitude:2,float_mcap_yi:30},
      driver:null,driver_short:null,driver_short_at:null,fund:fund(1)}),
    makeEntry({code:'sz000902',name:'不符合样本',sector:'测试方向B',group_name:'测试方向B',groups:[],
      tags:{concept:['测试方向B'],theme:[],event:[],other:[]},zone:'等待回踩',hint:'等待回踩提示B',
      quote:quote(12,-1),today_percent:-1,since_add_percent:-1,plan:planDefault(),
      history:[],windows:null,
      episodes:{total:1,today:0,first_at:'2026-11-09T10:00:00+08:00',last_at:'2026-11-10T10:00:00+08:00'},
      quant:{turnover_rate:2,volume_ratio:1.2,amplitude:2,float_mcap_yi:30},
      driver:null,driver_short:null,driver_short_at:null,fund:fund(2)}),
  ];
  await boot(page,{entries});
  await waitGroups(page,2);
  // 是：zone=已进入买区 + 现价 10 在买区 9.50–10.00 + 未破止损 9.00
  await groupOf(page,'测试方向A').locator('.pt-row').filter({hasText:'符合样本'}).click();
  let current=page.getByRole('region',{name:'详情 符合样本'}).locator('.pt-current');
  await expect(current).toBeVisible();
  await expect(current.locator('b')).toHaveText('当前符合：是');
  await expect(current).toHaveClass(/is-match/);
  await expect(current.locator('span')).toHaveText('zone 已进入买区、现价处于计划买区且未破止损，仍符合入选条件');
  await expect(current.locator('em')).toHaveText('不代表买入建议');
  // 否：zone=等待回踩 + hint
  await groupOf(page,'测试方向A').locator('.pt-row').filter({hasText:'符合样本'}).click();
  await groupOf(page,'测试方向B').locator('.pt-row').filter({hasText:'不符合样本'}).click();
  current=page.getByRole('region',{name:'详情 不符合样本'}).locator('.pt-current');
  await expect(current).toBeVisible();
  await expect(current.locator('b')).toHaveText('当前符合：否');
  await expect(current).not.toHaveClass(/is-match/);
  await expect(current.locator('span')).toContainText('当前 等待回踩');
  await expect(current.locator('span')).toContainText('等待回踩提示B');
  await expect(current.locator('em')).toHaveText('不代表买入建议');
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

// ===== 12. 详情操作：买入跳模拟交易、加自选调用 add_job =====
test('详情操作：买入跳模拟交易、加自选调用 add_job（K线按钮已移除）',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  await groupOf(page,'人形机器人').locator('.pt-row').filter({hasText:'甲机器人'}).click();
  let detail=page.getByRole('region',{name:'详情 甲机器人'});
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
  expect(headHeight1440).toBeLessThan(40);
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
  expect(headHeight1000).toBeLessThan(40);
  const innerScroll1000=await groupsLoc(page).evaluateAll(groups=>groups.map(group=>{
    const scroller=group.querySelector(':scope > .pt-scroll') as HTMLElement;
    return {scrollWidth:scroller.scrollWidth,clientWidth:scroller.clientWidth};
  }));
  for(const item of innerScroll1000)expect(item.scrollWidth).toBeLessThanOrEqual(item.clientWidth+1);
  expect(await inlineOverflowProblems(page)).toEqual([]);
  // 单列时组顺序 = 全局资金倒序
  const singleColumnLabels=await columnLabels(page);
  expect(singleColumnLabels.length).toBe(1);
  expect(singleColumnLabels[0]).toEqual(['分组 人形机器人','分组 商业航天','分组 通信光通信','分组 其他','分组 半导体电子','分组 东方']);
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
  await expect(detail.locator('.pt-detail-chart section.stock-chart-panel')).toBeVisible();
  await expect(detail.locator('.pt-muted').filter({hasText:'只读预览'})).toContainText('只读预览：添加/删除/自选/交易请在桌面客户端操作。');
  await page.locator('.pool-terminal').screenshot({path:SHOTS+'/05-preview-readonly.png'});
  const panel=await openBacktest(page);
  await expect(panel.locator('.pt-bt-summary')).toContainText('样本 6');
  await expect(panel.locator('.pt-bt-badge')).toHaveText('回放/历史样本');
  await expect(panel.locator('.pt-bt-note')).toContainText('不构成投资建议');
  expect((await rpcCalls(page)).length).toBe(0);
});

// ===== 24. 自选监控共用 ChartViewTabs smoke =====
test('自选监控共用 tabs：chart-toolbar 的分时/日K/周K 三按钮可切换',async({page})=>{
  await boot(page,{});
  await waitGroups(page);
  await page.getByRole('button',{name:'自选监控',exact:true}).click();
  await expect(page.locator('.workspace-heading h1')).toHaveText('自选监控');
  const toolbar=page.locator('.chart-toolbar');
  await expect(toolbar).toBeVisible();
  const tabs=toolbar.locator('.tabs');
  await expect(tabs).toHaveCount(1);
  const buttons=tabs.locator('button');
  await expect(buttons).toHaveCount(3);
  expect((await buttons.allInnerTexts()).map(text=>text.trim())).toEqual(['分时','日K','周K']);
  await expect(buttons.nth(0)).toHaveClass(/chosen/);
  await buttons.nth(1).click();
  await expect(buttons.nth(1)).toHaveClass(/chosen/);
  await expect(buttons.nth(0)).not.toHaveClass(/chosen/);
  await expect(toolbar).toBeVisible();
  await buttons.nth(2).click();
  await expect(buttons.nth(2)).toHaveClass(/chosen/);
  await expect(page.locator('.chart-toolbar')).toBeVisible();
});

// ===== 25. console 无 error =====
test('console：瀑布流浏览/排序/筛选/详情/回测无 console error 与 pageerror',async({page})=>{
  const consoleErrors:string[]=[];
  const pageErrors:string[]=[];
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
  page.on('pageerror',error=>pageErrors.push(String(error)));
  await boot(page,{});
  await waitGroups(page);
  await groupOf(page,'人形机器人').getByRole('button',{name:'按入选后涨幅排序'}).click();
  await page.getByRole('group',{name:'入选筛选'}).getByRole('button',{name:'今日入选 3'}).click();
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

test('股票池展开当天缓存只有上午数据时，收盘后自动补全到 15:00',async({page})=>{
  await page.clock.install({time:new Date('2026-11-12T16:15:00+08:00')});
  await boot(page,{today:'2026-11-12'});
  await page.evaluate(()=>{
    const w=window as any,original=w.__TAURI_INTERNALS__.invoke;
    w.poolStaleEnsures=0;
    w.__TAURI_INTERNALS__.invoke=async(command:string,params:any)=>{
      if(command==='rpc'&&params.method==='minute_ensure'&&params.args?.refresh===true)w.poolStaleEnsures++;
      const result=await original(command,params);
      if(command==='rpc'&&params.method==='chart'&&params.args?.code==='sz000101'&&params.args.kind==='minute'){
        const morning=[
          {time:'09:30',close:'10.00',volume:100,complete:true,average:'10.00'},
          {time:'10:00',close:'10.02',volume:120,complete:true,average:'10.01'},
          {time:'11:30',close:'10.05',volume:90,complete:true,average:'10.02'},
        ];
        const bars=w.poolStaleEnsures?[...morning,{time:'15:00',close:'10.20',volume:300,complete:true,average:'10.10'}]:morning;
        return [{day:'2026-11-12',data:{bars,previous_close:'10'}}];
      }
      return result;
    };
  });
  const row=page.locator('.pt-row').filter({has:page.locator('.pt-name[title="甲机器人"]')});
  await row.click();
  const detail=page.getByRole('region',{name:'详情 甲机器人'});
  // 收盘后缓存残缺：StockChartPanel 自动补取一次当天分时（无此修复时状态会停在“至 11:30”）。
  await expect.poll(()=>page.evaluate(()=>(window as any).poolStaleEnsures)).toBeGreaterThan(0);
  await expect(detail.locator('.scp-state')).toContainText('分时 2026-11-12 · 至 15:00');
  const value=await detail.locator('.chart').evaluate(async el=>{
    const source=await fetch('/src/Chart.tsx').then(r=>r.text());const e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);
    const option=e.getInstanceByDom(el).getOption();return option.series.find((s:any)=>s.name==='价格').data[option.xAxis[0].data.indexOf('15:00')];
  });
  expect(value).toBe(10.2);
  await page.screenshot({path:'../../outputs/stock-pool-stale-fix-20261113/screenshots/pool-after-close-full-day.png'});
});
