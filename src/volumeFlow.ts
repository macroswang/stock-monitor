import type {Bar,VolumeFlow} from './models';
export function splitMinuteVolume(bar:Bar,flow?:VolumeFlow){
 const raw=flow?.minutes.find(row=>row.time===bar.time);
 const total=Number.isSafeInteger(bar.volume)&&bar.volume>=0?bar.volume:0;
 const fallback={total,buy:0,sell:0,neutral:0,unknown:total,rawBuy:0,rawSell:0,sourceTotal:0,difference:0,verified:false,approximate:false};
 if(flow?.total_only||!bar.complete||!raw?.verified||raw.total!==total||![raw.buy,raw.sell,raw.neutral,raw.unknown].every(n=>Number.isSafeInteger(n)&&n>=0))return fallback;
 const sourceTotal=raw.source_total??raw.total,difference=sourceTotal-total,values=[raw.buy,raw.sell,raw.neutral,raw.unknown];
 if(!Number.isSafeInteger(sourceTotal)||sourceTotal<0||values.reduce((a,b)=>a+b,0)!==sourceTotal)return fallback;
 const approximate=difference!==0;
 if(approximate&&(!raw.approximate||total<=0||sourceTotal<=0||Math.abs(difference)>100||Math.abs(difference)/total>.01))return fallback;
 // Visual apportionment only: keep total bar height unchanged; tooltip retains raw packet counts.
 const scaled=values.map(value=>sourceTotal?value*total/sourceTotal:0),draw=scaled.map(Math.floor);
 const remaining=total-draw.reduce((a,b)=>a+b,0),order=[0,1,2,3].sort((a,b)=>(scaled[b]-draw[b])-(scaled[a]-draw[a]));
 for(let i=0;i<remaining;i++)draw[order[i%4]]++;
 return {total,buy:draw[0],sell:draw[1],neutral:draw[2],unknown:draw[3],rawBuy:raw.buy,rawSell:raw.sell,sourceTotal,difference,verified:true,approximate};
}
