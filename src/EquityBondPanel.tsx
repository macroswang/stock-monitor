import React,{useEffect,useRef,useState} from 'react';
import * as echarts from 'echarts';

type Row={date:string;pe:number;bond_yield:number;spread:number;collected_at:string;gap_before:boolean};
type Report={days:Row[];running:boolean;error:string;latest_eligible:string|null};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const fmt=(v:number|null|undefined,n=2)=>v==null||!Number.isFinite(v)?'—':v.toFixed(n);

export default function EquityBondPanel({request,selectedDate,intradayDate}:{request:Request;selectedDate:string;intradayDate:string}){
 const [report,setReport]=useState<Report>({days:[],running:false,error:'',latest_eligible:null});
 const [error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [chosenDate,setChosenDate]=useState(selectedDate);
 useEffect(()=>{setChosenDate(selectedDate);},[selectedDate]);
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null),alive=useRef(true),reading=useRef(false);
 const load=async()=>{if(reading.current)return;reading.current=true;try{const data=await request<Report>('equity_bond');if(alive.current){setReport(data);setError('');}}catch(e){if(alive.current)setError(String(e));}finally{reading.current=false;}};
 useEffect(()=>{alive.current=true;void load();const timer=setInterval(load,30000);return()=>{alive.current=false;clearInterval(timer);};},[request]);
 useEffect(()=>{if(!ref.current)return;const c=echarts.init(ref.current,'dark',{renderer:'canvas'});chart.current=c;const resize=new ResizeObserver(()=>c.resize());resize.observe(ref.current);return()=>{resize.disconnect();c.dispose();chart.current=null;};},[]);
 useEffect(()=>{if(!chart.current)return;const slots:(Row|null)[]=[];report.days.filter(r=>(!chosenDate||r.date<=chosenDate)&&(!intradayDate||r.date<intradayDate)).forEach((r,i)=>{if(i&&r.gap_before)slots.push(null);slots.push(r);});
  chart.current.setOption({animation:false,backgroundColor:'transparent',grid:{left:54,right:28,top:22,bottom:38},tooltip:{trigger:'axis',confine:true,formatter:(params:any)=>{const d=slots[params[0]?.dataIndex];return d?`${d.date}<br/>上交所股票市盈率：${fmt(d.pe)} 倍<br/>国债 10 年（11:30）：${fmt(d.bond_yield,4)}%<br/>股债差：${fmt(d.spread)} 个百分点`:'数据间隔';}},xAxis:{type:'category',data:slots.map((d,i)=>d?.date||`gap-${i}`),axisLabel:{color:'#9eafc7',hideOverlap:true,formatter:(s:string)=>s.startsWith('gap-')?'…':s.slice(5)},axisLine:{lineStyle:{color:'#69778a'}}},yAxis:{type:'value',scale:true,axisLabel:{color:'#9eafc7'},splitLine:{lineStyle:{color:'#28313d'}}},series:[{name:'股债差',type:'line',connectNulls:false,symbol:'circle',symbolSize:5,lineStyle:{color:'#80b8ff',width:2},itemStyle:{color:'#80b8ff'},data:slots.map(d=>d?.spread??null)}]},true);
 },[report.days,chosenDate,intradayDate]);
 const refresh=async()=>{setBusy(true);setError('');try{const job=await request<{job:string}>('equity_bond_refresh');for(;;){const r=await request<{status:string;error?:string;result?:Report}>('job',{job:job.job});if(!alive.current)return;if(r.status==='failed')throw Error(r.error);if(r.status==='done'){if(r.result)setReport(r.result);break;}await new Promise(resolve=>setTimeout(resolve,500));}}catch(e){if(alive.current)setError(String(e));}finally{if(alive.current)setBusy(false);}};
 const available=report.days.filter(r=>!intradayDate||r.date<intradayDate);
 const chosen=chosenDate?available.find(r=>r.date===chosenDate):available.at(-1);
 return <section className="option-panel" id="breadth-equity-bond" aria-label="股债估值参考">
  <div className="option-heading"><div><h3>股债估值参考 <small>沪市股票 · 10年国债</small></h3><p>100 ÷ 上交所股票平均市盈率 − 十年期国债收益率，单位：百分点</p></div><div><label>日期 <select aria-label="股债参考日期" value={chosenDate||chosen?.date||''} onChange={e=>setChosenDate(e.target.value)}>{chosenDate&&!chosen&&<option value={chosenDate}>{chosenDate}（无数据）</option>}{available.slice().reverse().map(r=><option key={r.date} value={r.date}>{r.date}</option>)}</select></label> <button onClick={refresh} disabled={busy||report.running}>{busy||report.running?'采集中…':'刷新股债参考'}</button></div></div>
  {(error||report.error)&&<div className="breadth-error" role="status">{error||report.error}；保留已有有效数据。</div>}
  <div className="option-readout"><div><span>{chosenDate||chosen?.date||'暂无统计日期'} · 股债差</span><strong>{chosen?`${fmt(chosen.spread)} 个百分点`:'—'}</strong></div><div><span>上交所股票平均市盈率</span><strong>{chosen?`${fmt(chosen.pe)} 倍`:'—'}</strong></div><div><span>国债 10 年收益率（11:30）</span><strong>{chosen?`${fmt(chosen.bond_yield,4)}%`:'—'}</strong></div></div>
  {!chosen&&<p className="option-missing">{intradayDate&&chosenDate>=intradayDate?'盘中不显示当日及之后的收盘股债参考。':chosenDate?'所选日期没有两项齐全的数据。':'暂无已核验的股债参照数据。'}</p>}
  <div className="option-chart" ref={ref} role="img" aria-label="沪市股票和十年国债估值差曲线"/>
  <div className="option-note">独立参照：上交所“股票”统计包含主板 A、B 股和科创板，并非沪深全市场；国债为中国货币网 11:30 报价曲线均值，与市盈率时点不同。{chosenDate&&'图表仅显示所选日期及之前的数据。'}市盈率倒数为估值指标，非实际收益或资金流向。{chosen&&<> 数据采集于 {chosen.collected_at.slice(0,19).replace('T',' ')} 北京时间，补采不代表当时可得。</>} <a href="https://www.sse.com.cn/market/stockdata/overview/day/" target="_blank" rel="noreferrer">上交所</a> · <a href="https://www.chinamoney.com.cn/chinese/sddsintigy/" target="_blank" rel="noreferrer">中国货币网</a></div>
 </section>;
}
