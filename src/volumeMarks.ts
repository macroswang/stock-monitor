import type {Bar} from './models';

const labels=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:116},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

// A completed running maximum is visible immediately, without confirmation bars.
export function topVolumeMarks(bars:Bar[]){
 let maximum=0,index=0;
 const marks:{coord:[string,number];value:string}[]=[];
 for(const bar of bars){
  if(!bar.complete||!labels.includes(bar.time))continue;
  if(bar.time!==labels[index])break;
  if(!Number.isFinite(bar.volume)||bar.volume<0||!Number.isFinite(+bar.close)||+bar.close<=0)break;
  index++;
  if(bar.volume>0&&bar.volume>=maximum)marks.push({coord:[bar.time,+bar.close],value:'触发'});
  maximum=Math.max(maximum,bar.volume);
 }
 return marks;
}
