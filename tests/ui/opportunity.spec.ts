import {test,expect,type Page} from '@playwright/test';

const DAY='2026-11-06';
const BATCH='2026-11-06T15:31:00+08:00';
const NOW='2026-11-06T16:00:00+08:00';
const QUOTE_TIME='2026-11-06T15:00:00+08:00';

const day={
  date:DAY,status:'closed',advance:3421,decline:1568,flat:142,suspended:0,
  advance_volume:0,decline_volume:0,flat_volume:0,advancing_percent:66.67,advancing_volume_percent:null,
  expected:5131,covered:5131,missing:0,collected_at:BATCH,first_quote:'2026-11-06T14:58:00+08:00',
  last_quote:'2026-11-06T15:01:00+08:00',source:'测试全市场广度',
};

const LIVE_NOW='2026-11-09T09:39:00+08:00';
const liveDay={
  date:'2026-11-09',status:'provisional',advance:2100,decline:2600,flat:431,suspended:0,
  advance_volume:0,decline_volume:0,flat_volume:0,advancing_percent:40.93,advancing_volume_percent:null,
  expected:5131,covered:5131,missing:0,collected_at:'2026-11-09T09:39:00+08:00',
  first_quote:'2026-11-09T09:37:00+08:00',last_quote:'2026-11-09T09:39:00+08:00',source:'测试盘中广度',
};
const levels=(ma5:number,ma10:number,ma20:number,high20:number,low20:number)=>({ma5,ma10,ma20,high20,low20});
const entry=(buy_low:number,buy_high:number,stop:number,chase:number,target1:number,target2:number,trail:number,note:string,sell_note:string)=>
  ({buy_low,buy_high,stop,chase,target1,target2,trail,note,sell_note});
const stock=(code:string,name:string,role:string,price:number,percent:number,amount_yuan:number,low:number,
  boards:number|null,limit_tag:string|null,stkLevels:unknown,stkEntry:unknown,reason:string|null=null)=>
  ({code,name,role,price,percent,amount_yuan,low,boards,limit_tag,reason,levels:stkLevels,entry:stkEntry});
const quote=(code:string,price:number,previous:number,dayLow:number,timestamp=QUOTE_TIME)=>
  ({code,price:String(price),previous_close:String(previous),day_low:String(dayLow),timestamp,amount_yuan:'100000000'});
const trigger='市场下跌家数≤2/3；板块当日上涨；板块资金净流入；候选涨幅<5%；候选站回昨收上方；同行至少 1 只上涨';

const quotes=[
  quote('sh603986',128.40,125.50,123.80),quote('sz301308',186.54,169.58,172.10),quote('sh688981',96.80,92.50,92.40),
  quote('sh688525',65.43,61.65,60.80),quote('sz001309',87.10,88.20,86.50),
  quote('sh600025',9.85,9.98,9.80),quote('sh600900',30.20,30.08,29.85),quote('sh600886',15.62,15.65,15.50),
  quote('sh600438',22.10,22.40,21.80,'2026-11-06T10:15:00+08:00'),quote('sh601012',21.58,19.62,20.10),quote('sz300274',96.20,95.80,94.60),
];

