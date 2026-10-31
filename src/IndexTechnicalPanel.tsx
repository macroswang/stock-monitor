import React,{useEffect,useRef,useState} from 'react';
import * as echarts from 'echarts';
type Row={date:string;first_date:string;open:number;high:number;low:number;close:number;boll_mid:number|null;boll_upper:number|null;boll_lower:number|null;cci:number|null;gap_before:boolean};
type Report={daily:Row[];weekly:Row[];running:boolean;error:string;collected_at?:string;source?:string};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const fmt=(n:number|null|undefined)=>n==null||!Number.isFinite(n)?'—':n.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});

export default function IndexTechnicalPanel({request,selectedDate,intradayDate}:{request:Request;selectedDate:string;intradayDate:string}){
 const [report,setReport]=useState<Report>({daily:[],weekly:[],running:false,error:''});
 const [period,setPeriod]=useState<'daily'|'weekly'>('daily'),[selected,setSelected]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{setSelected('');},[selectedDate]);
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null),alive=useRef(true),reading=useRef(false);
 const load=async()=>{if(reading.current)return;reading.current=true;try{const data=await request<Report>('index_technical');if(alive.current){setReport(data);setError('');}}catch(e){if(alive.current)setError(String(e));}finally{reading.current=false;}};
 useEffect(()=>{alive.current=true;void load();const timer=setInterval(load,30000);return()=>{alive.current=false;clearInterval(timer);};},[request]);
 useEffect(()=>{if(!ref.current)return;const c=echarts.init(ref.current,'dark',{renderer:'canvas'});chart.current=c;const resize=new ResizeObserver(()=>c.resize());resize.observe(ref.current);c.on('click',p=>{if(p.name&&/^\d{4}-\d{2}-\d{2}$/.test(p.name))setSelected(p.name);});return()=>{resize.disconnect();c.dispose();chart.current=null;};},[]);
 const available=(period==='daily'?report.daily:report.weekly).filter(r=>(!selectedDate||r.date<=selectedDate)&&(!intradayDate||r.date<intradayDate));
 const rows=available.slice(period==='daily'?-90:-60);
 const chosen=selected?rows.find(x=>x.date===selected):period==='daily'&&selectedDate?rows.find(x=>x.date===selectedDate):rows.at(-1);
 useEffect(()=>{if(!chart.current)return;const slots:(Row|null)[]=[];rows.forEach((r,i)=>{if(i&&r.gap_before)slots.push(null);slots.push(r);});const labels=slots.map((r,i)=>r?.date||`gap-${i}`);
  const line=(name:string,key:'boll_mid'|'boll_upper'|'boll_lower',color:string)=>({name,type:'line',showSymbol:false,connectNulls:false,lineStyle:{color,width:1},data:slots.map(d=>d?.[key]??null)});
  chart.current.setOption({animation:false,backgroundColor:'transparent',grid:[{left:65,right:25,top:28,height:'58%'},{left:65,right:25,top:'73%',height:'18%'}],axisPointer:{link:[{xAxisIndex:'all'}]},tooltip:{trigger:'axis',confine:true,formatter:(params:any)=>{const d=slots[params[0]?.dataIndex];return d?`${d.first_date}${d.date!==d.first_date?' 至 '+d.date:''}<br/>开 ${fmt(d.open)}　收 ${fmt(d.close)}<br/>高 ${fmt(d.high)}　低 ${fmt(d.low)}<br/>布林中轨 ${fmt(d.boll_mid)}<br/>上轨 ${fmt(d.boll_upper)}　下轨 ${fmt(d.boll_lower)}<br/>CCI(14) ${fmt(d.cci)}`:'缺少交易日';}},xAxis:[{type:'category',data:labels,axisLabel:{show:false},axisLine:{lineStyle:{color:'#69778a'}}},{type:'category',gridIndex:1,data:labels,axisLabel:{color:'#9eafc7',hideOverlap:true,formatter:(s:string)=>s.startsWith('gap-')?'…':s.slice(5)},axisLine:{lineStyle:{color:'#69778a'}}}],yAxis:[{type:'value',scale:true,axisLabel:{color:'#9eafc7'},splitLine:{lineStyle:{color:'#28313d'}}},{type:'value',gridIndex:1,scale:true,axisLabel:{color:'#9eafc7'},splitLine:{lineStyle:{color:'#28313d'}}}],series:[{name:'上证指数',type:'candlestick',data:slots.map(d=>d?[d.open,d.close,d.low,d.high]:null),itemStyle:{color:'#ef6c73',color0:'#38b99f',borderColor:'#ef6c73',borderColor0:'#38b99f'}},line('BOLL 中轨','boll_mid','#e4bc56'),line('BOLL 上轨','boll_upper','#7c9fca'),line('BOLL 下轨','boll_lower','#7c9fca'),{name:'CCI(14)',type:'line',xAxisIndex:1,yAxisIndex:1,showSymbol:false,connectNulls:false,lineStyle:{color:'#c8a7ed',width:1.5},data:slots.map(d=>d?.cci??null),markLine:{silent:true,symbol:'none',label:{show:false},lineStyle:{color:'#6a7489',type:'dashed'},data:[{yAxis:0}]}}]},true);
 },[report.daily,report.weekly,period,selectedDate,intradayDate]);
 const refresh=async()=>{setBusy(true);setError('');try{const j=await request<{job:string}>('index_technical_refresh');for(;;){const r=await request<{status:string;error?:string;result?:Report}>('job',{job:j.job});if(!alive.current)return;if(r.status==='failed')throw Error(r.error);if(r.status==='done'){if(r.result)setReport(r.result);break;}await new Promise(resolve=>setTimeout(resolve,500));}}catch(e){if(alive.current)setError(String(e));}finally{if(alive.current)setBusy(false);}};
 return <section className="option-panel" id="breadth-index-technical" aria-label="上证指数技术参考">
  <div className="option-heading"><div><h3>上证指数技术参考 <small>已结束{period==='daily'?'日':'周'}线</small></h3><p>布林带（20，2 倍标准差） · CCI（14）</p></div><div><label>周期 <select aria-label="指数技术周期" value={period} onChange={e=>{setPeriod(e.target.value as typeof period);setSelected('');}}><option value="daily">日线</option><option value="weekly">周线</option></select></label> <button onClick={refresh} disabled={busy||report.running}>{busy||report.running?'采集中…':'刷新指数参考'}</button></div></div>
  {(error||report.error)&&<div className="breadth-error" role="status">{error||report.error}；保留已有有效数据。</div>}
  <p className="option-note">{selectedDate?`大盘所选日期：${selectedDate}；${intradayDate?'盘中不显示当日及之后收盘数据':period==='daily'?'默认显示同日收盘':'默认显示该日之前（含当日）最近的完整周线'}，图表不显示该日期之后的数据。`:'未选择大盘日期，显示最新已结束行情。'}点击图表可查看更早的日期。</p>
  <div className="option-readout"><div><span>{chosen?.date||selectedDate||'暂无日期'} · 收盘</span><strong>{fmt(chosen?.close)}</strong></div><div><span>布林中轨 / 上轨 / 下轨</span><strong>{chosen?`${fmt(chosen.boll_mid)} / ${fmt(chosen.boll_upper)} / ${fmt(chosen.boll_lower)}`:'—'}</strong></div><div><span>CCI（14）</span><strong>{fmt(chosen?.cci)}</strong></div></div>
  <div className="index-technical-chart" ref={ref} role="img" aria-label="上证指数K线、布林带和CCI"/>
  {!chosen&&<p className="option-missing">{selectedDate?`所选日期${period==='daily'?'没有同日指数收盘数据':'之前没有完整周线数据'}。`:'暂无完整的指数数据。'}</p>}
  <div className="option-note">独立技术参照：使用腾讯上证指数日线，周线由完整交易周合成；缺日不连线，布林带与 CCI 分别需要 20 和 14 根连续K线。BOLL 采用简单均值和总体标准差；CCI 使用典型价格和平均绝对偏差。{report.collected_at&&<> 数据采集于 {report.collected_at.slice(0,19).replace('T',' ')} 北京时间；历史补采不代表当时已可获取。</>}</div>
 </section>;
}
