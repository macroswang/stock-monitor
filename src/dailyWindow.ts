export const DAILY_WINDOW=90;
export const DAILY_BATCH_DAYS=365;

/** Preserve the viewed dates as history is prepended; grow short initial data to 90 candles. */
export function dailyViewport(dates:string[],previous:string[],selected:string|undefined,lastDate:string,size=DAILY_WINDOW){
 const count=Math.min(size,dates.length);if(!count)return {lo:0,hi:0};
 let lo=previous.length?dates.indexOf(previous[0]):-1;
 let hi=previous.length?dates.indexOf(previous[1]):-1;
 if(hi<0)hi=dates.length-1;
 if(lo<0||hi<lo||hi-lo+1!==count){lo=Math.max(0,hi-count+1);hi=Math.min(dates.length-1,lo+count-1);}
 if(lastDate&&previous[1]===lastDate&&dates.at(-1)!==lastDate){hi=dates.length-1;lo=Math.max(0,hi-count+1);}
 const index=dates.indexOf(selected||'');
 if(index>=0&&index<lo){lo=index;hi=Math.min(dates.length-1,lo+count-1);}
 else if(index>hi){hi=index;lo=Math.max(0,hi-count+1);}
 return {lo,hi};
}

export const CANDLE_ZOOM_STEPS=[10,15,20,30,45,60,90,120,180,250,400,600];
export function zoomCandleWindow(length:number,lo:number,hi:number,direction:number,anchor=hi){
 const count=hi-lo+1,desired=direction>0?CANDLE_ZOOM_STEPS.find(n=>n>count)??600:[...CANDLE_ZOOM_STEPS].reverse().find(n=>n<count)??10;
 const size=Math.min(length,desired),focus=Math.max(lo,Math.min(hi,anchor));
 const fraction=count>1?(focus-lo)/(count-1):1;
 const start=Math.max(0,Math.min(length-size,Math.round(focus-fraction*(size-1))));
 return {lo:start,hi:start+size-1,desired};
}
