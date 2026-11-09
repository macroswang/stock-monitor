import {test,expect,type Page} from '@playwright/test';

type Json=Record<string,any>;
const quote=(price:number,percent:number,time='2026-11-09T13:18:00+08:00',basis:'live'|'last'='live')=>({price,percent,time,low:price*0.97,high:price*1.03,basis,fresh:basis==='live'});
const plan=()=>({buy_low:9.5,buy_high:10,chase:11,stop:9,target1:11,target2:12,trail:9.5,note:'回踩 9.50–10.00 可分批；跌破 9.00 离场。',sell_note:'接近 11.00 分批减半；跌破 9.00 离场。'});
const history=(day:string,price:number,percent:number,hit_buy=false,hit_stop=false,hit_target=false)=>({day,price,percent,high:price*1.02,low:price*0.98,hit_buy,hit_stop,hit_target});
const holdingDaysByDay:Record<string,number>={'2026-11-09':0,'2026-11-08':1,'2026-11-06':1,'2026-11-05':2,'2026-11-03':4,'2026-10-30':6};
const holdingBucket=(days:number)=>days<=0?'0':days===1?'1':days===2?'2':days<=5?'3-5':days<=10?'6-10':'10+';
const entry=(code:string,name:string,added_day:string,added_price:number,category:string,group_name:string,entry_tag:string,options:Json={}):Json=>({
  code,name,added_day,added_at:options.addedAt??(added_day+'T16:20:00+08:00'),added_price,
  source:options.source??'建仓清单',sector:group_name,role:options.role??'低吸候选',state:options.state??'观察',
  entry_tag,category,group_name,groups:options.groups??[category],
  reason:name+' 的入选理由：资金净流入、回踩买点附近。',updated_at:'2026-11-09T13:20:00+08:00',
  plan:plan(),quote:options.quote===undefined?quote(added_price*1.05,2):options.quote,
  today_percent:options.today===undefined?2:options.today,since_add_percent:options.since===undefined?5:options.since,
  distance_to_buy_percent:1,zone:'已进入买区',hint:name+' 提示',
  history:options.history??[history('2026-11-06',added_price,1),history('2026-11-09',added_price*1.05,2)],
  max_gain_percent:options.maxGain===undefined?6:options.maxGain,max_drawdown_percent:options.maxDrawdown===undefined?-1:options.maxDrawdown,
  hold_days:options.hold===undefined?1:options.hold,
  windows:options.windows??{'T+1':{n:1,date:'2026-11-09',close:added_price*1.02,return_percent:2,benchmark_return:0.42,excess_percent:1.58},'T+3':null,'T+5':null},
  holding_days:holdingDaysByDay[added_day]??0,holding_bucket:holdingBucket(holdingDaysByDay[added_day]??0),
});
const entries:Json[]=[
  entry('sz000001','测试A','2026-11-09',10,'行业','半导体','可建仓',{addedAt:'2026-11-09T14:18:00+08:00',quote:quote(10.5,2),today:2,since:5,maxGain:6,maxDrawdown:-1,hold:0,windows:{'T+1':{n:1,date:'2026-11-10',close:10.25,return_percent:2.5,benchmark_return:0.5,excess_percent:2.0},'T+3':null,'T+5':null},history:[history('2026-11-09',10.5,2,false,false,true)]}),
  entry('sz000002','测试B','2026-11-09',20,'概念','消费电子','涨停待回踩',{quote:quote(19.6,1.14),today:1.14,since:-2,maxGain:0.2,maxDrawdown:-2,hold:0}),
  entry('sz000003','测试C','2026-11-08',30,'题材','固态电池','题材观察',{quote:null,today:null,since:null,maxGain:null,maxDrawdown:null,hold:1}),
  entry('sz000004','测试D','2026-11-06',40,'事件','军工订单','条件未达',{quote:quote(41,1.6),today:1.6,since:2.5,maxGain:3,maxDrawdown:-1.5,hold:2,history:[history('2026-11-06',40,1),history('2026-11-09',41,1.6,false,false,true)]}),
  entry('sz000005','测试E','2026-11-09',5,'名称辈','东方','高于追高上限',{quote:quote(5,0),today:0,since:0,maxGain:1,maxDrawdown:-0.5,hold:0,history:[history('2026-11-09',5,0,true)]}),
  entry('sz000006','测试F','2026-11-05',12,'生肖玄学','2027 羊年（跨年）','题材观察',{quote:quote(11.4,-1.8),today:-1.8,since:-5,maxGain:0.5,maxDrawdown:-6,hold:3,source:'炒作雷达'}),
  entry('sz000007','测试G','2026-11-03',8,'手动','手动观察','观察',{quote:quote(8.4,2.5),today:2.5,since:5,maxGain:5,maxDrawdown:-1,hold:4,source:'手动'}),
  entry('sz000008','测试H','2026-10-30',15,'行业','银行','可建仓',{quote:quote(15.3,0.8),today:0.8,since:2,maxGain:2,maxDrawdown:-2,hold:6}),
  entry('sz002310','东方新能','2026-11-09',21.79,'名称辈','东方','条件未达',{addedAt:'2026-11-09T08:11:30+08:00',quote:null,today:null,since:null,maxGain:null,maxDrawdown:null,hold:0,role:'龙头',groups:['名称辈','概念']}),
];