const directions=[
  {rank:1,sector:'半导体',sector_code:'new_bdt',sector_kind:'行业',change:3.21,net:6820000000,net_5d:14200000000,net_5d_days:3,
   score:8.42,state:'可考虑建仓',why:'6 项盘中条件全部满足，板块净流入 68.20 亿元。',
   opportunity:'存储涨价与设备国产替代共振，板块放量突破 20 日新高，回踩可低吸。',
   logic:['板块当日上涨 3.21%，主力净流入 68.20 亿元。','近 3 个采集日累计净流入 142.00 亿元（3 天）。'],
   risk:'若候选股跌破 117.40 元则放弃。',candidate:{code:'sh603986',name:'兆易创新'},
   peers:[{code:'sz301308',name:'江波龙',stop:161.90},{code:'sh688981',name:'中芯国际',stop:86.83}],
   stocks:[
     stock('sh603986','兆易创新','低吸候选',128.40,2.31,4320000000,123.80,0,null,
       levels(124.60,119.80,112.40,131.20,98.60),
       entry(124.60,128.01,117.40,129.27,131.20,147.66,124.60,'回踩 124.60–128.01 可分批；高开超过 129.27 不追；跌破 117.40 离场。',
         '接近 131.20（+2.2%）分批减半；收盘跌破 124.60（均线）或 117.40（防守位）离场；持有 1–3 个交易日。')),
     stock('sz301308','江波龙','龙头',186.54,10,6850000000,172.10,2,'涨停',
       levels(172.40,165.20,152.80,186.54,128.30),
       entry(172.40,178.06,161.90,181.45,186.54,197.73,172.40,'回踩 172.40–178.06 可分批；高开超过 181.45 不追；跌破 161.90 离场。',
         '接近 186.54（+0.0%）分批减半；收盘跌破 172.40（均线）或 161.90（防守位）离场；持有 1–3 个交易日。'),'存储涨价'),
     stock('sh688981','中芯国际','中军',96.80,4.65,12400000000,92.40,0,null,
       levels(93.10,88.60,84.20,97.20,78.40),
       entry(93.10,94.35,86.83,97.13,97.20,111.78,93.10,'回踩 93.10–94.35 可分批；高开超过 97.13 不追；跌破 86.83 离场。',
         '接近 97.20（+0.4%）分批减半；收盘跌破 93.10（均线）或 86.83（防守位）离场；持有 1–3 个交易日。')),
   ],
   timing:{window:'下一交易日 9:45–10:30',
     triggers:['上证开盘 30 分钟不低于 MA5 3941.20。','兆易创新回踩 124.60–128.01 可分批。'],
     invalidation:['兆易创新跌破失效价 117.40 元。','半导体板块净流出超过 20 亿元。'],
     gates:[{kind:'market_decline_share_max',value:0.6667},{kind:'sector_change_min',value:0},{kind:'sector_net_min',value:0},
       {kind:'candidate_pct_max',value:5},{kind:'candidate_recover'},{kind:'peers_rising_min',value:1}]},
   evidence:[{label:'资金',value:'半导体主力净流入 68.20 亿元。',source:'东财行业资金流'}]},
  {rank:2,sector:'存储芯片',sector_code:'gn_cpc',sector_kind:'概念',change:4.12,net:5310000000,net_5d:10500000000,net_5d_days:3,
   score:7.65,state:'可考虑建仓',why:'生成时板块资金条件满足。',
   opportunity:'存储合约价连续第三周上调，等待候选回踩。',
   logic:['概念当日上涨 4.12%，净流入 53.10 亿元。'],risk:'候选股当日涨幅已超过 5%，不追高。',
   candidate:{code:'sh688525',name:'佰维存储'},peers:[{code:'sz301308',name:'江波龙',stop:161.90},{code:'sz001309',name:'德明利',stop:80.75}],
   stocks:[
     stock('sh688525','佰维存储','低吸候选',65.43,6.13,2860000000,60.80,0,null,
       levels(61.20,60.10,56.80,66.90,48.20),
       entry(61.20,62.88,58.90,63.50,66.90,75.29,61.20,'回踩 61.20–62.88 可分批；高开超过 63.50 不追；跌破 58.90 离场。',
         '接近 66.90（+2.2%）分批减半；收盘跌破 61.20（均线）或 58.90（防守位）离场；持有 1–3 个交易日。')),
     stock('sz301308','江波龙','龙头',186.54,10,6850000000,172.10,2,'涨停',
       levels(172.40,165.20,152.80,186.54,128.30),
       entry(172.40,178.06,161.90,181.45,186.54,197.73,172.40,'回踩 172.40–178.06 可分批；高开超过 181.45 不追；跌破 161.90 离场。',
         '接近 186.54（+0.0%）分批减半；收盘跌破 172.40（均线）或 161.90（防守位）离场；持有 1–3 个交易日。')),
     stock('sz001309','德明利','中军',87.10,-1.25,1880000000,86.50,null,null,
       levels(85.60,82.40,78.60,92.40,64.10),
       entry(86.50,87.10,80.75,92.61,92.40,106.26,85.60,'回踩 86.50–87.10 可分批；高开超过 92.61 不追；跌破 80.75 离场。',
         '接近 92.40（+6.1%）分批减半；收盘跌破 85.60（均线）或 80.75（防守位）离场；持有 1–3 个交易日。')),
   ],
   timing:{window:'下一交易日 9:45–10:30',triggers:['佰维存储回踩 61.20–62.88 可分批。'],
     invalidation:['佰维存储跌破失效价 58.90 元。'],gates:[{kind:'market_decline_share_max',value:0.6667},
       {kind:'sector_change_min',value:0},{kind:'sector_net_min',value:0},{kind:'candidate_pct_max',value:5},
       {kind:'candidate_recover'},{kind:'peers_rising_min',value:1}]},
   evidence:[{label:'资金',value:'存储芯片概念净流入 53.10 亿元。',source:'东财概念资金流'}]},
  {rank:3,sector:'电力改革',sector_code:'gn_dlgg',sector_kind:'概念',change:0.35,net:-860000000,net_5d:-2140000000,net_5d_days:3,
   score:4.80,state:'观察',why:'板块当日资金净流出，继续观察。',opportunity:'电价改革预期仍在，等待量能修复。',
   logic:['概念当日微涨 0.35%，但净流出 8.60 亿元。'],risk:'若继续净流出则退出观察。',
   candidate:{code:'sh600025',name:'华能水电'},peers:[{code:'sh600900',name:'长江电力',stop:29.01},{code:'sh600886',name:'国投电力',stop:15.05}],
   stocks:[
     stock('sh600025','华能水电','低吸候选',9.85,-1.30,620000000,9.80,0,null,
       levels(9.90,9.72,9.55,10.24,8.86),
       entry(9.80,9.85,9.53,10.28,10.24,11.33,9.90,'回踩 9.80–9.85 可分批；高开超过 10.28 不追；跌破 9.53 离场。',
         '接近 10.24（+4.0%）分批减半；收盘跌破 9.90（均线）或 9.53（防守位）离场；持有 1–3 个交易日。')),
     stock('sh600900','长江电力','龙头',30.20,0.40,3260000000,29.85,0,null,
       levels(29.92,29.60,29.10,30.64,28.20),
       entry(29.92,31.58,29.01,32.19,30.64,32.95,29.92,'回踩 29.92–31.58 可分批；高开超过 32.19 不追；跌破 29.01 离场。',
         '接近 30.64（+1.5%）分批减半；收盘跌破 29.92（均线）或 29.01（防守位）离场；持有 1–3 个交易日。')),
     stock('sh600886','国投电力','中军',15.62,-0.19,880000000,15.50,0,null,
       levels(15.58,15.36,15.02,16.10,14.40),
       entry(15.58,15.62,15.05,16.43,16.10,18.52,15.58,'回踩 15.58–15.62 可分批；高开超过 16.43 不追；跌破 15.05 离场。',
         '接近 16.10（+3.1%）分批减半；收盘跌破 15.58（均线）或 15.05（防守位）离场；持有 1–3 个交易日。')),
   ],
   timing:{window:'下一交易日 9:45–10:30',triggers:['概念当日涨幅 ≥0% 且净流入 ≥0。'],
     invalidation:['华能水电跌破失效价 9.53 元。'],gates:[{kind:'market_decline_share_max',value:0.6667},
       {kind:'sector_change_min',value:0},{kind:'sector_net_min',value:0},{kind:'candidate_pct_max',value:5},
       {kind:'candidate_recover'},{kind:'peers_rising_min',value:1}]},
   evidence:[{label:'资金',value:'电力改革概念净流出 8.60 亿元。',source:'东财概念资金流'}]},
  {rank:4,sector:'光伏设备',sector_code:'new_gf',sector_kind:'行业',change:2.08,net:2610000000,net_5d:null,net_5d_days:null,
   score:6.90,state:'继续等',why:'候选股尚未回落后重新站上昨收。',opportunity:'行业排产环比改善，等待回踩。',
   logic:['行业当日上涨 2.08%，净流入 26.10 亿元。'],risk:'组件价格若继续下行则证伪。',
   candidate:{code:'sh600438',name:'通威股份'},peers:[{code:'sh601012',name:'隆基绿能',stop:18.72},{code:'sz300274',name:'阳光电源',stop:89.77}],
   stocks:[
     stock('sh600438','通威股份','低吸候选',22.10,-1.34,2140000000,21.80,0,null,
       levels(22.60,21.90,21.20,23.80,18.40),
       entry(21.80,22.10,21.36,23.07,23.80,25.41,22.60,'回踩 21.80–22.10 可分批；高开超过 23.07 不追；跌破 21.36 离场。',
         '接近 23.80（+7.7%）分批减半；收盘跌破 22.60（均线）或 21.36（防守位）离场；持有 1–3 个交易日。')),
     stock('sh601012','隆基绿能','龙头',21.58,10,5620000000,20.10,1,'涨停',
       levels(19.40,19.10,18.70,21.58,16.20),
       entry(20.10,20.60,18.72,20.99,21.58,22.88,20.10,'回踩 20.10–20.60 可分批；高开超过 20.99 不追；跌破 18.72 离场。',
         '接近 21.58（+0.0%）分批减半；收盘跌破 20.10（均线）或 18.72（防守位）离场；持有 1–3 个交易日。'),'光伏反转'),
     stock('sz300274','阳光电源','中军',96.20,0.42,4860000000,94.60,0,null,
       levels(94.10,91.60,88.40,101.20,76.80),
       entry(94.60,96.20,89.77,100.59,101.20,110.60,94.60,'回踩 94.60–96.20 可分批；高开超过 100.59 不追；跌破 89.77 离场。',
         '接近 101.20（+5.2%）分批减半；收盘跌破 94.60（均线）或 89.77（防守位）离场；持有 1–3 个交易日。')),
   ],
   timing:{window:'下一交易日 9:45–10:30',triggers:['通威股份现价重新站上昨收 22.40。'],
     invalidation:['通威股份跌破失效价 21.36 元。'],gates:[{kind:'market_decline_share_max',value:0.6667},
       {kind:'sector_change_min',value:0},{kind:'sector_net_min',value:0},{kind:'candidate_pct_max',value:5},
       {kind:'candidate_recover'},{kind:'peers_rising_min',value:1}]},
   evidence:[{label:'资金',value:'光伏设备净流入 26.10 亿元。',source:'东财行业资金流'}]},
];

