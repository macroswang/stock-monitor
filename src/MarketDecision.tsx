import React,{useEffect,useState} from 'react';
import type {BreadthDay} from './MarketBreadth';
import type {MarketData} from './models';
import {breadthCountsConsistent,closedSnapshotReady,historicalMclChange,intradayBreadth,intradayEstimate,intradayIndex,priorTradingDay,verifiedFlowShare,verifiedTrin} from './intradayMarket';
import PositionExperiment from './PositionExperiment';
import positionSample from '../fixtures/market-position-experiment.json';
import {exchangeCalendar} from './exchangeCalendar';
import {requestWithTimeout} from './requestTimeout';

type IndexRow={date:string;close:number;boll_mid:number|null;gap_before?:boolean;vw_dif?:number|null;vw_dea?:number|null};
type Report={daily:IndexRow[];weekly?:IndexRow[];error:string;latest_eligible?:string|null;collected_at?:string};
type PcrReport={days:{date:string;pcr:number;call_volume:number;put_volume:number;band_lower:number|null;band_upper:number|null;collected_at:string}[];error:string};
type CSI300Report={date:string;member_date:string;collected_at:string;member_collected_at:string;available_at:string;status:string;advance:number;decline:number;flat:number;suspended:number;advance_amount:number;market_advance_amount:number;advance_amount_percent:number;decline_amount?:number;market_decline_amount?:number;decline_amount_percent?:number};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const pct=(v:number)=>`${v.toFixed(1)}%`;
// A previous close is usable only outside the next trading session and only
// when the exchange calendar identifies the most recent trading day.
function lastCloseDuringRest(today:string,now:number):string|null{
 const date=new Date(today+'T00:00:00Z');
 if(!Number.isFinite(date.getTime())||!exchangeCalendar.hasYear(date.getUTCFullYear()))return null;
 const time=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
 if(exchangeCalendar.tradingDay(today)===true&&time>='09:15')return null;
 for(let i=0;i<16;i++){date.setUTCDate(date.getUTCDate()-1);const day=date.toISOString().slice(0,10),trading=exchangeCalendar.tradingDay(day);if(trading===null)return null;if(trading)return day;}
 return null;
}

// Identify the last completed exchange week using the verified calendar.
// A missing calendar or an older weekly bar must not become current evidence.
function lastCompletedWeek(reference:string):string|null{
 const d=new Date(reference+'T00:00:00Z');
 if(!Number.isFinite(d.getTime())||d.toISOString().slice(0,10)!==reference||!exchangeCalendar.hasYear(d.getUTCFullYear()))return null;
 const monday=new Date(d);monday.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));
 for(let week=0;week<3;week++){
  const end:string[]=[];
  for(let n=0;n<5;n++){
   const date=new Date(monday);date.setUTCDate(monday.getUTCDate()-7*week+n);
   const label=date.toISOString().slice(0,10);
   const trading=exchangeCalendar.tradingDay(label);if(trading===null)return null;if(trading)end.push(label);
  }
  const last=end.at(-1);
  if(last&&last<=reference)return last;
 }
 return null;
}

