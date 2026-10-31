import MarketPanorama from './MarketPanorama';
import React,{useEffect,useRef,useState} from 'react';
import * as echarts from 'echarts';
import OptionPCRPanel from './OptionPCRPanel';
import EquityBondPanel from './EquityBondPanel';
import IndexTechnicalPanel from './IndexTechnicalPanel';
import AdvanceDeclinePanel from './AdvanceDeclinePanel';
import InstitutionDisclosure from './InstitutionDisclosure';
import MarketDecision from './MarketDecision';
import {breadthCountsConsistent,closedSnapshotReady,intradayBreadth,sameBreadthProvenance,verifiedFlowShare,verifiedTrin} from './intradayMarket';
import type {MarketData} from './models';
import p250Research from '../fixtures/author-p250-research.json';
import {exchangeCalendar} from './exchangeCalendar';

type MABreadth={date:string;active:number;source:string;status?:string;collected_at?:string;computed_at?:string;previous_close_mismatches?:number;warning?:string;windows:Record<string,{eligible:number;above:number;percent:number|null}>};
type ADReference={adl:number|null;adr:number|null;adl_start:string|null;adl_samples:number;adl_gap_before:boolean;source:string;universe:string};
export type BreadthDay={date:string;trin:number|null;trin_amount?:number|null;adl?:number|null;adr?:number|null;adl_start?:string|null;adl_samples?:number;adl_gap_before?:boolean;ad_history?:ADReference;mcl_standard?:number|null;mcl_samples?:number;mcl_history?:{date:string;value:number;samples:number;source:string;universe:string;collected_at:string|null};ma_breadth?:MABreadth;ma_history?:MABreadth;ma_daily?:MABreadth;advance:number;decline:number;flat:number;advance_volume:number;decline_volume:number;flat_volume:number;advance_amount?:number|null;decline_amount?:number|null;advancing_percent:number|null;advancing_volume_percent:number|null;advancing_amount_percent?:number|null;expected:number;covered:number;suspended:number;missing:number;status:string;historical?:boolean;collected_at:string;first_quote:string|null;last_quote:string|null;source:string;universe?:string;undefined_reason?:string;reconciliation_note?:string};
type Report={days:BreadthDay[];running:boolean;error:string;history_note:string;ma_note?:string;interval_seconds?:number};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const fmt=(n:number|null,digits=2)=>n===null?'—':n.toLocaleString('zh-CN',{maximumFractionDigits:digits,minimumFractionDigits:digits});
const state=(d:BreadthDay)=>d.status!=='closed'&&d.status!=='provisional'?'数据不完整':d.historical?'历史复核':d.status==='closed'?'收盘统计':'盘中暂值';
const color=(n:number|null)=>n===null?'#8293aa':n<1?'#ed7d81':n>1?'#51c7aa':'#9aabc2';
const pct=(n:number|null)=>n===null?'—':fmt(n,1)+'%';
const staleProvisional=(day:BreadthDay,now:number)=>{
 if(day.status!=='provisional')return false;
 const date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 const time=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
 const first=day.first_quote&&/\+08:00$/.test(day.first_quote)?Date.parse(day.first_quote):NaN;
 const session=time>='09:30'&&time<'11:30'?'morning':time>='13:00'&&time<'15:00'?'afternoon':null;
 const quoteTime=day.first_quote?.slice(11,16)||'';
 const matching=session==='morning'?quoteTime>='09:30'&&quoteTime<'11:30':session==='afternoon'?quoteTime>='13:00'&&quoteTime<'15:00':false;
 return day.date!==date||!matching||!Number.isFinite(first)||first>now+5000||first<now-300000;
};
// Missing trading dates must not be bridged by an apparently continuous line.
export const adjacent=(a:string,b:string)=>{
 const left=new Date(a+'T00:00:00Z'),right=new Date(b+'T00:00:00Z');
 const delta=(right.getTime()-left.getTime())/86400000;
 if(!Number.isInteger(delta)||delta<1||delta>32||left.toISOString().slice(0,10)!==a||right.toISOString().slice(0,10)!==b)return false;
 for(let t=left.getTime()+86400000;t<=right.getTime();t+=86400000){
  const day=new Date(t).toISOString().slice(0,10),trading=exchangeCalendar.tradingDay(day);
  if(trading===null)return false;
  if(trading)return day===b;
 }
 return false;
};

