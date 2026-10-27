import type {Daily} from './models';

export type DailyPatternKind='rising-flag'|'falling-flag'|'triangle'|'spring';
export type PatternPoint={index:number;date:string;price:number};
export type PatternLine={role:'upper'|'lower'|'pole'|'support'|'neckline'|'outline';from:PatternPoint;to:PatternPoint};
export type DailyPattern={
 key:string;kind:DailyPatternKind;name:string;start:PatternPoint;end:PatternPoint;
 detectedOn:string;detectedIndex:number;anchors:PatternPoint[];lines:PatternLine[];
 status:'forming'|'up'|'down'|'reclaimed'|'neckline'|'failed'|'expired';
 breakoutOn?:string;failedOn?:string;failureReason?:'support'|'low';necklineOn?:string;volumeNote:string;
};
type Candle={index:number;date:string;open:number;close:number;high:number;low:number;volume:number;atr:number;tr:number};
type Pivot=PatternPoint&{kind:'high'|'low';knownAt:number};
type Fit={slope:number;intercept:number};
type Channel={pattern:DailyPattern;upper:Fit;lower:Fit;first:number;limit:number;active:boolean};
type PendingSpring={support:Pivot;breach:Candle;neck:PatternPoint;expires:number};
type Spring={pattern:DailyPattern;support:number;low:number;neck:PatternPoint;limit:number;active:boolean};

const names:Record<DailyPatternKind,string>={'rising-flag':'上飘旗','falling-flag':'下飘旗',triangle:'收敛三角形',spring:'破底翻'};
const at=(line:Fit,i:number)=>line.slope*i+line.intercept;
const point=(b:Candle,price:number):PatternPoint=>({index:b.index,date:b.date,price});
const line=(role:PatternLine['role'],from:PatternPoint,to:PatternPoint):PatternLine=>({role,from,to});
const tolerance=(atr:number)=>Math.max(.010001,atr*.12);

export function dailyPatternStatus(p:DailyPattern){
 if(p.status==='forming')return '整理成形';
 if(p.status==='reclaimed')return '已收回前低';
 if(p.status==='neckline')return '已突破颈线';
 if(p.status==='failed')return '后续失效';
 if(p.status==='expired')return '整理超时';
 const reverse=p.kind==='rising-flag'&&p.status==='up'||p.kind==='falling-flag'&&p.status==='down';
 return `${reverse?'反向':''}${p.status==='up'?'向上突破':'向下突破'}`;
}

/** Least-squares boundary through confirmed swing highs/lows, shifted to enclose them. */
function boundary(points:Pivot[],side:'high'|'low',atr:number):Fit|null{
 const x=points.reduce((s,p)=>s+p.index,0)/points.length,y=points.reduce((s,p)=>s+p.price,0)/points.length;
 const variance=points.reduce((s,p)=>s+(p.index-x)**2,0);if(!variance)return null;
 const slope=points.reduce((s,p)=>s+(p.index-x)*(p.price-y),0)/variance;
 let intercept=y-slope*x;
 const residuals=points.map(p=>p.price-(slope*p.index+intercept));
 if(Math.max(...residuals)-Math.min(...residuals)>Math.max(.02,atr*.55))return null;
 intercept+=side==='high'?Math.max(...residuals):Math.min(...residuals);
 return {slope,intercept};
}

function volumeNote(bars:Candle[],start:number,end:number){
 const section=bars.filter(b=>b.index>=start&&b.index<=end),half=Math.floor(section.length/2);
 const a=section.slice(0,half),b=section.slice(half);
 if(!a.length||!b.length||a.some(x=>!Number.isFinite(x.volume))||b.some(x=>!Number.isFinite(x.volume)))return '成交量资料不足';
 const first=a.reduce((s,x)=>s+x.volume,0)/a.length,last=b.reduce((s,x)=>s+x.volume,0)/b.length;
 if(first<=0)return '成交量资料不足';
 return `整理后半段均量为前半段的${(last/first*100).toFixed(0)}%`;
}

