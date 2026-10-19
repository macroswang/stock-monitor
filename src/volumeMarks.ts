import type {Bar,Event} from './models';

const labels=[...Array.from({length:120},(_,i)=>571+i),...Array.from({length:116},(_,i)=>781+i)]
 .map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

// Confirmed events own signal timing (including limit-up reopening). Anchor each
// marker to its original candidate instead of the later confirmation minute.
export function topVolumeMarks(bars:Bar[],events:Event[]=[]){
 const byTime=new Map(bars.map(b=>[b.time,b]));
 const seen=new Set<string>();
 const marks:{coord:[string,number];value:string}[]=[];
 for(const event of events){
  const time=event.candidate_time,index=labels.indexOf(time),bar=byTime.get(time);
  const confirmation=event.confirmation_label?.slice(0,5),trigger=event.event_label?.slice(0,5);
  if(event.mode==='test'||seen.has(time)||index<0||index+2>=labels.length||!bar?.complete)continue;
  if(!byTime.get(labels[index+1])?.complete||!byTime.get(labels[index+2])?.complete)continue;
  if(!confirmation||confirmation<labels[index+2]||!trigger||trigger<confirmation||!bars.some(b=>b.time>=trigger))continue;
  if(!Number.isFinite(+bar.close)||+bar.close<=0)continue;
  seen.add(time);marks.push({coord:[time,+bar.close],value:'触发'});
 }
 return marks;
}