const sectors={
  new_bdt:{change:3.21,net:6820000000,time:QUOTE_TIME,inferred:false},
  gn_cpc:{change:4.12,net:5310000000,time:QUOTE_TIME,inferred:false},
  gn_dlgg:{change:0.35,net:-860000000,time:QUOTE_TIME,inferred:false},
  new_gf:{change:2.08,net:2610000000,time:QUOTE_TIME,inferred:false},
};

const topPicks=[
  {code:'sh603986',name:'兆易创新',role:'低吸候选',sector:'半导体',sector_code:'new_bdt',sector_kind:'行业',rank:1,
   state:'可考虑建仓',why:'6 项盘中条件全部满足，板块资金为净流入。',price:128.40,percent:2.31,boards:0,limit_tag:null,
   buy_low:124.60,buy_high:128.01,chase:129.27,stop:117.40,target1:131.20,target2:147.66,trail:124.60,
   note:'回踩 124.60–128.01 可分批；高开超过 129.27 不追；跌破 117.40 离场。',
   sell_note:'接近 131.20（+2.2%）分批减半；收盘跌破 124.60（均线）或 117.40（防守位）离场；持有 1–3 个交易日。',
   window:'下一交易日 9:45–10:30',sizing:'1–1.5 成',trigger},
  {code:'sz301308',name:'江波龙',role:'龙头',sector:'半导体',sector_code:'new_bdt',sector_kind:'行业',rank:1,
   state:'可考虑建仓',why:'6 项盘中条件全部满足，板块资金为净流入。',price:186.54,percent:10,boards:2,limit_tag:'涨停',
   buy_low:172.40,buy_high:178.06,chase:181.45,stop:161.90,target1:186.54,target2:197.73,trail:172.40,
   note:'回踩 172.40–178.06 可分批；高开超过 181.45 不追；跌破 161.90 离场。',
   sell_note:'接近 186.54（+0.0%）分批减半；收盘跌破 172.40（均线）或 161.90（防守位）离场；持有 1–3 个交易日。',
   window:'下一交易日 9:45–10:30',sizing:'1 成以内',trigger},
  {code:'sh688525',name:'佰维存储',role:'低吸候选',sector:'存储芯片',sector_code:'gn_cpc',sector_kind:'概念',rank:2,
   state:'继续等',why:'候选股佰维存储当日涨幅 +6.13%，上限 5.00%。',price:65.43,percent:6.13,boards:0,limit_tag:null,
   buy_low:61.20,buy_high:62.88,chase:63.50,stop:58.90,target1:66.90,target2:75.29,trail:61.20,
   note:'回踩 61.20–62.88 可分批；高开超过 63.50 不追；跌破 58.90 离场。',
   sell_note:'接近 66.90（+2.2%）分批减半；收盘跌破 61.20（均线）或 58.90（防守位）离场；持有 1–3 个交易日。',
   window:'下一交易日 9:45–10:30',sizing:'0.5–1 成',trigger},
  {code:'sh600438',name:'通威股份',role:'低吸候选',sector:'光伏设备',sector_code:'new_gf',sector_kind:'行业',rank:4,
   state:'继续等',why:'候选股尚未回落后重新站上昨收。',price:22.10,percent:-1.34,boards:0,limit_tag:null,
   buy_low:21.80,buy_high:22.10,chase:23.07,stop:21.36,target1:23.80,target2:25.41,trail:22.60,
   note:'回踩 21.80–22.10 可分批；高开超过 23.07 不追；跌破 21.36 离场。',
   sell_note:'接近 23.80（+7.7%）分批减半；收盘跌破 22.60（均线）或 21.36（防守位）离场；持有 1–3 个交易日。',
   window:'下一交易日 9:45–10:30',sizing:'1 成以内',trigger},
];