async function boot(page:Page,options:{pageSize?:number;filters?:Json}={}){
  await page.addInitScript(({entries,pageSize,filters})=>{
    try{if(filters)localStorage.setItem('stock-monitor-pool-filters',JSON.stringify(filters));else if(!sessionStorage.getItem('pool-test-cleared')){localStorage.removeItem('stock-monitor-pool-filters');}sessionStorage.setItem('pool-test-cleared','1');}catch{}
    (window as any).__poolCalls=[];
    const dateMinus=(day:string,offset:number)=>{const value=new Date(day+'T00:00:00Z');value.setUTCDate(value.getUTCDate()-offset);return value.toISOString().slice(0,10);};
    const round=(value:number)=>Math.round(value*100)/100;
    const average=(values:number[])=>values.length?round(values.reduce((sum,value)=>sum+value,0)/values.length):null;
    const median=(values:number[])=>{if(!values.length)return null;const sorted=[...values].sort((a,b)=>a-b);const middle=Math.floor(sorted.length/2);return round(sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2);};
    const CATEGORIES=['行业','概念','题材','事件','名称辈','生肖玄学','手动','其他'];
    const TAGS=['可建仓','涨停待回踩','高于追高上限','条件未达','题材观察','观察'];
    const groupsOf=(row:any)=>row.groups&&row.groups.length?row.groups:[row.category];
    const build=(args:any)=>{
      let timeRows=[...entries];
      if(typeof args.days==='number'){const cutoff=dateMinus('2026-11-09',args.days-1);timeRows=timeRows.filter((row:any)=>row.added_day>=cutoff);}
      if(args.start)timeRows=timeRows.filter((row:any)=>row.added_day>=args.start);
      if(args.end)timeRows=timeRows.filter((row:any)=>row.added_day<=args.end);
      for(const category of CATEGORIES){
        const members=[...timeRows].filter((row:any)=>row.category===category)
          .sort((left:any,right:any)=>(left.since_add_percent===null?1:0)-(right.since_add_percent===null?1:0)||((right.since_add_percent??-999)-(left.since_add_percent??-999)));
        members.forEach((row:any,index:number)=>{row.group_rank=index+1;row.group_size=members.length;});
      }
      const countTag=(rows:any[],tag:string)=>rows.filter((row:any)=>row.entry_tag===tag).length;
      const counts={total:timeRows.length,ready:countTag(timeRows,'可建仓'),limit_up:countTag(timeRows,'涨停待回踩'),
        above_chase:countTag(timeRows,'高于追高上限'),waiting:countTag(timeRows,'条件未达'),speculative:countTag(timeRows,'题材观察'),
        manual:timeRows.filter((row:any)=>row.category==='手动').length,
        bought:timeRows.filter((row:any)=>row.state==='已买入').length,
        exited:timeRows.filter((row:any)=>row.state==='已退出').length,
        ignored:timeRows.filter((row:any)=>row.state==='忽略').length};
      const tag_stats=TAGS.map(tag=>{
        const rows=timeRows.filter((row:any)=>row.entry_tag===tag);
        if(!rows.length)return null;
        const sample=rows.filter((row:any)=>row.quote&&Number.isFinite(row.since_add_percent));
        const wins=sample.filter((row:any)=>row.since_add_percent>0).length;
        return {entry_tag:tag,count:rows.length,sample:sample.length,win_rate:sample.length?round(100*wins/sample.length):null,
          avg_since_percent:average(sample.map((row:any)=>row.since_add_percent))};
      }).filter(Boolean);
      const groups=CATEGORIES.map(category=>{
        const members=timeRows.filter((row:any)=>groupsOf(row).includes(category));
        if(!members.length)return null;
        const sample=members.filter((row:any)=>row.quote&&Number.isFinite(row.since_add_percent));
        const wins=sample.filter((row:any)=>row.since_add_percent>0).length;
        return {category,count:members.length,sample:sample.length,win_rate:sample.length?round(100*wins/sample.length):null,
          avg_since_percent:average(sample.map((row:any)=>row.since_add_percent))};
      }).filter(Boolean);
      const windowStats=(key:string)=>{
        const sampled=timeRows.filter((row:any)=>(row.windows??{})[key]);
        const returns=sampled.map((row:any)=>row.windows?.[key]?.return_percent).filter((value:any)=>typeof value==='number');
        const excess=sampled.map((row:any)=>row.windows?.[key]?.excess_percent).filter((value:any)=>typeof value==='number');
        const windowWins=returns.filter((value:number)=>value>0).length;
        const beats=excess.filter((value:number)=>value>0).length;
        return {sample:returns.length,win_rate:returns.length?round(100*windowWins/returns.length):null,
          avg_return_percent:average(returns),beat_rate:excess.length?round(100*beats/excess.length):null,avg_excess_percent:average(excess)};
      };
      const holdingLabels:Record<string,string>={'0':'0日','1':'1日','2':'2日','3-5':'3–5日','6-10':'6–10日','10+':'10日以上'};
      const holdingStats=Object.keys(holdingLabels).map(bucket=>{
        const members=timeRows.filter((row:any)=>row.holding_bucket===bucket);
        if(!members.length)return null;
        const groupSample=members.filter((row:any)=>row.quote&&Number.isFinite(row.since_add_percent));
        const groupWins=groupSample.filter((row:any)=>row.since_add_percent>0).length;
        return {bucket,label:holdingLabels[bucket],count:members.length,sample:groupSample.length,
          win_rate:groupSample.length?round(100*groupWins/groupSample.length):null,
          avg_since_percent:average(groupSample.map((row:any)=>row.since_add_percent))};
      }).filter(Boolean);
      const windows={ 'T+1':windowStats('T+1'),'T+3':windowStats('T+3'),'T+5':windowStats('T+5') };
      let rows=timeRows;
      if(args.group)rows=rows.filter((row:any)=>groupsOf(row).includes(args.group));
      if(args.status)rows=rows.filter((row:any)=>row.entry_tag===args.status||row.state===args.status);
      if(args.holding)rows=rows.filter((row:any)=>row.holding_bucket===args.holding);
      const total=rows.length;
      const offset=Number(args.offset??0);
      const effectiveLimit=pageSize??Number(args.limit??60);
      const page=rows.slice(offset,offset+effectiveLimit);
      const sample=rows.filter((row:any)=>row.quote&&Number.isFinite(row.since_add_percent));
      const wins=sample.filter((row:any)=>row.since_add_percent>0).length;
      const sinceValues=sample.map((row:any)=>row.since_add_percent);
      const todayValues=rows.filter((row:any)=>Number.isFinite(row.today_percent)).map((row:any)=>row.today_percent);
      const drawdowns=rows.filter((row:any)=>Number.isFinite(row.max_drawdown_percent)).map((row:any)=>row.max_drawdown_percent);
      const summary={total:rows.length,sample:sample.length,wins,losses:sample.filter((row:any)=>row.since_add_percent<0).length,
        flat:sample.filter((row:any)=>row.since_add_percent===0).length,win_rate:sample.length?round(100*wins/sample.length):null,
        avg_since_percent:average(sinceValues),median_since_percent:median(sinceValues),
        max_since_percent:sinceValues.length?Math.max(...sinceValues):null,min_since_percent:sinceValues.length?Math.min(...sinceValues):null,
        avg_today_percent:average(todayValues),avg_max_gain_percent:null,avg_max_drawdown_percent:average(drawdowns),
        target_hits:rows.reduce((sum:number,row:any)=>sum+(row.history??[]).filter((item:any)=>item.hit_target).length,0),
        stop_hits:rows.reduce((sum:number,row:any)=>sum+(row.history??[]).filter((item:any)=>item.hit_stop).length,0),
        buy_zone_hits:rows.reduce((sum:number,row:any)=>sum+(row.history??[]).filter((item:any)=>item.hit_buy).length,0)};
      return {updated_at:'2026-11-09T13:20:30+08:00',quotes_time:'2026-11-09T13:18:00+08:00',trading:true,error:'',
        summary,counts,tag_stats,groups,entries:page,filtered_total:total,has_more:offset+page.length<total,offset,limit:effectiveLimit,filters:{},
        windows,holding:holdingStats,benchmark:'上证指数',daily_ready:true,archived_count:2};
    };
    Object.assign(window,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
      metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
      async invoke(command:string,params:{method:string;args?:Record<string,unknown>}){
        if(command!=='rpc')return 0;
        (window as any).__poolCalls.push({method:params.method,args:params.args??{}});
        switch(params.method){
          case 'snapshot':return {watch:[{code:'sz000001',name:'测试A',enabled:1,health:'正常',candidates:[],quote:null,broker_sources:[]}],events:[],config:{},now:new Date().toISOString(),market_open:true};
          case 'market':case 'market_overview':return {quotes:[],minute:null};
          case 'pool':return build(params.args??{});
          case 'pool_export':{const built=build(params.args??{});return {csv:'/tmp/pool-export-20261109.csv',report:'/tmp/pool-export-20261109.md',count:built.filtered_total};}
          case 'stock_search':return [{code:'sh601318',name:'中国平安',initials:'ZGPA'},{code:'sh600519',name:'贵州茅台',initials:'GZMT'}];
          case 'pool_add':case 'pool_remove':case 'pool_mark':case 'pool_sync':return {ok:true};
          case 'add_job':return {code:params.args?.code};
          case 'paper_sync':return {accounts:[],account:null,positions:[],orders:[],fills:[],order_count:0,fill_count:0};
          case 'paper_quote':return {code:params.args?.code,name:'测试A',stamp:params.args?.stamp,price:1050,volume:0,source:'测试',token:'t',order_mode:'paper'};
          case 'chart':return [];
          case 'history':return {daily:[],days:[],events:[],source:{}};
          case 'volume_flow':return {code:params.args?.code,day:'',status:'unavailable',minutes:[],message:''};
          default:throw Error('测试未提供 '+params.method);
        }
      }
    }});
  },{entries,pageSize:options.pageSize??60,filters:options.filters});
  await page.goto('/');
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  await expect(page.getByRole('region',{name:'股票池'})).toBeVisible();
}
const poolCalls=(page:Page)=>page.evaluate(()=>(window as any).__poolCalls as {method:string;args:Json}[]);
const lastPool=(page:Page)=>poolCalls(page).then(calls=>[...calls].reverse().find(call=>call.method==='pool')?.args??{});

