import type {BreadthDay} from './MarketBreadth';
import type {IndexQuote,MarketData} from './models';
import {exchangeCalendar} from './exchangeCalendar';
import {breadthCountsConsistent,closedSnapshotReady,intradayBreadth,verifiedFlowShare,verifiedTrin} from './intradayMarket';

export type ObservationKind='live'|'closed'|'cached';
export type QuoteView={quote:IndexQuote;kind:ObservationKind};
const dateTime=(now:number)=>({date:new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now),time:new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now)});

// 交易时段不得把昨收行情冒充当日快照；未知交易日历不推断日期。
export function lastClosedSession(now:number):string|null{
 const cn=dateTime(now),today=exchangeCalendar.tradingDay(cn.date);
 if(today===null)return null;
 if(today&&cn.time>='15:00')return cn.date;
 if(today&&cn.time>='09:15')return null;
 const d=new Date(cn.date+'T00:00:00Z');
 for(let i=0;i<16;i++){d.setUTCDate(d.getUTCDate()-1);const day=d.toISOString().slice(0,10),valid=exchangeCalendar.tradingDay(day);if(valid===null)return null;if(valid)return day;}
 return null;
}

export function quoteView(quote:IndexQuote|undefined,marketError:string|undefined,now:number):QuoteView|null{
 if(!quote||quote.source!=='tencent'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+08:00$/.test(quote.timestamp))return null;
 const price=Number(quote.price),prev=Number(quote.previous_close),change=Number(quote.change),percent=Number(quote.percent),time=Date.parse(quote.timestamp);
 if(![price,prev,change,percent,time].every(Number.isFinite)||price<=0||prev<=0||time>now+5000||Math.abs(price-prev-change)>0.021||Math.abs((price/prev-1)*100-percent)>0.025)return null;
 const cn=dateTime(now),fresh=now-time<=90000,day=quote.timestamp.slice(0,10),tm=quote.timestamp.slice(11,16);
 const session=exchangeCalendar.tradingDay(cn.date)===true&&((cn.time>='09:30'&&cn.time<'11:30')||(cn.time>='13:00'&&cn.time<'15:00'));
 const sameSession=cn.time<'11:30'?tm>='09:30'&&tm<'11:30':tm>='13:00'&&tm<'15:00';
 const quoteOk=!marketError||marketError==='上证分时暂时不可用';
 if(quoteOk&&session&&day===cn.date&&fresh&&sameSession)return {quote,kind:'live'};
 if(quoteOk&&lastClosedSession(now)===day&&tm>='15:00')return {quote,kind:'closed'};
 return {quote,kind:'cached'};
}

export function breadthView(day:BreadthDay|undefined,error:string|undefined,now:number){
 if(error||!day||day.missing!==0||day.expected<=0||day.covered!==day.expected||!breadthCountsConsistent(day))return null;
 const live=intradayBreadth(day,now);
 const closed=day.status==='closed'&&closedSnapshotReady(day,now)&&day.date===lastClosedSession(now);
 if(!live&&!closed)return null;
 const share=verifiedFlowShare(day,true),reported=day.advancing_amount_percent;
 const trin=reported!=null&&share===null?null:verifiedTrin(day,true);
 return {day,kind:live?'live' as const:'closed' as const,live,share,trin};
}

export function marketObservation(index:QuoteView|null,breadth:ReturnType<typeof breadthView>){
 if(!index||!breadth||index.kind==='cached'||index.kind!==breadth.kind||index.quote.timestamp.slice(0,10)!==breadth.day.date)return '市场数据暂未同步，先等待更新。';
 if(breadth.kind==='live'&&breadth.live){const ms=Date.parse(index.quote.timestamp);if(ms<breadth.live.firstMs-90000||ms>breadth.live.lastMs+90000)return '指数与全市场报价不同步，先等待更新。';}
 const {advance,decline,flat}=breadth.day;
 if(flat>(advance+decline+flat)/2)return '多数股票平盘，市场方向尚不明确。';
 const change=Number(index.quote.change);
 if(change>0&&decline>advance)return '指数上涨、个股跌多涨少，市场分化；先检查持仓。';
 if(change<0&&advance>decline)return '指数下跌、个股涨多跌少，市场分化；结合持股走势观察。';
 if(change<0&&decline>advance)return '指数下跌、个股跌多涨少；优先检查持仓风险，暂缓加仓。';
 if(change>0&&advance>decline)return '指数上涨、个股涨多跌少；结合个股信号制定计划。';
 return '指数与个股方向不明确，先观察。';
}
