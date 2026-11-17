import {reachedPriceRange,tradingDayTimestamp,type IntradayRangeReference} from './pricePresentation';

/** Display metadata only. Quote and minute-cache snapshots arrive separately;
 * a newer quote must not evict extrema that were already safely observed. */
export class IntradayRangeReferenceCache {
 private scope='';
 private cutoff:number|null=null;
 private observed:IntradayRangeReference|undefined;
 resolve(quote:IntradayRangeReference|undefined,cached:IntradayRangeReference|undefined,code:string,day:string,previousClose:number,cutoff:number|null,now=Date.now()){
  const scope=[code,day,previousClose].join('|');
  if(scope!==this.scope||cutoff===null||this.cutoff!==null&&cutoff<this.cutoff)this.observed=undefined;
  this.scope=scope;this.cutoff=cutoff;
  if(cutoff===null)return;
  const usable=(r:IntradayRangeReference|undefined)=>reachedPriceRange(r,code,day,previousClose,cutoff).length>0;
  if(usable(quote)){this.observed={...quote!};return this.observed;}
  const stamp=quote?tradingDayTimestamp(quote.timestamp,day):null;
  const pending=stamp!==null&&stamp>cutoff&&stamp<=now&&reachedPriceRange(quote,code,day,previousClose,stamp).length>0;
  // Keep an earlier observation only while an otherwise valid quote waits for
  // its minute capture. Missing/corrupt references and time rewinds clear it.
  const earlier=pending&&usable(this.observed)?this.observed:undefined;
  const cache=usable(cached)?cached:undefined;
  if(!earlier){this.observed=cache?{...cache}:undefined;return this.observed;}
  if(!cache)return earlier;
  const newest=[earlier,cache].sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp));
  const field=(key:'high'|'low')=>newest.map(r=>r[key]).find(n=>n!==undefined&&Number.isFinite(n)&&n>0);
  const combined={...newest[0],high:field('high'),low:field('low')};
  this.observed=usable(combined)?combined:cache;
  return this.observed;
 }
}