test('默认近3日摘要/小样本与状态 chips，切换全部后数字正确',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  await expect(root.getByLabel('时间段')).toHaveValue('近3日');
  const summary=root.getByRole('group',{name:'股票池摘要'});
  await expect(summary).toContainText('样本');
  await expect(summary).toContainText('3');
  await expect(summary).toContainText('+33.3%');
  await expect(summary).toContainText('小样本');
  await expect(summary.locator('.fp-kpi')).toHaveCount(6);
  await expect(root.getByText(/胜率=最新价高于入选基准价的样本占比/)).toBeHidden();
  await root.getByRole('button',{name:'样本说明'}).click();
  await expect(root.getByText(/胜率=最新价高于入选基准价的样本占比/)).toBeVisible();
  await expect(root.getByText('按入选状态胜率')).toBeVisible();
  await expect(root.getByText('提醒规则')).toBeVisible();
  await expect(root.getByText('免责声明')).toBeVisible();
  await expect(root.getByRole('button',{name:/^全部 5/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^可建仓 1/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^涨停待回踩 1/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^条件未达 1/})).toBeVisible();
  await root.getByLabel('时间段').selectOption('全部');
  await expect.poll(async()=>(await lastPool(page)).days).toBeUndefined();
  await expect(summary).toContainText('7');
  await expect(summary).toContainText('+57.1%');
  await expect(summary).not.toContainText('小样本');
  await expect(root.getByRole('button',{name:/^全部 9/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^条件未达 2/})).toBeVisible();
});

