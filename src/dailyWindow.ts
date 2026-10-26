export const DAILY_WINDOW=90;
export const DAILY_BATCH_DAYS=365;

/** Preserve the viewed dates as history is prepended; grow short initial data to 90 candles. */
export function dailyViewport(dates:string[],previous:string[],selected:string|undefined,lastDate:string){
 const count=Math.min(DAILY_WINDOW,dates.length);if(!count)return {lo:0,hi:0};
 let lo=previous.length?dates.indexOf(previous[0]):-1;
 let hi=previous.length?dates.indexOf(previous[1]):-1;
 if(hi<0)hi=dates.length-1;
 if(lo<0||hi<lo||hi-lo+1<count){lo=Math.max(0,hi-count+1);hi=Math.min(dates.length-1,lo+count-1);}
 if(lastDate&&previous[1]===lastDate&&dates.at(-1)!==lastDate){hi=dates.length-1;lo=Math.max(0,hi-count+1);}
 const index=dates.indexOf(selected||'');
 if(index>=0&&index<lo){lo=index;hi=Math.min(dates.length-1,lo+count-1);}
 else if(index>hi){hi=index;lo=Math.max(0,hi-count+1);}
 return {lo,hi};
}