const radarEntry=(buy_low:number,buy_high:number,stop:number,chase:number,target1:number,target2:number,note:string,sell_note:string)=>
  ({buy_low,buy_high,stop,chase,target1,target2,trail:null,note,sell_note});
const radar=[
  {theme:'东方',kind:'名称类',stage:'加速/高潮',stage_note:'连板高度或涨停家数快速抬升，接力风险高',
   signals:['今日涨停 6 家（昨日 1 家、近 5 日 13 家）','最高 8 板（东方海洋）','近 72 小时新闻提及 1 条'],
   limit_up_today:6,limit_up_prev:1,limit_up_5d:13,max_board:8,news_count:1,net_yuan:null,change:null,
   verdict:'只观察，不追高',risk:'纯名称/情绪炒作，无基本面证据；历史上退潮回撤大，只宜小仓短线。均线未取，只按当日报价价位。',
   watch:['只剩观察价值；断板或炸板增加即离场','不接高位加速'],
   stocks:[
     {code:'sz002086',name:'东方海洋',role:'龙头',price:3.97,percent:9.97,boards:8,limit_tag:'涨停',reason:'“羊”字辈+海洋养殖',levels:null,
      entry:radarEntry(3.67,3.79,3.6,3.86,4.29,4.57,'回踩 3.67–3.79 可分批；高开超过 3.86 不追；跌破 3.60 离场。',
        '接近 4.29（+8.1%）分批减半；跌破 3.60（防守位）离场；持有 1–3 个交易日。')},
     {code:'sh600327',name:'大东方',role:'跟风',price:4.91,percent:10.09,boards:2,limit_tag:'涨停',reason:'“东方”+百货零售',levels:null,
      entry:radarEntry(4.12,4.55,4.04,4.59,5.3,5.65,'回踩 4.12–4.55 可分批；高开超过 4.59 不追；跌破 4.04 离场。',
        '接近 5.30（+7.9%）分批减半；跌破 4.04（防守位）离场；持有 1–3 个交易日。')},
     {code:'sh600637',name:'东方明珠',role:'低吸候选',price:8.08,percent:4.8,boards:0,limit_tag:null,reason:null,levels:null,
      entry:radarEntry(7.86,7.86,7.71,7.94,8.73,9.29,'回踩 7.86 附近可分批；高开超过 7.94 不追；跌破 7.71 离场。',
        '接近 8.73（+8.0%）分批减半；跌破 7.71（防守位）离场；持有 1–3 个交易日。')}],
   evidence:[{label:'涨停池',value:'大东方（“东方”+百货零售）/ 东方明珠（“东方”）',source:'同花顺涨停池'}]},
  {theme:'2027 羊年（跨年）',kind:'生肖/玄学',stage:'加速/高潮',stage_note:'连板高度或涨停家数快速抬升，接力风险高',
   signals:['今日涨停 4 家（近 5 日 31 家）','最高 8 板（东方海洋）'],
   limit_up_today:4,limit_up_prev:4,limit_up_5d:31,max_board:8,news_count:0,net_yuan:null,change:null,
   verdict:'只观察，不追高',risk:'纯名称/情绪炒作，无基本面证据；退潮回撤大，只宜小仓短线。',
   watch:['断板或炸板增加即离场'],stocks:[],
   evidence:[{label:'涨停池',value:'红太阳 / 鲁阳节能 / 阳光照明（“羊”字辈）',source:'同花顺涨停池（当日+近 5 交易日）'}]},
  {theme:'AI硬件/算力',kind:'事件/题材',stage:'发酵',stage_note:'新闻与概念资金同步升温，尚可回踩低吸',
   signals:['近 72 小时新闻 9 条','概念内涨停 5 家'],
   limit_up_today:5,limit_up_prev:null,limit_up_5d:null,max_board:5,news_count:9,net_yuan:null,change:null,
   verdict:'回踩低吸，不追高',risk:'事件/题材驱动需要确认持续性；新闻热度不等于订单或业绩。',
   watch:['概念涨幅回落至 2% 以内再看'],stocks:[],
   evidence:[{label:'新闻',value:'AI算力东风下，高景气何以加速兑现？',source:'新浪滚动新闻（72 小时）'}]},
  {theme:'冰雪经济',kind:'事件/题材',stage:'启动初期',stage_note:'今日首批涨停出现，尚未形成连续梯队',
   signals:['今日涨停 2 家','近 72 小时新闻 3 条'],
   limit_up_today:2,limit_up_prev:0,limit_up_5d:2,max_board:1,news_count:3,net_yuan:null,change:null,
   verdict:'可小仓试错（≤0.5 成）',risk:'事件/题材驱动需要确认持续性；新闻热度不等于订单或业绩。',
   watch:['次日出现 2 家以上连板再加仓'],stocks:[],
   evidence:[{label:'新闻',value:'冰雪经济政策预期升温',source:'新浪滚动新闻（72 小时）'}]},
];