test('核心修复：切换状态 chip 后其它 chip 数字不变',async({page})=>{
  await boot(page,{filters:{period:'全部',group:'全部',status:'全部',sort:'自入选涨幅',startDay:'',endDay:''}});
  const root=page.getByRole('region',{name:'股票池'});
  await root.getByRole('button',{name:/^涨停待回踩 1/}).click();
  await expect(root.getByRole('button',{name:/^涨停待回踩 1/})).toHaveAttribute('aria-pressed','true');
  await expect.poll(async()=>(await lastPool(page)).status).toBe('涨停待回踩');
  await expect(root.getByRole('button',{name:/^全部 9/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^可建仓 2/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^高于追高上限 1/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^条件未达 2/})).toBeVisible();
  await expect(root.getByRole('button',{name:/^题材观察 2/})).toBeVisible();
  await expect(root.locator('.fp-row')).toHaveCount(1);
});

test('列头/分组/多标签/组内排名与名称辈东方新能',async({page})=>{
  await boot(page,{filters:{period:'全部',group:'全部',status:'全部',sort:'自入选涨幅',startDay:'',endDay:''}});
  const root=page.getByRole('region',{name:'股票池'});
  const head=root.locator('.fp-head-row').first();
  await expect(head).toContainText('股票');
  await expect(head).toContainText('入选时间');
  await expect(head).toContainText('入选价格');
  await expect(head).toContainText('自入选');
  await expect(head).toContainText('现价 · 今日');
  await expect(root.getByText(/分组计数可重复/)).toBeHidden();
  await expect(root.getByRole('button',{name:'分组说明',exact:true,includeHidden:true})).toBeHidden();
  const industry=root.getByRole('region',{name:'分组 行业'});
  await expect(industry.locator('.fp-group-head')).toContainText('2 条');
  await expect(industry.locator('.fp-group-head')).toContainText('胜率 100.0%');
  await expect(industry.locator('.fp-row').first()).toContainText('测试A');
  const known=root.getByRole('region',{name:'分组 名称辈'});
  await expect(known).toContainText('东方新能');
  await expect(known).toContainText('测试E');
  const newEnergy=known.locator('.fp-row').filter({hasText:'东方新能'});
  await expect(newEnergy).toContainText('+概念');
  await expect(newEnergy).toContainText('组内 #2/2');
  await root.getByRole('group',{name:'分组筛选'}).getByRole('button',{name:/^概念/}).click();
  await expect.poll(async()=>(await lastPool(page)).group).toBe('概念');
  await expect(root.locator('.fp-row')).toHaveCount(2);
  await root.getByRole('group',{name:'分组筛选'}).getByRole('button',{name:'全部',exact:true}).click();
  await expect(root.locator('.fp-row')).toHaveCount(9);
});