function channelCandidate(pivots:Pivot[],bars:Candle[],b:Candle):Channel|null{
 if(pivots.length<4)return null;
 const first=pivots[0],last=pivots.at(-1)!,span=last.index-first.index;
 if(span<5||span>65||b.index-last.index>3)return null;
 const highs=pivots.filter(p=>p.kind==='high'),lows=pivots.filter(p=>p.kind==='low');
 if(highs.length<2||lows.length<2)return null;
 const upper=boundary(highs,'high',b.atr),lower=boundary(lows,'low',b.atr);
 if(!upper||!lower)return null;
 const startWidth=at(upper,first.index)-at(lower,first.index),endWidth=at(upper,last.index)-at(lower,last.index);
 if(Math.min(startWidth,endWidth)<Math.max(.03,b.atr*.55))return null;
 let kind:DailyPatternKind,pole:PatternLine|undefined;
 if(upper.slope<0&&lower.slope>0){
  if(span<10||endWidth/startWidth>.75||Math.abs(upper.slope)*span<b.atr*.25||lower.slope*span<b.atr*.25)return null;
  kind='triangle';
 }else{
  if(span>25||upper.slope*lower.slope<=0)return null;
  const travel=Math.abs((upper.slope+lower.slope)/2)*span;
  if(travel<b.atr*.4||Math.abs(endWidth/startWidth-1)>.3||Math.abs(upper.slope-lower.slope)/Math.max(Math.abs(upper.slope),Math.abs(lower.slope))>.45)return null;
  kind=upper.slope>0?'rising-flag':'falling-flag';
  if(first.kind!==(kind==='falling-flag'?'high':'low'))return null;
  const prior=bars.filter(x=>x.index>=first.index-12&&x.index<=first.index-3);
  if(!prior.length)return null;
  const base=prior.reduce((a,c)=>kind==='falling-flag'?(c.low<a.low?c:a):(c.high>a.high?c:a));
  const height=kind==='falling-flag'?first.price-base.low:base.high-first.price;
  const inside=bars.filter(x=>x.index>=first.index&&x.index<=last.index);
  const retrace=kind==='falling-flag'?first.price-Math.min(...inside.map(x=>x.low)):Math.max(...inside.map(x=>x.high))-first.price;
  if(height<Math.max(b.atr*3,startWidth*1.8,first.price*.04)||retrace/height>.65||travel/span>=height/(first.index-base.index))return null;
  pole=line('pole',point(base,kind==='falling-flag'?base.low:base.high),first);
 }
 const section=bars.filter(x=>x.index>=first.index&&x.index<=b.index);
 const eps=tolerance(b.atr);
 // All observed closes must remain in the boundary until the last confirmed swing.
 // A later break can be recognised now, but is never backdated before detection.
 if(section.some(x=>x.index<=last.index&&(x.high>at(upper,x.index)+b.atr*.4||x.low<at(lower,x.index)-b.atr*.4||x.close>at(upper,x.index)+eps||x.close<at(lower,x.index)-eps)))return null;
 const recent=section.filter(x=>x.index>last.index),breaks=recent.filter(x=>x.close>at(upper,x.index)+eps||x.close<at(lower,x.index)-eps);
 if(breaks.some(x=>x.index<b.index-1))return null;
 const direction=b.close>at(upper,b.index)+eps?'up':b.close<at(lower,b.index)-eps?'down':null;
 if(breaks.length&&!direction||at(upper,b.index)-at(lower,b.index)<b.atr*.2)return null;
 const end=point(b,b.close),start:PatternPoint={index:first.index,date:first.date,price:first.price};
 const p:DailyPattern={key:`${kind}|${first.date}|${last.date}`,kind,name:names[kind],start,end,detectedOn:b.date,detectedIndex:b.index,
  status:direction||'forming',anchors:pivots.map(({index,date,price})=>({index,date,price})),
  lines:[...(pole?[pole]:[]),line('upper',{...start,price:at(upper,first.index)},point(b,at(upper,b.index))),line('lower',{...start,price:at(lower,first.index)},point(b,at(lower,b.index)))],
  volumeNote:volumeNote(bars,first.index,last.index),...(direction?{breakoutOn:b.date}:{})};
 return {pattern:p,upper,lower,first:first.index,limit:first.index+(kind==='triangle'?80:32),active:!direction};
}

