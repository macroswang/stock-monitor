import React,{useEffect,useRef} from 'react';
import * as echarts from 'echarts';
import reference from '../fixtures/author-chart-reference.json';

type Row={date:string;score:number;breadth:number;trin:number};

export default function AuthorReferenceChart(){
 const ref=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  if(!ref.current)return;
  const chart=echarts.init(ref.current,'dark',{renderer:'canvas'});
  const resize=new ResizeObserver(()=>chart.resize());resize.observe(ref.current);
  const slots:(Row|null)[]=[];
  reference.forEach((r,i)=>{if(i===5)slots.push(null);slots.push(r);});
  chart.setOption({animation:false,backgroundColor:'#202424',
   tooltip:{trigger:'axis',confine:true,formatter:(params:any)=>{const d=slots[params[0]?.dataIndex];return d?`${d.date}<br/>作者评分：${d.score.toFixed(1)}<br/>作者红盘率：${d.breadth.toFixed(1)}%<br/>作者 TRIN：${d.trin.toFixed(2)}`:'截图未提供中间日期';}},
   grid:{left:62,right:68,top:30,bottom:48},
   xAxis:{type:'category',data:slots.map((d,i)=>d?.date||`gap-${i}`),axisLabel:{color:'#9eafc7',hideOverlap:true,formatter:(s:string)=>s.startsWith('gap-')?'…':s.slice(5)},axisLine:{lineStyle:{color:'#69778a'}}},
   yAxis:[{type:'value',name:'评分 / 红盘率',min:0,max:100,axisLabel:{color:'#9eafc7'},splitLine:{lineStyle:{color:'#28313d'}}},{type:'value',name:'TRIN',min:0,max:2,axisLabel:{color:'#b4bd9e'},splitLine:{show:false}}],
   series:[{name:'作者评分',type:'bar',barMaxWidth:50,itemStyle:{color:'#e65d50'},label:{show:true,position:'insideBottom',color:'#fff',fontSize:11,formatter:(p:any)=>p.value==null?'':Number(p.value).toFixed(1)},data:slots.map(d=>d?.score??null)},
    {name:'作者红盘率',type:'line',connectNulls:false,symbol:'circle',symbolSize:6,lineStyle:{color:'#5186e0',width:2},itemStyle:{color:'#5186e0'},label:{show:true,position:'top',color:'#a8c5ef',fontSize:11,formatter:(p:any)=>p.value==null?'':Number(p.value).toFixed(1)+'%'},data:slots.map(d=>d?.breadth??null)},
    {name:'作者TRIN',type:'line',yAxisIndex:1,connectNulls:false,symbol:'circle',symbolSize:6,lineStyle:{color:'#c6d14f',width:2,type:'dashed'},itemStyle:{color:'#c6d14f'},label:{show:true,position:'top',color:'#d2dd8d',fontSize:11,formatter:(p:any)=>p.value==null?'':Number(p.value).toFixed(2)},data:slots.map(d=>d?.trin??null),markLine:{silent:true,symbol:'none',label:{formatter:'1',color:'#b6c57c'},lineStyle:{color:'#929d57',type:'dotted'},data:[{yAxis:1}]}}]});
  return()=>{resize.disconnect();chart.dispose();};
 },[]);
 return <section className="option-panel" aria-label="作者原图数据重绘">
  <div className="option-heading"><div><h3>作者原图数据重绘 <small>截图记录 · 非本机计算</small></h3><p>按视频中可辨认的 10 天数据重绘，缺少的日期断开</p></div></div>
  <div className="option-note">红柱为作者评分，蓝线为作者红盘率，黄绿虚线为作者 TRIN。数值按<a href="https://www.douyin.com/video/7701667092567538511" target="_blank" rel="noreferrer">作者视频截图</a>人工抄录；作者未公开评分公式、股票范围与时点，不能用于计算其他日期或作为交易信号。</div>
  <div className="breadth-chart" ref={ref} role="img" aria-label="作者截图中的评分柱、红盘率与TRIN曲线"/>
  <div className="breadth-key"><span><i style={{background:'#e65d50'}}/>作者评分</span><span><i style={{background:'#5186e0'}}/>作者红盘率</span><span><i style={{background:'#c6d14f'}}/>作者 TRIN（右轴）</span></div>
 </section>;
}
