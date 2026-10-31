import type {BreadthDay} from './MarketBreadth';
import type {MarketData} from './models';
import {exchangeCalendar} from './exchangeCalendar';

type IndexRow={date:string;close:number;gap_before?:boolean};
type IndexReport={daily:IndexRow[];latest_eligible?:string|null};
const stamp=(s:string|null|undefined)=>typeof s==='string'&&/\+08:00$/.test(s)?Date.parse(s):NaN;

/** Only connect observations whose source and stock universe are both known. */
export function sameBreadthProvenance(a:BreadthDay,b:BreadthDay){
 return typeof a.source==='string'&&!!a.source.trim()&&a.source===b.source&&
  typeof a.universe==='string'&&!!a.universe.trim()&&a.universe===b.universe;
}

/** Compare only consecutive, independently calculated historical MCL references. */
export function historicalMclChange(day:BreadthDay|undefined,previous:BreadthDay|undefined,now:number):number|null{
 const refFor=(row:BreadthDay|undefined)=>row?.mcl_history??(row?.historical&&typeof row.mcl_standard==='number'&&typeof row.mcl_samples==='number'?{
  date:row.date,value:row.mcl_standard,samples:row.mcl_samples,source:row.source,universe:row.universe??'',collected_at:row.collected_at
 }:undefined);
 const current=refFor(day),prior=refFor(previous);
 const ready=(row:BreadthDay|undefined,ref:typeof current)=>{
  if(!row||row.status!=='closed'||!ref||ref.date!==row.date||!Number.isFinite(ref.value)||
   !Number.isInteger(ref.samples)||ref.samples<39||typeof ref.source!=='string'||!ref.source.trim()||typeof ref.universe!=='string'||!ref.universe.trim()||
   typeof ref.collected_at!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+08:00$/.test(ref.collected_at))return false;
  const collected=Date.parse(ref.collected_at);
  return Number.isFinite(collected)&&collected<=now+5000&&ref.collected_at.slice(0,10)>=row.date&&
   (ref.collected_at.slice(0,10)>row.date||ref.collected_at.slice(11,16)>='15:00');
 };
 if(!ready(day,current)||!ready(previous,prior)||!day||!previous||!current||!prior||
  priorTradingDay(day.date)!==previous.date||current.samples!==prior.samples+1||
  current.source!==prior.source||current.universe!==prior.universe)return null;
 return current.value-prior.value;
}

function possibleTradingDay(day:string){
 return exchangeCalendar.tradingDay(day)===true;
}

// The latest available provider bar may itself be stale. Determine the
// immediately preceding trading day independently from the exchange calendar.
export function priorTradingDay(day:string):string|null{
 return exchangeCalendar.priorTradingDay(day);
}

/** Accept a quoted percentage only when it agrees with its underlying stock counts. */
export function breadthCountsConsistent(day:BreadthDay|undefined){
 if(!day||![day.advance,day.decline,day.flat,day.suspended,day.covered].every(v=>Number.isInteger(v)&&v>=0))return false;
 const total=day.advance+day.decline+day.flat;
 return total>0&&total+day.suspended===day.covered&&typeof day.advancing_percent==='number'&&Number.isFinite(day.advancing_percent)&&day.advancing_percent>=0&&day.advancing_percent<=100&&Math.abs(day.advancing_percent-100*day.advance/total)<=0.055;
}

/** Only use TRIN when it reproduces from the reported counts and turnover. */
export function verifiedTrin(day:BreadthDay|undefined,byAmount:boolean):number|null{
 if(!day||!breadthCountsConsistent(day)||day.advance<=0||day.decline<=0)return null;
 const value=byAmount?day.trin_amount:day.trin;
 const up=byAmount?day.advance_amount:day.advance_volume;
 const down=byAmount?day.decline_amount:day.decline_volume;
 if(typeof value!=='number'||!Number.isFinite(value)||value<=0||typeof up!=='number'||!Number.isFinite(up)||up<=0||typeof down!=='number'||!Number.isFinite(down)||down<=0)return null;
 const calculated=(day.advance/day.decline)*(down/up);
 return Number.isFinite(calculated)&&Math.abs(value-calculated)<=1e-9*Math.max(1,Math.abs(calculated))?value:null;
}

/** A reported group share must match the two underlying turnover totals. */
export function verifiedFlowShare(day:BreadthDay|undefined,byAmount:boolean):number|null{
 if(!day)return null;
 const value=byAmount?day.advancing_amount_percent:day.advancing_volume_percent;
 const up=byAmount?day.advance_amount:day.advance_volume;
 const down=byAmount?day.decline_amount:day.decline_volume;
 if(typeof value!=='number'||!Number.isFinite(value)||value<0||value>100||typeof up!=='number'||!Number.isFinite(up)||up<0||typeof down!=='number'||!Number.isFinite(down)||down<0||up+down<=0)return null;
 const calculated=100*up/(up+down);
 return Math.abs(value-calculated)<=1e-7?value:null;
}

