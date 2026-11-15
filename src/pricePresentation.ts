export const PRICE_UP='#ef6568',PRICE_DOWN='#36b898',PRICE_FLAT='#8c9db6';
export type IntradayRangeReference={code:string;day:string;timestamp:string;previousClose:number;high?:number;low?:number};
export type CachedRangeMetadata={date?:string;trading_date?:string;symbol?:string;previous_close?:string|number;day_high?:string|number;day_low?:string|number;limit_reference_time?:string};
/** Compare instants in the exchange timezone, rather than the written date prefix. */
export function tradingDayTimestamp(timestamp:string,day:string):number|null{
 if(typeof timestamp!=='string'||!/(Z|[+-]\d{2}:\d{2})$/.test(timestamp))return null;
 const stamp=Date.parse(timestamp),start=Date.parse(day+'T00:00:00+08:00');
 return !Number.isFinite(stamp)||!Number.isFinite(start)||new Date(start+8*3600000).toISOString().slice(0,10)!==day||stamp<start||stamp>=start+86400000?null:stamp;
}
/** Cache keys do not override conflicting dates or an explicit symbol in the payload. */
export function cachedPriceRangeReference(data:CachedRangeMetadata|undefined,code:string,day:string):IntradayRangeReference|undefined{
 if(!data?.limit_reference_time||(!data.date&&!data.trading_date)||(data.date&&data.date!==day)||(data.trading_date&&data.trading_date!==day))return;
 const symbol=data.symbol?.trim().toLowerCase();
 if(symbol&&symbol!==code&&(!/^\d{6}$/.test(symbol)||symbol!==code.slice(2)))return;
 return {code,day,timestamp:data.limit_reference_time,previousClose:Number(data.previous_close),high:Number(data.day_high),low:Number(data.day_low)};
}
/** Day extrema are cumulative observations, so only use a snapshot already reached. */
export function reachedPriceRange(reference:IntradayRangeReference|undefined,code:string,day:string|undefined,previousClose:number|undefined,cutoff:number|null){
 if(!reference||!day||cutoff===null||!Number.isFinite(cutoff)||reference.code!==code||reference.day!==day)return [];
 const stamp=tradingDayTimestamp(reference.timestamp,day),base=Number(previousClose);
 if(stamp===null||stamp>cutoff||!Number.isFinite(base)||base<=0||!Number.isFinite(reference.previousClose)||Math.abs(reference.previousClose-base)>.000001)return [];
 const {high,low}=reference;
 if(high!==undefined&&low!==undefined&&high<low)return [];
 return [high,low].filter((v):v is number=>v!==undefined&&Number.isFinite(v)&&v>0);
}
export function priceColor(value:number,previous:number|undefined){
 const base=Number(previous);
 return !Number.isFinite(value)||!Number.isFinite(base)||base<=0?PRICE_FLAT:value>base?PRICE_UP:value<base?PRICE_DOWN:PRICE_FLAT;
}
/** A cached endpoint cannot become confirmed by advancing the wall clock alone. */
export function minuteTimeCutoff(day:string,now:number,cachedAt?:string){
 const start=Date.parse(day+'T00:00:00+08:00');
 if(!Number.isFinite(start)||start>now)return null;
 if(!cachedAt)return now; // Legacy minute caches can still be displayed up to now.
 const stamp=Date.parse(cachedAt);
 return !Number.isFinite(stamp)||stamp<start||stamp>now+5000?null:Math.min(now,stamp);
}
