import type {DailyPattern,PatternLine} from './dailyPatterns';

type Region={left:number;right:number;low:number;high:number};
type Candidate={pattern:DailyPattern;confirmation:number;touches:number;fit:number;region:Region};
const valueAt=(line:PatternLine,index:number)=>line.from.price+(line.to.price-line.from.price)*(index-line.from.index)/Math.max(1,line.to.index-line.from.index);

function candidate(pattern:DailyPattern):Candidate|null{
 const p=pattern;
 if(p.anchors.length<4||p.end.index<p.start.index||p.anchors.some(a=>!Number.isFinite(a.price)||a.price<=0)||p.lines.some(l=>![l.from.price,l.to.price,l.from.index,l.to.index].every(Number.isFinite)))return null;
 let touches:number,fit:number,prices:number[];
 if(p.kind==='spring'){
  const [support,neck,breach,reclaim]=p.anchors;
  if(!support||!neck||!breach||!reclaim||breach.price>=support.price||reclaim.price<=support.price||breach.index<support.index||reclaim.index<breach.index)return null;
  // The reclaim is a confirmation event, not an independent swing anchor.
  touches=3;fit=1;prices=[support.price,breach.price,reclaim.price];
 }else{
  const upper=p.lines.find(l=>l.role==='upper'),lower=p.lines.find(l=>l.role==='lower');
  if(!upper||!lower)return null;
  const up=upper.to.price-upper.from.price,down=lower.to.price-lower.from.price;
  if(p.kind==='triangle'?(up>=0||down<=0):p.kind==='rising-flag'?(up<=0||down<=0):(up>=0||down>=0))return null;
  if(p.kind!=='triangle'){
   const pole=p.lines.find(l=>l.role==='pole');
   if(!pole||pole.from.index>=pole.to.index||(p.kind==='falling-flag'?pole.to.price<=pole.from.price:pole.to.price>=pole.from.price))return null;
  }
  let highTouches=0,lowTouches=0,error=0;
  for(const a of p.anchors){
   const high=valueAt(upper,a.index),low=valueAt(lower,a.index),width=high-low;if(width<=0)return null;
   const dh=Math.abs(a.price-high),dl=Math.abs(a.price-low);
   if(dh<=dl)highTouches++;else lowTouches++;
   error+=Math.min(dh,dl)/width;
  }
  if(highTouches<2||lowTouches<2)return null;
  touches=new Set(p.anchors.map(a=>a.index)).size;fit=Math.round(Math.max(0,1-error/p.anchors.length)*1e6)/1e6;
  prices=[upper.from.price,upper.to.price,lower.from.price,lower.to.price];
 }
 const confirmed=p.status==='neckline'||p.kind==='triangle'&&(p.status==='up'||p.status==='down')||p.kind==='falling-flag'&&p.status==='up'||p.kind==='rising-flag'&&p.status==='down';
 const confirmation=confirmed?3:p.status==='reclaimed'?2:p.status==='forming'?1:0;
 const low=Math.min(...prices),high=Math.max(...prices),padding=Math.max(.01,(low+high)/2*.005);
 return {pattern:p,confirmation,touches,fit,region:{left:p.start.index,right:p.end.index,low:low-padding,high:high+padding}};
}

function overlaps(a:Region,b:Region){
 const time=Math.min(a.right,b.right)-Math.max(a.left,b.left)+1;
 const price=Math.min(a.high,b.high)-Math.max(a.low,b.low);
 return time>0&&price>0&&time/Math.min(a.right-a.left+1,b.right-b.left+1)>=.5&&price/Math.min(a.high-a.low,b.high-b.low)>=.5;
}

/**
 * Resolve competing classifications of the same price/time region only.
 * Complete confirmed structures win, followed by independent swing support,
 * boundary fit, then recency. This is a reproducible classification order,
 * not a probability. Separate locations have no global display quota.
 */
export function selectDailyPatterns(patterns:DailyPattern[]):DailyPattern[]{
 const ranked=patterns.map(candidate).filter((c):c is Candidate=>c!==null).sort((a,b)=>
  b.confirmation-a.confirmation||b.touches-a.touches||b.fit-a.fit||b.pattern.detectedIndex-a.pattern.detectedIndex||b.pattern.start.index-a.pattern.start.index||a.pattern.key.localeCompare(b.pattern.key));
 const selected:Candidate[]=[];
 for(const c of ranked){
  if(selected.some(s=>s.pattern.key===c.pattern.key||overlaps(s.region,c.region)))continue;
  selected.push(c);
 }
 return selected.map(c=>c.pattern).sort((a,b)=>b.detectedIndex-a.detectedIndex||b.start.index-a.start.index||a.key.localeCompare(b.key));
}