const issue={
  screen_version:9,horizon:'未来 1–3 个交易日',verdict:'普涨修复 · 可跟随强势',bias:'进攻',
  position:'总仓 5–6 成，单方向 ≤2 成',published_at:'2026-11-06T16:20:00+08:00',quote_date:DAY,
  focus:{sector:'半导体',sector_code:'new_bdt',state:'可考虑建仓',why:'6 项盘中条件全部满足，板块资金为净流入。',
    candidate:{code:'sh603986',name:'兆易创新'},window:'下一交易日 9:45–10:30',
    summary:'首选 半导体 · 兆易创新：6 项盘中条件全部满足，板块资金为净流入。'},
  top_picks:topPicks,
  radar,
  radar_summary:'识别 4 个 · 启动初期 1 个 · 名称/玄学 2 个',
  pulse:{
    market:{indices:[
      {code:'sh000001',name:'上证指数',price:3987.62,percent:0.71,change:28.15,ma5:3941.20,ma10:3902.44,ma20:3859.73,
       above_ma5:true,above_ma20:true,high20:4021.36,low20:3812.55,volume:512000000000,volume_ratio:1.12,
       support:3941.20,resistance:4021.36,stamp:QUOTE_TIME}],
      breadth:{date:DAY,status:'closed',advance:3421,decline:1568,flat:142,advancing_percent:66.67,trin:0.91,
        amount_yuan:1986000000000,amount_5d_avg:1824000000000,amount_ratio:1.09,days_used:5},
      signals:['上证收于 3987.62，高于 MA5（3941.20）。','上涨 3421 家、下跌 1568 家，上涨占比 66.67%。']},
    capital:{industry:{inflow:[{code:'new_bdt',name:'半导体',net_yuan:6820000000,change_percent:3.21}],
        outflow:[{code:'new_jg',name:'军工装备',net_yuan:-1120000000,change_percent:-1.20}],measure:'买卖方向净额',date:DAY},
      concept:{inflow:[{code:'gn_cpc',name:'存储芯片',net_yuan:5310000000,change_percent:4.12}],
        outflow:[{code:'gn_dlgg',name:'电力改革',net_yuan:-860000000,change_percent:0.35}],measure:'买卖方向净额',date:DAY},
      persistent:[{code:'new_bdt',name:'半导体',sector_kind:'行业',net_yuan:6820000000,net_5d:14200000000,days:3,change_percent:3.21}],
      history_days:3},
    sentiment:{limit_up:{today:72,yesterday:58,attempt:101,sealed_rate:0.71,open_num:29},
      limit_down:{today:6,yesterday:9,attempt:14,sealed_rate:0.43,open_num:8},max_board:6,max_board_name:'江波龙',
      ladder:[{boards:6,count:1},{boards:3,count:4}],non_consecutive:56,
      yesterday_performance:{count:58,advance:31,avg_percent:1.84,promote:9,promote_rate:0.155},
      hot_reasons:[{name:'存储涨价',count:14,codes:['sz301308']}],
      trend:[{date:'2026-11-05',limit_up:58,limit_down:9,sealed_rate:0.66,max_board:5},
        {date:DAY,limit_up:72,limit_down:6,sealed_rate:0.71,max_board:6}],temperature:'升温'},
    hotspots:{news:[{time:'2026-11-06T14:32:00+08:00',title:'存储芯片合约价连续第三周上涨',url:'https://finance.sina.com.cn/',region:'domestic',match:'存储涨价'}],
      reasons:[{name:'存储涨价',count:14,stocks:[{code:'sz301308',name:'江波龙'}]}]},
  },
  playbooks:[{name:'修复延续',conditions:['上证站上 MA5（3941.20）'],action:'回踩分批不追高。',position:'5–6 成',active:true},
    {name:'高低切 / 分化',conditions:['指数在 MA5 附近 ±1%'],action:'只做低吸。',position:'3–4 成',active:false},
    {name:'补跌防守',conditions:['上证跌破 MA10'],action:'空仓观察。',position:'≤2 成',active:false}],
  timetable:[{time:'9:15–9:25',focus:'集合竞价',rule:'看候选高开是否超过 3%。'},
    {time:'10:30',focus:'板块资金',rule:'板块净流出超过 10 亿元不再开仓。'}],
  risk:['半导体两日累计上涨 6.8%，高开不追。','公开数据统计与研究，不构成投资建议。'],
  warnings:['资金近 5 个采集日累计只有 3 个可用采集日。'],
  coverage:{industry:31,concept:182,disclosed:6,unavailable:2},
  exclusions:{gn_robot:'盘中冲高回落，封板率 43%，未满足资金条件。'},
  directory:{gn_robot:'机器人'},
  directions,
};

const report={issue,quotes,sectors,day:DAY,batch:BATCH,day_info:day,schedule:'',completed_slot:null};

