import type {Daily} from './models';

export const isCandleView=(view:string)=>view==='daily'||view==='weekly';
export type Candle=Daily&{startDate?:string;weekStart?:string};
export function weekStart(date:string){
 const d=new Date(date+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);return d.toISOString().slice(0,10);
}
/** Calendar weeks, observed trading days only. No synthetic candles or future prices. */
export function weeklyBars(rows:ReadonlyArray<Daily>):Candle[]{
 const groups=new Map<string,Candle>();
 for(const b of [...new Map(rows.map(b=>[b.date,b])).values()].sort((a,b)=>a.date.localeCompare(b.date))){
  const key=weekStart(b.date),old=groups.get(key);
  if(!old){groups.set(key,{...b,startDate:b.date,weekStart:key});continue;}
  groups.set(key,{...b,open:old.open,high:String(Math.max(+old.high,+b.high)),low:String(Math.min(+old.low,+b.low)),
   volume:String(+old.volume + +b.volume),provisional:old.provisional||b.provisional,startDate:old.startDate,weekStart:key});
 }
 return [...groups.values()];
}
export function candleDate(rows:ReadonlyArray<Candle>,date:string|undefined,weekly:boolean){
 if(!date)return undefined;
 return weekly?rows.find(b=>b.weekStart===weekStart(date))?.date:date;
}
export const MA_COLORS=['#dce5f2','#efc25b','#c798ef','#65c9a5','#6ea9f7','#ef9a75','#e28db6','#90b0b8'];
export type MovingAverages={periods:number[];enabled:number[];visible:boolean};
export const defaultMovingAverages:MovingAverages={periods:[5,10,20,30],enabled:[5,10,20,30],visible:true};
export function parsePeriods(value:string){
 const fields=value.trim().split(/[,，、;；\s]+/);
 if(!value.trim()||fields.length>8||fields.some(s=>!/^\d+$/.test(s)||Number(s)<1||Number(s)>250))return null;
 return [...new Set(fields.map(Number))];
}
export function readMovingAverages():MovingAverages{
 try{const p=JSON.parse(localStorage.getItem('stock-monitor-moving-averages-v1')||'null');
  const periods=p&&Array.isArray(p.periods)?parsePeriods(p.periods.join(',')):null;
  if(periods&&Array.isArray(p.enabled))return {periods,enabled:periods.filter(n=>p.enabled.includes(n)),visible:p.visible!==false};
 }catch{}
 return defaultMovingAverages;
}
/** SMA uses all loaded history, including candles preceding the visible window. */
export function movingAverage(rows:ReadonlyArray<Daily>,period:number):(number|null)[]{
 let sum=0;return rows.map((b,i)=>{sum+=+b.close;if(i>=period)sum-=+rows[i-period].close;return i+1<period?null:Number((sum/period).toFixed(4));});
}
/**
 * 均线必须使用可见窗口之前的完整历史预热；否则旧行情稍后补入时，
 * 同一根K线的均线值会从空值变成数值，或随加载进度漂移。
 */
export function candleHistoryNeed(visibleCount:number,ma:MovingAverages){
 const visible=Math.max(1,Math.floor(visibleCount)||1);
 const enabled=ma.visible?ma.periods.filter(period=>ma.enabled.includes(period)):[];
 return visible+(enabled.length?Math.max(...enabled)-1:0);
}