// Window sizes count exchange sessions, even when observations are missing.
export const sessionWindow=(days:BreadthDay[],count:number)=>{
 const end=days.at(-1)?.date;
 if(!end)return {rows:[],start:null as string|null,known:true};
 if(count===120)return {rows:days.slice(-count),start:null as string|null,known:false};
 const date=new Date(end+'T00:00:00Z');
 if(!Number.isFinite(date.getTime())||date.toISOString().slice(0,10)!==end||!exchangeCalendar.hasYear(date.getUTCFullYear()))
  return {rows:days.slice(-count),start:null as string|null,known:false};
 let left=count,start:string|null=null;
 while(true){
  const d=date.toISOString().slice(0,10);
  const trading=exchangeCalendar.tradingDay(d);
  if(trading===null)break;
  if(trading&&--left===0){start=d;break;}
  date.setUTCDate(date.getUTCDate()-1);
 }
 if(!start)return {rows:days.slice(-count),start:null as string|null,known:false};
 return {rows:days.filter(d=>d.date>=start!&&d.date<=end),start,known:true};
};

export default function MarketBreadth({request,market,preview=false,mode,setMode,watch=[],onOpenStock}:{request:Request;market:MarketData;preview?:boolean;mode:'volume'|'amount';setMode:(mode:'volume'|'amount')=>void;watch?:{code:string;name:string}[];onOpenStock?:(code:string)=>void}){
 const [report,setReport]=useState<Report>({days:[],running:false,error:'',history_note:''});
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[span,setSpan]=useState(30),[selected,setSelected]=useState('');
 const [stage,setStage]=useState<'unknown'|'early'|'late'>('unknown');
 // The chart interpretation must age out even if requests never finish.
 const [,setClock]=useState(()=>Date.now());
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),15000);return()=>clearInterval(timer);},[]);
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null),alive=useRef(true),reading=useRef(false);
 const load=async()=>{if(reading.current)return;reading.current=true;try{const r=await request<Report>('breadth');if(alive.current){setReport(r);setError('');}}catch(e){if(alive.current)setError(String(e));}finally{reading.current=false;}};
 useEffect(()=>{alive.current=true;void load();const timer=setInterval(load,30000);return()=>{alive.current=false;clearInterval(timer);};},[request]);
 const refresh=async()=>{setBusy(true);setError('');try{const job=await request<{job:string}>('breadth_refresh');for(;;){const r=await request<{status:string;error?:string;result?:Report}>('job',{job:job.job});if(!alive.current)return;if(r.status==='failed')throw Error(r.error);if(r.status==='done'){if(r.result)setReport(r.result);break;}await new Promise(resolve=>setTimeout(resolve,500));}}catch(e){if(alive.current)setError(String(e));}finally{if(alive.current)setBusy(false);}};
 const countMismatch=(d:BreadthDay)=>(d.status==='closed'||d.status==='provisional')&&d.missing===0&&d.expected>0&&d.covered===d.expected&&!breadthCountsConsistent(d);
 const dateWindow=sessionWindow(report.days,span);
 const days=dateWindow.rows.map(d=>closedSnapshotReady(d,Date.now())&&!countMismatch(d)?d:{...d,status:'incomplete',trin:null,trin_amount:null,advancing_percent:null,advancing_volume_percent:null,advancing_amount_percent:null,adl:null,adr:null,adl_start:null,adl_samples:0,adl_gap_before:true,ad_history:undefined,mcl_standard:null,mcl_history:undefined,ma_breadth:undefined,ma_history:undefined,ma_daily:undefined}),day=days.find(d=>d.date===selected)||days.at(-1),byAmount=mode==='amount';
 const changeSpan=(n:number)=>{setSpan(n);if(selected&&!sessionWindow(report.days,n).rows.some(d=>d.date===selected))setSelected('');};
 useEffect(()=>{setStage('unknown');},[day?.date]);
 const dayIndex=day?report.days.findIndex(d=>d.date===day.date):-1;
 const previousDay=dayIndex>0?report.days[dayIndex-1]:undefined;
 const value=(d:BreadthDay)=>verifiedTrin(d,byAmount);
 const mclValue=(d:BreadthDay|undefined)=>d?.status==='closed'?(d.mcl_standard??d.mcl_history?.value??null):null;
 const mclLabel=(d:BreadthDay|undefined)=>d?.status==='closed'&&d.mcl_standard==null&&d.mcl_history?'（历史）':'';
 const proportion=(d:BreadthDay)=>verifiedFlowShare(d,byAmount);
 const trin=day?value(day):null;
 const pendingClose=!!day&&day.status==='incomplete'&&report.days.some(d=>d.date===day.date&&d.status==='closed'&&!closedSnapshotReady(d,Date.now()));
 const inconsistentCounts=!!day&&report.days.some(d=>d.date===day.date&&countMismatch(d));
 const rawTrin=day?(byAmount?day.trin_amount:day.trin):null;
 const inconsistentTrin=!!day&&rawTrin!=null&&verifiedTrin(day,byAmount)===null;
 const rawShare=day?(byAmount?day.advancing_amount_percent:day.advancing_volume_percent):null;
 const inconsistentShare=!!day&&rawShare!=null&&proportion(day)===null;
 const stale=!!day&&staleProvisional(day,Date.now());
 const timingInvalid=!!day&&day.status==='provisional'&&!stale&&day.missing===0&&day.expected>0&&day.covered===day.expected&&!intradayBreadth(day,Date.now());
 const guideReady=!!day&&(day.status==='closed'||(day.status==='provisional'&&!stale&&!timingInvalid))&&day.missing===0&&day.expected>0&&day.covered===day.expected&&typeof trin==='number'&&Number.isFinite(trin)&&trin>0&&!inconsistentShare&&breadthCountsConsistent(day)&&day.advance>0&&day.decline>0;
 const guideExample=guideReady?(trin!<1?`上涨股平均${byAmount?'成交额':'成交量'}约为下跌股的 ${(1/trin!).toFixed(2)} 倍`:trin!>1?`下跌股平均${byAmount?'成交额':'成交量'}约为上涨股的 ${trin!.toFixed(2)} 倍`:'上涨股与下跌股的平均成交相同'):null;
 const trinReading=guideReady?(trin!<0.5?'低于 0.5，上涨组相对放量突出，关注多头进攻迹象':trin!<0.6?'低于 0.6，上涨组相对放量明显，关注多头进攻迹象':trin!<0.7?'低于 0.7，上涨组相对放量，关注多头进攻迹象':trin!<0.9?'低于 1，上涨组平均成交较高':trin!<=1.1?'接近 1，涨跌两组平均成交相对接近':trin!>1.1?'高于 1，下跌组平均成交较高':'') : null;
 const breadthReading=guideReady?(day!.advancing_percent!<20?'上涨股票较少':day!.advancing_percent!<50?'上涨股票不足一半':'上涨股票占比至少一半'):null;
 const combinedReading=!guideReady?null:
  trin!<0.7&&day!.advancing_percent!<20?'上涨股票较少且 TRIN 较低，关注大资金是否集中进入少数上涨股。':
  trin!<0.7&&day!.advancing_percent!>=50?'上涨股票覆盖面较广，上涨组相对放量，多头量能较强。':
  trin!>=0.9&&trin!<=1.1?'量能结构相对中性，还需结合上涨家数观察市场宽度。':
  trin!>1.1&&day!.advancing_percent!<50?'上涨股票不足一半，下跌组相对放量。':
  trin!>1.1&&day!.advancing_percent!>=50?'上涨股票覆盖面较广，但下跌组平均成交更高。':null;
 const stageReading=guideReady&&trin!<0.7?(stage==='early'?'手动选择的趋势前段：低 TRIN 仅作成交结构观察，暂不直接判断反转。':stage==='late'?'手动选择的趋势中后段：结合市场宽度观察短线变化。':'趋势阶段未确认，低 TRIN 暂按成交结构观察。'):null;
 const historicalMcl=day?.status==='closed'&&day.mcl_standard==null?day.mcl_history:undefined;
 // During a session the current close is unknown. A completed immediately
 // preceding same-source session may be shown with its own date instead.
 const maDay=day?.status==='closed'?day:day?.status==='provisional'&&day.adl_gap_before===false&&previousDay?.status==='closed'?previousDay:undefined;
 const ma=maDay?(maDay.ma_daily??(maDay.historical?maDay.ma_breadth:maDay.ma_history)):undefined;
 const p250=maDay?(maDay.ma_daily?.windows['250']??p250Research.rows.find(r=>r.date===maDay.date)):undefined;
 const structure=trin===null||!Number.isFinite(trin)?'数据不足，无法比较':trin<1?`上涨组平均${byAmount?'成交额':'成交量'}较高`:trin>1?`下跌组平均${byAmount?'成交额':'成交量'}较高`:`两组平均${byAmount?'成交额':'成交量'}相同`;
 useEffect(()=>{
  if(!ref.current)return;const c=echarts.init(ref.current,'dark',{renderer:'canvas'});chart.current=c;
  const observer=new ResizeObserver(()=>c.resize());observer.observe(ref.current);
  c.on('click',p=>{if(p.name&&/^\d{4}-\d{2}-\d{2}$/.test(p.name))setSelected(p.name);});
  return()=>{observer.disconnect();c.dispose();chart.current=null;};
 },[]);
 useEffect(()=>{
  if(!chart.current)return;
  const slots:(BreadthDay|null)[]=[];
  days.forEach((d,i)=>{const p=days[i-1];if(i&&(!adjacent(p.date,d.date)||!sameBreadthProvenance(p,d)))slots.push(null);slots.push(d);});
  const usable=(d:BreadthDay|null)=>!!d&&(d.status==='closed'||d.status==='provisional')&&!(d.status==='provisional'&&!staleProvisional(d,Date.now())&&!intradayBreadth(d,Date.now()))&&d.missing===0&&d.expected>0&&d.covered===d.expected&&breadthCountsConsistent(d);
  const labels=slots.map((d,i)=>d?.date||`gap-${i}`);
  const showPointLabels=days.length<=15;
  chart.current.setOption({backgroundColor:'transparent',animation:false,
   tooltip:{trigger:'axis',confine:true,backgroundColor:'#162238',borderColor:'#34465e',textStyle:{color:'#e7edf7'},formatter:(params:any)=>{
    const d=slots[params[0]?.dataIndex];if(!d)return '日期间隔，可能有未显示的交易日';if(!usable(d))return `${d.date} · 数据不完整，暂不解读`;
    // Only numeric/date fields enter this formatter; provider text is rendered by React below.
    return `${d.date} · ${state(d)}<br/>上涨家数：${pct(d.advancing_percent)}（${d.advance} 只）<br/>上涨股${byAmount?'成交额':'成交量'}占比：${pct(proportion(d))}<br/>TRIN（${byAmount?'成交额对照':'成交股数'}）：${fmt(value(d),3)}<br/>下跌 ${d.decline} 只 · 平盘 ${d.flat} 只`;
   }},
   grid:{left:62,right:68,top:42,bottom:48},
   xAxis:{type:'category',data:labels,axisLabel:{color:'#9eafc7',hideOverlap:true,showMinLabel:true,showMaxLabel:true,formatter:(s:string)=>s.startsWith('gap-')?'…':s.slice(5)},axisTick:{show:false},axisLine:{lineStyle:{color:'#69778a'}}},
   yAxis:[{type:'value',name:'占比',min:0,max:100,splitNumber:5,axisLabel:{formatter:'{value}%',color:'#9eafc7'},splitLine:{lineStyle:{color:'#28313d'}}},{type:'value',name:'TRIN',min:0,max:(range:{max:number})=>Math.max(1.5,Math.ceil(range.max*1.1*2)/2),axisLabel:{color:'#b4bd9e'},splitLine:{show:false}}],
   series:[
    {name:byAmount?'上涨股成交额占比':'上涨股成交量占比',type:'bar',barMaxWidth:50,label:{show:showPointLabels,position:'insideBottom',fontSize:11,color:'#fff',formatter:(p:any)=>p.value==null?'':fmt(p.value,1)+'%'},data:slots.map(d=>usable(d)&&d?{value:proportion(d),itemStyle:{color:'#e65d50',opacity:d.status==='closed'?1:.55}}:null),z:1},
    {name:'上涨家数占比',type:'line',connectNulls:false,symbol:'circle',symbolSize:4,lineStyle:{color:'#5186e0',width:2},itemStyle:{color:'#5186e0'},label:{show:showPointLabels,position:'top',fontSize:11,color:'#a8c5ef',formatter:(p:any)=>p.value==null?'':fmt(p.value,1)+'%'},data:slots.map(d=>usable(d)?d?.advancing_percent??null:null),z:3},
    {name:'TRIN',type:'line',yAxisIndex:1,connectNulls:false,symbol:'circle',symbolSize:4,lineStyle:{color:'#c6d14f',width:2,type:'dashed'},itemStyle:{color:'#c6d14f'},label:{show:showPointLabels,position:'top',fontSize:11,color:'#d2dd8d',formatter:(p:any)=>p.value==null?'':fmt(p.value,2)},data:slots.map(d=>usable(d)&&d?value(d):null),markLine:{silent:true,symbol:'none',label:{position:'insideEndTop',color:'#b6c57c',formatter:'1'},lineStyle:{color:'#929d57',width:1,type:'dotted'},data:[{yAxis:1}]},z:4}
   ],
  },true);
 },[report.days,span,mode,timingInvalid,day?.date]);
 return <section className="card breadth-panel">
  <div className="breadth-heading"><div><span className="eyebrow">市场广度 × 成交量</span><h2>大盘阿姆氏 <small>TRIN</small></h2><p>沪深股票 · 收盘与盘中统计</p></div><div className="breadth-actions"><select aria-label="TRIN计算口径" value={mode} onChange={e=>setMode(e.target.value as 'volume'|'amount')}><option value="amount">成交额对照</option><option value="volume">成交股数</option></select><button onClick={refresh} disabled={busy||report.running}>{busy||report.running?'采集中…':'刷新全市场'}</button></div></div>
  {preview&&<div className="breadth-preview-notice" role="status">本地只读预览 · 行情为静态快照，不会自动更新；请以页面显示的数据日期为准。</div>}
  {pendingClose&&<div className="breadth-preview-notice" role="status">收盘数据时间尚未到达或采集时间异常，暂不用于市场判断。</div>}
  {inconsistentCounts&&<div className="breadth-preview-notice" role="status">涨跌家数或上涨比例异常，暂不进行市场判断。</div>}
  {inconsistentTrin&&<div className="breadth-preview-notice" role="status">当前图表口径的 TRIN 与成交数据不一致，可切换口径或刷新数据。</div>}
  {inconsistentShare&&<div className="breadth-preview-notice" role="status">当前图表口径的成交占比与成交数据不一致，可切换口径或刷新数据。</div>}
  {day&&stale&&<div className="breadth-preview-notice" role="status">{day.date} 的盘中快照已过期，以下数据仅供回看；请刷新后再判断当前市场。</div>}
  {timingInvalid&&<div className="breadth-preview-notice" role="status">盘中快照时间信息异常，暂不用于市场判断；请刷新数据。</div>}
  {(error||report.error)&&<div className="breadth-error" role="status">{error||report.error}；已保留上次有效统计。</div>}
  <MarketPanorama request={request} preview={preview} day={report.days.at(-1)} breadthError={error||report.error} watch={watch} onOpenStock={onOpenStock}/>
  <MarketDecision request={request} day={day} previous={previousDay} byAmount={true} market={market} stage={stage} feedError={error||report.error}/>
  <section className="market-trend" id="breadth-structure" aria-label="市场趋势图">
   <div className="market-trend-header"><div><h3>市场宽度与成交趋势</h3><p>{days.length?`${dateWindow.known?`最近${span}个交易日 · `:''}${dateWindow.start||days[0].date} 至 ${days.at(-1)!.date} · ${days.length} 条记录${dateWindow.known?'':span===120?'（按记录数展示）':'（交易日历不足，按记录数展示）'} · `:''}点击查看某日判断；缺失或来源变化时断开</p></div><div className="market-trend-ranges" role="group" aria-label="图表时间范围">{[30,60,90].map(n=><button key={n} type="button" aria-pressed={span===n} onClick={()=>changeSpan(n)}>{n}日</button>)}<button type="button" aria-label="查看最新市场数据" disabled={!selected||day?.date===days.at(-1)?.date} onClick={()=>setSelected('')}>最新</button></div></div>
   <div className="breadth-key"><span><i style={{background:'#e65d50'}}/>上涨股{byAmount?'成交额':'成交量'}占比（左轴）</span><span><i style={{background:'#5186e0'}}/>上涨家数占比（左轴）</span><span><i style={{background:'#c6d14f'}}/>TRIN{byAmount?' · 成交额对照':''}（右轴）</span></div>
   <div className="breadth-chart-wrap"><div className="breadth-chart" ref={ref} role="img" aria-label={`上涨股${byAmount?'成交额':'成交量'}占比柱状图、上涨家数占比与TRIN曲线`}/>{!days.length&&<div className="breadth-empty">{busy||report.running?'正在核对全市场股票与报价日期…':'尚无完整市场统计'}<small>点击“刷新全市场”开始采集；缺失数据不会画成0。</small></div>}</div>
   <div className="market-chart-reading" aria-label="市场解读">
    {guideReady?<><strong>{day!.date} · {state(day!)} · {byAmount?'成交额':'成交股数'}口径</strong><p>上涨 {pct(day!.advancing_percent)}，{breadthReading}；TRIN {trin!.toFixed(3)}，{trinReading}。</p>{combinedReading&&<p>{combinedReading}</p>}{stageReading&&<p>{stageReading}</p>}<small>上涨不足 20% 按“较少”展示；0.90—1.10 按“接近 1”展示，均为界面参考范围。</small></>:<p>{stale?'盘中数据已过期，等待更新后解读。':timingInvalid?'盘中数据时间异常，等待更新后解读。':'数据不足，暂无法解读市场。'}</p>}
   </div>
   <div className="market-chart-guide" aria-label="图表怎么看">
    <div><strong><i className="guide-blue"/>蓝线 · 涨的股票多不多</strong><p>上涨家数占涨、跌、平盘股票的比例；越高，上涨的股票越多。</p></div>
    <div><strong><i className="guide-red"/>红柱 · 成交集中在哪里</strong><p>上涨股占涨跌两组{byAmount?'成交额':'成交量'}的比例；越高，成交越集中在上涨股。</p></div>
    <div><strong><i className="guide-yellow"/>黄线 · TRIN 怎么看</strong><p>低于 1：上涨股平均成交较高；高于 1：下跌股平均成交较高。越低，上涨组的相对平均成交越高。</p><p>多数股票下跌、TRIN 较低时，结合趋势阶段观察大资金是否进入少数上涨股。</p></div>
   </div>
   {guideExample&&<p className="market-trend-note">{day!.date} 观察：上涨家数占比 {pct(day!.advancing_percent)} · TRIN {trin!.toFixed(3)}；{guideExample}。按股票涨跌分组统计。</p>}
   <p className="market-trend-note">淡色柱为盘中暂值；点击图表可查看某一天的数据。</p>
  </section>
  <details className="breadth-method breadth-research-details" aria-label="市场图表与研究详情"><summary>查看历史图表与研究详情</summary>
  <label className="breadth-research-range">历史范围 <select aria-label="TRIN显示日期数" value={span} onChange={e=>changeSpan(Number(e.target.value))}><option value={30}>最近30个交易日</option><option value={60}>最近60个交易日</option><option value={90}>最近90个交易日</option><option value={120}>最近120条记录</option></select></label>
  {!preview&&<div className="breadth-footnote">大盘数据独立采集：{report.interval_seconds===180?'交易时段约每 3 分钟启动检查，耗时较长时会延后':'交易时段每次采集结束后约 5 分钟检查'}；暂停自选监控不影响大盘采集。休市、断网、睡眠或退出会影响更新，请以数据时间为准。</div>}
  <section className="market-observation" aria-label="市场观察框架">
   <div className="observation-heading"><div><h3>市场观察</h3><p>结合趋势阶段、市场宽度与成交结构，辅助人工判断。</p></div><span>研究参考</span></div>
   <nav className="observation-nav" aria-label="市场观察顺序"><a href="#breadth-equity-bond">1 中期估值</a><a href="#breadth-index-technical">2 指数位置</a><a href="#breadth-structure">3 宽度与量价</a><a href="#breadth-option-pcr">4 期权情绪</a><a href="#breadth-institution">5 公开持仓</a></nav>
   {report.ma_note&&<p role="status">{report.ma_note}</p>}
   <div className="observation-grid">
    <div className="observation-item"><div className="observation-label">中期环境 <span>手动观察</span></div><label htmlFor="observation-stage">当前趋势阶段</label><select id="observation-stage" value={stage} onChange={e=>setStage(e.target.value as typeof stage)}><option value="unknown">尚未判断</option><option value="early">趋势前段</option><option value="late">趋势中后段</option></select><p>{stage==='unknown'?'先结合指数走势判断所处阶段。':stage==='early'?'结合市场宽度和成交结构观察。':'结合市场宽度和成交结构观察。'}</p></div>
    <div className="observation-item"><div className="observation-label">短期结构 <span>{day?`${day.date} · ${state(day)}${stale?' · 快照已过期，仅供回看':timingInvalid?' · 时间异常，仅供回看':''}`:'暂无数据'}</span></div><strong>{structure}</strong><p>上涨家数 {day?pct(day.advancing_percent):'—'} · TRIN {fmt(trin,3)}</p>{stale&&day?.first_quote&&day.last_quote&&<small>股票报价时间 {day.first_quote.slice(11,19)}–{day.last_quote.slice(11,19)}，不是当前行情。</small>}<small>反映两组平均量能，不能识别资金身份或预测涨跌。</small></div>
    <div className="observation-item"><div className="observation-label">标准 MCL <span>{historicalMcl?'历史收盘参照':'独立计算'}</span></div><strong>{fmt(mclValue(day),1)}</strong><p>{day?.status==='closed'&&day.mcl_standard!=null?`连续 ${day.mcl_samples} 个完整交易日`:historicalMcl?`${historicalMcl.date} · 历史数据连续 ${historicalMcl.samples} 天`:'连续同口径完整数据不足，暂不显示'}</p>{historicalMcl&&<small>来源：{historicalMcl.source}；未与当前报价拼接。</small>}{mclValue(day)!=null&&<small>历史起点会影响结果；连续时间较短时偏差可能较大。</small>}</div>
    <div className="observation-item"><div className="observation-label">均线宽度 <span>{maDay&&day&&maDay.date!==day.date?'前一交易日收盘参照':'历史收盘参照'}</span></div><strong>20日 {pct(ma?.windows['20']?.percent??null)} · 60日 {pct(ma?.windows['60']?.percent??null)}</strong><p>{ma?`${ma.date} · 有效样本 ${ma.windows['20']?.eligible??0} / ${ma.windows['60']?.eligible??0} 只`:'所选日期暂无已核验历史数据'}</p><small>高于各自未复权均线的股票占比；窗口内未处理除权等价格不连续。非实时数据。</small>{ma&&maDay?.ma_daily&&<small>{maDay.ma_daily.source}；当日昨收不一致排除 {maDay.ma_daily.previous_close_mismatches??0} 只。</small>}{p250&&<><p>250日研究参照 {pct(p250.percent)} · 样本 {p250.eligible} 只</p><small>{maDay?.ma_daily?maDay.ma_daily.source:p250Research.source}；未复权价格可能受除权影响。</small></>}</div>
   </div>
  </section>
  {day&&day.status!=='incomplete'&&<div className="breadth-stats"><div><span>{day.date} · {state(day)}{stale?' · 快照已过期，仅供回看':timingInvalid?' · 时间异常，仅供回看':''} · {byAmount?'成交额对照':'成交股数'}</span><strong style={{color:color(value(day))}}>{fmt(value(day),3)}</strong></div><div><span>上涨家数占比</span><strong>{pct(day.advancing_percent)}</strong><small>上涨 {day.advance} / 下跌 {day.decline} / 平盘 {day.flat}</small></div><div><span>上涨股{byAmount?'成交额':'成交量'}占比</span><strong>{pct(proportion(day))}</strong><small>仅比较上涨与下跌两组</small></div><div><span>{day.historical?'历史日线覆盖':'股票列表覆盖'}</span><strong>{day.covered}<em> / {day.expected}</em></strong><small>停牌 / 零成交 {day.suspended} 只</small></div></div>}
  <div className="breadth-footnote">{report.history_note||'每日积累完整市场快照。'}{days.length>0&&` 共收录 ${report.days.length} 个日期，当前显示 ${days.length} 个；盘中暂值单独标示，日期间隔不代表连续交易日。`}<br/>红柱显示上涨股{byAmount?'成交额':'成交量'}占比。{byAmount&&' 成交额是对照口径，旧数据可能没有该字段。'}{day&&<><br/>{day.historical?'历史底表获取于':'采集于'} {day.collected_at.slice(0,19).replace('T',' ')} 北京时间 · {day.source}{day.reconciliation_note&&<> · {day.reconciliation_note}</>}</>}</div>
  <AdvanceDeclinePanel days={days} selected={day} onSelect={setSelected}/>
  {day&&<OptionPCRPanel request={request} selectedDate={day.date} intradayDate={day.status!=='closed'?day.date:''}/>}
  <EquityBondPanel request={request} selectedDate={day?.date||''} intradayDate={day&&day.status!=='closed'?day.date:''}/>
  <IndexTechnicalPanel request={request} selectedDate={day?.date||''} intradayDate={day&&day.status!=='closed'?day.date:''}/>
  <InstitutionDisclosure/>
  <details className="breadth-method"><summary>计算口径与数据明细</summary><p>TRIN = (上涨家数 × 下跌股成交量) ÷ (下跌家数 × 上涨股成交量)。涨跌相对当日昨收；按整只股票的当日累计成交股数分组，不使用主动买盘、卖盘量。平盘、停牌及零成交不进入公式。上涨家数占比 = 上涨 ÷（上涨 + 下跌 + 平盘）；上涨股成交量占比 = 上涨股成交量 ÷（上涨股成交量 + 下跌股成交量）。缺一组或分母为0时显示“—”。</p><p>成交额对照将公式中的成交股数替换为成交额，红柱同步改为上涨股成交额占上涨与下跌两组成交额的比例。历史行情使用日线成交额；腾讯报价的成交额按来源精度换算，缺少某只股票的有效成交额时整日不显示此口径。它不是资金净流入。</p><p>数据来源：腾讯逐股报价，新浪沪深股票代码表；不包含北交所、B股及基金，部分存托凭证可能不在列表中。列表覆盖率以新浪列表为分母。普通A股原始量以手计，换算为股仍保留手级取整精度；科创板原始量以股计。盘中{report.interval_seconds===180?'约每3分钟启动检查，耗时较长时会延后':'每次采集结束后约5分钟检查'}，收盘15:15后核对；采集并非同一瞬间，盘中值会变动。收盘后没有完整数据的日期不补造，也不使用当前自选股推算大盘。</p><p>TRIN低于1表示上涨组的平均成交量大于下跌组，不能证明机构买入、空头回补或未来涨跌。</p>
   <p>标准 MCL 以每日上涨家数减下跌家数为输入，分别按 0.10 和 0.05 指数平滑后相减；首日差值初始化，至少连续 39 个同来源、同股票范围的完整收盘交易日才显示。缺少已核对日历、交易日缺失、数据不完整或来源变化时重新累计。初始化会影响数值；此值为独立研究计算。</p><p>历史复核使用 BaoStock 当日日线及 Money Tree 数据交叉核对，按沪深当日股票排除 689 类存托凭证，近似日常新浪列表，但历史名单未逐日与新浪完全核对。历史日线是收盘口径，与盘中采样不能直接视为同一时点。</p>
   {day&&!day.historical&&<p>报价区间：{day.first_quote?.slice(0,19).replace('T',' ')} 至 {day.last_quote?.slice(11,19)}；采集时间：{day.collected_at.slice(0,19).replace('T',' ')} 北京时间。{day.undefined_reason}</p>}
  </details>
  {!!days.length&&<div className="table-wrap breadth-table"><table><thead><tr><th>日期</th><th>TRIN{byAmount?'（成交额）':''}</th><th>标准 MCL</th><th>上涨 / 下跌 / 平盘</th><th>上涨股量（亿股）</th><th>下跌股量（亿股）</th><th>状态</th></tr></thead><tbody>{[...days].reverse().map(d=><tr key={d.date} onClick={()=>setSelected(d.date)} className={day?.date===d.date?'selected':''}><td>{d.date}</td>{d.status==='incomplete'?<><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></>:<><td style={{color:color(value(d))}}>{fmt(value(d),3)}</td><td>{fmt(mclValue(d),1)}{mclLabel(d)}</td><td>{d.advance} / {d.decline} / {d.flat}</td><td>{fmt(d.advance_volume/1e8)}</td><td>{fmt(d.decline_volume/1e8)}</td></>}<td>{state(d)}</td></tr>)}</tbody></table></div>}</details>
 </section>;
}