async function boot(page:Page,data:unknown,options:{now?:string}={}){
  await page.clock.setFixedTime(new Date(options.now??NOW));
  await page.addInitScript(({data})=>{
    (window as any).__rpcCalls=[];
    Object.assign(window,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
      metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
      async invoke(command:string,args:{method:string}){
        if(command!=='rpc')return 0;
        (window as any).__rpcCalls.push(args.method);
        switch(args.method){
          case 'snapshot':return {watch:[],events:[],config:{},now:new Date().toISOString(),market_open:true};
          case 'market':case 'market_overview':return {quotes:[],minute:null};
          case 'daily_outlook':return data;
          default:throw Error('测试未提供 '+args.method);
        }
      }
    }});
  },{data});
  await page.goto('/');
  await page.evaluate(()=>{(window as any).__rpcCalls=[];});
  await page.getByRole('button',{name:'市场机会',exact:true}).click();
  await expect(page.getByRole('region',{name:'市场机会研判'})).toBeVisible();
}

const foldOpen=(page:Page,selector:string)=>page.locator(selector).evaluate(element=>(element as HTMLDetailsElement).open);

test('首屏聚焦：定调、首选行、建仓清单与默认方向详情',async({page})=>{
  await boot(page,report);
  const rpc=await page.evaluate(()=>(window as any).__rpcCalls as string[]);
  expect(rpc).not.toContain('breadth');
  const root=page.getByRole('region',{name:'市场机会研判'});
  await expect(root).toContainText('普涨修复 · 可跟随强势');
  await expect(root).toContainText('总仓 5–6 成');
  await expect(root.locator('.mo-focus-line')).toHaveText('首选 半导体 · 兆易创新：6 项盘中条件全部满足，板块资金为净流入。');
  const picks=page.getByRole('region',{name:'建仓清单'});
  await expect(picks).toBeVisible();
  await expect(picks.locator('.mo-pick-row')).toHaveCount(4);
  await expect(picks).toContainText('买点区间');
  await expect(picks).toContainText('止损');
  await expect(picks).toContainText('止盈目标');
  await expect(picks).toContainText('仓位');
  const first=picks.locator('.mo-pick-row').first();
  await expect(first).toContainText('兆易创新');
  await expect(first).toContainText('sh603986');
  await expect(first).toContainText('124.60–128.01');
  await expect(first).toContainText('117.40');
  await expect(first).toContainText('131.20');
  await expect(first).toContainText('+2.2%');
  await expect(first).toContainText('1–1.5 成');
  await expect(first).toContainText('9:45–10:30');
  await expect(first).toContainText('市场下跌家数≤2/3');
  expect(await first.getAttribute('title')).toContain('卖出：');
  const detail=page.getByRole('region',{name:'方向详情'});
  await expect(detail).toBeVisible();
  await expect(detail.locator('.mo-tab')).toHaveCount(4);
  await expect(detail.locator('.mo-tab').first()).toHaveAttribute('aria-pressed','true');
  await expect(detail).toContainText('半导体');
  await expect(detail).toContainText('买入时机');
  await expect(detail).toContainText('重点股票');
  await expect(detail).toContainText('卖点');
  await expect(detail).toContainText('卖出提示');
  // 首屏不展示市场背景/行动计划区域
  expect(await foldOpen(page,'details.mo-fold-market')).toBe(false);
  expect(await foldOpen(page,'details.mo-fold-action')).toBe(false);
  expect(await foldOpen(page,'details.mo-fold-rank')).toBe(false);
  await expect(page.getByRole('region',{name:'市场温度'})).toBeHidden();
});

test('点击建仓清单行切换方向详情，买卖点数字可见',async({page})=>{
  await boot(page,report);
  const picks=page.getByRole('region',{name:'建仓清单'});
  const detail=page.getByRole('region',{name:'方向详情'});
  await picks.locator('.mo-pick-row').filter({hasText:'佰维存储'}).click();
  await expect(detail.locator('.mo-tab').nth(1)).toHaveAttribute('aria-pressed','true');
  await expect(detail).toContainText('存储芯片');
  await expect(detail).toContainText('佰维存储');
  await expect(detail).toContainText('61.20–62.88');
  await expect(detail).toContainText('目标 66.90');
  await expect(detail).toContainText('移动止损 61.20');
  await expect(detail).toContainText('接近 66.90（+2.2%）分批减半');
  await picks.locator('.mo-pick-row').filter({hasText:'通威股份'}).click();
  await expect(detail).toContainText('光伏设备');
  await expect(detail).toContainText('通威股份');
  await expect(detail).toContainText('21.36');
});

test('实时 gate 状态反映到建仓清单：可考虑建仓/继续等/行情待核对',async({page})=>{
  await boot(page,report);
  const picks=page.getByRole('region',{name:'建仓清单'});
  const row=(name:string)=>picks.locator('.mo-pick-row').filter({hasText:name});
  await expect(row('兆易创新')).toContainText('可考虑建仓');
  await expect(row('江波龙')).toContainText('可考虑建仓');
  await expect(row('佰维存储')).toContainText('继续等');
  await expect(row('佰维存储')).toContainText('上限 5.00%');
  await expect(row('通威股份')).toContainText('行情待核对');
  await row('佰维存储').click();
  const detail=page.getByRole('region',{name:'方向详情'});
  await expect(detail.locator('.mo-gates li.bad')).toHaveCount(1);
  await expect(detail.locator('.mo-gates li.bad')).toContainText('上限 5.00%');
});

