import React,{useEffect,useRef} from 'react';
import * as echarts from 'echarts';
import type {MarketData} from './models';
import type {QuoteView} from './marketOverview';

const labels=[...Array.from({length:121},(_,i)=>570+i),...Array.from({length:121},(_,i)=>780+i)].map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
const labelSet=new Set(labels);

export default function HomeIndexTrend({market,index,now,name='上证'}:{market:MarketData;index:QuoteView|null;now:number;name?:string}){
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null);
 const minute=market.minute,base=Number(minute?.previous_close),stamp=Date.parse(minute?.cached_at||market.collected_at||'');
 const raw=minute?.bars||[],times=raw.map(row=>row.time);
 const valid=!!index&&!!minute&&minute.source==='tencent'&&minute.date===index.quote.timestamp.slice(0,10)&&Number.isFinite(base)&&base>0&&
  Math.abs(base-Number(index.quote.previous_close))<=0.021&&Number.isFinite(stamp)&&stamp<=now+5000&&
  raw.length>0&&times.every((t,i)=>labelSet.has(t)&&(i===0||times[i-1]<t))&&raw.every(row=>Number.isFinite(Number(row.close))&&Number(row.close)>0)&&
  raw.every(row=>Date.parse(`${minute.date}T${row.time}:00+08:00`)<=now+5000)&&!market.error?.includes('上证分时');
 useEffect(()=>{if(!ref.current)return;const instance=echarts.init(ref.current,'dark',{renderer:'canvas'});chart.current=instance;const observer=new ResizeObserver(()=>instance.resize());observer.observe(ref.current);return()=>{observer.disconnect();instance.dispose();chart.current=null;};},[]);
 useEffect(()=>{
  if(!chart.current)return;
  const points=new Map(valid?raw.map(row=>[row.time,Number(row.close)]):[]);
  const values=labels.map(t=>points.has(t)?(points.get(t)!/base-1)*100:null);
  chart.current.setOption({backgroundColor:'transparent',animation:false,grid:{left:42,right:12,top:8,bottom:21},
   tooltip:{trigger:'axis',confine:true,backgroundColor:'#162238',borderColor:'#34465e',textStyle:{color:'#e7edf7',fontSize:11},formatter:(items:any)=>{const item=items[0],t=item?.axisValue,n=points.get(t);return n==null?`${t} · 暂无行情`:`${t}<br/>${name} ${n.toFixed(2)} 点<br/>涨跌 ${(n/base-1)*100>=0?'+':''}${((n/base-1)*100).toFixed(2)}%`; }},
   xAxis:{type:'category',boundaryGap:false,data:labels,axisTick:{show:false},axisLine:{lineStyle:{color:'#506178'}},axisLabel:{fontSize:9,color:'#94a8c2',interval:(_i:number,t:string)=>['09:30','10:30','11:30','14:00','15:00'].includes(t),formatter:(t:string)=>t==='11:30'?'11:30/13:00':t}},
   yAxis:{type:'value',scale:true,splitNumber:2,axisLabel:{fontSize:9,color:'#94a8c2',formatter:(v:number)=>`${v>0?'+':''}${v.toFixed(1)}%`},splitLine:{lineStyle:{color:'#29384b'}}},
   series:[{name:`${name}分时涨跌幅`,type:'line',symbol:'none',connectNulls:false,lineStyle:{color:'#84b8ff',width:1.5},data:values,markLine:{silent:true,symbol:'none',label:{show:false},lineStyle:{color:'#687a92',type:'dashed'},data:[{yAxis:0}]}}]
  },true);
 },[minute,index,now,market.error,market.collected_at,name]);
 const stale=index?.kind==='cached'||(index?.kind==='live'&&valid&&(now-stamp>150000||now-Date.parse(`${minute!.date}T${raw.at(-1)!.time}:00+08:00`)>150000));
 return <div className="overview-index-trend"><div className="overview-chart-heading"><strong>{name}分时</strong><span>{valid?`${minute!.date} · 截至 ${raw.at(-1)!.time}${stale?' · 缓存':''}`:'分时数据暂不可用'}</span></div><div ref={ref} className="overview-index-chart" role="img" aria-label={`${name}当日分时涨跌幅`}/></div>;
}