/** Prevent a closed snapshot dated in the future or collected after the current time from becoming actionable. */
export function closedSnapshotReady(day:BreadthDay,now:number){
 if(day.status!=='closed')return true;
 // Reject impossible dates and weekends even if a provider labels them closed.
 // Known calendars reject exchange holidays; older historical years may still
 // be displayed when their exchange calendar is not available.
 const tradingDate=new Date(day.date+'T00:00:00Z');
 if(!Number.isFinite(tradingDate.getTime())||tradingDate.toISOString().slice(0,10)!==day.date||tradingDate.getUTCDay()===0||tradingDate.getUTCDay()===6)return false;
 if(exchangeCalendar.hasYear(tradingDate.getUTCFullYear())&&!possibleTradingDay(day.date))return false;
 const date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 if(day.date>date)return false;
 const collected=stamp(day.collected_at);
 if(!Number.isFinite(collected)||collected>now+5000)return false;
 // A timestamp before the record's date or before that day's market close
 // cannot establish a closed observation, even when viewed on a later day.
 const collectedDay=day.collected_at.slice(0,10),collectedTime=day.collected_at.slice(11,16);
 if(collectedDay<day.date||(collectedDay===day.date&&collectedTime<'15:00'))return false;
 if(day.date<date)return true;
 const time=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
 return time>='15:00';
}

/** Check the breadth snapshot independently from the index quote. */
export function intradayBreadth(day:BreadthDay|undefined,now:number){
 if(!day||day.status!=='provisional'||day.missing!==0||day.covered!==day.expected||day.expected<=0)return null;
 const cnDate=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 const cnTime=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
 if(cnDate!==day.date||!possibleTradingDay(cnDate)||!((cnTime>='09:30'&&cnTime<'11:30')||(cnTime>='13:00'&&cnTime<'15:00')))return null;
 const first=stamp(day.first_quote),last=stamp(day.last_quote),collected=stamp(day.collected_at);
 if(![first,last,collected].every(Number.isFinite)||first>last||last>collected||first<now-300000||collected>now+5000)return null;
 const sameSession=(s:string)=>{const t=s.slice(11,16);return cnTime<'11:30'?t>='09:30'&&t<'11:30':t>='13:00'&&t<'15:00';};
 if(!sameSession(day.first_quote!)||!sameSession(day.last_quote!))return null;
 return {first:day.first_quote!,last:day.last_quote!,firstMs:first,lastMs:last,sameSession};
}

/** A provisional index mean can be shown independently, but not combined with stale breadth. */
export function intradayIndex(day:BreadthDay|undefined,report:IndexReport,market:MarketData,now:number){
 // The index minute chart and index quotes are fetched independently. A
 // minute-only failure does not invalidate a fresh, otherwise verified quote.
 // Unknown or quote failures remain blocking rather than guessing their cause.
 if(!day||day.status!=='provisional'||(market.error&&market.error!=='上证分时暂时不可用'))return null;
 const cnDate=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 const cnTime=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
 if(cnDate!==day.date||!possibleTradingDay(cnDate)||!((cnTime>='09:30'&&cnTime<'11:30')||(cnTime>='13:00'&&cnTime<'15:00')))return null;
 const quote=market.quotes.find(q=>q.code==='sh000001'),price=Number(quote?.price);
 if(!quote||quote.source!=='tencent'||quote.timestamp.slice(0,10)!==day.date||!Number.isFinite(price)||price<=0)return null;
 const quoted=stamp(quote.timestamp);
 const t=quote.timestamp.slice(11,16);
 const sameSession=cnTime<'11:30'?t>='09:30'&&t<'11:30':t>='13:00'&&t<'15:00';
 if(!Number.isFinite(quoted)||quoted>now+5000||quoted<now-90000||!sameSession)return null;
 const prev=report.daily.filter(r=>r.date<day.date).slice(-19);
 if(prev.length!==19||!report.latest_eligible||prev.at(-1)?.date!==report.latest_eligible||report.latest_eligible!==priorTradingDay(day.date)||prev.some((r,i)=>!Number.isFinite(r.close)||r.close<=0||(i>0&&r.gap_before)))return null;
 return {price,ma:(prev.reduce((sum,r)=>sum+r.close,0)+price)/20,quoteTime:quote.timestamp,quoteMs:quoted};
}

/** Combined state additionally requires breadth and index timestamps to align. */
export function intradayEstimate(day:BreadthDay|undefined,report:IndexReport,market:MarketData,now:number){
 const breadth=intradayBreadth(day,now),index=intradayIndex(day,report,market,now);
 if(!breadth||!index||index.quoteMs<breadth.firstMs-90000||index.quoteMs>breadth.lastMs+90000)return null;
 return {...index,first:breadth.first,last:breadth.last};
}
