import {useEffect,useRef,useState} from 'react';
import * as echarts from 'echarts';
import type {Bar,Daily,Event,IndexMinute} from './models';
import {price,wan,wanShares} from './format';
import {topVolumeMarks} from './volumeMarks';
import {dailyGaps} from './dailyGaps';
import {defaultTCosts,tProfit} from './tCosts';
import type {TCosts} from './tCosts';
import TCostSettings from './TCostSettings';
import {appendTradeTooltip} from './tradeTooltip';
export default function Chart({minute=[],daily=[],view,events=[],selectedDay,onSelectDay,onOpenDay,onMove,compact=false,benchmark,previousClose,buySignals=[]}:{buySignals?:{key:string;time:string;price:number}[];benchmark?:IndexMinute|null;previousClose?:number;minute?:Bar[];daily?:Daily[];view:string;events?:Event[];selectedDay?:string;onSelectDay?:(day:string)=>void;onOpenDay?:(day:string)=>void;onMove?:(direction:number)=>void;compact?:boolean}){
 const [costs,setCosts]=useState<TCosts>(()=>{try{const saved=JSON.parse(localStorage.getItem('stock-monitor-t-costs-v4')||'null');return saved&&tProfit(10,10,saved)?saved:defaultTCosts;}catch{return defaultTCosts;}});
 const [showOpening,setShowOpening]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-opening')!=='false';}catch{return true;}});
 const costsRef=useRef(costs);costsRef.current=costs;
 const refreshTrade=useRef<(()=>void)|null>(null);
 const updateCosts=(next:TCosts)=>{costsRef.current=next;setCosts(next);refreshTrade.current?.();if(tProfit(10,10,next)){try{localStorage.setItem('stock-monitor-t-costs-v4',JSON.stringify(next));}catch{}}};
 const scope=view+'|'+(selectedDay||events[0]?.trading_date||'');
 const [choice,setChoice]=useState<{scope:string;time:string;price:number}|null>(null);
 useEffect(()=>setChoice(null),[scope]);
 const visibleMarks=view==='daily'?[]:topVolumeMarks(minute,events,showOpening);
 const latestEvent=events.filter(e=>visibleMarks.some(m=>m.coord[0]===e.candidate_time)).sort((a,b)=>a.event_label.localeCompare(b.event_label)||a.candidate_time.localeCompare(b.candidate_time)).at(-1);
 const latestMark=visibleMarks.find(m=>m.coord[0]===latestEvent?.candidate_time);
 const chosen=choice?.scope===scope&&visibleMarks.some(m=>m.coord[0]===choice.time)?choice:latestMark?{scope,time:latestMark.coord[0],price:latestMark.coord[1]}:null;
 const scopeRef=useRef(scope);scopeRef.current=scope;
 const contentKey=JSON.stringify([minute.map(b=>[b.time,b.close,b.volume,b.complete,b.average]),daily.map(b=>[b.date,b.open,b.close,b.low,b.high,b.volume,b.provisional]),view,events.map(e=>[e.key,e.trading_date,e.candidate_time,e.confirmation_label,e.event_label,e.mode]),selectedDay,benchmark,previousClose,buySignals,chosen,showOpening]);
 const open=useRef(onOpenDay);open.current=onOpenDay;const plot=useRef({daily,view});plot.current={daily,view};
 const windowDates=useRef<string[]>([]);const lastDailyDate=useRef('');
 const ref=useRef<HTMLDivElement>(null);const instance=useRef<echarts.ECharts|null>(null);const labelsKey=useRef('');const select=useRef(onSelectDay);select.current=onSelectDay;
 useEffect(()=>{if(!ref.current)return;const chart=echarts.init(ref.current,undefined,{renderer:'canvas'});instance.current=chart;
  chart.on('click',params=>{
   if(plot.current.view!=='daily'&&params.componentType==='markPoint'){
    const data=params.data as {value?:unknown;coord?:[string,number]}|undefined;
    if((data?.value==='触发'||data?.value==='开盘量')&&data.coord&&Number.isFinite(+data.coord[1])&&+data.coord[1]>0)setChoice({scope:scopeRef.current,time:data.coord[0],price:+data.coord[1]});
   }
   if(params.componentType==='series'&&params.name&&/^\d{4}-\d{2}-\d{2}$/.test(params.name))select.current?.(params.name);
  });
  chart.on('dblclick',params=>{if(plot.current.view==='daily'&&params.componentType==='series'&&params.name)open.current?.(params.name);});
  chart.on('datazoom',()=>{const z=(chart.getOption()?.dataZoom as {start?:number;end?:number}[])?.[0];const d=plot.current.daily;if(plot.current.view==='daily'&&d.length&&z)windowDates.current=[d[Math.round((d.length-1)*(z.start??0)/100)]?.date,d[Math.round((d.length-1)*(z.end??100)/100)]?.date];});
  const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);
  return()=>{observer.disconnect();chart.dispose();instance.current=null;};
 },[]);
 useEffect(()=>{
  const chart=instance.current;if(!chart)return;const isDay=view==='daily';const labels=isDay?daily.map(b=>b.date):[...Array.from({length:121},(_,i)=>570+i),...Array.from({length:120},(_,i)=>781+i)].map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
  const byTime=new Map(minute.map(b=>[b.time,b]));const aligned=labels.map(t=>byTime.get(t));
  const gaps=isDay?dailyGaps(daily):[];
  const volume=isDay?daily.map(b=>+b.volume/10000):aligned.map(b=>b?b.volume/100:null);
  const colors=isDay?daily.map(b=>+b.close>=+b.open?'#ef6568':'#36b898'):aligned.map((b,i)=>!b||!aligned[i-1]||+b.close>=+aligned[i-1]!.close?'#ef6568':'#36b898');
  const indexByTime=new Map(benchmark?.bars.map(b=>[b.time,+b.close])||[]);
  const canOverlay=!isDay&&!!benchmark&&!!previousClose&&previousClose>0&&+benchmark.previous_close>0;
  const indexLine=aligned.map(b=>b&&canOverlay&&indexByTime.has(b.time)?indexByTime.get(b.time)!/+benchmark!.previous_close*previousClose!:null);
  const averages=aligned.map(b=>b?.average&&Number.isFinite(+b.average)&&+b.average>0?+b.average:null);
  const showPercent=!isDay&&Number.isFinite(previousClose)&&Number(previousClose)>0&&minute.length>0;
  const priceValues=[...minute.map(b=>+b.close),...averages,...indexLine].filter((n):n is number=>n!==null&&Number.isFinite(n)&&n>0);
  let priceScale:{}|{min:number;max:number;interval:number}={};
  if(showPercent&&priceValues.length){
   const low=Math.min(...priceValues),high=Math.max(...priceValues),raw=Math.max((high-low)/4,.01);
   const unit=10**Math.floor(Math.log10(raw)),step=[1,2,2.5,5,10].map(n=>n*unit).find(n=>n>=raw)!;
   const min=Math.floor(low/step)*step,max=Math.ceil(high/step)*step;
   priceScale={min:min===max?min-step:min,max:min===max?max+step:max,interval:step};
  }
  const percentLabel=(value:number)=>{const pct=(value/Number(previousClose)-1)*100,rounded=Math.abs(pct)<.005?0:pct;return `{${rounded>0?'rise':rounded<0?'fall':'flat'}|${rounded>0?'+':''}${rounded.toFixed(2)}%}`;};

  const marks=isDay?daily.filter(b=>events.some(e=>e.trading_date===b.date)).map(b=>({coord:[b.date,+b.high],value:String(events.filter(e=>e.trading_date===b.date).length)})):
    topVolumeMarks(minute,events,showOpening);
  const key=view+labels.join('|');const old=chart.getOption()?.dataZoom as {start?:number;end?:number}[]|undefined;
  let zoom=key===labelsKey.current?{start:old?.[0]?.start??0,end:old?.[0]?.end??100}:{start:0,end:100};labelsKey.current=key;
  if(isDay&&labels.length){let lo=windowDates.current.length?Math.max(0,labels.indexOf(windowDates.current[0])):Math.max(0,labels.length-60);let hi=windowDates.current.length?labels.indexOf(windowDates.current[1]):labels.length-1;if(hi<lo)hi=Math.min(labels.length-1,lo+59);if(lastDailyDate.current&&windowDates.current[1]===lastDailyDate.current&&labels.at(-1)!==lastDailyDate.current){const width=hi-lo;hi=labels.length-1;lo=Math.max(0,hi-width);}lastDailyDate.current=labels.at(-1)||'';const idx=labels.indexOf(selectedDay||'');const width=hi-lo;if(idx>=0&&idx<lo){lo=idx;hi=Math.min(labels.length-1,lo+width);}else if(idx>hi){hi=idx;lo=Math.max(0,hi-width);}zoom={start:lo/Math.max(1,labels.length-1)*100,end:hi/Math.max(1,labels.length-1)*100};windowDates.current=[labels[lo],labels[hi]];}
  const visibleMinutes=Math.max(1,(zoom.end-zoom.start)/100*Math.max(0,labels.length-1)+1);
  const gridStep=visibleMinutes>100?30:visibleMinutes>40?15:5;
  const timeTick=(_index:number,label:string)=>{const [h,m]=label.split(':').map(Number);return label===labels[0]||label===labels.at(-1)||(h*60+m)%gridStep===0;};
  const timeGrid=isDay?{}:{axisTick:{interval:timeTick},splitLine:{show:true,interval:timeTick,lineStyle:{color:'#69343f',opacity:.65,width:1}}};
  chart.setOption({backgroundColor:'transparent',animation:false,textStyle:{color:'#9dacc5',fontFamily:'sans-serif'},
   legend:{show:!isDay,data:['价格','均价',...(canOverlay?['上证走势']:[])],top:0,textStyle:{color:'#9dacc5'}},
   tooltip:{trigger:'axis',confine:true,enterable:false,className:'interactive-price-tooltip',transitionDuration:0,showDelay:0,hideDelay:100,axisPointer:{type:'cross',lineStyle:{color:'#a8bad1',type:'dashed'},crossStyle:{color:'#a8bad1',type:'dashed'}},backgroundColor:'#162238',borderColor:'#34465e',textStyle:{color:'#e7edf7'},
    formatter:(params:unknown)=>{const first=(Array.isArray(params)?params[0]:params) as {dataIndex?:number}|undefined;const idx=first?.dataIndex??-1;const root=document.createElement('div');root.className=isDay?'quote-tooltip':'quote-tooltip minute-tooltip';
     const rows:string[]=[];if(isDay){const b=daily[idx];if(b){rows.push(b.provisional?b.date+' · 盘中日K（未收盘）':b.date,`开盘：${price(b.open)} 元`,`收盘：${price(b.close)} 元`,`最高：${price(b.high)} 元`,`最低：${price(b.low)} 元`,`成交量：${wanShares(b.volume)} 万股`);for(const gap of gaps.filter(g=>g.date===b.date))rows.push(`${gap.provisional?'盘中':''}${gap.direction==='up'?'向上':'向下'}跳空：${price(gap.originalLow)}—${price(gap.originalHigh)} 元`,gap.filledOn?`已回补：${gap.filledOn}`:`未回补：${price(gap.low)}—${price(gap.high)} 元`);const n=events.filter(e=>e.trading_date===b.date).length;if(n)rows.push(`触发：${n} 次`);rows.push('双击查看当天分时 · 左右键逐日浏览');}}
     else{const b=aligned[idx];const hoverPct=b&&Number.isFinite(previousClose)&&Number(previousClose)>0?(+b.close/Number(previousClose)-1)*100:null;const roundedPct=hoverPct!==null&&Math.abs(hoverPct)<.005?0:hoverPct;if(!b)rows.push(labels[idx]||'', '暂无该分钟成交数据');if(b)rows.push(b.time,`价格：${price(b.close)} 元`,`涨跌幅：${roundedPct===null?'暂无昨收':(roundedPct>0?'+':'')+roundedPct.toFixed(2)+'%'}`,`均价：${b.average&&Number.isFinite(+b.average)?price(b.average)+' 元':'暂无成交额数据'}`,`分钟量：${wan(b.volume/100)} 手`,...(!b.complete?['当前分钟（未结束）']:[]));if(b&&chosen){const change=(+b.close/chosen.price-1)*100;rows.push(`基准触发：${chosen.time} · ${price(chosen.price)} 元`,`相对触发涨跌幅：${change>0?'+':''}${(Math.abs(change)<.005?0:change).toFixed(2)}%`);
     }if(b&&canOverlay&&indexByTime.has(b.time)){const v=indexByTime.get(b.time)!;rows.push(`上证：${v.toFixed(2)} 点（${(v/+benchmark!.previous_close*100-100).toFixed(2)}%）`);}}
     const comparison=document.createElement('div');comparison.className='tooltip-comparison';
     for(const text of rows){
      const row=document.createElement('div');
      const split=text.indexOf('：');
      if(!isDay&&split>=0){const label=document.createElement('span');label.textContent=text.slice(0,split+1);const value=document.createElement('span');value.textContent=text.slice(split+1).trim();row.append(label,value);row.className='quote-detail';if(text.startsWith('涨跌幅：'))value.style.color=text.includes('：-')?'#51c7aa':text.includes('：+')?'#ed7d81':'#e7edf7';}else row.textContent=text;
      if(text.startsWith('相对触发涨跌幅')){row.className='trigger-change';row.style.color=text.includes('：-')?'#69d9ac':text.includes('：+')?'#ef8585':'#e7edf7';comparison.append(row);}else{if(text.startsWith('上证：'))row.classList.add('quote-index');root.append(row);}
     }
     if(comparison.childElementCount)root.append(comparison);
     refreshTrade.current=null;if(!isDay&&chosen&&aligned[idx])refreshTrade.current=appendTradeTooltip(root,chosen.price,+aligned[idx].close,()=>costsRef.current,aligned[idx].time<chosen.time,aligned[idx].time===chosen.time);return root;}
   },axisPointer:{link:[{xAxisIndex:'all'}]},grid:[{left:65,right:showPercent?72:35,top:30,height:'55%'},{left:65,right:showPercent?72:35,top:'72%',height:'17%'}],
   xAxis:[{type:'category',data:labels,boundaryGap:isDay,...timeGrid,axisLine:{lineStyle:{color:isDay?'#2a374c':'#69343f'}},axisLabel:{hideOverlap:true,...(!isDay?{interval:timeTick,formatter:(t:string)=>t==='11:30'?'11:30/13:00':t}:{})}},{type:'category',gridIndex:1,data:labels,boundaryGap:isDay,...timeGrid,axisLabel:{show:false},axisLine:{lineStyle:{color:isDay?'#2a374c':'#69343f'}}}],
   yAxis:[{scale:true,...priceScale,splitNumber:isDay?5:4,splitLine:{lineStyle:{color:isDay?'#202c40':'#69343f',opacity:isDay?1:.65,width:1}},axisLabel:{formatter:(n:number)=>n.toFixed(2)}},{scale:true,gridIndex:1,splitNumber:2,name:isDay?'成交量（万股）':'成交量（手）',splitLine:{lineStyle:{color:isDay?'#202c40':'#69343f',opacity:isDay?1:.65,width:1}},axisLabel:{formatter:(n:number)=>isDay?wan(n):n>=10000?(n/10000).toFixed(1)+'万':n.toFixed(0)}},...(showPercent?[{type:'value',gridIndex:0,position:'right',scale:true,...priceScale,splitLine:{show:false},axisLine:{show:false},axisTick:{show:false},axisPointer:{show:false},axisLabel:{margin:10,formatter:percentLabel,rich:{rise:{color:'#ed7d81',fontSize:11},fall:{color:'#51c7aa',fontSize:11},flat:{color:'#c8d5eb',fontSize:11}}}}]:[])],
   dataZoom:[{type:'inside',xAxisIndex:[0,1],...zoom,...(isDay?{zoomLock:true,zoomOnMouseWheel:false,moveOnMouseWheel:false,moveOnMouseMove:true}:{})},{type:'slider',xAxisIndex:[0,1],...zoom,bottom:1,height:18,borderColor:'#28354b',fillerColor:'rgba(82,138,230,.14)',...(isDay?{zoomLock:true,handleSize:0,brushSelect:false}: {})}],
   series:[isDay?{name:'日K',type:'candlestick',data:daily.map(b=>[+b.open,+b.close,+b.low,+b.high]),itemStyle:{color:'#ef6568',color0:'#36b898',borderColor:'#ef6568',borderColor0:'#36b898'},markArea:{silent:true,label:{fontSize:10,color:'#b6c6da',position:'insideTopRight',align:'right',padding:[2,4]},data:gaps.filter(g=>!g.filledOn).map(g=>[{name:`${g.provisional?'盘中':''}${g.direction==='up'?'上':'下'}缺口 ${price(g.low)}—${price(g.high)}`,xAxis:daily[Math.max(0,daily.findIndex(b=>b.date===g.date)-1)].date,yAxis:g.low,itemStyle:{color:g.direction==='up'?'rgba(239,101,104,.10)':'rgba(54,184,152,.10)',borderColor:g.direction==='up'?'#b66770':'#4c9988',borderWidth:1,borderType:'dashed'}},{xAxis:daily.at(-1)!.date,yAxis:g.high}])},markPoint:{symbolSize:34,label:{fontSize:10},itemStyle:{color:'#dba853'},data:marks},markLine:{symbol:'none',silent:true,label:{show:false},lineStyle:{color:'#8baeed',type:'dashed'},data:selectedDay&&labels.includes(selectedDay)?[{xAxis:selectedDay}]:[]}}:
    {name:'价格',type:'line',data:aligned.map(b=>b?+b.close:null),connectNulls:false,showSymbol:false,z:5,lineStyle:{color:'#8cbcff',width:2.4},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(83,139,230,.16)'},{offset:1,color:'rgba(83,139,230,0)'}])},markPoint:{symbol:'pin',symbolSize:38,itemStyle:{color:'#e9ad58'},label:{fontSize:10},data:[...marks.map(m=>({...m,...(m.value==='开盘量'?{symbolSize:44,itemStyle:{color:'#8798b2'}}:{}),...(chosen&&m.coord[0]===chosen.time?{itemStyle:{color:'#62cdbb',borderColor:'#e7fff8',borderWidth:2}}:{})})),...buySignals.filter(e=>labels.includes(e.time)).map(e=>({coord:[e.time,e.price],value:'买研',symbol:'triangle',symbolSize:20,itemStyle:{color:'#69d9ac'},label:{position:'bottom',color:'#69d9ac',fontSize:10}}))]}},
    ...(canOverlay?[{name:'上证走势',type:'line',data:indexLine,showSymbol:false,connectNulls:false,z:2,lineStyle:{color:'#929aa9',width:1.2,type:'dashed',opacity:0.8},itemStyle:{color:'#929aa9'}}]:[]),
    ...(!isDay?[{name:'均价',type:'line',data:averages,showSymbol:false,connectNulls:false,lineStyle:{color:'#e9b949',width:1.5},itemStyle:{color:'#e9b949'}}]:[]),
    {name:isDay?'成交量（万股）':'分钟量（手）',type:'bar',xAxisIndex:1,yAxisIndex:1,data:volume.map((v,i)=>({value:v,itemStyle:{color:colors[i]}}))}]
  },{notMerge:true});
  if(isDay&&selectedDay){const index=labels.indexOf(selectedDay);if(index>=0)chart.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:index});}
 },[contentKey]);
 return <>{view!=='daily'&&<label className="opening-volume-toggle"><input type="checkbox" checked={showOpening} onChange={e=>{setShowOpening(e.target.checked);try{localStorage.setItem('stock-monitor-show-opening',String(e.target.checked));}catch{}}}/>显示开盘量<span>09:31单独标记</span></label>}{view!=='daily'&&<TCostSettings value={costs} onChange={updateCosts}/>}<div className={'chart'+(compact?' compact-chart':'')} ref={ref} tabIndex={view==='daily'?0:undefined} onClick={()=>{if(view==='daily')ref.current?.focus();}} onKeyDown={e=>{if(view==='daily'&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();onMove?.(e.key==='ArrowLeft'?-1:1);}else if(view==='daily'&&e.key==='Enter'&&selectedDay)onOpenDay?.(selectedDay);}} aria-label={view==='daily'?'日K线及成交量':'分时价格及分钟成交量'}/>{view==='daily'&&<div className="average-caption">缺口阴影：截至最新日K尚未回补的区间 · 红色向上，绿色向下 · 盘中缺口待收盘确认 · 拖动浏览，缩放已关闭</div>}{view!=='daily'&&<div className="average-caption">开盘量：09:31；触发：盘中顶部量。均在连续两分钟缩量确认后标在原分钟，仍封涨停时等待开板 · 亮蓝实线：个股 · 黄线：均价（累计成交额 ÷ 累计成交股数，含集合竞价）{benchmark&&previousClose&&previousClose>0?' · 灰色虚线：上证（以双方昨收涨跌幅对齐）':' · 上证叠加暂无对应日期分时或昨收数据'}{minute.some(b=>b.average&&Number.isFinite(+b.average)&&+b.average>0)?'':' · 当前缓存缺少成交额，暂无法显示均价线'}</div>}</>;
}