test('折叠区默认收起，展开后市场背景/行动计划/排名与数据覆盖可见',async({page})=>{
  await boot(page,report);
  const marketFold=page.locator('details.mo-fold-market');
  await expect(marketFold.locator('> summary')).toContainText('上证');
  await expect(marketFold.locator('> summary')).toContainText('上涨占比');
  await marketFold.locator('> summary').click();
  expect(await foldOpen(page,'details.mo-fold-market')).toBe(true);
  await expect(page.getByRole('region',{name:'市场温度'})).toContainText('上证指数');
  await expect(page.getByRole('region',{name:'资金流向'})).toContainText('半导体');
  await expect(page.getByRole('region',{name:'市场人气'})).toContainText('72 / 58');
  await expect(page.getByRole('region',{name:'热点题材'})).toContainText('存储芯片合约价连续第三周上涨');
  const actionFold=page.locator('details.mo-fold-action');
  await expect(actionFold.locator('> summary')).toContainText('修复延续');
  await actionFold.locator('> summary').click();
  await expect(page.getByRole('region',{name:'行动计划'})).toContainText('时间表');
  await expect(page.getByRole('region',{name:'行动计划'})).toContainText('不构成投资建议');
  const rankFold=page.locator('details.mo-fold-rank');
  await expect(rankFold.locator('> summary')).toContainText('个方向');
  await expect(rankFold.locator('> summary')).toContainText('数据缺口');
  await rankFold.locator('> summary').click();
  await expect(page.getByRole('region',{name:'方向排名'}).locator('.mo-rank-row')).toHaveCount(4);
  await expect(page.getByRole('region',{name:'数据覆盖'})).toContainText('资金近 5 个采集日累计只有 3 个可用采集日');
});

test('炒作雷达：4 条主题/阶段/标的/结论，点击展开买卖点与风险',async({page})=>{
  await boot(page,report);
  const radar=page.getByRole('region',{name:'炒作雷达'});
  await expect(radar).toBeVisible();
  await expect(radar.locator('.mo-radar-head')).toContainText('识别 4 个 · 启动初期 1 个 · 名称/玄学 2 个');
  await expect(radar.locator('.mo-radar-head')).toContainText('炒作雷达');
  await expect(radar.locator('.mo-radar-head')).not.toContainText('风险高，只宜小仓或观察');
  const rows=radar.locator('.mo-radar-row');
  await expect(rows).toHaveCount(4);
  const first=rows.first();
  await expect(first).toContainText('东方');
  await expect(first).toContainText('名称类');
  await expect(first).toContainText('加速/高潮');
  await expect(first).toContainText('涨停 6 家');
  await expect(first).toContainText('最高 8 板');
  await expect(first).toContainText('东方海洋、大东方、东方明珠');
  await expect(first).toContainText('只观察，不追高');
  await expect(radar.locator('.mo-stage.start')).toHaveCount(1);
  await expect(first).toHaveAttribute('aria-expanded','false');
  await first.click();
  await expect(first).toHaveAttribute('aria-expanded','true');
  const detail=radar.locator('.mo-radar-detail');
  await expect(detail).toHaveCount(1);
  await expect(detail).toContainText('今日涨停 6 家');
  await expect(detail).toContainText('纯名称/情绪炒作');
  await expect(detail).toContainText('断板或炸板增加即离场');
  await expect(detail).toContainText('东方海洋');
  await expect(detail).toContainText('3.67–3.79');
  await expect(detail).toContainText('3.60');
  await expect(detail).toContainText('4.29（+8.1%）');
  await expect(detail).toContainText('≤0.5 成或只观察');
  await rows.nth(1).click();
  await expect(first).toHaveAttribute('aria-expanded','false');
  await expect(rows.nth(1)).toHaveAttribute('aria-expanded','true');
  await expect(radar.locator('.mo-radar-detail')).toHaveCount(1);
});

test('炒作雷达为空时显示未识别提示并保留风险说明',async({page})=>{
  const empty=JSON.parse(JSON.stringify(report));
  empty.issue.radar=[];
  empty.issue.radar_summary='';
  await boot(page,empty);
  const radar=page.getByRole('region',{name:'炒作雷达'});
  await expect(radar).toContainText('本期没有识别到新的炒作/概念信号');
  await expect(radar).toContainText('本期没有识别到新的炒作/概念信号');
  await expect(radar).not.toContainText('风险高，只宜小仓或观察');
});

test('研判为 null 时显示今日研判尚未生成',async({page})=>{
  await boot(page,{issue:null,quotes:[],sectors:{},day:DAY,batch:BATCH,schedule:''});
  await expect(page.getByRole('region',{name:'市场机会研判'})).toContainText('今日研判尚未生成');
});

test('市场或人气缺失时对应卡显示待取得，其余卡照常渲染',async({page})=>{
  const partial=JSON.parse(JSON.stringify(report));
  partial.issue.pulse.market=null;
  partial.issue.pulse.sentiment=null;
  await boot(page,partial);
  await page.locator('details.mo-fold-market > summary').click();
  await expect(page.getByRole('region',{name:'市场温度'})).toContainText('待取得');
  await expect(page.getByRole('region',{name:'市场人气'})).toContainText('待取得');
  await expect(page.getByRole('region',{name:'资金流向'})).toContainText('半导体');
  await expect(page.getByRole('region',{name:'热点题材'})).toContainText('存储涨价');
});

test('旧格式研判（无 pulse/directions/focus/top_picks）不崩溃并提示增强尚未生成',async({page})=>{
  const legacy={issue:{ideas:[],published_at:'2026-11-06T16:20:00+08:00',quote_date:DAY,coverage:{industry:31,concept:182}},
    quotes:[],sectors:{},day:DAY,batch:BATCH,schedule:''};
  await boot(page,legacy);
  const root=page.getByRole('region',{name:'市场机会研判'});
  await expect(root).toContainText('研判增强尚未生成（等待本机每 30 分钟更新）');
  await expect(page.getByRole('region',{name:'建仓清单'})).toContainText('研判增强尚未生成');
  await expect(page.getByRole('region',{name:'方向详情'})).toContainText('研判增强尚未生成');
  await page.locator('details.mo-fold-market > summary').click();
  await expect(page.getByRole('region',{name:'市场温度'})).toContainText('待取得');
  await page.locator('details.mo-fold-rank > summary').click();
  await expect(page.getByRole('region',{name:'方向排名'})).toContainText('方向排名待取得');
});