export default function MarketDecision({request,day,previous,byAmount,market,stage,feedError='',compact=false,onOpen,preview=false}:{request:Request;day:BreadthDay|undefined;previous:BreadthDay|undefined;byAmount:boolean;market:MarketData;stage:'unknown'|'early'|'late';feedError?:string;compact?:boolean;onOpen?:()=>void;preview?:boolean}){
 const [report,setReport]=useState<Report>({daily:[],error:''});
 const [pcr,setPcr]=useState<(PcrReport|null)[]|null>(null);
 const [csi300,setCsi300]=useState<CSI300Report|null>(null);
 // Age out a live observation even when all pending requests remain stalled.
 const [,setClock]=useState(()=>Date.now());
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),15000);return()=>clearInterval(timer);},[]);
 // A slow older response must never replace a newer result or error.
 useEffect(()=>{let alive=true,sequence=0;const load=async()=>{const current=++sequence;try{const data=await requestWithTimeout(request<Report>('index_technical'));if(alive&&current===sequence)setReport(data);}catch{if(alive&&current===sequence)setReport({daily:[],error:'指数数据获取失败'});}};void load();const timer=setInterval(load,30000);return()=>{alive=false;clearInterval(timer);};},[request]);
 useEffect(()=>{let alive=true,reading=false;const load=async()=>{if(reading)return;reading=true;const data=await Promise.allSettled(['510050','510300'].map(security_code=>requestWithTimeout(request<PcrReport>('option_pcr',{security_code}))));if(alive)setPcr(data.map(x=>x.status==='fulfilled'?x.value:null));reading=false;};void load();const timer=setInterval(load,compact?180000:30000);return()=>{alive=false;clearInterval(timer);};},[request,compact]);
 useEffect(()=>{let alive=true,reading=false;setCsi300(null);const load=async()=>{if(!day?.date||reading)return;reading=true;try{const result=await requestWithTimeout(request<CSI300Report|null>('csi300',{day:day.date}));if(alive)setCsi300(result);}catch{if(alive)setCsi300(null);}finally{reading=false;}};void load();const timer=setInterval(load,compact?180000:30000);return()=>{alive=false;clearInterval(timer);};},[request,day?.date,day?.collected_at,compact]);
 const breadth=day?.advancing_percent;
 const now=Date.now(),indexStamp=typeof report.collected_at==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+08:00$/.test(report.collected_at)?Date.parse(report.collected_at):NaN;
 const indexLast=report.daily.at(-1)?.date;
 // An index snapshot is usable only after it was actually collected, and
 // only if its last close was already available at that collection time.
 const indexReady=Number.isFinite(indexStamp)&&indexStamp<=now+5000&&!!indexLast&&!!report.collected_at&&(report.collected_at.slice(0,10)>indexLast||(report.collected_at.slice(0,10)===indexLast&&report.collected_at.slice(11,16)>='16:30'));
 const indexReport=indexReady?report:{...report,daily:[],weekly:[],latest_eligible:null};
 // Only closed, same-date observations can be compared; never borrow a later close.
 const idx=day?.status==='closed'?indexReport.daily.find(r=>r.date===day.date):undefined;
 const breadthLive=intradayBreadth(day,now),indexLive=intradayIndex(day,indexReport,market,now),intraday=intradayEstimate(day,indexReport,market,now);
 // During a valid live session the index service identifies the latest completed
 // close; label it explicitly and never read a future or same-day close.
 const vwReference=idx??(intraday&&day&&indexReport.latest_eligible&&indexReport.latest_eligible<day.date?indexReport.daily.find(r=>r.date===indexReport.latest_eligible):undefined);
 const dailyVw=vwReference&&typeof vwReference.vw_dif==='number'&&Number.isFinite(vwReference.vw_dif)&&typeof vwReference.vw_dea==='number'&&Number.isFinite(vwReference.vw_dea)?vwReference:null;
 const price=indexLive?.price??idx?.close,ma=indexLive?.ma??idx?.boll_mid;
 const missingIndex=day?.status==='closed'&&!idx?(report.error?`指数数据获取失败：${report.error}`:report.latest_eligible&&day.date>report.latest_eligible?'同日指数收盘参考尚未进入采集范围；本地按北京时间 16:30 后检查，实际到达时间可能更晚。':'缺少同日指数收盘数据，可在下方刷新指数参考。'):idx&&idx.boll_mid==null?'指数连续日线不足，无法计算20日均线。':null;
 const visibleBreadth=day&&(day.status==='closed'||breadthLive)?breadth:undefined;
 const available=(day?.status==='closed'||!!intraday)&&day?.missing===0&&day.covered===day.expected&&day.expected>0&&typeof breadth==='number'&&Number.isFinite(breadth)&&breadth>=0&&breadth<=100&&typeof price==='number'&&Number.isFinite(price)&&typeof ma==='number'&&Number.isFinite(ma)&&ma>0;
 const countsValid=breadthCountsConsistent(day);
 const breadthReady=!!day&&(day.status==='closed'||!!breadthLive)&&day.missing===0&&day.expected>0&&day.covered===day.expected&&countsValid&&typeof visibleBreadth==='number'&&Number.isFinite(visibleBreadth)&&visibleBreadth>=0&&visibleBreadth<=100;
 // A market dominated by unchanged shares cannot be described as broadly
 // rising or falling just because one small moving group exceeds the other.
 const flatMajority=countsValid&&!!day&&day.flat>(day.advance+day.decline+day.flat)/2;
 const weak=!!available&&countsValid&&!flatMajority&&breadth!<20&&price!<ma!&&day!.decline>day!.advance;
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 const calendarMissing=!!day&&day.date===today&&!exchangeCalendar.hasYear(Number(today.slice(0,4)));
 const recentClose=!!day&&day.status==='closed'&&day.date===lastCloseDuringRest(today,now)&&!!available&&countsValid;
 const dataError=feedError?'市场数据更新失败':report.error?'指数数据更新失败':null;
 const liveDecision=!calendarMissing&&!dataError&&!!day&&(day.date===today||recentClose)&&!!available&&countsValid;
 const riskPrompt=liveDecision?(flatMajority?'多数个股平盘，市场方向不明确：先观察。':weak?'弱势风险检查：评估持仓和减仓计划，避免仅凭低 TRIN 加仓。':
  price!<ma!&&day!.advance<day!.decline?'指数低于20日均线且跌多涨少：检查持仓风险，避免仅凭低 TRIN 加仓。':
  price!>ma!&&day!.advance>day!.decline?'指数高于20日均线且涨多跌少：结合仓位计划观察，避免单凭一天表现加仓。':
  price!==ma&&day!.advance!==day!.decline?'指数位置与涨跌家数表现分化：先观察，避免单凭一项数据调整仓位。':
  '指数或个股涨跌接近均衡：结合持仓计划观察。'):
  day?.status==='closed'&&day.date!==today?'历史回看，不作为当前操作依据。':'数据暂不足以给出当前风险提示。';
 const breadthLabel=!countsValid?'个股涨跌数据不足':flatMajority?'多数个股平盘':day!.advance>day!.decline?'个股涨多跌少':day!.advance<day!.decline?'个股跌多涨少':'个股涨跌家数持平';
 const breadthOnlyLabel=breadthReady?`${visibleBreadth!<20?'上涨个股不足两成':breadthLabel} · 指数数据不足或不同步`:'数据不足';
 const trendLabel=price!<ma!?'指数低于20日均线':price!>ma!?'指数高于20日均线':'指数持平20日均线';
 const indexAt=idx?indexReport.daily.indexOf(idx):-1;
 const priorClose=intraday?Number(market.quotes.find(q=>q.code==='sh000001')?.previous_close):idx&&idx.gap_before===false&&indexAt>0&&priorTradingDay(idx.date)===indexReport.daily[indexAt-1].date?indexReport.daily[indexAt-1].close:NaN;
 const indexMove=available&&Number.isFinite(priorClose)&&priorClose>0?(price!-priorClose)/priorClose*100:null;
 const divergence=indexMove!==null&&countsValid&&!flatMajority&&day&&indexMove>0&&day.advance<day.decline?'指数上涨，个股跌多涨少':indexMove!==null&&countsValid&&!flatMajority&&day&&indexMove<0&&day.advance>day.decline?'指数下跌，个股涨多跌少':null;
 const trin=day&&(day.status==='closed'||breadthLive)?verifiedTrin(day,byAmount):null;
 const reportedShare=day?(byAmount?day.advancing_amount_percent:day.advancing_volume_percent):null;
 const checkedShare=verifiedFlowShare(day,byAmount);
 const shareMismatch=reportedShare!=null&&checkedShare===null;
 const structureReady=!!day&&(day.status==='closed'||!!breadthLive)&&day.missing===0&&day.expected>0&&day.covered===day.expected&&countsValid&&!shareMismatch&&day.advance>0&&day.decline>0&&typeof breadth==='number'&&Number.isFinite(breadth)&&breadth>=0&&breadth<=100&&typeof trin==='number'&&Number.isFinite(trin)&&trin>0;
 const memberStamp=typeof csi300?.member_collected_at==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+08:00$/.test(csi300.member_collected_at)?Date.parse(csi300.member_collected_at):NaN;
 const coreAvailable=typeof csi300?.available_at==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+08:00$/.test(csi300.available_at)?Date.parse(csi300.available_at):NaN;
 const quoteStamp=typeof csi300?.collected_at==='string'?Date.parse(csi300.collected_at):NaN;
 const coreReady=!!csi300&&!!day&&structureReady&&csi300.date===day.date&&csi300.member_date===day.date&&csi300.status===day.status&&csi300.collected_at===day.collected_at&&Number.isFinite(memberStamp)&&csi300.member_collected_at.slice(0,10)>=day.date&&Number.isFinite(quoteStamp)&&Number.isFinite(coreAvailable)&&coreAvailable===Math.max(memberStamp,quoteStamp)&&coreAvailable<=now+5000&&[csi300.advance,csi300.decline,csi300.flat,csi300.suspended].every(v=>Number.isInteger(v)&&v>=0)&&csi300.advance+csi300.decline+csi300.flat+csi300.suspended===300&&typeof day.advance_amount==='number'&&Number.isFinite(day.advance_amount)&&day.advance_amount>0&&csi300.market_advance_amount===day.advance_amount&&Number.isFinite(csi300.advance_amount)&&csi300.advance_amount>=0&&csi300.advance_amount<=csi300.market_advance_amount&&Number.isFinite(csi300.advance_amount_percent)&&Math.abs(csi300.advance_amount_percent-100*csi300.advance_amount/csi300.market_advance_amount)<1e-7;
 const coreDeclineReady=coreReady&&typeof day!.decline_amount==='number'&&Number.isFinite(day!.decline_amount)&&day!.decline_amount>0&&csi300!.market_decline_amount===day!.decline_amount&&typeof csi300!.decline_amount==='number'&&Number.isFinite(csi300!.decline_amount)&&csi300!.decline_amount>=0&&csi300!.decline_amount<=day!.decline_amount&&typeof csi300!.decline_amount_percent==='number'&&Number.isFinite(csi300!.decline_amount_percent)&&Math.abs(csi300!.decline_amount_percent-100*csi300!.decline_amount/day!.decline_amount)<1e-7;
 const coreConcentration=coreDeclineReady&&csi300!.advance_amount_percent.toFixed(1)!==csi300!.decline_amount_percent!.toFixed(1)?`${csi300!.advance_amount_percent>csi300!.decline_amount_percent!?'上涨':'下跌'}组成交额更集中在沪深300。`:null;
 const coreRelation=coreDeclineReady?(csi300!.advance_amount_percent.toFixed(1)===csi300!.decline_amount_percent!.toFixed(1)?'接近':csi300!.advance_amount_percent>csi300!.decline_amount_percent!?'高于':'低于'):null;
 const jointStructure=structureReady?`${breadth!<50?'不足一半':breadth!>50?'超过一半':'恰好一半'}的活跃股票上涨；${trin!<1?'上涨':trin!>1?'下跌':'上涨与下跌'}组的每只平均${byAmount?'成交额':'成交量'}${trin===1?'相同':'较高'}。`:null;
 const ratio=structureReady?(trin!<1?1/trin!:trin!):null;
 const ratioText=ratio!==null&&Number.isFinite(ratio)&&trin!==1?`${trin!<1?'上涨':'下跌'}股平均${byAmount?'成交额':'成交量'}约为${trin!<1?'下跌':'上涨'}股的 ${ratio.toFixed(2)} 倍。`:null;
 const share=structureReady?checkedShare:null;
 const validShare=typeof share==='number'&&Number.isFinite(share)&&share>=0&&share<=100;
 const comparable=!!day&&!!previous&&priorTradingDay(day.date)===previous.date&&closedSnapshotReady(previous,now)&&countsValid&&breadthCountsConsistent(previous)&&(day.status==='closed'||!!breadthLive)&&day.missing===0&&day.expected>0&&day.covered===day.expected&&day.adl_gap_before===false&&previous.status==='closed'&&previous.missing===0&&previous.expected>0&&previous.covered===previous.expected&&!!day.source&&!!day.universe&&previous.source===day.source&&previous.universe===day.universe;
 // 只比较完整交易日的成交量：盘中累计量不是全天总量，数据来源或股票范围不一致时也不能直接比较。
 const totalShares=(d:BreadthDay|undefined)=>{if(!d)return null;const parts=[d.advance_volume,d.decline_volume,d.flat_volume];if(!parts.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0))return null;const sum=parts.reduce((a,b)=>a+b,0);return Number.isSafeInteger(sum)&&sum>0?sum:null;};
 const todayShares=totalShares(day),previousShares=totalShares(previous);
 const volumeChange=comparable&&day?.status==='closed'&&closedSnapshotReady(day,now)&&todayShares!==null&&previousShares!==null?(todayShares/previousShares-1)*100:null;
 const volumeSummary=volumeChange!==null&&Number.isFinite(volumeChange)?`${day!.date} 收盘沪深股票成交股数较 ${previous!.date} ${Math.abs(volumeChange)<0.05?'基本持平':`${volumeChange>0?'增加':'减少'} ${Math.abs(volumeChange).toFixed(1)}%`}。`:null;
 const previousTrin=verifiedTrin(previous,byAmount);
 // 过期的盘中快照不能当成当前信号；前收盘参考必须完整、连续并注明日期。
 const closeReference=day?.status==='provisional'&&!breadthLive&&day.adl_gap_before===false&&previous?.status==='closed'&&previous.date<day.date&&closedSnapshotReady(previous,now)&&breadthCountsConsistent(previous)&&previous.missing===0&&previous.expected>0&&previous.covered===previous.expected&&!!day.source&&!!day.universe&&day.source===previous.source&&day.universe===previous.universe&&typeof previous.advancing_percent==='number'&&Number.isFinite(previous.advancing_percent)&&previous.advancing_percent>=0&&previous.advancing_percent<=100?previous:undefined;
 const breadthChange=comparable&&typeof breadth==='number'&&Number.isFinite(breadth)&&typeof previous?.advancing_percent==='number'&&Number.isFinite(previous.advancing_percent)?breadth-previous.advancing_percent:null;
 // Describe a widening divergence only for consecutive, comparable snapshots.
 const narrowingBreadth=indexMove!==null&&indexMove>0&&breadthChange!==null&&breadthChange<0&&typeof previous?.advancing_percent==='number'&&previous.advancing_percent>=50&&typeof breadth==='number'&&breadth<50;
 const divergenceText=narrowingBreadth?`指数上涨，但上涨股票占比从上一交易日收盘的 ${pct(previous!.advancing_percent!)} 降至 ${pct(breadth!)}${breadthLive?'（盘中暂值）':''}，上涨范围收窄`:divergence;
 const trinChange=comparable&&structureReady&&previous&&Number.isInteger(previous.advance)&&Number.isInteger(previous.decline)&&previous.advance>0&&previous.decline>0&&previous.advance+previous.decline<=previous.covered&&previousTrin!=null&&Number.isFinite(previousTrin)&&previousTrin>0?trin!-previousTrin:null;
 const changeSummary=breadthChange!==null&&trinChange!==null?`上涨股票占比${Math.abs(breadthChange)<0.05?'基本持平':`${breadthChange>0?'上升':'下降'} ${Math.abs(breadthChange).toFixed(1)} 个百分点`}；上涨股相对平均成交${Math.abs(trinChange)<0.0005?'基本持平':trinChange<0?'增强':'减弱'}。`:null;
 const signed=(n:number,digits:number)=>`${n>0?'+':''}${n.toFixed(digits)}`;
 const current=liveDecision;
 const marketWeak=!!available&&!flatMajority&&price!<ma!&&day!.advance<day!.decline;
 const marketStrong=!!available&&!flatMajority&&price!>ma!&&day!.advance>day!.decline;
 // 只有最近一个完整交易周的数据才能参与当日判断，避免旧周线影响操作参考。
 const weekly=day?indexReport.weekly?.filter(r=>day.status==='provisional'?r.date<day.date:r.date<=day.date).at(-1):undefined;
 const weeklyVw=weekly&&typeof weekly.vw_dif==='number'&&Number.isFinite(weekly.vw_dif)?weekly.vw_dif:null;
 const weeklyPair=weekly&&weeklyVw!==null&&typeof weekly.vw_dea==='number'&&Number.isFinite(weekly.vw_dea)?weekly:null;
 const closedReference=idx?day!.date:intraday?indexReport.latest_eligible:null;
 const weeklyAvailable=!!weeklyPair&&!!closedReference&&weeklyPair.date===lastCompletedWeek(closedReference);
 const weeklySummary=weeklyAvailable?`周线量价${weeklyPair!.vw_dif!<0&&weeklyPair!.vw_dea!<0?'偏弱':weeklyPair!.vw_dif!>0&&weeklyPair!.vw_dea!>0?'偏强':'分化'}（${weeklyPair!.date} 收盘参考）。`:null;
 const weeklyWeak=weeklyAvailable&&weeklyPair!.vw_dif!<0&&weeklyPair!.vw_dea!<0;
 const weeklyStrong=weeklyAvailable&&weeklyPair!.vw_dif!>0&&weeklyPair!.vw_dea!>0;
 const weakVw=!!dailyVw&&dailyVw.vw_dif!<0&&dailyVw.vw_dea!<0;
 const trendConflict=marketStrong&&!!dailyVw&&!(dailyVw.vw_dif!>0&&dailyVw.vw_dea!>0);
 const weeklyConflict=marketStrong&&!!dailyVw&&!trendConflict&&weeklyAvailable&&!weeklyStrong;
 const weeklyMissing=marketStrong&&!!dailyVw&&!trendConflict&&!weeklyAvailable;
 const canAdd=marketStrong&&!!dailyVw&&!trendConflict&&weeklyAvailable&&weeklyStrong&&structureReady&&trin!<=1;
 const headline=!available||!countsValid?'数据不足，等待更新':!structureReady?'市场数据待核对':weak?'市场偏弱，防守为主':marketWeak?'市场偏弱，控制风险':trendConflict?'市场信号分化，先观察':marketStrong&&trin!>1?'涨多跌少，成交结构分化':weeklyConflict?`短期转强，周线${weeklyWeak?'偏弱':'分化'}`:weeklyMissing?'周线量价待确认':marketStrong&&!dailyVw?'量价数据不足，先观察':marketStrong?'指数高于均线，涨多跌少':'市场分化，先观察';
 const action=dataError&&day&&(day.date===today||recentClose)?`${dataError}，等待恢复后再查看操作参考。`:calendarMissing?`当年交易日历尚未配置，暂不提供${day?.status==='provisional'?'盘中':'当前'}操作参考。`:!current?'所选数据不是可用的当前行情，请先查看最新数据，暂不依据它调整仓位。':!structureReady?'成交结构数据不足，先等待完整数据，暂不调整仓位。':weak||marketWeak?'先不加仓；空仓继续观望，持仓较重可考虑分批减仓。':trendConflict?`暂不加仓，先观察；上涨股票较多，但${intraday?`${dailyVw!.date} 收盘的`:''}日线量价指标${weakVw?'偏弱':'仍有分歧'}。`:marketStrong&&trin!>1?'暂不加仓，先观察；上涨股票较多，但下跌股平均成交更高。':weeklyConflict?`暂不加仓，先观察；短期量价偏强，但 ${weeklyPair!.date} 收盘的周线量价${weeklyWeak?'仍偏弱':'仍有分歧'}。`:weeklyMissing?'暂不加仓，等待最近完整周线量价数据。':marketStrong&&!dailyVw?'暂不加仓，先观察；缺少可用的最近收盘量价数据。':marketStrong?'可考虑小幅、分批加仓，避免一次买满。':'暂不加仓，先观察；已有持仓按计划管理。';
 const reason=available&&countsValid?`${narrowingBreadth?`指数上涨，但上涨股票占比从 ${pct(previous!.advancing_percent!)} 降至 ${pct(breadth!)}${breadthLive?'（盘中暂值）':''}`:divergence?`${divergence}（上涨股票 ${pct(breadth!)}）`:`上涨股票 ${pct(breadth!)}，${breadthLabel}`}；上证${price!<ma!?'低于':price!>ma!?'高于':'持平'}20日均线。`:null;
 const compactFlow=structureReady?(trin!<0.7&&breadth!<20?`少数上涨股平均${byAmount?'成交额':'成交量'}高于下跌股。`:trin===1?`涨跌股平均${byAmount?'成交额':'成交量'}相同。`:`${trin!<1?'上涨股':'下跌股'}平均${byAmount?'成交额':'成交量'}较高。`):null;
 // 只比较同一快照中已核验的成交额占比；它描述成交分布，不能直接代表参与者身份或资金净流向。
 const compactCore=structureReady&&trin!<0.7&&breadth!<20&&coreRelation&&coreRelation!=='接近'?`${coreRelation==='高于'?'上涨':'下跌'}组成交额相对更集中在沪深300成分股。`:null;
 const mclChange=historicalMclChange(day,previous,now);
 const mclSummary=mclChange!==null&&Math.abs(mclChange)>=0.1?`宽度辅助：市场宽度动能较上一交易日${mclChange<0?'减弱':'增强'}（${day!.date} 收盘参考）。`:null;
 const flowSummary=structureReady?(trin!<0.7&&breadth!<20?'上涨股票较少但相对放量，关注大资金是否集中进入少数上涨股。':trin!<1?'上涨股的平均成交较高。':trin!>1?'下跌股的平均成交较高。':'涨跌股票的平均成交相同。'):null;
 const verifiedPcr=(r:PcrReport|null|undefined,date:string)=>{
  const row=r&&!r.error?r.days.find(x=>x.date===date):undefined;
  const collected=row?Date.parse(row.collected_at):NaN;
  if(!row||typeof row.collected_at!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+08:00$/.test(row.collected_at)||!Number.isFinite(collected)||collected>now+5000||row.collected_at.slice(0,10)<row.date||(row.collected_at.slice(0,10)===row.date&&row.collected_at.slice(11,16)<'15:00')||!Number.isInteger(row.call_volume)||row.call_volume<=0||!Number.isInteger(row.put_volume)||row.put_volume<0||!Number.isFinite(row.pcr)||row.pcr<0||Math.abs(row.pcr-row.put_volume/row.call_volume)>1e-8)return undefined;
  return row;
 };
 const pcrText=(i:number)=>{if(!pcr)return '加载中';if(!pcr[i]||pcr[i]!.error)return '获取失败';if(!day||day.status!=='closed')return '收盘后更新';const row=verifiedPcr(pcr[i],day.date);return row?row.pcr.toFixed(3):'无同日数据';};
 const pcrPrior=day&&pcr?.[0]&&pcr[1]&&(pcrText(0)==='无同日数据'||pcrText(1)==='无同日数据'||day.status==='provisional')?pcr[0].days.filter(x=>x.date<day.date&&!!verifiedPcr(pcr[0],x.date)&&!!verifiedPcr(pcr[1],x.date)).sort((a,b)=>a.date.localeCompare(b.date)).at(-1):undefined;
 const pcrPriorOther=pcrPrior?verifiedPcr(pcr?.[1],pcrPrior.date):undefined;
 const maDay=day?.status==='closed'?day:day?.status==='provisional'&&day.adl_gap_before===false&&previous?.status==='closed'&&previous.date<day.date&&closedSnapshotReady(previous,now)&&breadthCountsConsistent(previous)?previous:undefined;
 const maCandidate=maDay?(maDay.ma_daily??(maDay.historical?maDay.ma_breadth:maDay.ma_history)):undefined;
 const maData=maCandidate?.date===maDay?.date?maCandidate:undefined;
 const maParts=['20','60','250'].flatMap(n=>{const w=maData?.windows?.[n];return w&&w.eligible>0&&typeof w.percent==='number'&&Number.isFinite(w.percent)&&w.percent>=0&&w.percent<=100?[`${n}日 ${pct(w.percent)}`]:[];});
 // A missing same-day close may use the immediately preceding, same-source
 // close, but the date and eligible sample must always be visible.
 const priorMaDay=day&&previous&&day.adl_gap_before===false&&previous.date<day.date&&previous.status==='closed'&&closedSnapshotReady(previous,now)&&previous.missing===0&&previous.expected>0&&previous.covered===previous.expected&&breadthCountsConsistent(previous)&&!!day.source&&!!day.universe&&day.source===previous.source&&day.universe===previous.universe?previous:undefined;
 const annualCandidate=day?.status==='closed'&&day.ma_daily?day:priorMaDay;
 const annual=annualCandidate?.ma_daily,annualWindow=annual?.windows?.['250'];
 const annualStamp=annual?.collected_at?Date.parse(annual.collected_at):NaN;
 const annualReady=!!annual&&annual.status==='closed'&&annual.date===annualCandidate?.date&&typeof annual.collected_at==='string'&&/\+08:00$/.test(annual.collected_at)&&Number.isFinite(annualStamp)&&annualStamp<=now+5000&&(annual.collected_at.slice(0,10)>annual.date||(annual.collected_at.slice(0,10)===annual.date&&annual.collected_at.slice(11,16)>='15:00'))&&!!annual.source&&Number.isInteger(annual.active)&&annual.active>0&&annual.active<=annualCandidate!.covered&&!!annualWindow&&Number.isInteger(annualWindow.eligible)&&annualWindow.eligible>0&&annualWindow.eligible<=annual.active&&Number.isInteger(annualWindow.above)&&annualWindow.above>=0&&annualWindow.above<=annualWindow.eligible&&typeof annualWindow.percent==='number'&&Number.isFinite(annualWindow.percent)&&Math.abs(annualWindow.percent-100*annualWindow.above/annualWindow.eligible)<=0.055;
 const annualSummary=annualReady?`长期参考：${annualWindow!.percent!<50?'仅 ':''}${pct(annualWindow!.percent!)} 的有效股票在各自年线上方（${annual!.date} 收盘）。`:current?'长期参考：年线数据暂缺。':null;
 // The ETF observations are independently dated close data, not the author's
 // full-market PCR. Only surface an unusual band position; never alter advice.
 const pcrDate=day?.status==='closed'?day.date:intraday&&report.latest_eligible&&report.latest_eligible<day!.date?report.latest_eligible:null;
 const pcrAlerts=pcrDate?(pcr?.flatMap((r,i)=>{
  const row=verifiedPcr(r,pcrDate);
  if(!row||typeof row.band_lower!=='number'||!Number.isFinite(row.band_lower)||typeof row.band_upper!=='number'||!Number.isFinite(row.band_upper)||row.band_lower>row.band_upper)return [];
  const history=r!.days.filter(x=>x.date<=pcrDate).slice().sort((a,b)=>a.date.localeCompare(b.date)).slice(-20);
  if(history.length!==20||history.at(-1)?.date!==pcrDate||new Set(history.map(x=>x.date)).size!==20||history.some((x,n)=>verifiedPcr(r,x.date)!==x||(n>0&&priorTradingDay(x.date)!==history[n-1].date)))return [];
  const mean=history.reduce((sum,x)=>sum+x.pcr,0)/20;
  const deviation=Math.sqrt(history.reduce((sum,x)=>sum+(x.pcr-mean)**2,0)/20);
  if(Math.abs(row.band_lower-(mean-2*deviation))>1e-8||Math.abs(row.band_upper-(mean+2*deviation))>1e-8)return [];
  const position=row.pcr<row.band_lower?'看跌/看涨成交比低于参考区间':row.pcr>row.band_upper?'看跌/看涨成交比高于参考区间':null;
  return position?[`${i===0?'50ETF':'300ETF'} ${position}`]:[];
 })??[]):[];
 if(compact)return <section className="home-market-decision" aria-label="首页市场判断">
  <div className="home-market-title"><strong>市场判断</strong><span>{current&&day?`${day.date} · ${recentClose?'最近收盘':day.status==='closed'?'收盘统计':'盘中暂值'}`:'等待最新数据'}{preview?' · 静态预览':''}</span><span>本机规则 · 成交额口径</span></div>
  <div className="home-market-result">
   <div className="home-market-summary"><strong>{dataError??(calendarMissing?'交易日历未配置':current?headline:'数据不足，等待更新')}</strong><span className="home-market-action"><span className="home-market-action-label">操作建议</span>{dataError?'等待恢复后再查看操作参考。':calendarMissing?action:current?action:'等待最新市场数据，再查看操作参考。'}</span></div>
   {current&&reason&&<span className="home-market-reason">原因：{reason}{compactFlow}{compactCore}</span>}
   {current&&structureReady&&(weak||marketWeak)&&<span className="home-market-next">后续关注：上涨股票能否变多、上证能否回到20日均线上方。</span>}
   {current&&(canAdd||annualReady||narrowingBreadth||structureReady||pcrAlerts.length>0||volumeSummary||changeSummary||mclSummary)&&<details className="home-market-evidence"><summary>查看依据</summary><div>
    {changeSummary&&previous&&<span>较 {previous.date.slice(5)} 收盘{breadthLive?'（盘中暂值）':''}：{changeSummary}</span>}
    {structureReady&&<span>成交：{breadth!<20&&trin!<0.7?'少数上涨股相对放量；':''}{ratioText?.replace(/。$/, '')||`上涨与下跌股票平均${byAmount?'成交额':'成交量'}相同`}（TRIN {trin!.toFixed(3)}）。</span>}
    {coreDeclineReady&&<span className="home-market-core">沪深300：上涨组成交额占比{coreRelation}下跌组（{pct(csi300!.advance_amount_percent)} 对 {pct(csi300!.decline_amount_percent!)}）。</span>}
    {stage==='unknown'&&<span>趋势阶段尚未确认；操作参考采用本地组合规则。</span>}
    {volumeSummary&&<span>总成交：{volumeSummary}</span>}
    {mclSummary&&<span>{mclSummary}</span>}
    {canAdd&&<span>量价：日线和周线均偏强（日线 {dailyVw!.date}、周线 {weeklyPair!.date} 收盘）。</span>}
    {annualReady&&<span>长期：{pct(annualWindow!.percent!)} 的有效股票高于年线（{annual!.date} 收盘）。</span>}
    {coreConcentration&&<span>{coreConcentration}</span>}
    {pcrAlerts.length>0&&<span>期权：{pcrAlerts.join('；')}（{pcrDate} 收盘，20日参考）。</span>}
   </div></details>}
  </div>
  <button type="button" onClick={onOpen}>查看市场趋势</button>
 </section>;
 return <section className="market-observation market-decision" aria-label="市场状态与操作参考">
  <div className="observation-heading"><div><h3>市场判断</h3><p>{day?`${day.date} · ${day.status==='closed'?'收盘统计':breadthLive?'盘中暂值':'盘中或未完成数据'}`:'暂无市场数据'}{recentClose?' · 最近交易日收盘参考':day&&day.date>today?' · 日期未到':day&&day.date<today?' · 历史数据':''} · 本机规则 · 成交额口径</p></div><span>操作参考</span></div>
  <div className="market-summary">
   <strong>{dataError&&day&&(day.date===today||recentClose)?dataError:current?headline:day&&day.date!==today?'历史回看':headline}</strong>
   <p className="market-summary-action">{recentClose?'最近收盘操作参考':'操作参考'}：{action}</p>
   {reason&&<p>原因：{reason}{weeklySummary&&` ${weeklySummary}`}</p>}
   {divergenceText&&<p>盘面分化：{divergenceText}。</p>}
   {flowSummary&&<p>资金观察：{flowSummary}（TRIN {trin!.toFixed(3)}）{coreConcentration&&` ${coreConcentration}`}{trin!<0.7&&stage==='unknown'?' 趋势阶段未确认，低 TRIN 暂按成交结构观察。':trin!<0.7&&stage==='early'?' 趋势前段，低 TRIN 暂不直接判断反转。':''}</p>}
   <details className="market-quick-evidence" aria-label="指标依据"><summary>查看指标依据</summary>
   {volumeSummary&&<p>总成交：{volumeSummary}（上涨、下跌和平盘股票合计）。</p>}
   {annualSummary&&<p>{annualSummary}</p>}
   {coreReady&&<p>沪深300：{csi300!.advance>csi300!.decline?'涨多跌少':csi300!.advance<csi300!.decline?'跌多涨少':'涨跌家数持平'}（{csi300!.advance} 只上涨、{csi300!.decline} 只下跌）；{coreDeclineReady?`占全市场对应组成交额：上涨股 ${pct(csi300!.advance_amount_percent)}，下跌股 ${pct(csi300!.decline_amount_percent!)}。${coreConcentration||''}`:`上涨股成交额占全市场上涨组 ${pct(csi300!.advance_amount_percent)}。`}</p>}
   {current&&!coreReady&&<p>沪深300：等待同日成分和行情数据。</p>}
   {changeSummary&&<p>较上一交易日{breadthLive?'收盘（盘中暂值）':''}：{changeSummary}</p>}
   <small>本机参考条件：结合上证20日均线、涨跌家数、TRIN{dailyVw?`、${dailyVw.date}日线量价`:''}{weeklyConflict?`及${weeklyPair!.date}周线量价`:''}；中期趋势尚未确认。</small>
   <p>市场数据：上涨 {breadthReady?pct(visibleBreadth!):'—'} · 上证 {available?price!.toFixed(2):'—'} / 20日均线 {available?ma!.toFixed(2):'—'} · TRIN {structureReady?trin!.toFixed(3):'—'}（{byAmount?'成交额':'成交股数'}）</p>
   {jointStructure&&<p className="market-summary-structure">成交结构：{jointStructure}{ratioText&&` ${ratioText}`}</p>}
   {structureReady&&validShare&&<p>涨跌股{byAmount?'成交额':'成交量'}占比：上涨股 {pct(share)} · 下跌股 {pct(100-share)}（不含平盘）</p>}
   {(breadthChange!==null||trinChange!==null)&&<p>较上个交易日{breadthLive?'收盘（盘中暂值）':''}：{breadthChange!==null?`上涨家数占比 ${signed(breadthChange,1)} 个百分点`:''}{breadthChange!==null&&trinChange!==null?' · ':''}{trinChange!==null?`TRIN ${signed(trinChange,3)}`:''}</p>}
   <p>期权 PCR（收盘）：50ETF {pcrText(0)} · 300ETF {pcrText(1)}</p>
   {pcrPrior&&pcrPriorOther&&<p>期权最近共同记录（{pcrPrior.date} 收盘）：50ETF {pcrPrior.pcr.toFixed(3)} · 300ETF {pcrPriorOther.pcr.toFixed(3)}</p>}
   {!!maParts.length&&<p>均线上方个股（{maDay!.date} 收盘，未复权）：{maParts.join(' · ')}</p>}
   {dailyVw&&<p>日线量价（{dailyVw.date} 收盘）：{dailyVw.vw_dif!<0&&dailyVw.vw_dea!<0?'指标偏弱，快慢线均在零轴下方':dailyVw.vw_dif!>0&&dailyVw.vw_dea!>0?'指标偏强，快慢线均在零轴上方':'指标分化，快慢线分别位于零轴两侧或触及零轴'}。</p>}
   {weeklyVw!==null&&<p>周线量价（{weekly!.date} 收盘）：12周成交加权均价{weeklyVw>0?'高于':weeklyVw<0?'低于':'等于'}26周。</p>}
   <small>当前趋势阶段：{stage==='unknown'?'尚未判断':stage==='early'?'趋势前段':'趋势中后段'}。本机采用{byAmount?'成交额对照':'成交股数'}计算；操作参考结合上证20日均线、涨跌家数与 TRIN，偏强时另参考已结束日线和周线量价。</small>
   </details>
  </div>
  {day?.status==='closed'&&day.date<today&&!recentClose&&<p className="market-close-reference">当前展示 {day.date} 的历史收盘数据，不是当前行情；请核对所选日期和更新状态。</p>}
  {recentClose&&<p className="market-close-reference">依据 {day!.date} 收盘数据；开盘后请以更新的盘中行情为准。</p>}
  {breadthLive&&!intraday&&<p className="market-close-reference">全市场报价 {breadthLive.first.slice(11,19)}–{breadthLive.last.slice(11,19)}；{indexLive?`上证报价 ${indexLive.quoteTime.slice(11,19)}，两类数据不同步`:'指数数据不足或过期'}，暂不判断综合状态和仓位。</p>}
  {indexLive&&!intraday&&<p className="market-close-reference">上证现价与20日暂时均线仅供单独查看，指数报价 {indexLive.quoteTime.slice(11,19)}；均线使用前19日收盘及当前指数价。</p>}
  {missingIndex&&<p className="market-close-reference">{missingIndex} 暂不判断综合状态和仓位。</p>}
  {closeReference&&<p className="market-close-reference">前一交易日收盘参考 · {closeReference.date}：上涨家数 {pct(closeReference.advancing_percent!)} · TRIN {typeof previousTrin==='number'&&Number.isFinite(previousTrin)?previousTrin.toFixed(3):'—'}（{byAmount?'成交额对照':'成交股数'}）。仅供回看，不是当前行情或操作指令。</p>}
  <details className="breadth-method market-summary-details"><summary>查看判断依据和研究试算</summary><div className="observation-grid">
   <div className="observation-item"><div className="observation-label">市场状态</div><strong>{!available?breadthOnlyLabel:weak?'普跌 · 指数低于20日均线':`${trendLabel} · ${breadthLabel}`}</strong><p>上涨家数 {typeof visibleBreadth==='number'?pct(visibleBreadth):'—'} · 上证{day?.status==='provisional'?'现价':'收盘'} {typeof price==='number'?price.toFixed(2):'—'} · 20日均线 {typeof ma==='number'?ma.toFixed(2):'—'}</p>{divergence&&<p className="market-divergence">{divergence} · 上证较昨收 {signed(indexMove!,2)}%{intraday?'（盘中暂值）':''}</p>}<p>{breadthChange===null?'暂无法与上一交易日同口径比较':`上涨家数占比相比上一交易日 ${signed(breadthChange,1)} 个百分点${breadthLive?'（盘中暂值）':''}`}</p><small>“普跌”条件：上涨家数占比低于20%、下跌多于上涨、平盘不占多数，且指数低于20日均线。{intraday?`盘中均线由前19日收盘及现价计算，指数 ${intraday.quoteTime.slice(11,19)}，全市场报价 ${intraday.first.slice(11,19)}–${intraday.last.slice(11,19)}，非同步数据；盘中状态尚未做历史验证。`:'缺少可靠的同日数据时不判断。'}</small></div>
   <div className="observation-item"><div className="observation-label">成交结构</div><strong>{!structureReady?'数据不足':trin!<1?'上涨组平均成交较高':trin!>1?'下跌组平均成交较高':'两组平均成交相同'}</strong><p>TRIN {structureReady?trin!.toFixed(3):'—'} · {byAmount?'成交额对照':'成交股数'}</p>{jointStructure&&<p>{jointStructure}</p>}{ratioText&&<p>{ratioText}</p>}<div className="market-flow" aria-label="上涨和下跌股票成交占比"><div className="market-flow-label"><span>上涨股{byAmount?'成交额':'成交量'} {validShare?pct(share):'—'}</span><span>下跌股{byAmount?'成交额':'成交量'} {validShare?pct(100-share):'—'}</span></div>{validShare&&<div className="market-flow-bar" aria-hidden="true"><i style={{width:`${share}%`}}/><i style={{width:`${100-share}%`}}/></div>}</div><p>{trinChange===null?'暂无法与上一交易日同口径比较':`TRIN 相比上一交易日 ${signed(trinChange,3)}${breadthLive?'（盘中暂值）':''}`}</p><small>成交占比不含平盘股；上涨家数占比含平盘股。不是主动买卖量，不能识别主力身份或证明资金净流入。</small></div>
   <div className="observation-item"><div className="observation-label">仓位操作 · 研究提示</div><strong>判断依据与历史试算</strong><p>{riskPrompt}</p><p>历史试算：弱势条件下模拟减半仓、5 个交易日后买回，{positionSample.n} 次中 {positionSample.better} 次优于一直持有、{positionSample.worse} 次较差。</p><small>风险检查是独立研究假设，不代表预测；请结合个人持仓、风险承受能力和计划自行决定。固定 510300 ETF 示例假设成本与滑点，样本可能重叠；展开下方实验可查看细节。</small></div>
  </div>
  <PositionExperiment/></details>
 </section>;
}
