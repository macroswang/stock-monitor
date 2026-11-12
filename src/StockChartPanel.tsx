// 可复用行情图表面板：分时 / 日K / 周K，内部复用自选监控同款 Chart.tsx 引擎。
// 股票池行详情内嵌使用；同时导出共享的 ChartViewTabs（自选监控 chart-toolbar 复用）。
import {useCallback,useEffect,useRef,useState} from 'react';
import './stockChartPanel.css';
import Chart from './Chart';
import {weeklyBars} from './candleData';
import {exchangeCalendar} from './exchangeCalendar';
import type {Bar,Daily,HistoryView} from './models';
import type {Request} from './poolTableModel';

export type ChartView = 'minute' | 'daily' | 'weekly';
const VIEW_LABEL:Record<ChartView,string>={minute:'分时',daily:'日K',weekly:'周K'};
const VIEWS:ChartView[]=['minute','daily','weekly'];

/** 共享三视图 tab 组件；asTabs=true 时输出 role=tablist/tab（股票池内嵌），否则保持普通 button（自选监控既有测试依赖）。 */
export function ChartViewTabs({value,onChange,asTabs=false,className}:{
  value:string;onChange:(view:ChartView)=>void;asTabs?:boolean;className?:string;
}){
  return <div className={'tabs'+(className?' '+className:'')} role={asTabs?'tablist':undefined} aria-label={asTabs?'图表视图':undefined}>
    {VIEWS.map(view=>asTabs
      ?<button type="button" key={view} role="tab" aria-selected={value===view} className={value===view?'chosen':''} onClick={()=>onChange(view)}>{VIEW_LABEL[view]}</button>
      :<button type="button" key={view} className={value===view?'chosen':''} onClick={()=>onChange(view)}>{VIEW_LABEL[view]}</button>)}
  </div>;
}

type CachedMinute={day:string;data?:{bars?:Bar[];previous_close?:string|number}};
type MinuteBundle={bars:Bar[];shapeOpening:Bar[];day:string;previousClose:number|undefined};

const dateText=(value:Date)=>value.toLocaleDateString('sv-SE');
const todayText=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
const yearsAgoText=(years:number)=>{const value=new Date();value.setFullYear(value.getFullYear()-years);return dateText(value);};
const readError=(cause:unknown)=>cause instanceof Error?cause.message:'图表加载失败';

function pickMinute(list:CachedMinute[]|null|undefined):MinuteBundle{
  const rows=(Array.isArray(list)?list:[]).filter((item):item is CachedMinute=>Boolean(item&&item.day&&item.data));
  rows.sort((left,right)=>String(right.day).localeCompare(String(left.day)));
  const latest=rows[0];
  if(!latest||!Array.isArray(latest.data?.bars))return {bars:[],shapeOpening:[],day:'',previousClose:undefined};
  const all=latest.data!.bars as Bar[];
  const bars=all.filter(bar=>{const time=String(bar.time||'');return (time>='09:31'&&time<='11:30')||(time>='13:01'&&time<='15:00');});
  const shapeOpening=all.filter(bar=>bar.time==='09:30');
  const previous=Number(latest.data?.previous_close);
  return {bars,shapeOpening,day:latest.day,previousClose:Number.isFinite(previous)&&previous>0?previous:undefined};
}

