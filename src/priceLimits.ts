export type PriceLimits={up?:number;down?:number};
const positive=(v:unknown)=>Number.isFinite(Number(v))&&Number(v)>0?Number(v):undefined;
export const samePrice=(a:number,b:number)=>Math.abs(a-b)<.000001;
export function resolvedPriceLimits(previous:number|undefined,prices:number[],input:PriceLimits):PriceLimits{
 const base=positive(previous);if(!base)return {};
 const values=prices.filter(n=>Number.isFinite(n)&&n>0),up=positive(input.up),down=positive(input.down);
 // A wrong-day or inconsistent reference must never clip actual stock prices.
 return {up:up&&up>base&&values.every(p=>p<=up+.000001)?up:undefined,down:down&&down<base&&values.every(p=>p>=down-.000001)?down:undefined};
}
export function intradayPriceScale(previous:number|undefined,prices:number[],limits:PriceLimits){
 const values=prices.filter(n=>Number.isFinite(n)&&n>0);if(!previous||previous<=0||!values.length)return {};
 const low=Math.min(previous,...values),high=Math.max(previous,...values),raw=Math.max((high-low)/4,.01);
 const unit=10**Math.floor(Math.log10(raw)),step=[1,2,2.5,5,10].map(n=>n*unit).find(n=>n>=raw)!;
 let min=Math.floor(low/step)*step,max=Math.ceil(high/step)*step;
 if(min===max){min-=step;max+=step;}
 if(limits.down!==undefined)min=Math.max(min,limits.down);
 if(limits.up!==undefined)max=Math.min(max,limits.up);
 return {min,max,interval:step};
}
export function priceLimitState(value:number,limits:PriceLimits){return limits.up!==undefined&&samePrice(value,limits.up)?'涨停':limits.down!==undefined&&samePrice(value,limits.down)?'跌停':null;}
export function pricePercent(value:number,previous:number){const p=(value/previous-1)*100;return `${p>0?'+':''}${(Math.abs(p)<.005?0:p).toFixed(2)}%`;}
