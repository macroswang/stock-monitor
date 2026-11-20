import {useEffect,useMemo,useState} from 'react';
import Chart from './Chart';
import {ChartViewTabs} from './StockChartPanel';
import {indexes} from './MarketIndexStrip';
import {indexSparkline} from './indexSparkline';
import {indexLeadingPoints} from './indexLeading';
import {weeklyBars,candleDate,candleHistoryNeed,readMovingAverages} from './candleData';
import {DAILY_WINDOW,WEEKLY_WINDOW} from './dailyWindow';
import {readMacdParameters} from './minuteMacd';
import type {Daily,MarketData} from './models';
import type {Request} from './poolTableModel';

type History={code:string;start:string;end:string;daily:Daily[];cached_at:string};
export default function IndexChartPanel({request,code,market,view,onView,active,onBack,onMarket}:{request:Request;code:string;market?:MarketData;view:string;onView:(view:string)=>void;active:boolean;onBack:()=>void;onMarket:(data:MarketData)=>void}){
 const name=indexes.find(([value])=>value===code)![1],today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
 const [history,setHistory]=useState<History>(),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const [years,setYears]=useState(()=>{const size=view==='weekly'?WEEKLY_WINDOW:DAILY_WINDOW,parameters=readMacdParameters(),need=Math.max(candleHistoryNeed(size,readMovingAverages()),size+5*(parameters.slow+parameters.signal));return Math.min(25,Math.max(3,Math.ceil(need*(view==='weekly'?7:1.5)/365)+1));}),[revision,setRevision]=useState(0),[selectedDay,setSelectedDay]=useState('');
 const start=new Date(Date.UTC(Number(today.slice(0,4))-years,Number(today.slice(5,7))-1,Number(today.slice(8,10)))).toISOString().slice(0,10);
 const rows=history?.code===code?history.daily:[];
 const weekly=useMemo(()=>weeklyBars(rows),[rows]);
 useEffect(()=>{if(!active||view==='minute')return;const timer=setInterval(()=>setRevision(value=>value+1),60000);return()=>clearInterval(timer);},[active,view==='minute']);
 useEffect(()=>{
  if(!active||view==='minute')return;
  let alive=true;setLoading(true);setError('');
  void (async()=>{
   const task=await request<History|{job:string}>('index_chart_history',{code,start,end:today});
   let result:History|undefined;
   if('job' in task){
    for(let attempt=0;alive&&attempt<200;attempt++){
     const job=await request<{status:string;result?:History;error?:string}>('job',{job:task.job});
     if(job.status==='failed')throw Error(job.error||'指数日线加载失败');
     if(job.status==='done'){result=job.result;break;}
     await new Promise(resolve=>setTimeout(resolve,300));
    }
   }else result=task;
   if(alive){if(!result||result.code!==code||result.start!==start||result.end!==today)throw Error('指数日线日期或代码不匹配');setHistory(result);}
  })().catch(cause=>{if(alive)setError(String(cause instanceof Error?cause.message:cause));}).finally(()=>{if(alive)setLoading(false);});
  return()=>{alive=false;};
 },[active,code,start,today,view==='minute',revision,request]);
 const now=Date.now(),safe=market&&indexSparkline(market,code,now);
 const group=safe?market!.minute:null,day=group?.date||'';
 const reached=new Set(safe?safe.points.map(point=>point.time):[]);
 const minute=group?group.bars.filter(bar=>reached.has(bar.time)).map(bar=>({time:bar.time,close:bar.close,volume:bar.volume_lots===undefined?NaN:bar.volume_lots*100,complete:true})):[];
 const leading=indexLeadingPoints(safe?market:undefined,code,now).filter(point=>reached.has(point.time));
 const leadingUntil=leading.at(-1)?.time,minuteUntil=minute.at(-1)?.time;
 const leadingState=!leadingUntil?'黄线暂不可用':market?.leading_error||leadingUntil!==minuteUntil?'黄线截至 '+leadingUntil:'';
 const quote=market?.quotes.find(q=>q.code===code&&q.timestamp.slice(0,10)===day);
 const currentPrice=quote&&Number.isFinite(Date.parse(quote.timestamp))&&Date.parse(quote.timestamp)<=now?{price:Number(quote.price),percent:Number.isFinite(Number(quote.percent))?Number(quote.percent):null,time:quote.timestamp.slice(11,19),timestamp:quote.timestamp,live:true}:undefined;
 const date=rows.some(row=>row.date===selectedDay)?selectedDay:rows.at(-1)?.date;
 const dates=view==='weekly'?weekly.map(row=>row.date):rows.map(row=>row.date);
 const move=(direction:number)=>{const index=dates.indexOf(candleDate(view==='weekly'?weekly:rows,date,view==='weekly')||'');if(index>=0&&dates[index+direction])setSelectedDay(dates[index+direction]);};
 const refresh=async()=>{if(view!=='minute'){setRevision(value=>value+1);return;}try{onMarket(await request<MarketData>('index_minute',{code,include_leading:true}));setError('');}catch{setError('指数行情刷新失败，保留上次数据');}};
 return <div className={'card detail index-detail'+(view==='minute'?' minute-detail':'')}>
  <div className="detail-top"><div className="detail-identity"><h2>{name} <small>{code.toUpperCase()}</small></h2><p>{view==='minute'?(quote?'行情时间 '+quote.timestamp.slice(0,19).replace('T',' '):'指数行情'):'指数行情 · '+(rows.at(-1)?.date||'等待加载')}</p></div><div className="detail-actions"><button disabled={loading} onClick={()=>void refresh()}>刷新行情</button><button onClick={onBack}>返回个股</button></div></div>
  <div className="chart-toolbar"><ChartViewTabs value={view} onChange={onView}/>{loading&&<span className="daily-load-state" role="status">正在加载指数日线…</span>}</div>
  {view==='minute'&&<div className="index-line-guide" aria-label="指数分时线说明"><span className="leading">黄线在蓝线上方：通常中小盘股相对强</span><span className="weighted">黄线在蓝线下方：通常权重股相对强</span><span>{leadingState&&<b role="status"> {leadingState}</b>}</span></div>}
  {error&&<p className="history-empty" role="status">{error}{rows.length?' · 保留上次数据':''}</p>}
  {view!=='minute'&&<div className="chart-caption">{rows.length?`${rows[0].date} 至 ${rows.at(-1)!.date} · ${view==='weekly'?weekly.length:rows.length} 根${view==='weekly'?'周':'日'}K · 成交量（万股）`:loading?'指数日线加载中…':'暂无指数日线'}</div>}
  {view==='minute'&&!minute.length?<div className="watch-chart-empty"><div className="history-empty">{market?.error||'暂无匹配日期的指数分时缓存'}</div></div>:<Chart key={code} indexMode indexLeading={leading} drawingRequest={request} stockCode={code} stockName={name} daily={rows} minute={minute} view={view} selectedDay={view==='minute'?day:date} previousClose={group?Number(group.previous_close):undefined} minuteCachedAt={group?.cached_at} currentPrice={currentPrice} onSelectDay={setSelectedDay} onMove={move} onHistoryNeed={count=>setYears(old=>Math.max(old,Math.min(25,Math.ceil(count*(view==='weekly'?7:1.5)/365)+1)))}/>}
 </div>;
}