function confirmedPivot(bars:Candle[]):Pivot|null{
 if(bars.length<5)return null;
 const window=bars.slice(-5),b=window[2],left=window.slice(0,2),right=window.slice(3);
 const high=left.every(x=>b.high>x.high)&&right.every(x=>b.high>=x.high);
 const low=left.every(x=>b.low<x.low)&&right.every(x=>b.low<=x.low);
 // An outside bar can be both; OHLC cannot establish the intraday order of its extremes.
 if(high===low)return null;
 return {...point(b,high?b.high:b.low),kind:high?'high':'low',knownAt:window[4].index};
}

/**
 * Closed daily OHLC only. Walks forward; a swing needs two later closed candles.
 * Geometry is frozen when first identified. Later candles append status, never
 * move the original anchors/detection date or invent a forecast price path.
 */
export function dailyPatterns(days:Daily[]):DailyPattern[]{
 const results:DailyPattern[]=[],channels:Channel[]=[],springs:Spring[]=[];
 let bars:Candle[]=[],pivots:Pivot[]=[],allLows:Pivot[]=[],pending:PendingSpring[]=[];
 const dates=new Set<string>(),duplicates=new Set<string>();
 for(const d of days){if(dates.has(d.date))duplicates.add(d.date);dates.add(d.date);}
 const reset=()=>{bars=[];pivots=[];allLows=[];pending=[];channels.forEach(c=>{c.active=false;});springs.forEach(s=>{s.active=false;});};
 for(let i=0;i<days.length;i++){
  const d=days[i],o=+d.open,c=+d.close,h=+d.high,l=+d.low;
  if(d.provisional||duplicates.has(d.date)||!/^\d{4}-\d{2}-\d{2}$/.test(d.date)||i>0&&d.date<=days[i-1].date||![o,c,h,l].every(x=>Number.isFinite(x)&&x>0)||h<Math.max(o,c,l)||l>Math.min(o,c,h)){
   reset();continue;
  }
  const previous=bars.at(-1),tr=Math.max(h-l,previous?Math.abs(h-previous.close):0,previous?Math.abs(l-previous.close):0);
  const ranges=bars.slice(-13).map(b=>b.tr);
  const atr=Math.max(.01,([...ranges,tr].reduce((s,x)=>s+x,0))/(ranges.length+1));
  const b:Candle={index:i,date:d.date,open:o,close:c,high:h,low:l,volume:+d.volume,atr,tr};bars.push(b);
  const eps=tolerance(atr);
  for(const ch of channels.filter(x=>x.active)){
   const p=ch.pattern;
   if(i>ch.limit||at(ch.upper,i)<=at(ch.lower,i)){p.status='expired';ch.active=false;continue;}
   p.end=point(b,c);for(const edge of p.lines){if(edge.role==='upper'||edge.role==='lower')edge.to=point(b,at(edge.role==='upper'?ch.upper:ch.lower,i));}
   const side=c>at(ch.upper,i)+eps?'up':c<at(ch.lower,i)-eps?'down':null;
   if(side){p.status=side;p.breakoutOn=d.date;ch.active=false;}
  }
  for(const s of springs.filter(x=>x.active)){
   const p=s.pattern;
   if(i>s.limit){s.active=false;continue;}
   if(l<s.low-eps||c<s.support-eps){p.status='failed';p.failedOn=d.date;p.failureReason=l<s.low-eps?'low':'support';s.active=false;}
   else if(c>s.neck.price+eps){p.status='neckline';p.necklineOn=d.date;s.active=false;}
   p.end=point(b,c);for(const edge of p.lines){if(edge.role==='support'||edge.role==='neckline')edge.to=point(b,edge.from.price);}
  }
  pending=pending.filter(x=>i<=x.expires);
  // Support has to have been observable before today's breach, not a future low.
  const supports=allLows.filter(p=>p.knownAt<i&&i-p.index>=5&&i-p.index<=60&&l<p.price-eps&&
   bars.filter(x=>x.index>p.index&&x.index<i).every(x=>x.close>=p.price-eps));
  for(const support of supports){
   if(pending.some(p=>p.support.date===support.date))continue;
   const between=bars.filter(x=>x.index>support.index&&x.index<i);if(!between.length)continue;
   const neck=between.reduce((a,x)=>x.high>a.high?x:a);
   pending.push({support,breach:b,neck:point(neck,neck.high),expires:i+3});
  }
  for(const p of pending){if(l<p.breach.low)p.breach=b;}
  const recovered=pending.filter(p=>c>p.support.price+eps).sort((a,z)=>a.support.price-z.support.price);
  // Multiple nearby broken levels on the same bar describe one reversal; retain the lowest reclaimed support.
  if(recovered.length){
   const s=recovered[0],support=s.support,breach=point(s.breach,s.breach.low),end=point(b,c);
   if(!results.some(p=>p.kind==='spring'&&p.start.date===support.date&&i-p.detectedIndex<5)){
    const p:DailyPattern={key:`spring|${support.date}|${d.date}`,kind:'spring',name:names.spring,start:{index:support.index,date:support.date,price:support.price},end,
     detectedOn:d.date,detectedIndex:i,status:c>s.neck.price+eps?'neckline':'reclaimed',...(c>s.neck.price+eps?{necklineOn:d.date}:{}),
     anchors:[support,s.neck,breach,end].map(({index,date,price})=>({index,date,price})),
     lines:[line('support',support,point(b,support.price)),line('neckline',s.neck,point(b,s.neck.price)),line('outline',support,s.neck),line('outline',s.neck,breach),line('outline',breach,end)],
     volumeNote:'收回前低与突破颈线分别记录'};
    results.push(p);springs.push({pattern:p,support:support.price,low:breach.price,neck:s.neck,limit:i+20,active:p.status!=='neckline'});
   }
   pending=pending.filter(p=>!recovered.includes(p));
  }
  const pivot=confirmedPivot(bars);
  if(pivot){
   if(pivot.kind==='low')allLows.push(pivot);
   const last=pivots.at(-1);
   if(last?.kind===pivot.kind){if(pivot.kind==='high'?pivot.price>last.price:pivot.price<last.price)pivots[pivots.length-1]=pivot;}
   else pivots.push(pivot);
  }
  if(!pivot||pivots.length<4)continue;
  for(const count of [6,5,4]){
   if(pivots.length<count)continue;
   const candidate=channelCandidate(pivots.slice(-count),bars,b);if(!candidate)continue;
   const p=candidate.pattern;
   const duplicate=channels.some(x=>{
    if(x.pattern.kind!==p.kind)return false;
    const common=p.anchors.filter(a=>x.pattern.anchors.some(old=>old.date===a.date)).length;
    const overlap=Math.min(x.pattern.end.index,p.end.index)-Math.max(x.first,p.start.index);
    return common>=2||overlap>0&&overlap/Math.min(x.pattern.end.index-x.first,p.end.index-p.start.index)>.6;
   });
   if(!duplicate){results.push(p);channels.push(candidate);}
   break;
  }
 }
 return results.sort((a,b)=>a.detectedIndex-b.detectedIndex||a.key.localeCompare(b.key));
}