test('时间段筛选：今日/近3日与自定义起止日请求参数',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  await expect(root.getByLabel('时间段')).toHaveValue('近3日');
  await root.getByLabel('时间段').selectOption('今日');
  await expect.poll(async()=>(await lastPool(page)).days).toBe(1);
  await expect(root.locator('.fp-row')).toHaveCount(4);
  await root.getByLabel('时间段').selectOption('自定义');
  await root.getByLabel('开始日期').fill('2026-11-01');
  await root.getByLabel('结束日期').fill('2026-11-06');
  await expect.poll(async()=>{const args=await lastPool(page);return args.start+'|'+args.end;}).toBe('2026-11-01|2026-11-06');
  await expect(root.locator('.fp-row')).toHaveCount(3);
});

test('行显示入选时间/入选价格/自入选，详情显示跟踪天数与最大浮盈回撤且无按钮',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  const row=root.locator('.fp-row').filter({hasText:'测试A'});
  await expect(row.locator('.fp-added-time')).toHaveText(/\d{2}-\d{2} \d{2}:\d{2}/);
  await expect(row.locator('.fp-cell-base').nth(1)).toContainText('10.00');
  await expect(row.locator('.fp-since-big')).toContainText('+5.00%');
  await row.getByRole('button',{name:/测试A/}).first().click();
  const detail=root.getByRole('region',{name:'股票池详情'});
  await expect(detail).toContainText('入选基准 10.00 元（2026-11-09 14:18 入选）');
  await expect(detail).toContainText('已跟踪交易日 0 天');
  await expect(detail).toContainText('最大浮盈 +6.0%');
  await expect(detail).toContainText('最大回撤 -1.0%');
  await expect(detail.getByRole('button')).toHaveCount(0);
});

