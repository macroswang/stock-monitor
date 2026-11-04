/** Display-only 1-minute MACD. No trading, signal or notification dependency. */
export type MacdPoint={dif:number;dea:number;histogram:number};
export const minuteSlots=[...Array.from({length:121},(_,i)=>570+i),...Array.from({length:120},(_,i)=>781+i)].map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);

export function benchmarkForStock(code:string){
 const value=code.trim().toLowerCase();
 if(/^(sh)?6\d{5}$/.test(value))return {code:'sh000001',name:'上证指数'};
 if(/^(sz)?30\d{4}$/.test(value))return {code:'sz399006',name:'创业板指'};
 if(/^(sz)?[03]\d{5}$/.test(value))return {code:'sz399001',name:'深证成指'};
 return null;
}

/** EMA12-EMA26, DEA=EMA9(DIF), histogram=2*(DIF-DEA).
 * Formula: https://help335.dzh.com.cn/help123/index.php?_url=/index/single&post_id=11504&tree_path=0-10065-11500
 * Both series start at the first observed price of the selected day. Lunch is
 * continuous; missing/duplicate/invalid minutes break the series and reset EMA.
 * Unobserved future minutes stay null. Zoom never changes the EMA input window.
 */
export function minuteMacd(bars:ReadonlyArray<{time:string;close:string|number}>):Array<MacdPoint|null>{
 const values=new Map<string,number>();
 for(const bar of bars){const n=Number(bar.close);values.set(bar.time,values.has(bar.time)?NaN:n);}
 let fast:number|null=null,slow=0,dea=0;
 return minuteSlots.map(time=>{
  const price=values.get(time);
  if(price===undefined||!Number.isFinite(price)||price<=0){fast=null;slow=0;dea=0;return null;}
  if(fast===null){fast=price;slow=price;dea=0;}
  else{fast+=(price-fast)*2/13;slow+=(price-slow)*2/27;}
  const dif=fast-slow;dea+=(dif-dea)*2/10;
  return {dif,dea,histogram:2*(dif-dea)};
 });
}

export function macdNumber(value:number){
 if(!Number.isFinite(value))return '—';
 if(Math.abs(value)<1e-10)return '0.0000';
 return value.toFixed(Math.abs(value)>=1?2:Math.abs(value)<.0001?6:4);
}
export function macdRange(points:Array<MacdPoint|null>){
 let min=0,max=0;
 for(const point of points)if(point)for(const value of [point.dif,point.dea,point.histogram])if(Number.isFinite(value)){min=Math.min(min,value);max=Math.max(max,value);}
 if(min===max)return {min:-.001,max:.001};
 const padding=(max-min)*.08;
 return {min:min-padding,max:max+padding};
}
