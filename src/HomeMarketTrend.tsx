import React,{useEffect,useRef,useState} from 'react';
import * as echarts from 'echarts';
import {adjacent,sessionWindow} from './MarketBreadth';
import type {BreadthDay} from './MarketBreadth';
import {breadthCountsConsistent,closedSnapshotReady,intradayBreadth,sameBreadthProvenance,verifiedFlowShare,verifiedTrin} from './intradayMarket';

export default function HomeMarketTrend({days,byAmount}:{days:BreadthDay[];byAmount:boolean}){
 const [span,setSpan]=useState(30),[selected,setSelected]=useState('');
 const [,setClock]=useState(()=>Date.now());
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null);
 const slotsRef=useRef<(BreadthDay|null)[]>([]);
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),15000);return()=>clearInterval(timer);},[]);
 useEffect(()=>{
  if(!ref.current)return;
  const instance=echarts.init(ref.current,'dark',{renderer:'canvas'});chart.current=instance;
  instance.getZr().on('click',event=>{
   const grid=instance.containPixel({gridIndex:0},[event.offsetX,event.offsetY])?0:instance.containPixel({gridIndex:1},[event.offsetX,event.offsetY])?1:-1;
   if(grid<0)return;
   const index=instance.convertFromPixel({xAxisIndex:grid},event.offsetX);
   const row=Number.isInteger(index)?slotsRef.current[index]:null;
   if(row)setSelected(row.date);
  });
  const observer=new ResizeObserver(()=>instance.resize());observer.observe(ref.current);
  return()=>{observer.disconnect();instance.dispose();chart.current=null;};
 },[]);
 const window=sessionWindow(days,span), rows=window.rows, now=Date.now();
 const usable=(d:BreadthDay)=>d.missing===0&&d.expected>0&&d.covered===d.expected&&breadthCountsConsistent(d)&&
  ((d.status==='closed'&&closedSnapshotReady(d,now))||(d.status==='provisional'&&!!intradayBreadth(d,now)));
 // Match the current-advice gate: an absent share does not invalidate a
 // independently checked TRIN, but a reported share that contradicts its
 // underlying totals makes the structure untrustworthy.
 const structureTrin=(d:BreadthDay)=>{
  const reported=byAmount?d.advancing_amount_percent:d.advancing_volume_percent;
  return reported!=null&&verifiedFlowShare(d,byAmount)===null?null:verifiedTrin(d,byAmount);
 };
 const slots:(BreadthDay|null)[]=[];
 rows.forEach((d,i)=>{const p=rows[i-1];if(i&&(!adjacent(p.date,d.date)||!sameBreadthProvenance(p,d)))slots.push(null);slots.push(d);});
 slotsRef.current=slots;
 const validCount=rows.filter(d=>usable(d)&&verifiedTrin(d,byAmount)!==null&&verifiedFlowShare(d,byAmount)!==null).length;
 const selectedDay=rows.find(d=>d.date===selected)??rows.at(-1);
 const selectedTrin=selectedDay&&usable(selectedDay)?structureTrin(selectedDay):null;
 const selectedBreadth=selectedDay&&usable(selectedDay)?selectedDay.advancing_percent:null;
 const selectedShare=selectedDay&&usable(selectedDay)?verifiedFlowShare(selectedDay,byAmount):null;
 const flatMajority=!!selectedDay&&selectedDay.flat>(selectedDay.advance+selectedDay.decline+selectedDay.flat)/2;
 const combination=selectedDay&&selectedTrin!==null?(flatMajority?'多数股票平盘，涨跌组的成交对比仅覆盖少数股票。':selectedDay.advancing_percent!<20&&selectedTrin<0.7?'上涨股票很少，但这部分股票平均成交较大。':selectedDay.advancing_percent!>=50&&selectedTrin<0.7?'上涨范围较广，上涨股平均成交也较大。':selectedTrin<0.9?'上涨股平均成交较高。':selectedTrin<=1.1?'涨跌两组平均成交相近。':'下跌股平均成交较高。'):'';
 const reading=selectedDay&&usable(selectedDay)&&selectedTrin!==null?`${selectedDay.date} · ${selectedDay.status==='provisional'?'盘中暂值':'收盘'}：上涨 ${selectedDay.advancing_percent!.toFixed(1)}% · TRIN ${selectedTrin.toFixed(3)}。${combination}`:selectedDay?`${selectedDay.date} · 数据不足，暂无法解读。`:'暂无可解读的市场数据。';
 useEffect(()=>{
  if(!chart.current)return;
  chart.current.setOption({backgroundColor:'transparent',animation:false,
   grid:[{left:43,right:35,top:10,height:105},{left:43,right:35,top:137,height:65}],
   axisPointer:{link:[{xAxisIndex:[0,1]}]},
   tooltip:{trigger:'axis',confine:true,backgroundColor:'#162238',borderColor:'#34465e',textStyle:{color:'#e7edf7',fontSize:12},formatter:(params:any)=>{
    const d=slots[params[0]?.dataIndex];if(!d)return '数据间隔';if(!usable(d))return `${d.date} · 数据暂不可用`;
    const share=verifiedFlowShare(d,byAmount),trin=structureTrin(d);
    return `${d.date}${d.status==='provisional'?' · 盘中暂值':''}<br/>上涨股票：${d.advancing_percent!.toFixed(1)}%<br/>上涨股${byAmount?'成交额':'成交量'}占比：${share==null?'—':share.toFixed(1)+'%'}<br/>TRIN：${trin==null?'—':trin.toFixed(3)}`;
   }},
   xAxis:[{type:'category',gridIndex:0,data:slots.map((d,i)=>d?.date||`gap-${i}`),axisLabel:{show:false},axisTick:{show:false},axisLine:{lineStyle:{color:'#69778a'}}},{type:'category',gridIndex:1,data:slots.map((d,i)=>d?.date||`gap-${i}`),axisLabel:{color:'#9eafc7',hideOverlap:true,formatter:(s:string)=>s.startsWith('gap-')?'…':s.slice(5)},axisTick:{show:false},axisLine:{lineStyle:{color:'#69778a'}}}],
   yAxis:[{type:'value',gridIndex:0,min:0,max:100,splitNumber:2,axisLabel:{formatter:'{value}%',color:'#9eafc7',fontSize:10},splitLine:{lineStyle:{color:'#28313d'}}},{type:'value',gridIndex:1,min:0,max:(range:{max:number})=>Math.max(1.5,Math.ceil(range.max*1.1*2)/2),axisLabel:{color:'#b4bd9e',fontSize:10},splitLine:{show:false}}],
   series:[
    {name:`上涨股${byAmount?'成交额':'成交量'}占比`,type:'bar',barMaxWidth:28,data:slots.map(d=>d&&usable(d)?{value:verifiedFlowShare(d,byAmount),itemStyle:{color:'#e65d50',opacity:d.status==='closed'?1:.55}}:null)},
    {name:'上涨家数占比',type:'line',connectNulls:false,symbol:'none',lineStyle:{color:'#76aaff',width:2},markLine:{silent:true,symbol:'none',label:{show:true,formatter:'一半上涨',color:'#a8b5c6',position:'insideEndTop'},lineStyle:{color:'#6c7888',type:'dashed'},data:[{yAxis:50}]},data:slots.map(d=>d&&usable(d)?d.advancing_percent:null)},
    {name:'TRIN',type:'line',xAxisIndex:1,yAxisIndex:1,connectNulls:false,symbol:'none',lineStyle:{color:'#c6d14f',width:2},markLine:{silent:true,symbol:'none',label:{show:true,formatter:'TRIN 1.0',color:'#a8b5c6',position:'insideEndTop'},lineStyle:{color:'#6c7888',type:'dashed'},data:[{yAxis:1}]},data:slots.map(d=>d&&usable(d)?structureTrin(d):null)}
   ]
  },true);
 },[days,span,byAmount,now]);
 return <section className="home-market-trend" aria-label="首页市场趋势">
  <div className="home-trend-header"><div><strong>市场趋势</strong><small>{rows.length?`${window.known?'最近'+span+'个交易日 · ':'按记录数展示 · '}${window.start||rows[0].date} 至 ${rows.at(-1)!.date} · 有效 ${validCount} 条`:'暂无完整数据'}</small></div><div className="market-trend-ranges" role="group" aria-label="首页图表时间范围">{[30,60,90].map(n=><button key={n} type="button" aria-pressed={span===n} onClick={()=>{setSpan(n);if(selected&&!sessionWindow(days,n).rows.some(d=>d.date===selected))setSelected('');}}>{n}日</button>)}</div></div>
  <div className="home-trend-metrics" aria-label="同日市场指标"><span><i style={{background:'#76aaff'}}/>上涨股票 <strong>{selectedBreadth==null?'—':`${selectedBreadth.toFixed(1)}%`}</strong></span><span><i style={{background:'#e65d50'}}/>上涨股{byAmount?'成交额':'成交量'}占比 <strong>{selectedShare==null?'—':`${selectedShare.toFixed(1)}%`}</strong></span><span><i style={{background:'#c6d14f'}}/>TRIN <strong>{selectedTrin==null?'—':selectedTrin.toFixed(3)}</strong></span></div>
  <div className="home-trend-explanation"><span>上图比较上涨股票与成交占比，成交占比不含平盘；下图查看 TRIN。三项按同一日期对齐。</span><small>点击图表查看当日解读 · 数据缺失处断开</small></div>
  <div ref={ref} className="home-trend-chart" role="img" aria-label="首页上涨家数、成交占比与TRIN趋势"/>
  <div className="home-trend-reading" aria-label="首页趋势解读"><span>{reading}</span>{selectedDay&&selectedDay.date!==rows.at(-1)?.date&&<><small>历史数据，操作参考以首页上方为准。</small><button type="button" onClick={()=>setSelected('')}>查看最新</button></>}</div>
 </section>;
}
