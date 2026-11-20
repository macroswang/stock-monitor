import type {MarketData} from './models';
import {minuteTimeCutoff,tradingDayTimestamp} from './pricePresentation';
import {minuteSlots} from './minuteMacd';

/** Join display-only series by identity, session, base AND the same observed minute. */
export function indexLeadingPoints(market:MarketData|undefined,code:string,now:number){
 const primary=market?.minute,leading=market?.leading;
 if(!primary||!leading||primary.code!==code||leading.code!==code||leading.source!=='eastmoney'||leading.date!==primary.date)return [];
 const day=primary.date,base=Number(primary.previous_close),otherBase=Number(leading.previous_close);
 // A weekend refresh can legitimately cache Friday's observed data on Sunday.
 const stamp=tradingDayTimestamp(leading.timestamp,day),cached=Date.parse(leading.cached_at);
 const cutoff=minuteTimeCutoff(day,now,primary.cached_at||market?.collected_at);
 if(!Number.isFinite(base)||base<=0||!Number.isFinite(otherBase)||Math.abs(base-otherBase)>.021||stamp===null||!Number.isFinite(cached)||stamp>now+5000||cached>now+5000||stamp>cached+5000||cutoff===null||!Array.isArray(leading.bars))return [];
 const prices=new Map(primary.bars.map(bar=>[bar.time,Number(bar.close)])),slots=new Set(minuteSlots);
 if(!leading.bars.every((bar,i)=>bar&&slots.has(bar.time)&&(!i||leading.bars[i-1].time<bar.time)))return [];
 return leading.bars.flatMap(bar=>{
  const time=Date.parse(`${day}T${bar.time}:00+08:00`),weighted=Number(bar.close),value=Number(bar.value),paired=prices.get(bar.time);
  return time<=Math.min(cutoff,stamp,now)&&Number.isFinite(weighted)&&weighted>0&&paired!==undefined&&Number.isFinite(paired)&&Math.abs(weighted-paired)<=.021&&Number.isFinite(value)&&value>0?[{time:bar.time,value}]:[];
 });
}
