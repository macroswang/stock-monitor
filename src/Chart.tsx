import {useEffect,useMemo,useRef,useState} from 'react';
import * as echarts from 'echarts';
import type {Bar,Daily,Event,IndexMinute,VolumeFlow} from './models';
import {price,wan,wanShares} from './format';
import {topVolumeMarks} from './volumeMarks';
import {turningQualityQ1} from './turningQualityQ1';
import {turningShapes} from './turningShapes';
import {turningDisplayPoints} from './turningDisplay';
import {paperChartMarks} from './paperMarks';
import type {PaperFillPoint} from './paperMarks';
import {splitMinuteVolume} from './volumeFlow';
import {resolvedPriceLimits,intradayPriceScale,pricePercent} from './priceLimits';
import {dailyGaps} from './dailyGaps';
import {dailyPatterns,dailyPatternStatus} from './dailyPatterns';
import {dailyPatternOverlay,dailyPatternColors} from './dailyPatternOverlay';
import {selectDailyPatterns} from './dailyPatternSelection';
import {DAILY_WINDOW,dailyViewport} from './dailyWindow';
import {defaultTCosts,tProfit} from './tCosts';
import type {TCosts} from './tCosts';
import TCostSettings from './TCostSettings';
import {appendTradeTooltip} from './tradeTooltip';
const renderTurningConnector:echarts.CustomSeriesRenderItem=(_params,api)=>{
 const [x,y]=api.coord!([api.value(0),api.value(1)]),direction=Number(api.value(2));
 return {type:'line',shape:{x1:x,y1:y+direction*3,x2:x,y2:y+direction*10.5},
  style:{stroke:direction>0?'#ff5b78':'#00bf83',lineWidth:1,lineDash:[2,2]},silent:true};
};
export default function Chart({minute=[],daily=[],view,events=[],selectedDay,onSelectDay,onOpenDay,onMove,compact=false,benchmark,previousClose,buySignals=[],onPaperTrade,paperFills=[],volumeFlow,limitUp,limitDown,currentPrice}:{limitUp?:number;limitDown?:number;currentPrice?:{price:number;time:string};volumeFlow?:VolumeFlow;paperFills?:PaperFillPoint[];onPaperTrade?:(point:{time:string;price:number;kind:string;side:'buy'|'sell';inChart?:boolean})=>void;buySignals?:{key:string;time:string;price:number}[];benchmark?:IndexMinute|null;previousClose?:number;minute?:Bar[];daily?:Daily[];view:string;events?:Event[];selectedDay?:string;onSelectDay?:(day:string)=>void;onOpenDay?:(day:string)=>void;onMove?:(direction:number)=>void;compact?:boolean}){
 const [costs,setCosts]=useState<TCosts>(()=>{try{const saved=JSON.parse(localStorage.getItem('stock-monitor-t-costs-v4')||'null');return saved&&tProfit(10,10,saved)?saved:defaultTCosts;}catch{return defaultTCosts;}});
 const [showOpening,setShowOpening]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-opening')!=='false';}catch{return true;}});
 const [showShapes,setShowShapes]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-turning-shapes-v1')!=='false';}catch{return true;}});
 const [showQuality,setShowQuality]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-turning-v2')!=='false';}catch{return true;}});
 const [showDailyPatterns,setShowDailyPatterns]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-daily-patterns-v1')!=='false';}catch{return true;}});
 const dayPatterns=useMemo(()=>view==='daily'?selectDailyPatterns(dailyPatterns(daily)):[],[daily,view]);
 useEffect(()=>{const sync=()=>{try{setShowShapes(localStorage.getItem('stock-monitor-show-turning-shapes-v1')!=='false');setShowQuality(localStorage.getItem('stock-monitor-show-turning-v2')!=='false');}catch{}};window.addEventListener('storage',sync);window.addEventListener('turning-display-change',sync);return()=>{window.removeEventListener('storage',sync);window.removeEventListener('turning-display-change',sync);};},[]);
 const costsRef=useRef(costs);costsRef.current=costs;
 const refreshTrade=useRef<(()=>void)|null>(null);
 const updateCosts=(next:TCosts)=>{costsRef.current=next;setCosts(next);refreshTrade.current?.();if(tProfit(10,10,next)){try{localStorage.setItem('stock-monitor-t-costs-v4',JSON.stringify(next));}catch{}}};
 const scope=view+'|'+(selectedDay||events[0]?.trading_date||'');
 const [choice,setChoice]=useState<{scope:string;time:string;price:number;kind?:'底'|'顶'|'位置'}|null>(null);
 useEffect(()=>setChoice(null),[scope]);
 const visibleMarks=view==='daily'?[]:topVolumeMarks(minute,events,showOpening);
 const latestEvent=events.filter(e=>visibleMarks.some(m=>m.coord[0]===e.candidate_time)).sort((a,b)=>a.event_label.localeCompare(b.event_label)||a.candidate_time.localeCompare(b.candidate_time)).at(-1);
 const latestMark=visibleMarks.find(m=>m.coord[0]===latestEvent?.candidate_time);
 const selectableTurns=view==='daily'?[]:turningDisplayPoints(showShapes?turningShapes(minute):[],showQuality?turningQualityQ1(minute):[],showShapes,showQuality);
 const chosen=choice?.scope===scope&&(choice.kind==='位置'?minute.some(b=>b.time===choice.time&&b.complete):choice.kind?selectableTurns.some(m=>m.time===choice.time&&(m.kind==='bottom'?'底':'顶')===choice.kind):visibleMarks.some(m=>m.coord[0]===choice.time))?choice:latestMark?{scope,time:latestMark.coord[0],price:latestMark.coord[1]}:null;
 const hasSplitVolume=view!=='daily'&&minute.some(bar=>splitMinuteVolume(bar,volumeFlow?.day===selectedDay?volumeFlow:undefined).verified);
 const quotePrices=[...minute.map(b=>+b.close),...(currentPrice?[currentPrice.price]:[])];
 const priceLimits=resolvedPriceLimits(previousClose,quotePrices,{up:limitUp,down:limitDown});
 const [tradeHint,setTradeHint]=useState<{scope:string;text:string}|null>(null);
 const contextTrade=(event:React.MouseEvent<HTMLDivElement>)=>{
  if(view==='daily'||!onPaperTrade||!instance.current)return;
  event.preventDefault();
  const chart=instance.current,box=event.currentTarget.getBoundingClientRect(),pixel=[event.clientX-box.left,event.clientY-box.top];
  const grid=chart.containPixel({gridIndex:0},pixel)?0:chart.containPixel({gridIndex:1},pixel)?1:null;
  if(grid===null)return;
  const coord=chart.convertFromPixel({gridIndex:grid},pixel) as number[];
  const all=[...Array.from({length:121},(_,i)=>570+i),...Array.from({length:120},(_,i)=>781+i)],m=all[Math.round(coord[0])];
  const time=m===undefined?'':`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;
  const bar=minute.find(b=>b.time===time&&b.complete);
  const value=grid===0?coord[1]:Number(bar?.close),price=Math.round(value*100)/100;
  if(!bar||!Number.isFinite(price)||price<=0){setTradeHint({scope,text:'请选择已有完整行情的分钟，未来时间不能委托。'});return;}
  setTradeHint(null);chart.dispatchAction({type:'hideTip'});
  onPaperTrade({time,price,kind:'分时右键委托',side:'buy',inChart:true});
 };
 const scopeRef=useRef(scope);scopeRef.current=scope;
 const contentKey=JSON.stringify([minute.map(b=>[b.time,b.close,b.volume,b.complete,b.average]),daily.map(b=>[b.date,b.open,b.close,b.low,b.high,b.volume,b.provisional]),view,events.map(e=>[e.key,e.trading_date,e.candidate_time,e.confirmation_label,e.event_label,e.mode]),selectedDay,benchmark,previousClose,buySignals,chosen,showOpening,showShapes,showQuality,showDailyPatterns,dayPatterns.map(p=>p.key),paperFills,volumeFlow,limitUp,limitDown,currentPrice?.price]);
 const open=useRef(onOpenDay);open.current=onOpenDay;const plot=useRef({daily,view,minute});plot.current={daily,view,minute};
 const windowDates=useRef<string[]>([]);const lastDailyDate=useRef('');
 const ref=useRef<HTMLDivElement>(null);const instance=useRef<echarts.ECharts|null>(null);const labelsKey=useRef('');const select=useRef(onSelectDay);select.current=onSelectDay;
 useEffect(()=>{if(!ref.current)return;const chart=echarts.init(ref.current,undefined,{renderer:'canvas'});instance.current=chart;
  chart.on('click',params=>{
   if(plot.current.view!=='daily'&&params.componentType==='markPoint'){
    const data=params.data as {value?:unknown;coord?:[string,number];turningKind?:'底'|'顶'}|undefined;
    if((data?.value==='触发'||data?.value==='开盘量'||!!data?.turningKind)&&data.coord&&Number.isFinite(+data.coord[1])&&+data.coord[1]>0)setChoice({scope:scopeRef.current,time:data.coord[0],price:+data.coord[1],kind:data.turningKind});
   }
   if(plot.current.view!=='daily'&&params.componentType==='series'&&['价格','涨停走势','跌停走势'].includes(params.seriesName||'')){const bar=plot.current.minute.find(b=>b.time===params.name);if(bar?.complete)setChoice({scope:scopeRef.current,time:bar.time,price:+bar.close,kind:'位置'});}
   if(params.componentType==='series'&&params.name&&/^\d{4}-\d{2}-\d{2}$/.test(params.name))select.current?.(params.name);
  });
  chart.on('dblclick',params=>{if(plot.current.view==='daily'&&params.componentType==='series'&&params.name)open.current?.(params.name);});
  chart.on('datazoom',()=>{const z=(chart.getOption()?.dataZoom as {start?:number;end?:number}[])?.[0];const d=plot.current.daily;if(plot.current.view==='daily'&&d.length&&z)windowDates.current=[d[Math.round((d.length-1)*(z.start??0)/100)]?.date,d[Math.round((d.length-1)*(z.end??100)/100)]?.date];});
  chart.getZr().on('click',event=>{if(event.target||plot.current.view==='daily'||!chart.containPixel({gridIndex:0},[event.offsetX,event.offsetY]))return;const coord=chart.convertFromPixel({gridIndex:0},[event.offsetX,event.offsetY]) as number[];const all=[...Array.from({length:121},(_,i)=>570+i),...Array.from({length:120},(_,i)=>781+i)];const m=all[Math.round(coord[0])];if(m===undefined)return;const time=`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;if(plot.current.minute.some(b=>b.time===time&&b.complete)&&Number.isFinite(coord[1])&&coord[1]>0)setChoice({scope:scopeRef.current,time,price:Math.round(coord[1]*100)/100,kind:'位置'});});
  const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);
  return()=>{observer.disconnect();chart.dispose();instance.current=null;};
 },[]);
 useEffect(()=>{
  const chart=instance.current;if(!chart)return;const isDay=view==='daily';const labels=isDay?daily.map(b=>b.date):[...Array.from({length:121},(_,i)=>570+i),...Array.from({length:120},(_,i)=>781+i)].map(m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`);
  const byTime=new Map(minute.map(b=>[b.time,b]));const aligned=labels.map(t=>byTime.get(t));
  const gaps=isDay?dailyGaps(daily):[];
  const visibleGaps=gaps.filter(g=>!g.filledOn).slice(-1);
  const patternSeries=isDay&&showDailyPatterns?dailyPatternOverlay(dayPatterns,()=>chart.getWidth()):[];
  const tradePoints=paperChartMarks(isDay?paperFills:paperFills.filter(f=>f.stamp.slice(0,10)===selectedDay),isDay);
  const tradesByTime=new Map<string,typeof tradePoints>();for(const t of tradePoints){const arr=tradesByTime.get(t.time)||[];arr.push(t);tradesByTime.set(t.time,arr);}
  const tradeMarks=tradePoints.filter(m=>labels.includes(m.time)).map(m=>({coord:[m.time,m.price],value:m.value,paperTrade:true,silent:true,symbol:'circle',symbolSize:20,
   symbolOffset:m.value==='B'?[0,16]:m.value==='S'?[0,-16]:[0,-20],itemStyle:{color:m.value==='B'?'#ed6d79':m.value==='S'?'#32b99a':'#b48bff',borderColor:'#edf4ff',borderWidth:1},label:{show:true,formatter:m.value,color:'#fff',fontSize:11,fontWeight:'bold'}}));

  const shapes=isDay||!showShapes?[]:turningShapes(minute);
  const quality=isDay||!showQuality?[]:turningQualityQ1(minute);
  const observations=turningDisplayPoints(shapes,quality,showShapes,showQuality);
  const volume=isDay?daily.map(b=>+b.volume/10000):aligned.map(b=>b?b.volume/100:null);
  const splits=aligned.map(b=>b?splitMinuteVolume(b,volumeFlow?.day===selectedDay?volumeFlow:undefined):null);
  const colors=isDay?daily.map(b=>+b.close>=+b.open?'#ef6568':'#36b898'):aligned.map((b,i)=>!b||!aligned[i-1]||+b.close>=+aligned[i-1]!.close?'#ef6568':'#36b898');
  const indexByTime=new Map(benchmark?.bars.map(b=>[b.time,+b.close])||[]);
  const canOverlay=!isDay&&!!benchmark&&!!previousClose&&previousClose>0&&+benchmark.previous_close>0;
  const indexLine=aligned.map(b=>b&&canOverlay&&indexByTime.has(b.time)?indexByTime.get(b.time)!/+benchmark!.previous_close*previousClose!:null);
  const averages=aligned.map(b=>b?.average&&Number.isFinite(+b.average)&&+b.average>0?+b.average:null);
  const showPercent=!isDay&&Number.isFinite(previousClose)&&Number(previousClose)>0&&minute.length>0;
  // Benchmark overlays cannot expand the stock's price axis beyond its actual limit.
  const priceValues=[...tradePoints.map(m=>m.price),...minute.map(b=>+b.close),...averages,...(currentPrice?[currentPrice.price]:[])].filter((n):n is number=>n!==null&&Number.isFinite(n)&&n>0);
  const priceScale=showPercent?intradayPriceScale(previousClose,priceValues,priceLimits):{};
  const limitLines=[{kind:'涨停',value:priceLimits.up,color:'#ef6568',position:'insideEndBottom'},{kind:'跌停',value:priceLimits.down,color:'#36b898',position:'insideEndTop'}].filter(row=>row.value!==undefined&&row.value>=Number(priceScale.min)&&row.value<=Number(priceScale.max)).map(row=>({name:row.kind,yAxis:row.value,lineStyle:{color:row.color,type:'dashed',width:1},label:{show:true,position:row.position,color:row.color,fontSize:10,formatter:`${row.kind} ${row.value!.toFixed(2)}（${pricePercent(row.value!,Number(previousClose))}）`}}));
  const percentLabel=(value:number)=>{const pct=(value/Number(previousClose)-1)*100,rounded=Math.abs(pct)<.005?0:pct;return `{${rounded>0?'rise':rounded<0?'fall':'flat'}|${rounded>0?'+':''}${rounded.toFixed(2)}%}`;};

  const marks=isDay?[]:
    topVolumeMarks(minute,events,showOpening);
  const key=view+labels.join('|');const old=chart.getOption()?.dataZoom as {start?:number;end?:number}[]|undefined;
  let zoom=key===labelsKey.current?{start:old?.[0]?.start??0,end:old?.[0]?.end??100}:{start:0,end:100};labelsKey.current=key;
  if(isDay&&labels.length){const {lo,hi}=dailyViewport(labels,windowDates.current,selectedDay,lastDailyDate.current);lastDailyDate.current=labels.at(-1)||'';zoom={start:lo/Math.max(1,labels.length-1)*100,end:hi/Math.max(1,labels.length-1)*100};windowDates.current=[labels[lo],labels[hi]];}
  const visibleMinutes=Math.max(1,(zoom.end-zoom.start)/100*Math.max(0,labels.length-1)+1);
  const gridStep=visibleMinutes>100?30:visibleMinutes>40?15:5;
  const timeTick=(_index:number,label:string)=>{const [h,m]=label.split(':').map(Number);return label===labels[0]||label===labels.at(-1)||(h*60+m)%gridStep===0;};
  const timeGrid=isDay?{}:{axisTick:{interval:timeTick},splitLine:{show:true,interval:timeTick,lineStyle:{color:'#69343f',opacity:.65,width:1}}};
  const observationMarks=observations.map(m=>{
   const color=m.kind==='bottom'?'#ff5b78':'#00bf83';
   return {coord:[m.time,m.price],turningKind:m.kind==='bottom'?'底':'顶',value:m.shape?(m.kind==='bottom'?'底形态':'顶形态'):(m.kind==='bottom'?'Q1底信号':'Q1顶信号'),
    observationKey:m.shape?.key,qualityKey:m.q1?.key,symbol:'circle',symbolSize:chosen?.kind===(m.kind==='bottom'?'底':'顶')&&chosen.time===m.time?9:5,
    itemStyle:{color,borderColor:'#fff',borderWidth:chosen?.kind===(m.kind==='bottom'?'底':'顶')&&chosen.time===m.time?2:m.q1?1:0},
    label:{show:!!m.shape||!showShapes,position:m.kind==='bottom'?'bottom':'top',distance:8,formatter:m.kind==='bottom'?'底':'顶',
     color:'#fff',backgroundColor:color,borderRadius:8,width:16,height:16,padding:0,align:'center',
     fontFamily:'"PingFang SC","Microsoft YaHei",sans-serif',fontSize:11,fontWeight:400,lineHeight:16}};
  });
  chart.setOption({backgroundColor:'transparent',animation:false,textStyle:{color:'#9dacc5',fontFamily:'sans-serif'},
   legend:{show:!isDay,data:['价格','均价',...(canOverlay?['上证走势']:[])],top:0,textStyle:{color:'#9dacc5'}},
   tooltip:{trigger:'axis',confine:true,enterable:false,className:'interactive-price-tooltip',transitionDuration:0,showDelay:0,hideDelay:100,axisPointer:isDay?{type:'none',label:{show:false}}:{type:'cross',lineStyle:{color:'#a8bad1',type:'dashed'},crossStyle:{color:'#a8bad1',type:'dashed'}},backgroundColor:'#162238',borderColor:'#34465e',textStyle:{color:'#e7edf7'},
    formatter:(params:unknown)=>{const first=(Array.isArray(params)?params[0]:params) as {dataIndex?:number}|undefined;const idx=first?.dataIndex??-1;const root=document.createElement('div');root.className=isDay?'quote-tooltip':'quote-tooltip minute-tooltip';
     if(observations.some(m=>m.time===aligned[idx]?.time)){root.style.maxWidth='min(580px, calc(100vw - 80px))';root.style.whiteSpace='normal';}
     const rows:string[]=[];if(isDay){const b=daily[idx];if(b){rows.push(b.provisional?b.date+' · 盘中日K（未收盘）':b.date,`开盘：${price(b.open)} 元`,`收盘：${price(b.close)} 元`,`最高：${price(b.high)} 元`,`最低：${price(b.low)} 元`,`成交量：${wanShares(b.volume)} 万股`);for(const gap of gaps.filter(g=>g.date===b.date))rows.push(`${gap.provisional?'盘中':''}${gap.direction==='up'?'向上':'向下'}跳空：${price(gap.originalLow)}—${price(gap.originalHigh)} 元`,gap.filledOn?`已回补：${gap.filledOn}`:`未回补：${price(gap.low)}—${price(gap.high)} 元`);const n=events.filter(e=>e.trading_date===b.date).length;if(n)rows.push(`触发：${n} 次`);rows.push('双击查看当天分时 · 左右键逐日浏览');}}
     else{const b=aligned[idx];const hoverPct=b&&Number.isFinite(previousClose)&&Number(previousClose)>0?(+b.close/Number(previousClose)-1)*100:null;const roundedPct=hoverPct!==null&&Math.abs(hoverPct)<.005?0:hoverPct;if(!b)rows.push(labels[idx]||'', '暂无该分钟成交数据');if(b)rows.push(b.time,`价格：${price(b.close)} 元`,`涨跌幅：${roundedPct===null?'暂无昨收':(roundedPct>0?'+':'')+roundedPct.toFixed(2)+'%'}`,`均价：${b.average&&Number.isFinite(+b.average)?price(b.average)+' 元':'暂无成交额数据'}`,`分钟量：${wan(b.volume/100)} 手`,...(!b.complete?['当前分钟（未结束）']:[]));if(b&&chosen){const change=(+b.close/chosen.price-1)*100;rows.push(`基准${chosen.kind||'触发'}：${chosen.time} · ${price(chosen.price)} 元`,`相对${chosen.kind||'触发'}涨跌幅：${change>0?'+':''}${(Math.abs(change)<.005?0:change).toFixed(2)}%`);
     }}
     if(isDay&&showDailyPatterns&&daily[idx])for(const p of dayPatterns.filter(p=>p.lines.some(l=>l.from.index<=idx&&l.to.index>=idx)).slice(-3)){
      rows.push(`${p.name}：${dailyPatternStatus(p)}`,`轮廓起点：${p.start.date}；首次识别：${p.detectedOn}`,...(p.breakoutOn?[`收盘突破：${p.breakoutOn}`]:[]),...(p.kind==='spring'?[`收回前低：${p.detectedOn}`]:[]),...(p.necklineOn?[`颈线突破：${p.necklineOn}`]:[]),...(p.failedOn?[`${p.failureReason==='support'?'收盘再失守前低':'跌破破底低点'}：${p.failedOn}`]:[]));
     }
     if(!isDay&&aligned[idx]){if(priceLimits.up)rows.push(`涨停：${priceLimits.up.toFixed(2)} 元（${pricePercent(priceLimits.up,Number(previousClose))}）`);if(priceLimits.down)rows.push(`跌停：${priceLimits.down.toFixed(2)} 元（${pricePercent(priceLimits.down,Number(previousClose))}）`);const split=splits[idx]!;const total=aligned[idx]!.volume;
      if(split.verified){const suffix=split.approximate?'（约）':'';rows.push(`买盘量${suffix}：${wan(split.rawBuy/100)} 手（${split.sourceTotal?(split.rawBuy/split.sourceTotal*100).toFixed(1):'0.0'}%）`,`卖盘量${suffix}：${wan(split.rawSell/100)} 手（${split.sourceTotal?(split.rawSell/split.sourceTotal*100).toFixed(1):'0.0'}%）`);if(split.approximate)rows.push(`买卖量为约值，分笔合计较总量${split.difference>0?'多':'少'}${wan(Math.abs(split.difference)/100)}手`);}
     }
     for(const point of observations.filter(m=>m.time===aligned[idx]?.time)){
      const observation=(point.shape||point.q1)!;
      rows.push(`${point.shape?'': 'Q1'}${point.kind==='bottom'?'底':'顶'}${point.shape?'形态':''}：${price(point.price)} 元`,
       `候选点：${observation.candidateTime} · ${price(observation.candidatePrice)} 元`,
       `确认时间：${point.time} · ${price(point.price)} 元`);
     }
     for(const t of tradesByTime.get(labels[idx])||[])rows.push(`模拟成交 ${t.value}：${t.buyShares?`买入${t.buyShares}股 · 均价${price(t.buyAmount/t.buyShares/100)}元`:''}${t.buyShares&&t.sellShares?'；':''}${t.sellShares?`卖出${t.sellShares}股 · 均价${price(t.sellAmount/t.sellShares/100)}元`:''}${t.value==='T'?'（当日有买有卖）':''}`);
     const comparison=document.createElement('div');comparison.className='tooltip-comparison';
     for(const text of rows){
      const row=document.createElement('div');
      const split=text.indexOf('：');
      if(!isDay&&split>=0){const label=document.createElement('span');label.textContent=text.slice(0,split+1);const value=document.createElement('span');value.textContent=text.slice(split+1).trim();row.append(label,value);row.className='quote-detail';if(text.startsWith('涨停：'))value.style.color='#ed7d81';if(text.startsWith('跌停：'))value.style.color='#51c7aa';if(text.startsWith('涨跌幅：'))value.style.color=text.includes('：-')?'#51c7aa':text.includes('：+')?'#ed7d81':'#e7edf7';}else row.textContent=text;
      if(/^相对(触发|底|顶|位置)涨跌幅/.test(text)){row.className='trigger-change';row.style.color=text.includes('：-')?'#69d9ac':text.includes('：+')?'#ef8585':'#e7edf7';comparison.append(row);}else{if(text.startsWith('上证：'))row.classList.add('quote-index');root.append(row);}
     }
     if(comparison.childElementCount)root.append(comparison);
     refreshTrade.current=null;if(!isDay&&chosen&&aligned[idx])refreshTrade.current=appendTradeTooltip(root,chosen.price,+aligned[idx].close,()=>costsRef.current,aligned[idx].time<chosen.time,aligned[idx].time===chosen.time);return root;}
   },axisPointer:{link:[{xAxisIndex:'all'}]},grid:[{left:65,right:showPercent?72:35,top:30,height:'55%'},{left:65,right:showPercent?72:35,top:'72%',height:'17%'}],
   xAxis:[{type:'category',data:labels,boundaryGap:isDay,...timeGrid,axisLine:{lineStyle:{color:isDay?'#2a374c':'#69343f'}},axisLabel:{hideOverlap:true,...(!isDay?{interval:timeTick,formatter:(t:string)=>t==='11:30'?'11:30/13:00':t}:{})}},{type:'category',gridIndex:1,data:labels,boundaryGap:isDay,...timeGrid,axisLabel:{show:false},axisLine:{lineStyle:{color:isDay?'#2a374c':'#69343f'}}}],
   yAxis:[{scale:true,...priceScale,splitNumber:isDay?5:4,splitLine:{lineStyle:{color:isDay?'#202c40':'#69343f',opacity:isDay?1:.65,width:1}},axisLabel:{formatter:(n:number)=>n.toFixed(2)}},{scale:true,gridIndex:1,splitNumber:2,name:isDay?'成交量（万股）':'成交量（手）',splitLine:{lineStyle:{color:isDay?'#202c40':'#69343f',opacity:isDay?1:.65,width:1}},axisLabel:{formatter:(n:number)=>isDay?wan(n):n>=10000?(n/10000).toFixed(1)+'万':n.toFixed(0)}},...(showPercent?[{type:'value',gridIndex:0,position:'right',scale:true,...priceScale,splitLine:{show:false},axisLine:{show:false},axisTick:{show:false},axisPointer:{show:false},axisLabel:{margin:10,formatter:percentLabel,rich:{rise:{color:'#ed7d81',fontSize:11},fall:{color:'#51c7aa',fontSize:11},flat:{color:'#c8d5eb',fontSize:11}}}}]:[])],
   dataZoom:[{type:'inside',xAxisIndex:[0,1],...zoom,...(isDay?{filterMode:'weakFilter',zoomLock:true,zoomOnMouseWheel:false,moveOnMouseWheel:false,moveOnMouseMove:true}:{})},{type:'slider',xAxisIndex:[0,1],...zoom,bottom:1,height:18,borderColor:'#28354b',fillerColor:'rgba(82,138,230,.14)',...(isDay?{filterMode:'weakFilter',zoomLock:true,handleSize:0,brushSelect:false}: {})}],
   series:[isDay?{name:'日K',type:'candlestick',data:daily.map(b=>[+b.open,+b.close,+b.low,+b.high]),itemStyle:{color:'#ef6568',color0:'#36b898',borderColor:'#ef6568',borderColor0:'#36b898'},markArea:{silent:true,label:{fontSize:10,color:'#91a2bb',position:'insideTopRight',align:'right',padding:[2,4]},data:visibleGaps.map(g=>[{name:`${g.provisional?'盘中':''}${g.direction==='up'?'上':'下'}缺口 ${price(g.low)}—${price(g.high)}`,xAxis:daily[Math.max(0,daily.findIndex(b=>b.date===g.date)-1)].date,yAxis:g.low,itemStyle:{color:g.direction==='up'?'rgba(239,101,104,.035)':'rgba(54,184,152,.035)',borderColor:g.direction==='up'?'rgba(239,101,104,.24)':'rgba(54,184,152,.24)',borderWidth:.7,borderType:'solid'}},{xAxis:daily.at(-1)!.date,yAxis:g.high}])},markPoint:{data:tradeMarks},markLine:{data:[]}}:
    {name:'价格',type:'line',data:aligned.map(b=>b?+b.close:null),connectNulls:false,showSymbol:false,z:5,lineStyle:{color:'#8cbcff',width:2.4},markLine:{silent:true,symbol:'none',data:limitLines},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(83,139,230,.16)'},{offset:1,color:'rgba(83,139,230,0)'}])},markPoint:{symbol:'pin',symbolSize:38,itemStyle:{color:'#e9ad58'},label:{fontSize:10},data:[...tradeMarks,...observationMarks,...marks.map(m=>({...m,...(m.value==='开盘量'?{symbolSize:44,itemStyle:{color:'#8798b2'}}:{}),...(chosen&&!chosen.kind&&m.coord[0]===chosen.time?{itemStyle:{color:'#62cdbb',borderColor:'#e7fff8',borderWidth:2}}:{})})),...buySignals.filter(e=>labels.includes(e.time)).map(e=>({coord:[e.time,e.price],value:'买研',symbol:'triangle',symbolSize:20,itemStyle:{color:'#69d9ac'},label:{position:'bottom',color:'#69d9ac',fontSize:10}}))]}},
    ...(!isDay?[{value:priceLimits.up,name:'涨停走势',color:'#ef6568'},{value:priceLimits.down,name:'跌停走势',color:'#36b898'}].filter(row=>row.value!==undefined).map(row=>({name:row.name,type:'line',data:aligned.map(b=>b&&Math.abs(+b.close-row.value!)<.000001?+b.close:null),connectNulls:false,showSymbol:true,symbol:'circle',symbolSize:3,z:7,silent:true,lineStyle:{color:row.color,width:2.8},itemStyle:{color:row.color}})):[]),
    ...(canOverlay?[{name:'上证走势',type:'line',data:indexLine,showSymbol:false,connectNulls:false,z:2,lineStyle:{color:'#929aa9',width:1.2,type:'dashed',opacity:0.8},itemStyle:{color:'#929aa9'}}]:[]),
    ...(!isDay?[{name:'均价',type:'line',data:averages,showSymbol:false,connectNulls:false,lineStyle:{color:'#e9b949',width:1.5},itemStyle:{color:'#e9b949'}}]:[]),
    ...(isDay?[{name:'成交量（万股）',type:'bar',xAxisIndex:1,yAxisIndex:1,data:volume.map((v,i)=>({value:v,itemStyle:{color:colors[i]}}))}]:[
     {name:'买盘量',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,itemStyle:{color:'#ef6568'},data:splits.map(b=>b?b.buy/100:null)},
     {name:'卖盘量',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,itemStyle:{color:'#36b898'},data:splits.map(b=>b?b.sell/100:null)},
     {name:'中性 / 未分类量',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,itemStyle:{color:'#718096'},data:splits.map(b=>b?b.verified?(b.neutral+b.unknown)/100:0:null)},
     {name:'总成交量（回退）',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,itemStyle:{opacity:hasSplitVolume?.65:1,color:(params:{dataIndex:number})=>colors[params.dataIndex]},data:splits.map(b=>b?b.verified?0:b.total/100:null)}]),
    ...patternSeries,
    ...(!isDay?[{name:'底顶标签连线',type:'custom',silent:true,z:6,clip:false,tooltip:{show:false},renderItem:renderTurningConnector,
     dimensions:['time','price','direction'],encode:{x:0,y:1},data:observations.filter(m=>m.shape||!showShapes).map(m=>[m.time,m.price,m.kind==='bottom'?1:-1])}]:[])]
  },{notMerge:true});
  if(isDay&&selectedDay){const index=labels.indexOf(selectedDay);if(index>=0)chart.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:index});}
 },[contentKey]);
 return <>{view==='daily'&&<div className="daily-pattern-controls" role="group" aria-label="日线形态显示选项">
  <label className="opening-volume-toggle"><input type="checkbox" checked={showDailyPatterns} onChange={e=>{setShowDailyPatterns(e.target.checked);try{localStorage.setItem('stock-monitor-show-daily-patterns-v1',String(e.target.checked));}catch{}}}/>显示日线形态</label>
  {showDailyPatterns&&<><span className="daily-pattern-mode">自动识别 · 同一区域择优显示</span><span className="daily-pattern-legend">{([...new Set(dayPatterns.map(p=>p.kind))]).map(kind=><span key={kind}><i style={{backgroundColor:dailyPatternColors[kind]}}/>{dayPatterns.find(p=>p.kind===kind)!.name}</span>)}</span></>}
 </div>}{view!=='daily'&&<TCostSettings value={costs} onChange={updateCosts} displayOptions={<div className="chart-display-options" role="group" aria-label="分时显示选项">
  <label className="opening-volume-toggle"><input type="checkbox" checked={showOpening} onChange={e=>{setShowOpening(e.target.checked);try{localStorage.setItem('stock-monitor-show-opening',String(e.target.checked));}catch{}}}/>显示开盘量</label>
  <label className="opening-volume-toggle"><input aria-label="显示形态底/顶" type="checkbox" checked={showShapes} onChange={e=>{setShowShapes(e.target.checked);try{localStorage.setItem('stock-monitor-show-turning-shapes-v1',String(e.target.checked));window.dispatchEvent(new window.Event('turning-display-change'));}catch{}}}/>显示形态底/顶</label>
  <label className="opening-volume-toggle"><input aria-label="显示Q1质量" type="checkbox" checked={showQuality} onChange={e=>{setShowQuality(e.target.checked);try{localStorage.setItem('stock-monitor-show-turning-v2',String(e.target.checked));window.dispatchEvent(new window.Event('turning-display-change'));}catch{}}}/>显示Q1质量</label>
 </div>}/>}{tradeHint?.scope===scope&&<div className="chart-trade-hint" role="status">{tradeHint.text}</div>}<div className={'chart'+(compact?' compact-chart':'')} ref={ref} onContextMenu={contextTrade} tabIndex={view==='daily'?0:undefined} onClick={()=>{if(view==='daily')ref.current?.focus();}} onKeyDown={e=>{if(view==='daily'&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();onMove?.(e.key==='ArrowLeft'?-1:1);}else if(view==='daily'&&e.key==='Enter'&&selectedDay)onOpenDay?.(selectedDay);}} aria-label={view==='daily'?'日K线及成交量':'分时价格及分钟成交量'}/>{view==='daily'&&<div className="average-caption">{Math.min(daily.length,DAILY_WINDOW)}根日K视窗 · ← / → 逐日移动，边界自动加载 · 缺口阴影：仅最近一个未回补区间，淡红向上、淡绿向下 · 盘中缺口待收盘确认 · 拖动浏览，缩放已关闭</div>}{view!=='daily'&&<div className="average-caption">{paperFills.some(f=>f.stamp.slice(0,10)===selectedDay&&f.side==='buy')&&paperFills.some(f=>f.stamp.slice(0,10)===selectedDay&&f.side==='sell')&&<span className="paper-day-t">T · 当日有买有卖　</span>}模拟成交：B买 / S卖；{(showShapes||showQuality)&&<>红点底 / 绿点顶：白字彩底为已确认形态，白边小点为Q1入选；独立Q1只画小点，重合只画一次。均标在确认时刻，不强制成对；Q1筛选未改，未证明稳定盈利 · </>}开盘量：09:31；触发：盘中顶部量。均在连续两分钟缩量确认后标在原分钟，仍封涨停时等待开板 · 亮蓝实线：个股 · 黄线：均价（累计成交额 ÷ 累计成交股数，含集合竞价）{benchmark&&previousClose&&previousClose>0?' · 灰色虚线：上证（以双方昨收涨跌幅对齐）':' · 上证叠加暂无对应日期分时或昨收数据'}{minute.some(b=>b.average&&Number.isFinite(+b.average)&&+b.average>0)?'':' · 当前缓存缺少成交额，暂无法显示均价线'}</div>}</>;
}