test('行操作固定 4 个按钮，K线打开日K并显示名称',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  const row=root.locator('.fp-row').filter({hasText:'测试A'});
  await expect(row.locator('.fp-actions button')).toHaveCount(4);
  await expect(row.getByRole('button',{name:'测试A 买入',exact:true})).toBeVisible();
  await expect(row.getByRole('button',{name:'测试A 加入自选',exact:true})).toBeVisible();
  await expect(row.getByRole('button',{name:'测试A 打开K线',exact:true})).toBeVisible();
  await expect(row.getByRole('button',{name:'测试A 删除',exact:true})).toBeVisible();
  await row.getByRole('button',{name:'测试A 打开K线',exact:true}).click();
  await expect(page.getByRole('heading',{level:1,name:'自选监控'})).toBeVisible();
  await expect(page.getByRole('heading',{level:2,name:/测试A/}).first()).toBeVisible();
});

test('加载更多：请求 offset=已显示数量并 append 列表',async({page})=>{
  await boot(page,{pageSize:5,filters:{period:'全部',group:'全部',status:'全部',sort:'自入选涨幅',startDay:'',endDay:''}});
  const root=page.getByRole('region',{name:'股票池'});
  await expect(root.locator('.fp-row')).toHaveCount(5);
  const more=root.getByRole('button',{name:/加载更多（已显示 5 \/ 共 9）/});
  await expect(more).toBeVisible();
  await more.click();
  await expect.poll(async()=>{const args=await lastPool(page);return String(args.offset)+'|'+String(args.limit);}).toBe('5|60');
  await expect(root.locator('.fp-row')).toHaveCount(9);
  await expect(root.getByRole('button',{name:/加载更多/})).toHaveCount(0);
  await expect(root).toContainText('已显示 9 / 共 9');
});

