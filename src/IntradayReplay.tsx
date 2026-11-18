import {useEffect,useState,type ReactNode} from 'react';
import Chart from './Chart';
import {benchmarkForStock,minuteSlots} from './minuteMacd';
import {minuteTimeCutoff} from './pricePresentation';
import type {Bar,Event,IndexMinute,MarketData} from './models';
import type {Request} from './poolTableModel';

type MinuteCacheRow={day:string;data:{date?:string;trading_date?:string;symbol?:string;cached_at?:string;previous_close?:string;bars?:Bar[]}};
type ReplayData={bars:Bar[];index:IndexMinute|null;previousClose:number};
const session=new Set(minuteSlots);
const end=minuteSlots.length-1;

function historicalMinutes<T extends {time:string;close:string}>(bars:T[],day:string,cachedAt?:string){
 const cutoff=minuteTimeCutoff(day,Date.now(),cachedAt);
 if(cutoff===null)return [];
 return bars.filter(bar=>session.has(bar.time)&&Number.isFinite(Number(bar.close))&&Number(bar.close)>0
  &&Date.parse(`${day}T${bar.time}:00+08:00`)<=cutoff);
}

export default function IntradayReplay({request,code,name,day,active,events=[],stockSwitcher,onExit}:{request:Request;code:string;name:string;day:string;active:boolean;events?:Event[];stockSwitcher?:ReactNode;onExit:()=>void}){
 const [data,setData]=useState<ReplayData>(),[error,setError]=useState('');
 const [cursor,setCursor]=useState(0),[playing,setPlaying]=useState(true);
 const benchmark=benchmarkForStock(code);
 const time=minuteSlots[cursor]!;
 const finished=cursor===end;
 useEffect(()=>{
  let mounted=true;
  const historical=request<MinuteCacheRow[]>('chart',{code,day,kind:'minute'});
  const market=benchmark?request<MarketData>('index_minute',{code:benchmark.code,day}).catch(()=>null):Promise.resolve(null);
  Promise.all([historical,market]).then(([rows,result])=>{
   if(!mounted)return;
   const cached=rows.find(row=>row.day===day)?.data;
   const matches=cached&&[cached.date,cached.trading_date].every(date=>!date||date===day)
    &&(!cached.symbol||[code,code.slice(2)].includes(String(cached.symbol).toLowerCase()));
   const bars=matches?historicalMinutes(cached.bars||[],day,cached.cached_at).filter(bar=>bar.time==='09:30'||bar.complete===true):[];
   if(!bars.some(bar=>bar.time!=='09:30')){setError('该日暂无可用的个股分时数据，无法回放。');return;}
   const index=result?.minute;
   const indexBars=index&&index.code===benchmark?.code&&index.date===day?historicalMinutes(index.bars,day,index.cached_at):[];
   setData({bars,previousClose:Number(cached?.previous_close),index:index&&indexBars.length?{...index,bars:indexBars}:null});
  }).catch(()=>{if(mounted)setError('读取该日个股分时失败，无法回放。');});
  return()=>{mounted=false;};
 },[request,code,day,benchmark?.code]);

 useEffect(()=>{
  if(!active||!data||!playing||finished)return;
  const timer=window.setTimeout(()=>setCursor(i=>Math.min(end,i+1)),1000);
  return()=>window.clearTimeout(timer);
 },[active,data,playing,cursor,finished]);

 const index=data?.index;
 return <>
  <div className="intraday-replay-controls" role="group" aria-label="历史回放控制">
   <strong>{day} · 历史回放</strong><time aria-label="回放时刻">{time}</time>
   {data&&<>
    <button type="button" disabled={finished} onClick={()=>setPlaying(value=>!value)}>{playing&&!finished?'暂停回放':'继续回放'}</button>
    <button type="button" disabled={finished} onClick={()=>{setPlaying(false);setCursor(i=>Math.min(end,i+1));}}>单步前进</button>
    <button type="button" onClick={()=>{setCursor(0);setPlaying(true);}}>从头播放</button>
   </>}
   <button type="button" title="退出后查看所选日期的完整分时图" onClick={onExit}>退出回放</button>
   {finished&&<span role="status">回放结束</span>}
   {data&&!index&&benchmark&&<span role="status">{benchmark.name}分时缺失，个股继续回放</span>}
  </div>
  {data?<Chart view="minute" fixedTurningMode="zhangle" stockCode={code} stockName={name} selectedDay={day} replayTime={time} stockSwitcher={stockSwitcher}
    events={events.filter(event=>event.symbol===code.slice(2)&&event.trading_date===day&&event.mode!=='test'
      &&event.confirmation_label?.slice(0,5)<=time&&event.event_label?.slice(0,5)<=time)}
    previousClose={data.previousClose} minute={data.bars.filter(bar=>bar.time<=time)}
    macdBenchmark={index?{...index,bars:index.bars.filter(bar=>bar.time<=time)}:null}/>
   :<div className="history-empty" role="status">{error||'正在读取历史分时数据…'}</div>}
 </>;
}