export default function StockChartPanel({request,code,name,initialView='minute',live=false,onError}:{
  request:Request;code:string;name:string;initialView?:ChartView;live?:boolean;onError?:(error:unknown)=>void;
}){
  const [view,setView]=useState<ChartView>(initialView);
  const [minute,setMinute]=useState<MinuteBundle|null>(null);
  const minuteRef=useRef(minute);minuteRef.current=minute;
  const [daily,setDaily]=useState<Daily[]|null>(null);
  const [minuteLoading,setMinuteLoading]=useState(false);
  const [dailyLoading,setDailyLoading]=useState(false);
  const [minuteError,setMinuteError]=useState('');
  const [dailyError,setDailyError]=useState('');
  const [expanded,setExpanded]=useState(false);
  const [selectedDay,setSelectedDay]=useState('');
  const token=useRef(0);
  const minuteLoaded=useRef(false);
  const dailyLoaded=useRef(false);
  const loadingRef=useRef({minute:false,daily:false});
  const onErrorRef=useRef(onError);onErrorRef.current=onError;

  useEffect(()=>{
    token.current+=1;
    minuteLoaded.current=false;dailyLoaded.current=false;
    loadingRef.current={minute:false,daily:false};
    setMinute(null);setDaily(null);setMinuteError('');setDailyError('');setSelectedDay('');
    setView(initialView);
    return ()=>{token.current+=1;};
  },[code,initialView]);

  const alive=(seq:number)=>seq===token.current;

  const waitJob=useCallback(async(method:string,args:Record<string,unknown>,seq:number)=>{
    const task=await request<{job?:string}>(method,args);
    if(!task||typeof task.job!=='string')return;
    for(let attempt=0;attempt<50;attempt+=1){
      if(!alive(seq))return;
      const state=await request<{status?:string;error?:string}>( 'job',{job:task.job});
      if(state?.status==='failed')throw new Error(state.error||'任务失败');
      if(state?.status==='done')return;
      await new Promise(resolve=>setTimeout(resolve,350));
    }
    throw new Error('图表更新尚未完成，请稍后重试');
  },[request]);

  const ensureMinute=useCallback(async(refresh=false)=>{
    if((minuteLoaded.current&&!refresh)||loadingRef.current.minute)return;
    const seq=token.current;
    loadingRef.current.minute=true;setMinuteLoading(!minuteLoaded.current);setMinuteError('');
    try{
      if(refresh)await waitJob('minute_ensure',{code,day:todayText(),refresh:true},seq);
      if(!alive(seq))return;
      let list=await request<CachedMinute[]>('chart',{code,kind:'minute'});
      if(!alive(seq))return;
      let bundle=pickMinute(list);
      if(!bundle.bars.length&&!refresh){
        try{await waitJob('minute_ensure',{code,day:todayText()},seq);}catch{/* 静默：分时补取失败按空态处理 */}
        if(!alive(seq))return;
        list=await request<CachedMinute[]>('chart',{code,kind:'minute'});
        bundle=pickMinute(list);
      }
      if(!alive(seq))return;
      setMinute(bundle);
      if(bundle.bars.length&&!selectedDay)setSelectedDay(bundle.day);
    }catch(cause){
      if(alive(seq)){setMinuteError(readError(cause));onErrorRef.current?.(cause);}
    }finally{
      if(alive(seq)){setMinuteLoading(false);minuteLoaded.current=true;loadingRef.current.minute=false;}
    }
  },[code,request,waitJob,selectedDay]);

  const ensureDaily=useCallback(async()=>{
    if(dailyLoaded.current||loadingRef.current.daily)return;
    const seq=token.current;
    loadingRef.current.daily=true;setDailyLoading(true);setDailyError('');
    try{
      const start=yearsAgoText(3),end=todayText();
      let data=await request<HistoryView>('history',{code,start,end});
      if(!alive(seq))return;
      let rows=Array.isArray(data?.daily)?data.daily:[];
      if(!rows.length){
        try{await waitJob('daily_load',{code,start,end},seq);}catch{/* 静默：日K补取失败按空态处理 */}
        if(!alive(seq))return;
        data=await request<HistoryView>('history',{code,start,end});
        rows=Array.isArray(data?.daily)?data.daily:[];
      }
      rows=[...rows].sort((left,right)=>String(left.date).localeCompare(String(right.date)));
      if(!alive(seq))return;
      setDaily(rows);
      if(rows.length)setSelectedDay(rows[rows.length-1].date);
    }catch(cause){
      if(alive(seq)){setDailyError(readError(cause));onErrorRef.current?.(cause);}
    }finally{
      if(alive(seq)){setDailyLoading(false);dailyLoaded.current=true;}
      loadingRef.current.daily=false;
    }
  },[code,request,waitJob]);

  useEffect(()=>{
    if(view==='minute')void ensureMinute();else void ensureDaily();
  },[view,ensureMinute,ensureDaily]);

  useEffect(()=>{
    if(!live||view!=='minute')return;
    let timer:ReturnType<typeof setTimeout>;
    const refresh=()=>{
      clearTimeout(timer);
      if(document.visibilityState==='hidden')return;
      const now=Date.now(),dayMs=86400000;
      let next=now+dayMs;
      // 北京时间；休市直接等到下次开盘，不用六秒轮询检查时钟。
      sessions:for(let offset=0;offset<16;offset+=1){
        const day=new Date(now+8*3600000+offset*dayMs).toISOString().slice(0,10);
        if(exchangeCalendar.tradingDay(day)!==true)continue;
        for(const [start,end] of [['09:20','11:30'],['13:00','15:00']]){
          const open=Date.parse(day+'T'+start+':00+08:00'),close=Date.parse(day+'T'+end+':00+08:00');
          if(now<open){next=open;break sessions;}
          if(now<close){
            const current=minuteRef.current;
            if(current?.day!==day||current.bars.at(-1)?.time!=='15:00')void ensureMinute(true);
            next=Math.min(now+6000,close);break sessions;
          }
        }
      }
      timer=setTimeout(refresh,Math.max(1,next-now));
    };
    refresh();
    document.addEventListener('visibilitychange',refresh);
    return ()=>{clearTimeout(timer);document.removeEventListener('visibilitychange',refresh);};
  },[live,view,ensureMinute]);

  const changeView=(next:ChartView)=>setView(next);
  const loading=view==='minute'?minuteLoading:dailyLoading;
  const error=view==='minute'?minuteError:dailyError;
  const ready=view==='minute'?Boolean(minute&&minute.bars.length):Boolean(daily&&daily.length);
  const candleDay=daily&&daily.length?selectedDay||daily[daily.length-1].date:'';
  const activeDay=view==='minute'?(minute?.day||''):candleDay;
  const weeklyCount=daily&&daily.length?weeklyBars(daily).length:0;
  const statusText=ready
    ?(view==='minute'?'分时 '+(minute?.day||'—')+' · 至 '+(minute?.bars.at(-1)?.time||'—')
      :view==='daily'?'日K '+(daily?.length||0)+'根 · '+(candleDay||'—')
      :'周K '+weeklyCount+'根 · '+(candleDay||'—'))
    :(loading?'加载中…':'—');
  const chartView=view==='minute'?'minute':view==='daily'?'daily':'weekly';
  return <section className={'stock-chart-panel'+(expanded?' is-expanded':'')} aria-label={'行情图表 '+name}>
    <div className="scp-toolbar">
      <ChartViewTabs value={view} onChange={changeView} asTabs/>
      <span className="scp-state" role="status">{statusText}</span>
      <button type="button" className="scp-expand" aria-label={expanded?'缩小图表':'放大图表'} aria-pressed={expanded}
        title={expanded?'恢复默认高度':'放大图表'} onClick={()=>setExpanded(value=>!value)}>{expanded?'缩小':'放大'}</button>
    </div>
    {loading&&!ready&&<p className="scp-message" role="status">图表加载中…</p>}
    {!loading&&error&&<p className="scp-error" role="status">{error}</p>}
    {!loading&&!error&&!ready&&<p className="scp-message" role="status">
      {view==='minute'?'该股暂无可用的分时数据（可稍后重试或查看日K）。':'该股暂无可用的日K数据。'}
    </p>}
    {ready&&<div className="scp-chart">
      {/* stockCode 传 MACD 中性前缀：内嵌面板不请求/展示指数 MACD（契约要求不传高级数据），名称仍用真实 name */}
      <Chart stockCode={'pool-'+code} stockName={name} minute={minute?.bars||[]} shapeOpening={minute?.shapeOpening||[]}
        daily={daily||[]} view={chartView} selectedDay={activeDay} onSelectDay={day=>setSelectedDay(day)}
        compact previousClose={minute?.previousClose} benchmark={null}/>
    </div>}
  </section>;
}
