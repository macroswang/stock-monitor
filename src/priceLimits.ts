export type PriceLimits={up?:number;down?:number};
const positive=(v:unknown)=>Number.isFinite(Number(v))&&Number(v)>0?Number(v):undefined;
export const samePrice=(a:number,b:number)=>Math.abs(a-b)<.000001;
export function resolvedPriceLimits(previous:number|undefined,prices:number[],input:PriceLimits):PriceLimits{
 const base=positive(previous);if(!base)return {};
 const values=prices.filter(n=>Number.isFinite(n)&&n>0),up=positive(input.up),down=positive(input.down);
 // A wrong-day or inconsistent reference must never clip actual stock prices.
 return {up:up&&up>base&&values.every(p=>p<=up+.000001)?up:undefined,down:down&&down<base&&values.every(p=>p>=down-.000001)?down:undefined};
}
/** Display range only: yesterday's close is central, with four ticks on either side. */
export function intradayPriceScale(previous:number|undefined,prices:number[]){
 const base=positive(previous),values=prices.filter(n=>Number.isFinite(n)&&n>0);if(!base||!values.length)return {};
 const deviation=values.reduce((max,n)=>Math.max(max,Math.abs(n-base)),0);
 // Expand to cents, rather than a coarse "nice" price tick. A flat/early session
 // retains at least 1% and four cents per side to keep 2-decimal labels distinct.
 const radius=Math.ceil((Math.max(deviation,base*.01,.04)-1e-9)*100)/100;
 // IPO/no-limit moves can exceed 100%; never show negative prices or clip them.
 const min=Number(Math.max(.01,base-radius).toFixed(8)),max=Number((base+radius).toFixed(8));
 return {min,max,interval:Number(((max-min)/8).toFixed(8))};
}
export function priceLimitState(value:number,limits:PriceLimits){return limits.up!==undefined&&samePrice(value,limits.up)?'涨停':limits.down!==undefined&&samePrice(value,limits.down)?'跌停':null;}
export function pricePercent(value:number,previous:number){const p=(value/previous-1)*100;return `${p>0?'+':''}${(Math.abs(p)<.005?0:p).toFixed(2)}%`;}
