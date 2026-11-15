import type {MarketData} from './models';
import {quoteView,type QuoteView} from './marketOverview';
import {minuteSlots} from './minuteMacd';
import {minuteTimeCutoff,priceColor} from './pricePresentation';

const positions=new Map(minuteSlots.map((time,index)=>[time,index]));
export function indexSparkline(market:MarketData,code:string,now:number,quote:QuoteView|null=quoteView(Array.isArray(market?.quotes)?market.quotes.find(q=>q?.code===code):undefined,market?.error,now)){
 const minute=market?.minute;
 const base=Number(minute?.previous_close),stamp=Date.parse(minute?.cached_at||market.collected_at||'');
 if(!quote||!minute||minute.code!==code||minute.source!=='tencent'||minute.date!==quote.quote.timestamp.slice(0,10)||
  !Number.isFinite(base)||base<=0||Math.abs(base-Number(quote.quote.previous_close))>.021||!Number.isFinite(stamp)||stamp>now+5000)return null;
 const cutoff=minuteTimeCutoff(minute.date,now,minute.cached_at||market.collected_at),bars=minute.bars;
 if(cutoff===null||!Array.isArray(bars)||!bars.length||!bars.every((b,i)=>b&&(positions.has(b.time)||b.time==='13:00')&&(!i||bars[i-1].time<b.time)&&
  Number.isFinite(Number(b.close))&&Number(b.close)>0&&Date.parse(`${minute.date}T${b.time}:00+08:00`)<=cutoff+65000))return null;
 // An endpoint may label the pending minute. Plot only observations already reached.
 const confirmed=bars.filter(b=>positions.has(b.time)&&Date.parse(`${minute.date}T${b.time}:00+08:00`)<=cutoff);
 if(!confirmed.length)return null;
 const returns=confirmed.map(b=>(Number(b.close)/base-1)*100),extent=Math.max(.01,...returns.map(Math.abs));
 const points=confirmed.map((b,i)=>({time:b.time,value:Number(b.close),x:2+positions.get(b.time)!/(minuteSlots.length-1)*156,y:20-returns[i]/extent*17}));
 let line='',area='',flatLine='';let start=0;
 for(let i=0;i<points.length;i++){
  const p=points[i],gap=i===0||positions.get(p.time)!-positions.get(points[i-1].time)!>1;
  if(gap){if(i)area+=` L${points[i-1].x},20 L${points[start].x},20 Z `;start=i;line+=`M${p.x},${p.y}`;area+=`M${p.x},20 L${p.x},${p.y}`;}
  else {line+=` L${p.x},${p.y}`;area+=` L${p.x},${p.y}`;if(p.value===base&&points[i-1].value===base)flatLine+=`M${points[i-1].x},20 L${p.x},20 `;}
 }
 area+=` L${points.at(-1)!.x},20 L${points[start].x},20 Z`;
 const until=points.at(-1)!.time,stale=!!market.error||quote.kind==='cached'||quote.kind==='closed'&&until<'15:00'||quote.kind==='live'&&(now-stamp>150000||now-Date.parse(`${minute.date}T${until}:00+08:00`)>150000);
 return {points,line,area,flatLine,baseline:20,color:priceColor(points.at(-1)!.value,base),day:minute.date,until,stale};
}
