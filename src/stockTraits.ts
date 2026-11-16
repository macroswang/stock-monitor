import type {Daily} from './models';
import {exchangeCalendar} from './exchangeCalendar';

export type StockTraits={amplitude:number;change:number;up:number;volumeRatio:number|null;samples:number};
const local=(stamp:number)=>new Date(stamp+8*3600000).toISOString();
export function stockTraits(daily:Daily[],asOf:string,now=Date.now()):StockTraits|null{
  if(!Number.isFinite(now)||!/^\d{4}-\d{2}-\d{2}$/.test(asOf)||!Number.isFinite(Date.parse(asOf+'T00:00:00Z'))||new Date(asOf+'T00:00:00Z').toISOString().slice(0,10)!==asOf||exchangeCalendar.tradingDay(asOf)===null)return null;
  const clock=local(now),today=clock.slice(0,10);
  const unique=new Map<string,Daily>(),conflicts=new Set<string>();
  for(const bar of daily){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(bar.date)||exchangeCalendar.tradingDay(bar.date)!==true||bar.date>asOf||bar.date>today)continue;
    // Match the daily cache's closing settlement boundary. The wall clock passing
    // close does not turn an old intraday candle into a completed daily candle.
    if(bar.date===today&&(clock.slice(11,16)<'15:15'||bar.provisional||!bar.cached_at))continue;
    const prior=unique.get(bar.date);
    if(prior&&['open','close','high','low','volume','volume_unit','provisional'].some(k=>prior[k as keyof Daily]!==bar[k as keyof Daily]))conflicts.add(bar.date);
    unique.set(bar.date,bar);
  }
  const rows=[...unique.values()].sort((a,b)=>a.date.localeCompare(b.date)).slice(-21);
  if(rows.length<21)return null;
  for(const bar of rows){
    if(bar.provisional||conflicts.has(bar.date))return null;
    for(const key of ['cached_at','quote_time'] as const){
      const text=bar[key];if(!text)continue;
      const stamp=Date.parse(text);if(!/(?:Z|[+-]\d\d:\d\d)$/.test(text)||!Number.isFinite(stamp)||stamp>now)return null;
      const label=local(stamp);
      if(label.slice(0,10)<bar.date||key==='quote_time'&&label.slice(0,10)!==bar.date)return null;
      if(label.slice(0,10)===bar.date&&label.slice(11,16)<(key==='cached_at'?'15:15':'15:00'))return null;
    }
    const [open,close,high,low,volume]=[bar.open,bar.close,bar.high,bar.low,bar.volume].map(Number);
    if(![open,close,high,low,volume].every(Number.isFinite)||Math.min(open,close,high,low)<=0||volume<0||high<Math.max(open,close)||low>Math.min(open,close))return null;
  }
  const recent=rows.slice(1);
  const amplitude=recent.reduce((sum,row,i)=>sum+(+row.high-+row.low)/+rows[i].close*5,0);
  const change=(+rows[20].close/+rows[0].close-1)*100;
  const priorVolume=rows.slice(0,-1).reduce((sum,row)=>sum+ +row.volume/20,0);
  const provider=(row:Daily)=>typeof row.source==='string'?row.source:JSON.stringify(row.source??null);
  const sameUnit=rows.every(row=>row.volume_unit===rows[0].volume_unit)&&
    (rows[0].volume_unit!==undefined||rows.every(row=>provider(row)===provider(rows[0])));
  const ratio=sameUnit&&priorVolume>0?+rows[20].volume/priorVolume:null;
  if(!Number.isFinite(amplitude)||!Number.isFinite(change))return null;
  return {amplitude,change,up:recent.filter((row,i)=>+row.close>+rows[i].close).length,
    volumeRatio:ratio!==null&&Number.isFinite(ratio)?ratio:null,samples:20};
}
