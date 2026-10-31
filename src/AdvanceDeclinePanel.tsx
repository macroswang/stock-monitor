import React,{useEffect,useRef} from 'react';
import * as echarts from 'echarts';
import type {BreadthDay} from './MarketBreadth';

const num=(value:number|null|undefined,digits=0)=>value==null||!Number.isFinite(value)?'—':value.toLocaleString('zh-CN',{minimumFractionDigits:digits,maximumFractionDigits:digits});
const reference=(row:BreadthDay)=>row.status==='closed'&&row.ad_history?row.ad_history:row;

export default function AdvanceDeclinePanel({days,selected,onSelect}:{days:BreadthDay[];selected:BreadthDay|undefined;onSelect:(date:string)=>void}){
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null);
 useEffect(()=>{if(!ref.current)return;const c=echarts.init(ref.current,'dark',{renderer:'canvas'});chart.current=c;const observer=new ResizeObserver(()=>c.resize());observer.observe(ref.current);c.on('click',p=>{if(p.name&&/^\d{4}-\d{2}-\d{2}$/.test(p.name))onSelect(p.name);});return()=>{observer.disconnect();c.dispose();chart.current=null;};},[]);
 useEffect(()=>{
  if(!chart.current)return;
  const slots:(BreadthDay|null)[]=[];
  days.forEach((day,i)=>{if(i&&reference(day).adl_gap_before)slots.push(null);slots.push(day);});
  chart.current.setOption({animation:false,backgroundColor:'transparent',grid:{left:64,right:64,top:30,bottom:38},
   tooltip:{trigger:'axis',confine:true,formatter:(params:any)=>{const row=slots[params[0]?.dataIndex];if(!row)return '数据缺口或口径变化，曲线不连接';const value=reference(row);return `${row.date}${value===row?'':' · 历史参照'}<br/>腾落线：${num(value.adl)}<br/>涨跌家数比：${num(value.adr,2)}<br/>累计起点 ${value.adl_start||'—'}`;}},
   xAxis:{type:'category',data:slots.map((row,i)=>row?.date||`gap-${i}`),axisLabel:{color:'#9eafc7',hideOverlap:true,formatter:(s:string)=>s.startsWith('gap-')?'…':s.slice(5)},axisLine:{lineStyle:{color:'#69778a'}}},
   yAxis:[{type:'value',scale:true,name:'腾落线',axisLabel:{color:'#9eafc7'},splitLine:{lineStyle:{color:'#28313d'}}},{type:'value',scale:true,name:'涨跌比',axisLabel:{color:'#9eafc7'},splitLine:{show:false}}],
   series:[{name:'腾落线 ADL',type:'line',connectNulls:false,showSymbol:true,symbol:'circle',symbolSize:4,lineStyle:{color:'#80b8ff',width:2},itemStyle:{color:'#80b8ff'},data:slots.map(row=>row?reference(row).adl??null:null)},
    {name:'每日涨跌比 ADR',type:'line',yAxisIndex:1,connectNulls:false,showSymbol:true,symbol:'circle',symbolSize:4,lineStyle:{color:'#d8b663',width:1.5},itemStyle:{color:'#d8b663'},data:slots.map(row=>row?reference(row).adr??null:null)}]},true);
 },[days]);
 const selectedReference=selected?reference(selected):undefined;
 return <section className="option-panel" aria-label="腾落线和涨跌比参考">
  <div className="option-heading"><div><h3>腾落线与涨跌比 <small>独立参考</small></h3><p>结合所选日期的市场宽度观察</p></div></div>
  <div className="option-readout"><div><span>{selected?.date||'暂无日期'} · 腾落线{selected&&selectedReference!==selected?'（历史参照）':''}</span><strong>{num(selectedReference?.adl)}</strong></div><div><span>涨跌家数比</span><strong>{num(selectedReference?.adr,2)}</strong></div><div><span>累计起点 / 交易日</span><strong>{selectedReference?.adl_start?`${selectedReference.adl_start} / ${selectedReference.adl_samples} 天`:'—'}</strong></div></div>
  <div className="option-chart" ref={ref} role="img" aria-label="腾落线和每日涨跌家数比曲线"/>
  <div className="breadth-key"><span><i style={{background:'#80b8ff'}}/>腾落线 ADL（左轴）</span><span><i style={{background:'#d8b663'}}/>每日涨跌比 ADR（右轴）</span></div>
  <div className="option-note">ADL 为所示起点以来每日上涨家数减下跌家数的累计，绝对值受起点影响；ADR 为当日上涨家数 ÷ 下跌家数，下跌家数为 0 时留空。遇到缺日、数据不完整或来源变化时重新累计并断线；盘中为暂值。{selected&&selectedReference!==selected&&<>所选日使用单独计算的历史参照，来源：{selectedReference?.source}；未与当前报价拼接。</>}<a href="https://www.fidelity.com/learning-center/trading-investing/advance-decline" target="_blank" rel="noreferrer">ADL 说明</a> · <a href="https://www.tradingview.com/support/solutions/43000589093-advance-decline-ratio/" target="_blank" rel="noreferrer">ADR 说明</a></div>
 </section>;
}