test('盘中未核对：警示横幅、研判价标注与“数据未核对”操作提示',async({page})=>{
  const stale=JSON.parse(JSON.stringify(report));
  stale.day='2026-11-09';
  stale.day_info={...liveDay};
  stale.batch='2026-11-09T09:31:00+08:00';
  stale.quotes=stale.quotes.map((quote:any)=>({...quote,timestamp:'2026-11-06T15:00:00+08:00'}));
  stale.issue.quote_date='2026-11-06';
  await boot(page,stale,{now:LIVE_NOW});
  const alert=page.getByRole('region',{name:'数据未核对警示'});
  await expect(alert).toBeVisible();
  await expect(alert).toContainText('数据未核对，先不要按此价格操作');
  await expect(alert).toContainText('当前研判基准 2026-11-06');
  await expect(alert).toContainText('行情批次与全市场广度快照未对齐');
  await expect(alert).toContainText('今日盘中：上涨 2100 / 下跌 2600');
  await expect(alert).toContainText('等待面板自动刷新（每 15 秒检查、研判每 30 分钟更新）；核对前不要下单。');
  const picks=page.getByRole('region',{name:'建仓清单'});
  await expect(picks.locator('.mo-p-fresh').first()).toHaveText('研判时');
  await expect(picks.locator('.mo-pick-row').first()).toContainText('128.40');
  await expect(page.locator('.mo-next-step')).toContainText('数据未核对，暂不操作；继续等本机更新');
  await expect(page.locator('.mo-next-step')).toHaveClass(/is-warn/);
  await expect(page.locator('.mo-meta')).toContainText('行情批次 2026-11-09 09:39');
  await expect(page.locator('.mo-meta')).toContainText('研判生成 2026-11-06 16:20');
  await expect(page.locator('.mo-meta')).toContainText('数据未核对');
  await page.setViewportSize({width:1000,height:900});
  await expect(alert).toBeVisible();
  const dimensions=await page.evaluate(()=>({
    scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,
    body:document.body.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client+1);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.client+1);
});

test('盘中已核对：无警示横幅、实时价格与可建仓操作提示',async({page})=>{
  const live=JSON.parse(JSON.stringify(report));
  live.day='2026-11-09';
  live.day_info={...liveDay};
  live.batch=liveDay.collected_at;
  live.quotes=live.quotes.map((quote:any)=>quote.code==='sh600438'?quote:{...quote,timestamp:'2026-11-09T09:38:30+08:00'});
  live.sectors=Object.fromEntries(Object.entries(live.sectors).map(([code,sector]:any)=>[code,{...sector,time:'2026-11-09T09:38:00+08:00'}]));
  live.issue.quote_date='2026-11-09';
  live.issue.published_at='2026-11-09T09:30:00+08:00';
  await boot(page,live,{now:LIVE_NOW});
  await expect(page.getByRole('region',{name:'数据未核对警示'})).toHaveCount(0);
  const picks=page.getByRole('region',{name:'建仓清单'});
  const row=(name:string)=>picks.locator('.mo-pick-row').filter({hasText:name});
  await expect(row('兆易创新').locator('.mo-p-fresh')).toHaveText('实时 09:38');
  await expect(row('兆易创新')).toContainText('128.40');
  await expect(row('兆易创新')).toContainText('+2.31%');
  await expect(row('兆易创新')).toContainText('可考虑建仓');
  await expect(row('通威股份').locator('.mo-p-fresh')).toHaveText('研判时');
  await expect(row('通威股份')).toContainText('行情待核对');
  await expect(page.locator('.mo-next-step')).toContainText('可考虑建仓：兆易创新、江波龙（按买点区间分批，单方向 ≤2 成）');
  await expect(page.locator('.mo-meta')).toContainText('盘中已核对 · 行情 09:39');
  await expect(page.locator('.mo-meta')).toContainText('行情批次 2026-11-09 09:39');
});

test('1000px 桌面宽度无横向溢出，建仓清单折叠为卡片',async({page})=>{
  await boot(page,report);
  await page.getByRole('region',{name:'建仓清单'}).locator('.mo-pick-row').first().click();
  await page.setViewportSize({width:1000,height:900});
  await expect(page.getByRole('region',{name:'方向详情'})).toBeVisible();
  await expect(page.locator('.mo-pick-head')).toBeHidden();
  const radar=page.getByRole('region',{name:'炒作雷达'});
  await expect(radar.locator('.mo-radar-row')).toHaveCount(4);
  await expect(page.locator('.mo-radar-head-row')).toBeHidden();
  await radar.locator('.mo-radar-row').first().click();
  await expect(radar.locator('.mo-radar-detail')).toBeVisible();
  const dimensions=await page.evaluate(()=>({
    scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,
    body:document.body.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client+1);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.client+1);
});

test('首屏顺序：炒作雷达位于建仓清单上方',async({page})=>{
  await boot(page,report);
  const radar=page.getByRole('region',{name:'炒作雷达'});
  const picks=page.getByRole('region',{name:'建仓清单'});
  await expect(radar).toBeVisible();
  await expect(picks).toBeVisible();
  const radarBox=await radar.boundingBox(),picksBox=await picks.boundingBox();
  expect(radarBox).not.toBeNull();
  expect(picksBox).not.toBeNull();
  expect(radarBox!.y).toBeLessThan(picksBox!.y);
});
