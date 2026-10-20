import type {Daily} from './models';
export type DailyGap={date:string;direction:'up'|'down';originalLow:number;originalHigh:number;low:number;high:number;filledOn?:string;provisional:boolean};
export function dailyGaps(days:Daily[]){
 const gaps:DailyGap[]=[];
 const valid=(b:Daily)=>Number.isFinite(+b.low)&&Number.isFinite(+b.high)&&+b.low>0&&+b.high>=+b.low;
 for(let i=0;i<days.length;i++){
  const b=days[i];if(!valid(b))continue;
  for(const gap of gaps){
   if(gap.filledOn)continue;
   if(gap.direction==='up')gap.high=Math.min(gap.high,+b.low);
   else gap.low=Math.max(gap.low,+b.high);
   if(gap.low>=gap.high)gap.filledOn=b.date;
  }
  const previous=days[i-1];if(!previous||!valid(previous))continue;
  const up=+b.low>+previous.high,down=+b.high<+previous.low;
  if(!up&&!down)continue;
  const low=up?+previous.high:+b.high,high=up?+b.low:+previous.low;
  gaps.push({date:b.date,direction:up?'up':'down',originalLow:low,originalHigh:high,low,high,provisional:!!b.provisional});
 }
 return gaps;
}
