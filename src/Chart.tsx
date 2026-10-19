import {useEffect,useRef} from 'react';
import * as echarts from 'echarts';
import type {Bar,Daily,Event,IndexMinute} from './models';
import {price,wan,wanShares} from './format';
export default function Chart({minute=[],daily=[],view,events=[],selectedDay,onSelectDay,onOpenDay,onMove,compact=false,benchmark,previousClose,buySignals=[]}:{buySignals?:{key:string;time:string;price:number}[];benchmark?:IndexMinute|null;previousClose?:number;minute?:Bar[];daily?:Daily[];view:string;events?:Event[];selectedDay?:string;onSelectDay?:(day:string)=>void;onOpenDay?:(day:string)=>void;onMove?:(direction:number)=>void;compact?:boolean}){
 const contentKey=JSON.stringify([minute.map(b=>[b.time,b.close,b.volume,b.complete,b.average]),daily.map(b=>[b.date,b.open,b.close,b.low,b.high,b.volume,b.provisional]),view,events.map(e=>[e.key,e.trading_date,e.event_label]),selectedDay,benchmark,previousClose,buySignals]);
 const open=useRef(onOpenDay);open.current=onOpenDay;const plot=useRef({daily,view});plot.current={daily,view};
 const windowDates=useRef<string[]>([]);const lastDailyDate=useRef('');
 const ref=useRef<HTMLDivElement>(null);const instance=useRef<echarts.ECharts|null>(null);const labelsKey=useRef('');const select=useRef(onSelectDay);select.current=onSelectDay;
 useEffect(()=>{if(!ref.current)return;const chart=echarts.init(ref.current,undefined,{renderer:'canvas'});instance.current=chart;
  chart.on('click',params=>{if(params.componentType==='series'&&params.name&&/^\d{4}-\d{2}-\d{2}$/.test(params.name))select.current?.(params.name);});
  chart.on('dblclick',params=>{if(plot.current.view==='daily'&&params.componentType==='series'&&params.name)open.current?.(params.name);});
  chart.on('datazoom',()=>{const z=(chart.getOption()?.dataZoom as {start?:number;end?:number}[])?.[0];const d=plot.current.daily;if(plot.current.view==='daily'&&d.length&&z)windowDates.current=[d[Math.round((d.length-1)*(z.start??0)/100)]?.date,d[Math.round((d.length-1)*(z.end??100)/100)]?.date];});
  const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);
  return()=>{observer.disconnect();chart.dispose();instance.current=null;};
 },[]);
 useEffect(()=>{
  const chart=instance.current;if(!chart)return;const isDay=view==='daily';const labels=isDay?daily.map(b=>b.date):minute.map(b=>b.time);
  const volume=isDay?daily.map(b=>+b.volume/10000):minute.map(b=>b.volume/100);
  const colors=isDay?daily.map(b=>+b.close>=+b.open?'#ef6568':'#36b898'):minute.map((b,i)=>i===0||+b.close>=+minute[i-1].close?'#ef6568':'#36b898');
  const indexByTime=new Map(benchmark?.bars.map(b=>[b.time,+b.close])||[]);
  const canOverlay=!isDay&&!!benchmark&&!!previousClose&&previousClose>0&&+benchmark.previous_close>0;
  const indexLine=minute.map(b=>canOverlay&&indexByTime.has(b.time)?indexByTime.get(b.time)!/+benchmark!.previous_close*previousClose!:null);
  const averages=minute.map(b=>b.average&&Number.isFinite(+b.average)&&+b.average>0?+b.average:null);
  const marks=isDay?daily.filter(b=>events.some(e=>e.trading_date===b.date)).map(b=>({coord:[b.date,+b.high],value:String(events.filter(e=>e.trading_date===b.date).length)})):
    events.filter(e=>labels.includes(e.event_label.slice(0,5))).map(e=>({coord:[e.event_label.slice(0,5),minute.find(b=>b.time===e.event_label.slice(0,5))?.close],value:'触发'}));
  const key=view+labels.join('|');const old=chart.getOption()?.dataZoom as {start?:number;end?:number}[]|undefined;
  let zoom=key===labelsKey.current?{start:old?.[0]?.start??0,end:old?.[0]?.end??100}:{start:0,end:100};labelsKey.current=key;
  if(isDay&&labels.length){let lo=windowDates.current.length?Math.max(0,labels.indexOf(windowDates.current[0])):Math.max(0,labels.length-60);let hi=windowDates.current.length?labels.indexOf(windowDates.current[1]):labels.length-1;if(hi<lo)hi=Math.min(labels.length-1,lo+59);if(lastDailyDate.current&&windowDates.current[1]===lastDailyDate.current&&labels.at(-1)!==lastDailyDate.current){const width=hi-lo;hi=labels.length-1;lo=Math.max(0,hi-width);}lastDailyDate.current=labels.at(-1)||'';const idx=labels.indexOf(selectedDay||'');const width=hi-lo;if(idx>=0&&idx<lo){lo=idx;hi=Math.min(labels.length-1,lo+width);}else if(idx>hi){hi=idx;lo=Math.max(0,hi-width);}zoom={start:lo/Math.max(1,labels.length-1)*100,end:hi/Math.max(1,labels.length-1)*100};windowDates.current=[labels[lo],labels[hi]];}
  chart.setOption({backgroundColor:'transparent',animation:false,textStyle:{color:'#9dacc5',fontFamily:'sans-serif'},
   legend:{show:!isDay,data:['价格','均价',...(canOverlay?['上证走势']:[])],top:0,textStyle:{color:'#9dacc5'}},
   tooltip:{trigger:'axis',confine:true,axisPointer:{type:'cross'},backgroundColor:'#162238',borderColor:'#34465e',textStyle:{color:'#e7edf7'},
    formatter:(params:unknown)=>{const first=(Array.isArray(params)?params[0]:params) as {dataIndex?:number}|undefined;const idx=first?.dataIndex??-1;const root=document.createElement('div');root.className='quote-tooltip';
     const rows:string[]=[];if(isDay){const b=daily[idx];if(b){rows.push(b.provisional?b.date+' · 盘中日K（未收盘）':b.date,`开盘：${price(b.open)} 元`,`收盘：${price(b.close)} 元`,`最高：${price(b.high)} 元`,`最低：${price(b.low)} 元`,`成交量：${wanShares(b.volume)} 万股`);const n=events.filter(e=>e.trading_date===b.date).length;if(n)rows.push(`触发：${n} 次`);rows.push('双击查看当天分时 · 左右键逐日浏览');}}
     else{const b=minute[idx];if(b)rows.push(b.time,`价格：${price(b.close)} 元`,`均价：${b.average&&Number.isFinite(+b.average)?price(b.average)+' 元':'暂无成交额数据'}`,`分钟量：${wan(b.volume/100)} 手`,b.complete?'已结束分钟':'当前分钟（未结束）');if(b&&canOverlay&&indexByTime.has(b.time)){const v=indexByTime.get(b.time)!;rows.push(`上证：${v.toFixed(2)} 点（${(v/+benchmark!.previous_close*100-100).toFixed(2)}%）`);}}
     for(const text of rows){const row=document.createElement('div');row.textContent=text;root.appendChild(row);}return root;}
   },axisPointer:{link:[{xAxisIndex:'all'}]},grid:[{left:65,right:35,top:30,height:'55%'},{left:65,right:35,top:'72%',height:'17%'}],
   xAxis:[{type:'category',data:labels,boundaryGap:isDay,axisLine:{lineStyle:{color:'#2a374c'}},axisLabel:{hideOverlap:true}},{type:'category',gridIndex:1,data:labels,axisLabel:{show:false},axisLine:{lineStyle:{color:'#2a374c'}}}],
   yAxis:[{scale:true,splitLine:{lineStyle:{color:'#202c40'}},axisLabel:{formatter:(n:number)=>n.toFixed(2)}},{scale:true,gridIndex:1,splitNumber:2,name:isDay?'成交量（万股）':'成交量（手）',splitLine:{lineStyle:{color:'#202c40'}},axisLabel:{formatter:(n:number)=>isDay?wan(n):n>=10000?(n/10000).toFixed(1)+'万':n.toFixed(0)}}],
   dataZoom:[{type:'inside',xAxisIndex:[0,1],...zoom},{type:'slider',xAxisIndex:[0,1],...zoom,bottom:1,height:18,borderColor:'#28354b',fillerColor:'rgba(82,138,230,.14)'}],
   series:[isDay?{name:'日K',type:'candlestick',data:daily.map(b=>[+b.open,+b.close,+b.low,+b.high]),itemStyle:{color:'#ef6568',color0:'#36b898',borderColor:'#ef6568',borderColor0:'#36b898'},markPoint:{symbolSize:34,label:{fontSize:10},itemStyle:{color:'#dba853'},data:marks},markLine:{symbol:'none',silent:true,label:{show:false},lineStyle:{color:'#8baeed',type:'dashed'},data:selectedDay&&labels.includes(selectedDay)?[{xAxis:selectedDay}]:[]}}:
    {name:'价格',type:'line',data:minute.map(b=>+b.close),showSymbol:false,z:5,lineStyle:{color:'#8cbcff',width:2.4},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(83,139,230,.16)'},{offset:1,color:'rgba(83,139,230,0)'}])},markPoint:{symbol:'pin',symbolSize:38,itemStyle:{color:'#e9ad58'},label:{fontSize:10},data:[...marks,...buySignals.filter(e=>labels.includes(e.time)).map(e=>({coord:[e.time,e.price],value:'买研',symbol:'triangle',symbolSize:20,itemStyle:{color:'#69d9ac'},label:{position:'bottom',color:'#69d9ac',fontSize:10}}))]}},
    ...(canOverlay?[{name:'上证走势',type:'line',data:indexLine,showSymbol:false,connectNulls:false,z:2,lineStyle:{color:'#929aa9',width:1.2,type:'dashed',opacity:0.8},itemStyle:{color:'#929aa9'}}]:[]),
    ...(!isDay?[{name:'均价',type:'line',data:averages,showSymbol:false,connectNulls:false,lineStyle:{color:'#e9b949',width:1.5},itemStyle:{color:'#e9b949'}}]:[]),
    {name:isDay?'成交量（万股）':'分钟量（手）',type:'bar',xAxisIndex:1,yAxisIndex:1,data:volume.map((v,i)=>({value:v,itemStyle:{color:colors[i]}}))}]
  },{notMerge:true});
  if(isDay&&selectedDay){const index=labels.indexOf(selectedDay);if(index>=0)chart.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:index});}
 },[contentKey]);
 return <><div className={'chart'+(compact?' compact-chart':'')} ref={ref} tabIndex={view==='daily'?0:undefined} onClick={()=>{if(view==='daily')ref.current?.focus();}} onKeyDown={e=>{if(view==='daily'&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();onMove?.(e.key==='ArrowLeft'?-1:1);}else if(view==='daily'&&e.key==='Enter'&&selectedDay)onOpenDay?.(selectedDay);}} aria-label={view==='daily'?'日K线及成交量':'分时价格及分钟成交量'}/>{view!=='daily'&&<div className="average-caption">亮蓝实线：个股 · 黄线：均价（累计成交额 ÷ 累计成交股数，含集合竞价）{benchmark&&previousClose&&previousClose>0?' · 灰色虚线：上证（以双方昨收涨跌幅对齐）':' · 上证叠加暂无对应日期分时或昨收数据'}{minute.some(b=>b.average&&Number.isFinite(+b.average)&&+b.average>0)?'':' · 当前缓存缺少成交额，暂无法显示均价线'}</div>}</>;
}