test('筛选条件写入 localStorage，reload 后恢复并带原参数请求',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  await root.getByLabel('时间段').selectOption('全部');
  await root.getByRole('group',{name:'分组筛选'}).getByRole('button',{name:/^概念/}).click();
  await expect.poll(async()=>(await lastPool(page)).group).toBe('概念');
  await page.reload();
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  await expect(page.getByRole('region',{name:'股票池'})).toBeVisible();
  await expect.poll(async()=>{const args=await lastPool(page);return String(args.group)+'|'+String(args.days);}).toBe('概念|undefined');
  const restored=page.getByRole('region',{name:'股票池'});
  await expect(restored.getByLabel('时间段')).toHaveValue('全部');
  await expect(restored.getByRole('group',{name:'分组筛选'}).getByRole('button',{name:/^概念/})).toHaveAttribute('aria-pressed','true');
});

test('跨日窗口表与持有交易日筛选：holding 请求参数可叠加',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  const windows=root.getByRole('group',{name:'跨日窗口表现'});
  await expect(windows).toContainText('T+1');
  await expect(windows).toContainText('T+3');
  await expect(windows).toContainText('T+5');
  await expect(windows).toContainText('跑赢上证占比');
  await expect(windows.locator('.fp-window-grid > span').nth(1)).not.toHaveText('待积累');
  await expect(windows).toContainText('待积累');
  await expect(windows.getByText(/基准：上证指数/)).toBeHidden();
  await root.getByRole('button',{name:'跨日窗口说明'}).click();
  await expect(windows.getByText(/基准：上证指数/)).toBeVisible();
  await expect(windows.getByText(/日K覆盖/)).toBeVisible();
  await root.getByRole('button',{name:'折叠跨日窗口'}).click();
  await expect(windows.locator('.fp-window-grid')).toBeHidden();
  await expect(root.getByRole('button',{name:'展开跨日窗口'})).toHaveAttribute('aria-expanded','false');
  await root.getByRole('button',{name:'展开跨日窗口'}).click();
  await expect(windows.locator('.fp-window-grid')).toBeVisible();
  await root.getByRole('button',{name:'折叠按持有交易日'}).click();
  await expect(root.getByRole('group',{name:'按持有交易日'}).locator('.fp-holding-chips')).toBeHidden();
  await root.getByRole('button',{name:'展开按持有交易日'}).click();
  const holdings=root.getByRole('group',{name:'按持有交易日'});
  const oneDay=holdings.getByRole('button',{name:/^1日/});
  await expect(oneDay).toBeVisible();
  await oneDay.click();
  await expect.poll(async()=>(await lastPool(page)).holding).toBe('1');
  await oneDay.click();
  await expect.poll(async()=>(await lastPool(page)).holding).toBeUndefined();
  await root.getByRole('button',{name:/^可建仓 1/}).click();
  await oneDay.click();
  await expect.poll(async()=>{const args=await lastPool(page);return String(args.status)+'|'+String(args.holding);}).toBe('可建仓|1');
});

test('说明浮层点击内部保留、点击空白关闭，工具条隐藏归档与导出入口',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  await expect(root.getByText(/进入买区\/跌破防守位会按观量现有通知设置/)).toBeHidden();
  await root.getByRole('button',{name:'样本说明'}).click();
  const reminder=root.getByText(/进入买区\/跌破防守位会按观量现有通知设置/);
  await expect(reminder).toBeVisible();
  await reminder.click();
  await expect(root.getByRole('button',{name:'样本说明'})).toHaveAttribute('aria-expanded','true');
  await root.locator('.fp-kpis').click({position:{x:5,y:5}});
  await expect(reminder).toBeHidden();
  await expect(root.getByRole('button',{name:'样本说明'})).toHaveAttribute('aria-expanded','false');
  await expect(root.getByText('已归档 2')).toBeHidden();
  await expect(root.getByLabel('包含归档')).toBeHidden();
  for(const name of ['分组说明','归档说明','导出复盘','自动同步说明']){
    await expect(root.getByRole('button',{name,exact:true,includeHidden:true})).toBeHidden();
  }
  await expect(root.getByText('复盘记录 · 不构成投资建议',{exact:true})).toHaveCount(0);
  expect((await lastPool(page)).include_archived).toBe(false);
  expect((await poolCalls(page)).some(item=>item.method==='pool_export')).toBe(false);
});

test('详情区间表现：T+1 收益与相对上证超额，未覆盖显示待积累',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  const row=root.locator('.fp-row').filter({hasText:'测试A'});
  await row.getByRole('button',{name:/测试A/}).first().click();
  const detail=root.getByRole('region',{name:'股票池详情'});
  await expect(detail).toContainText('区间表现');
  await expect(detail).toContainText('基准：上证指数');
  const table=detail.locator('.fp-window-table');
  await expect(table).toContainText('T+1');
  await expect(table).toContainText('11-10');
  await expect(table).toContainText('+2.50%');
  await expect(table).toContainText('+2.00%');
  await expect(table).toContainText('待积累');
});

test('拼音首字母搜索：股票池与自选添加',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  const search=root.getByLabel('股票代码/名称/拼音首字母');
  await search.fill('zgpa');
  const option=root.getByRole('option',{name:/中国平安/});
  await expect(option).toBeVisible();
  await option.click();
  await expect.poll(async()=>(await poolCalls(page)).some(call=>call.method==='pool_add'&&call.args.code==='sh601318')).toBe(true);
  await page.getByRole('button',{name:'自选监控',exact:true}).click();
  const watchSearch=page.locator('.watchlist input[role="combobox"]');
  await watchSearch.fill('zgpa');
  const watchOption=page.locator('.watchlist').getByRole('option',{name:/中国平安/});
  await expect(watchOption).toBeVisible();
  await watchOption.click();
  await expect.poll(async()=>(await poolCalls(page)).some(call=>call.method==='add_job'&&call.args.code==='sh601318')).toBe(true);
});

test('空态显示引导文案',async({page})=>{
  await page.addInitScript(()=>{
    try{localStorage.removeItem('stock-monitor-pool-filters');}catch{}
    Object.assign(window,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
      metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
      async invoke(command:string,params:{method:string}){
        if(command!=='rpc')return 0;
        switch(params.method){
          case 'snapshot':return {watch:[],events:[],config:{},now:new Date().toISOString(),market_open:true};
          case 'market':case 'market_overview':return {quotes:[],minute:null};
          case 'pool':return {updated_at:null,quotes_time:null,summary:null,counts:null,tag_stats:[],groups:[],entries:[],filtered_total:0,has_more:false,error:''};
          default:throw Error('测试未提供 '+params.method);
        }
      }
    }});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'股票池',exact:true}).click();
  const root=page.getByRole('region',{name:'股票池'});
  await expect(root).toContainText('股票池还没有标的');
  await expect(root.getByRole('group',{name:'股票池摘要'})).toContainText('待取得');
});

test('1000px 桌面宽度无横向溢出，行折叠为卡片',async({page})=>{
  await boot(page);
  const root=page.getByRole('region',{name:'股票池'});
  await root.locator('.fp-row').filter({hasText:'测试A'}).getByRole('button',{name:/测试A/}).first().click();
  await expect(root.getByRole('region',{name:'股票池详情'})).toBeVisible();
  await page.setViewportSize({width:1000,height:900});
  await expect(root.locator('.fp-head-row').first()).toBeHidden();
  const dimensions=await page.evaluate(()=>({
    scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,
    body:document.body.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client+1);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.client+1);
});
