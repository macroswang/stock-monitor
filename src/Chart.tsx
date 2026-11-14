import InfoNote from './InfoNote';
import {autoTradeMarks,autoTradeDetails,type AutoTradeChart} from './autoTradeMarks';
import {useEffect,useMemo,useRef,useState} from 'react';
import * as echarts from 'echarts';
import type {Bar,Daily,Event,IndexMinute,Ma250Pullback,E2Research,VolumeFlow} from './models';
import {price,wan,wanShares} from './format';
import {topVolumeMarks} from './volumeMarks';
import {turningQualityQ1} from './turningQualityQ1';

import {turningDisplayPoints} from './turningDisplay';
import {turningFinal,TURNING_FINAL_MODES} from './turningFinal';
import {turningFinalV3} from './turningFinalV3';
import {turningCombinedSignals} from './turningCombined';

// Chart top/bottom mode. Default = zhangle (shape-v2.4, the auto-trading signal);
// shape-v3 is an experimental feature flag (default off) selectable for comparison, and
// stable v2.0 stays available. Persisted across the page chart and the linked K-line
// minute chart via the same key. Auto-trading and autoTradeMarks always use v2.4.
type TurningChartMode='v3'|'zhangle'|'stable';
const TURNING_MODE_KEY='stock-monitor-turning-mode-v1';
const TURNING_MODE_LABELS:Record<TurningChartMode,string>={v3:'贴近涨乐通 v3（实验）',zhangle:'贴近涨乐通 v2.4（默认）',stable:'稳健 v2.0'};
const chartTurningEvents=(bars:Bar[],mode:TurningChartMode)=>mode==='v3'?turningFinalV3(bars):turningFinal(bars,TURNING_FINAL_MODES[mode]);
const readTurningMode=():TurningChartMode=>{try{const stored=localStorage.getItem(TURNING_MODE_KEY);return stored==='v3'||stored==='stable'?stored:'zhangle';}catch{return 'zhangle';}};
import {paperChartMarks,paperTradeColors} from './paperMarks';
import type {PaperFillPoint,PaperOrderPoint} from './paperMarks';
import {splitMinuteVolume} from './volumeFlow';
import {resolvedPriceLimits,intradayPriceScale,pricePercent} from './priceLimits';
import {dailyGaps} from './dailyGaps';
import {dailyPatterns,dailyPatternStatus} from './dailyPatterns';
import {dailyPatternOverlay,dailyPatternColors} from './dailyPatternOverlay';
import {selectDailyPatterns} from './dailyPatternSelection';
import {DAILY_WINDOW,dailyViewport,zoomCandleWindow} from './dailyWindow';
import CandleControls from './CandleControls';
import {isCandleView,weeklyBars,candleDate,movingAverage,readMovingAverages,candleHistoryNeed,MA_COLORS,type MovingAverages} from './candleData';
import {defaultTCosts,tProfit} from './tCosts';
import type {TCosts} from './tCosts';
import TCostSettings from './TCostSettings';
import {appendTradeTooltip} from './tradeTooltip';
import {benchmarkForStock,minuteMacd,minuteSlots,macdRange,macdNumber,readMacdParameters,macdParametersKey,type MacdParameters} from './minuteMacd';
import MacdSettings from './MacdSettings';
import {volumeDisplayMaximum} from './volumeScale';
const volumeTick=(n:number)=>Math.abs(n)>=1e8?(n/1e8).toFixed(1)+'亿':Math.abs(n)>=1e4?(n/1e4).toFixed(1)+'万':n.toFixed(0);
// Give both volume panes a little more room while keeping the stack in view.
function minutePanelLayout(height:number,priceExpansion=0){
 const auxiliaryHeight=Math.max(350,height-priceExpansion),auxiliary=Math.min(320,118+Math.max(0,auxiliaryHeight-350)*.7),volume=Math.round(auxiliary*.25),macd=Math.round(auxiliary*.3),indexVolume=volume;
 const price=height-22-4*22-volume-2*macd-indexVolume-32;
 const heights=[price,volume,macd,indexVolume,macd],grids:{top:number;height:number}[]=[],headers:number[]=[];
 let top=22;
 for(const [i,h] of heights.entries()){grids.push({top,height:h});top+=h;if(i<4){headers.push(top+6);top+=22;}}
 return {grids,headers};
}
const tradeLabelOffsets=new Map<string,[number,number]>();
// Font-box centering leaves small capital letters slightly high. Measure the
// visible glyph once per letter, using the exact font painted by the chart.
function tradeLabelOffset(text:string):[number,number]{
 const saved=tradeLabelOffsets.get(text);if(saved)return saved;
 let offset:[number,number]=[0,.5];
 const ctx=typeof document==='undefined'?null:document.createElement('canvas').getContext('2d');
 if(ctx){
  ctx.font='normal bold 8px Arial, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
  const m=ctx.measureText(text),x=(m.actualBoundingBoxLeft-m.actualBoundingBoxRight)/2,y=(m.actualBoundingBoxAscent-m.actualBoundingBoxDescent)/2;
  if(Number.isFinite(x)&&Number.isFinite(y))offset=[x,y];
 }
 tradeLabelOffsets.set(text,offset);return offset;
}
const renderTurningConnector:echarts.CustomSeriesRenderItem=(_params,api)=>{
 const [x,y]=api.coord!([api.value(0),api.value(1)]),direction=Number(api.value(2)),distance=Number(api.value(3));
 return {type:'line',shape:{x1:x,y1:y+direction*3,x2:x,y2:y+direction*(distance-1)},
  style:{stroke:String(api.visual('color')),lineWidth:1,lineDash:[2,2]},silent:true};
};
const renderHighVolumeConnector:echarts.CustomSeriesRenderItem=(_params,api)=>{
 const [x,y]=api.coord!([api.value(0),api.value(1)]),direction=Number(api.value(2)),distance=Number(api.value(3));
 return {type:'line',shape:{x1:x,y1:y+direction*3,x2:x-16,y2:y+direction*(distance-1)},style:{stroke:'#e9ad58',lineWidth:1,lineDash:[2,2]},silent:true};
};
const renderPaperConnector:echarts.CustomSeriesRenderItem=(_params,api)=>{
 const [x,y]=api.coord!([api.value(0),api.value(1)]),kind=Number(api.value(2)),direction=kind>0?1:-1,color=paperTradeColors[kind===1?'B':kind===-1?'S':'T'];
 return {type:'group',silent:true,children:[
  {type:'line',shape:{x1:x,y1:y+direction*2,x2:x,y2:y+direction*13},style:{stroke:color,lineWidth:1,lineDash:[3,3]}},
  {type:'circle',shape:{cx:x,cy:y,r:1.5},style:{fill:color}}
 ]};
};
export type BottomSignal={day:string;time:string;price:number};

export default function Chart({stockCode='',stockName='',macdBenchmark,autoTrading,minute=[],shapeOpening,daily:sourceDaily=[],view,events=[],selectedDay,onSelectDay,onOpenDay,onMove,onHistoryNeed,compact=false,fixedTurningMode,benchmark,previousClose,buySignals=[],onPaperTrade,paperFills=[],paperOrders,volumeFlow,limitUp,limitDown,currentPrice,ma250,e2,annualLineFocus=false,onBottomSignal}:{fixedTurningMode?:TurningChartMode;onBottomSignal?:(signal:BottomSignal|null)=>void;stockCode?:string;stockName?:string;macdBenchmark?:IndexMinute|null;autoTrading?:AutoTradeChart;limitUp?:number;limitDown?:number;currentPrice?:{price:number;time:string};volumeFlow?:VolumeFlow;paperFills?:PaperFillPoint[];paperOrders?:PaperOrderPoint[];onPaperTrade?:(point:{time:string;price:number;kind:string;side:'buy'|'sell';inChart?:boolean})=>void;buySignals?:{key:string;time:string;price:number}[];benchmark?:IndexMinute|null;previousClose?:number;minute?:Bar[];shapeOpening?:Bar[];daily?:Daily[];view:string;events?:Event[];selectedDay?:string;onSelectDay?:(day:string)=>void;onOpenDay?:(day:string)=>void;onMove?:(direction:number)=>void;onHistoryNeed?:(count:number)=>void;compact?:boolean;ma250?:Ma250Pullback|null;e2?:E2Research|null;annualLineFocus?:boolean}){
 // Opening quotes seed R1 only; plotted prices, volumes, MACD and Q1 keep their original input.
 const shapeBars=shapeOpening?[...shapeOpening,...minute]:minute;
 const daily=useMemo(()=>view==='weekly'?weeklyBars(sourceDaily):sourceDaily,[sourceDaily,view]);
 const selectedCandle=candleDate(daily,selectedDay,view==='weekly');
 const [maSetting,setMa]=useState(readMovingAverages);
 const annualMa=useMemo(()=>({periods:[250],enabled:[250],visible:true}),[]);
 const ma=annualLineFocus&&view==='daily'?annualMa:maSetting;
 const [macdParameters,setMacdParameters]=useState(readMacdParameters),[editMacd,setEditMacd]=useState(false);
 useEffect(()=>{const sync=()=>setMacdParameters(readMacdParameters());window.addEventListener('storage',sync);window.addEventListener('macd-parameters-change',sync);return()=>{window.removeEventListener('storage',sync);window.removeEventListener('macd-parameters-change',sync);};},[]);
 const updateMacd=(next:MacdParameters)=>{setMacdParameters(next);try{localStorage.setItem(macdParametersKey,JSON.stringify(next));window.dispatchEvent(new window.Event('macd-parameters-change'));}catch{}};
 const maValues=useMemo(()=>new Map(ma.periods.map(n=>[n,movingAverage(daily,n)])),[daily,ma.periods]);
 const [candleSizes,setCandleSizes]=useState<Record<string,number>>({daily:DAILY_WINDOW,weekly:DAILY_WINDOW});
 const candleWindows=useRef(new Map<string,{dates:string[];lastDate:string}>());
 const candleSelections=useRef(new Map<string,string|undefined>());
 const updateMa=(next:MovingAverages)=>{setMa(next);try{localStorage.setItem('stock-monitor-moving-averages-v1',JSON.stringify(next));}catch{}};
 const candleHistoryCount=candleHistoryNeed(candleSizes[view]||DAILY_WINDOW,ma);
 // 日K年线和E2研究标记始终开启；不读取旧的隐藏偏好。
 const showMa250=true,showE2=true;
 // 年线信号需要 250 根均线加 60 根方向比较；即使均线未显示也补足这段预热。
 const ma250HistoryNeed=view==='daily'&&(showMa250||showE2)?310:0;
 // 首次进入、切换日/周K以及读取已保存的长周期均线时，都主动补足预热历史。
 // onHistoryNeed 由父组件内联传入，不能放入依赖，否则会在每次渲染时重复请求。
 useEffect(()=>{if(isCandleView(view))onHistoryNeed?.(Math.max(candleHistoryCount,ma250HistoryNeed));},[view,stockCode,candleHistoryCount,ma250HistoryNeed]);
 const macdIndex=benchmarkForStock(stockCode),hasMacd=!isCandleView(view)&&!!macdIndex;
 const macdDataReady=!!macdIndex&&macdBenchmark?.code===macdIndex.code&&macdBenchmark.date===selectedDay&&macdBenchmark.bars.some(b=>minuteSlots.includes(b.time)&&Number(b.close)>0);
 const macdHeaders=useRef<(HTMLDivElement|null)[]>([]),volumeHeaders=useRef<(HTMLDivElement|null)[]>([]),refreshMacd=useRef<((index?:number)=>void)|null>(null);
 const [costs,setCosts]=useState<TCosts>(()=>{try{const saved=JSON.parse(localStorage.getItem('stock-monitor-t-costs-v4')||'null');return saved&&tProfit(10,10,saved)?saved:defaultTCosts;}catch{return defaultTCosts;}});
 const [showOpening,setShowOpening]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-opening')!=='false';}catch{return true;}});
 const [showShapes,setShowShapes]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-turning-shapes-v1')!=='false';}catch{return true;}});
 const showQuality=true;
 // v3 = experimental (feature flag, default off); zhangle = v2.4 (default/trading); stable = v2.0.
 // All three are hard-capped at 3/kind/day.
 const [preferredTurningMode,setTurningMode]=useState<TurningChartMode>(readTurningMode);
 const turningMode=fixedTurningMode||preferredTurningMode;
 const updateTurningMode=(mode:TurningChartMode)=>{setTurningMode(mode);try{localStorage.setItem(TURNING_MODE_KEY,mode);window.dispatchEvent(new window.Event('turning-display-change'));}catch{}};
 const [plotHeight,setPlotHeight]=useState(0);
 const minutePanels=minutePanelLayout(plotHeight||350,compact?0:30);
 const [showTriggered,setShowTriggered]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-trigger-volume')!=='false';}catch{return true;}});
 const [showDailyPatterns,setShowDailyPatterns]=useState(()=>{try{return localStorage.getItem('stock-monitor-show-daily-patterns-v1')!=='false';}catch{return true;}});
 const dayPatterns=useMemo(()=>view==='daily'&&!annualLineFocus?selectDailyPatterns(dailyPatterns(daily)):[],[daily,view,annualLineFocus]);
 const ma250Signals=useMemo(()=>{
  if(view!=='daily'||!showMa250||!ma250?.signals?.length)return [];
  const dates=new Set(daily.map(b=>b.date));
  return ma250.signals.filter(s=>s&&dates.has(s.date));
 },[daily,view,ma250,showMa250]);
 const e2Signals=useMemo(()=>{
  if(view!=='daily'||!showE2)return [];
  const dates=new Set(daily.filter(b=>!b.provisional).map(b=>b.date));
  return (e2?.signals||[]).filter(s=>s.research_only&&dates.has(s.date));
 },[daily,view,e2,showE2]);
 const ma250Breakouts=useMemo(()=>{
  if(view!=='daily'||!showMa250||!ma250?.breakouts?.length)return [];
  const dates=new Set(daily.map(b=>b.date));
  return ma250.breakouts.filter(s=>s&&dates.has(s.date)).map(s=>({...s,
   quality:!!s.quality&&s.slope60_pct!==null&&s.slope60_pct>=0&&s.volume_ratio!==null&&s.volume_ratio>=1}));
 },[daily,view,ma250,showMa250]);
 useEffect(()=>{const sync=()=>{try{setShowShapes(localStorage.getItem('stock-monitor-show-turning-shapes-v1')!=='false');setShowTriggered(localStorage.getItem('stock-monitor-show-trigger-volume')!=='false');setTurningMode(readTurningMode());}catch{}};window.addEventListener('storage',sync);window.addEventListener('turning-display-change',sync);return()=>{window.removeEventListener('storage',sync);window.removeEventListener('turning-display-change',sync);};},[]);
 const costsRef=useRef(costs);costsRef.current=costs;
 const refreshTrade=useRef<(()=>void)|null>(null);
 const updateCosts=(next:TCosts)=>{costsRef.current=next;setCosts(next);refreshTrade.current?.();if(tProfit(10,10,next)){try{localStorage.setItem('stock-monitor-t-costs-v4',JSON.stringify(next));}catch{}}};
 const scope=view+'|'+(selectedDay||events[0]?.trading_date||'');
 const [choice,setChoice]=useState<{scope:string;time:string;price:number;kind?:'底'|'顶'|'位置'}|null>(null);
 useEffect(()=>setChoice(null),[scope]);
 const visibleMarks=isCandleView(view)?[]:topVolumeMarks(minute,events,showOpening,showTriggered);
 const latestEvent=events.filter(e=>visibleMarks.some(m=>m.coord[0]===e.candidate_time)).sort((a,b)=>a.event_label.localeCompare(b.event_label)||a.candidate_time.localeCompare(b.candidate_time)).at(-1);
 const latestMark=visibleMarks.find(m=>m.coord[0]===latestEvent?.candidate_time);
 const finalTurns=isCandleView(view)?[]:chartTurningEvents(shapeBars,turningMode);
 const q1Turns=isCandleView(view)?[]:turningQualityQ1(minute);
 // 用户规则（2026-11-12）：Q1 顶/底成立时也分别标记为“顶/底”信号；与同 kind 的 v2 信号同分钟出现时
 // 按既有显示规则合并（shape 优先、Q1 只在剩余槽位补位、每日每类≤3），且同一股价不重复出现。
 // “底/顶”计数器都统计实际显示的同类信号（v2 + 补位 Q1）。
 const capPoints=fixedTurningMode?[]:turningDisplayPoints(finalTurns,q1Turns,true,true);
 // 用户规则：Q1 顶/底都升级为对应信号；“底/顶”计数器统计实际显示的同类信号数（v2 + 补位 Q1，均≤3）。
 const turnCounts={bottom:capPoints.filter(m=>m.kind==='bottom').length,top:capPoints.filter(m=>m.kind==='top').length};
 const selectableTurns=isCandleView(view)?[]:turningDisplayPoints(showShapes?finalTurns:[],showQuality?q1Turns:[],showShapes,showQuality);
 const latestBottom=selectableTurns.filter(point=>point.kind==='bottom').at(-1);
 const bottomCallback=useRef(onBottomSignal);bottomCallback.current=onBottomSignal;
 useEffect(()=>{
  if(!isCandleView(view)&&selectedDay)bottomCallback.current?.(latestBottom?{day:selectedDay,time:latestBottom.time,price:latestBottom.price}:null);
 },[stockCode,view,selectedDay,latestBottom?.time,latestBottom?.price]);
 const chosen=choice?.scope===scope&&(choice.kind==='位置'?minute.some(b=>b.time===choice.time&&b.complete):choice.kind?selectableTurns.some(m=>m.time===choice.time&&(m.kind==='bottom'?'底':'顶')===choice.kind):visibleMarks.some(m=>m.coord[0]===choice.time))?choice:latestMark?{scope,time:latestMark.coord[0],price:latestMark.coord[1]}:null;
 const quotePrices=[...minute.map(b=>+b.close),...(currentPrice?[currentPrice.price]:[])];
 const priceLimits=resolvedPriceLimits(previousClose,quotePrices,{up:limitUp,down:limitDown});
 const [tradeHint,setTradeHint]=useState<{scope:string;text:string}|null>(null);
 const contextTrade=(event:React.MouseEvent<HTMLDivElement>)=>{
  if(isCandleView(view)||!onPaperTrade||!instance.current)return;
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
 const pointer=useRef<{x:number;y:number;scope:string}|null>(null),renderedScope=useRef('');
 const contentKey=JSON.stringify([shapeOpening?.map(b=>[b.time,b.close,b.complete]),minute.map(b=>[b.time,b.close,b.volume,b.complete,b.average]),daily.map(b=>[b.date,b.open,b.close,b.low,b.high,b.volume,b.provisional]),view,events.map(e=>[e.key,e.trading_date,e.candidate_time,e.confirmation_label,e.event_label,e.mode]),selectedDay,benchmark,macdBenchmark,stockCode,hasMacd,macdParameters,previousClose,buySignals,chosen,showOpening,showTriggered,showShapes,showQuality,turningMode,autoTrading,showDailyPatterns,dayPatterns.map(p=>p.key),showMa250,ma250Signals,ma250Breakouts,showE2,e2Signals,paperFills,paperOrders,volumeFlow,limitUp,limitDown,currentPrice?.price,plotHeight,ma,candleSizes]);
 const open=useRef(onOpenDay);open.current=onOpenDay;const plot=useRef({daily,view,minute,stockCode});plot.current={daily,view,minute,stockCode};
 const ref=useRef<HTMLDivElement>(null);const instance=useRef<echarts.ECharts|null>(null);const labelsKey=useRef('');const select=useRef(onSelectDay);select.current=onSelectDay;
 // Fit the comparison stack to the remaining viewport without reacting to scroll.
 useEffect(()=>{
  const node=ref.current;if(!node||!hasMacd||compact)return;
  let frame=0;
  const fit=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
   if(!node.getClientRects().length)return;
   const top=node.getBoundingClientRect().top+window.scrollY;
   const height=Math.round(Math.max(350,document.documentElement.clientHeight-top-22));
   const value=height+'px';if(node.style.getPropertyValue('--minute-chart-height')!==value)node.style.setProperty('--minute-chart-height',value);
  });};
  const observer=new ResizeObserver(fit),shell=node.parentElement;
  for(const sibling of node.closest('.detail')?.children||[])if(shell&&sibling.compareDocumentPosition(shell)&Node.DOCUMENT_POSITION_FOLLOWING)observer.observe(sibling);
  const overview=document.querySelector('.home-overview');if(overview)observer.observe(overview);
  window.addEventListener('resize',fit);fit();
  return()=>{cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('resize',fit);node.style.removeProperty('--minute-chart-height');};
 },[hasMacd,compact]);
 const windowDates=useRef<string[]>([]);const lastDailyDate=useRef('');
 const zoomCandles=(direction:number)=>{
  const chart=instance.current,rows=daily;if(!chart||!isCandleView(view)||!rows.length)return;
  const z=(chart.getOption().dataZoom as {start:number;end:number}[])[0],n=rows.length-1;
  const lo=Math.round(n*z.start/100),hi=Math.round(n*z.end/100),anchor=rows.findIndex(b=>b.date===selectedCandle);
  const next=zoomCandleWindow(rows.length,lo,hi,direction,anchor>=lo&&anchor<=hi?anchor:hi);
  candleWindows.current.set(stockCode+'|'+view,{dates:[rows[next.lo].date,rows[next.hi].date],lastDate:rows.at(-1)!.date});
  pointer.current=null;setCandleSizes(old=>({...old,[view]:next.desired}));onHistoryNeed?.(candleHistoryNeed(next.desired,ma));
  ref.current?.focus({preventScroll:true});
 };
 useEffect(()=>{if(!ref.current)return;const chart=echarts.init(ref.current,undefined,{renderer:'canvas'});instance.current=chart;
  chart.on('click',params=>{
   if(!isCandleView(plot.current.view)&&params.componentType==='markPoint'){
    const data=params.data as {value?:unknown;coord?:[string,number];turningKind?:'底'|'顶'}|undefined;
    if((data?.value==='高'||data?.value==='开盘量'||!!data?.turningKind)&&data.coord&&Number.isFinite(+data.coord[1])&&+data.coord[1]>0)setChoice({scope:scopeRef.current,time:data.coord[0],price:+data.coord[1],kind:data.turningKind});
   }
   if(!isCandleView(plot.current.view)&&params.componentType==='series'&&['价格','涨停走势','跌停走势'].includes(params.seriesName||'')){const bar=plot.current.minute.find(b=>b.time===params.name);if(bar?.complete)setChoice({scope:scopeRef.current,time:bar.time,price:+bar.close,kind:'位置'});}
   if(params.componentType==='series'&&params.name&&/^\d{4}-\d{2}-\d{2}$/.test(params.name))select.current?.(params.name);
  });
  chart.on('dblclick',params=>{if(isCandleView(plot.current.view)&&params.componentType==='series'&&params.name)open.current?.(params.name);});
  chart.on('datazoom',()=>{const z=(chart.getOption()?.dataZoom as {start?:number;end?:number}[])?.[0];const d=plot.current.daily;if(isCandleView(plot.current.view)&&d.length&&z){windowDates.current=[d[Math.round((d.length-1)*(z.start??0)/100)]?.date,d[Math.round((d.length-1)*(z.end??100)/100)]?.date];candleWindows.current.set(plot.current.stockCode+'|'+plot.current.view,{dates:windowDates.current,lastDate:d.at(-1)!.date});}});
  chart.on('updateAxisPointer',event=>{const value=(event as {axesInfo?:{axisDim?:string;value:unknown}[]}).axesInfo?.find(a=>a.axisDim==='x')?.value;const index=typeof value==='number'?value:typeof value==='string'?minuteSlots.indexOf(value):-1;if(Number.isInteger(index)&&index>=0&&index<minuteSlots.length)refreshMacd.current?.(index);});
  const rememberPointer=(event:{offsetX:number;offsetY:number})=>{pointer.current={x:event.offsetX,y:event.offsetY,scope:scopeRef.current};};
  chart.getZr().on('mousemove',rememberPointer);chart.getZr().on('mousedown',rememberPointer);
  chart.getZr().on('globalout',()=>{pointer.current=null;refreshMacd.current?.();});
  chart.getZr().on('click',event=>{if(event.target||isCandleView(plot.current.view)||!chart.containPixel({gridIndex:0},[event.offsetX,event.offsetY]))return;const coord=chart.convertFromPixel({gridIndex:0},[event.offsetX,event.offsetY]) as number[];const all=[...Array.from({length:121},(_,i)=>570+i),...Array.from({length:120},(_,i)=>781+i)];const m=all[Math.round(coord[0])];if(m===undefined)return;const time=`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;if(plot.current.minute.some(b=>b.time===time&&b.complete)&&Number.isFinite(coord[1])&&coord[1]>0)setChoice({scope:scopeRef.current,time,price:Math.round(coord[1]*100)/100,kind:'位置'});});
  const observer=new ResizeObserver(()=>{chart.resize();setPlotHeight(chart.getHeight());});observer.observe(ref.current);
  return()=>{observer.disconnect();chart.dispose();instance.current=null;};
 },[]);
 useEffect(()=>{
  const chart=instance.current;if(!chart)return;const isDay=isCandleView(view);const labels=isDay?daily.map(b=>b.date):minuteSlots;
  const byTime=new Map(minute.map(b=>[b.time,b]));const aligned=labels.map(t=>byTime.get(t));
  const gaps=view==='daily'?dailyGaps(daily):[];
  const visibleGaps=gaps.filter(g=>!g.filledOn).slice(-1);
  const patternSeries=isDay&&showDailyPatterns?dailyPatternOverlay(dayPatterns,()=>chart.getWidth()):[];
  const executionPoints=paperChartMarks(isDay?paperFills:paperFills.filter(f=>f.stamp.slice(0,10)===selectedDay),isDay).map(t=>view==='weekly'?{...t,time:candleDate(daily,t.time,true)||t.time}:t);
  const tradePoints=!isDay&&paperOrders!==undefined?paperChartMarks(paperOrders.filter(f=>f.stamp.slice(0,10)===selectedDay)):executionPoints;
  const tradesByTime=new Map<string,typeof executionPoints>();for(const t of executionPoints){const arr=tradesByTime.get(t.time)||[];arr.push(t);tradesByTime.set(t.time,arr);}
  const candleByDate=new Map(daily.map(b=>[b.date,b]));
  const tradeAnchors=tradePoints.filter(m=>labels.includes(m.time)).map(m=>{
   const candle=candleByDate.get(m.time),value=isDay?(m.value==='B'?candle?.low:candle?.high):byTime.get(m.time)?.close;
   return {...m,anchor:Number(value)>0?Number(value):m.price};
  });
  const tradeMarks=tradeAnchors.map(m=>({coord:[m.time,m.anchor],value:m.value,executionPrice:m.price,paperTrade:true,silent:true,symbol:'circle',symbolSize:10,
   symbolOffset:m.value==='B'?[0,18]:[0,-18],itemStyle:{color:paperTradeColors[m.value],borderColor:'#edf4ff',borderWidth:.7},label:{show:true,formatter:m.value,position:'inside',align:'center',verticalAlign:'middle',offset:tradeLabelOffset(m.value),padding:0,lineHeight:10,color:'#fff',fontFamily:'Arial, sans-serif',fontSize:8,fontWeight:'bold'}}));

  // Automatic-trade annotations read the fixed high-coverage shape-v2.4 stream: the
  // display mode may switch to stable, but order matching must follow the trading rule.
 // Auto-trade annotations follow the backend trading stream: v2.4 + Q1 fill (shape-v2-q1).
 const autoTradeShapes=isDay?[]:turningCombinedSignals(turningFinal(shapeBars,TURNING_FINAL_MODES.zhangle),q1Turns),shapes=isDay||!showShapes?[]:finalTurns;
  const automatic=isDay?[]:autoTradeMarks(autoTrading,autoTradeShapes,selectedDay||'').filter(m=>labels.includes(m.time));
  const quality=isDay||!showQuality?[]:q1Turns;
  const observations=turningDisplayPoints(shapes,quality,showShapes,showQuality);
  const volume=isDay?daily.map(b=>+b.volume/10000):aligned.map(b=>b?b.volume/100:null);
  const splits=aligned.map(b=>b?splitMinuteVolume(b,volumeFlow?.day===selectedDay?volumeFlow:undefined):null);
  const colors=isDay?daily.map(b=>+b.close>=+b.open?'#ef6568':'#36b898'):aligned.map((b,i)=>!b||!aligned[i-1]||+b.close>=+aligned[i-1]!.close?'#ef6568':'#36b898');
  const indexByTime=new Map(benchmark?.bars.map(b=>[b.time,+b.close])||[]);
  const canOverlay=!isDay&&!!benchmark&&!!previousClose&&previousClose>0&&+benchmark.previous_close>0;
  const indexLine=aligned.map(b=>b&&canOverlay&&indexByTime.has(b.time)?indexByTime.get(b.time)!/+benchmark!.previous_close*previousClose!:null);
  const averages=aligned.map(b=>b?.average&&Number.isFinite(+b.average)&&+b.average>0?+b.average:null);
  const showPercent=!isDay&&Number.isFinite(previousClose)&&Number(previousClose)>0&&minute.length>0;
  const stockMacd=hasMacd?minuteMacd(minute,macdParameters):[],stockTimes=minute.filter(b=>minuteSlots.includes(b.time)&&Number(b.close)>0).map(b=>b.time).sort(),firstStockTime=stockTimes[0]||'',lastStockTime=stockTimes.at(-1)||'';
  const matchingMacdIndex=!!macdIndex&&macdBenchmark?.code===macdIndex.code&&macdBenchmark.date===selectedDay;
  const indexBars=matchingMacdIndex?macdBenchmark!.bars.filter(b=>b.time>=firstStockTime&&b.time<=lastStockTime):[];
  const indexMacd=hasMacd?minuteMacd(indexBars,macdParameters):[];
  const indexVolumeByTime=new Map<string,number|null>();
  for(const b of indexBars)indexVolumeByTime.set(b.time,indexVolumeByTime.has(b.time)?null:Number.isSafeInteger(b.volume_lots)&&b.volume_lots!>=0?b.volume_lots!:null);
  const indexVolume=labels.map(t=>{const lots=indexVolumeByTime.get(t);return lots===undefined||lots===null?null:lots/10000;});
  const volumeMax=isDay?undefined:volumeDisplayMaximum(volume),indexVolumeMax=volumeDisplayMaximum(indexVolume);
  const indexPrices=new Map<string,number>();for(const b of indexBars)indexPrices.set(b.time,indexPrices.has(b.time)?NaN:Number(b.close));
  let indexPrevious=Number(macdBenchmark?.previous_close),indexColor='#ef6568',indexStarted=false;
  const indexVolumeColors=labels.map(time=>{const close=indexPrices.get(time);if(!Number.isFinite(close)||!close||close<=0){if(indexStarted)indexPrevious=NaN;return '#8c9db6';}const color=Number.isFinite(indexPrevious)?close>indexPrevious?'#ef6568':close<indexPrevious?'#36b898':indexColor:'#8c9db6';indexPrevious=close;indexStarted=true;if(color!=='#8c9db6')indexColor=color;return color;});
  const macdYAxis=2+Number(showPercent),axisIndices=hasMacd?[0,1,2,3,4]:[0,1];
  let lastHeaderIndex=-2;
  refreshMacd.current=hasMacd?(index)=>{
   const idx=index??stockMacd.reduce((last,p,i)=>p?i:last,-1);if(idx===lastHeaderIndex)return;lastHeaderIndex=idx;
   for(const [i,values] of [volume,indexVolume].entries()){
    const header=volumeHeaders.current[i],value=values[idx];if(!header)continue;
    const time=header.querySelector('time'),number=header.querySelector('.volume-value');
    if(time)time.textContent=labels[idx]||'';if(number)number.textContent=value===null||value===undefined?'—':wan(value)+(i?' 万手':' 手');
   }
   for(const [i,points] of [stockMacd,indexMacd].entries()){
    const header=macdHeaders.current[i],p=points[idx];if(!header)continue;
    for(const [key,value] of [['time',labels[idx]||''],['dif',`DIF ${p?macdNumber(p.dif):'—'}`],['dea',`DEA ${p?macdNumber(p.dea):'—'}`],['histogram',`MACD ${p?macdNumber(p.histogram):'—'}`]]){const el=header.querySelector<HTMLElement>(`[data-macd="${key}"]`);if(el){el.textContent=value;if(key==='histogram')el.style.color=p&&p.histogram<0?'#36b898':'#ef6568';}}
   }
  }:null;
  // Benchmark overlays cannot expand the stock's price axis beyond its actual limit.
  const priceValues=[...automatic.map(m=>m.price),...tradePoints.map(m=>m.price),...minute.map(b=>+b.close),...averages,...(currentPrice?[currentPrice.price]:[])].filter((n):n is number=>n!==null&&Number.isFinite(n)&&n>0);
  const priceScale=showPercent?intradayPriceScale(previousClose,priceValues,priceLimits):{};
  const limitLines=[{kind:'涨停',value:priceLimits.up,color:'#ef6568',position:'insideEndBottom'},{kind:'跌停',value:priceLimits.down,color:'#36b898',position:'insideEndTop'}].filter(row=>row.value!==undefined&&row.value>=Number(priceScale.min)&&row.value<=Number(priceScale.max)).map(row=>({name:row.kind,yAxis:row.value,lineStyle:{color:row.color,type:'dashed',width:1},label:{show:true,position:row.position,color:row.color,fontSize:10,formatter:`${row.kind} ${row.value!.toFixed(2)}（${pricePercent(row.value!,Number(previousClose))}）`}}));
  const percentLabel=(value:number)=>{const pct=(value/Number(previousClose)-1)*100,rounded=Math.abs(pct)<.005?0:pct;return `{${rounded>0?'rise':rounded<0?'fall':'flat'}|${rounded>0?'+':''}${rounded.toFixed(2)}%}`;};

  const marks=isDay?[]:
    topVolumeMarks(minute,events,showOpening,showTriggered);
  const key=view+labels.join('|');const old=chart.getOption()?.dataZoom as {start?:number;end?:number}[]|undefined;
  let zoom=key===labelsKey.current?{start:old?.[0]?.start??0,end:old?.[0]?.end??100}:{start:0,end:100};labelsKey.current=key;
  if(isDay&&labels.length){const candleKey=stockCode+'|'+view,saved=candleWindows.current.get(candleKey),selectionChanged=candleSelections.current.get(candleKey)!==selectedCandle;const {lo,hi}=dailyViewport(labels,saved?.dates||[],!saved||selectionChanged?selectedCandle:undefined,saved?.lastDate||'',candleSizes[view]);candleSelections.current.set(candleKey,selectedCandle);lastDailyDate.current=labels.at(-1)||'';zoom={start:lo/Math.max(1,labels.length-1)*100,end:hi/Math.max(1,labels.length-1)*100};windowDates.current=[labels[lo],labels[hi]];candleWindows.current.set(stockCode+'|'+view,{dates:windowDates.current,lastDate:lastDailyDate.current});}
  const visibleMinutes=Math.max(1,(zoom.end-zoom.start)/100*Math.max(0,labels.length-1)+1);
  const gridStep=visibleMinutes>100?30:visibleMinutes>40?15:5;
  const timeTick=(_index:number,label:string)=>{const [h,m]=label.split(':').map(Number);return label===labels[0]||label===labels.at(-1)||(h*60+m)%gridStep===0;};
  const timeGrid=isDay?{}:{axisTick:{interval:timeTick},splitLine:{show:true,interval:timeTick,lineStyle:{color:'#69343f',opacity:.65,width:1}}};
  const axisLow=showPercent?Number(priceScale.min):Math.min(...priceValues),axisHigh=showPercent?Number(priceScale.max):Math.max(...priceValues);
  const priceHeight=hasMacd?minutePanels.grids[0].height:chart.getHeight()*.55;
  const ma250Reason:Record<string,string>={market:'指数不在年线上或数据缺失','broke-line':'回踩跌破年线','no-higher-low':'回踩低点低于前低',extended:'距年线超过7%'};
const signalLayout=(value:number,direction:number,flippedDistance=45)=>{
   const room=(direction>0?value-axisLow:axisHigh-value)/Math.max(.000001,axisHigh-axisLow)*priceHeight;
   const flipped=room<41,dir=flipped?-direction:direction;
   return {direction:dir,distance:flipped?flippedDistance:24,position:dir>0?'bottom':'top'};
  };
  const observationMarks=observations.map(m=>{
   const color=m.kind==='bottom'?'#ff5b78':'#00bf83',layout=signalLayout(m.price,m.kind==='bottom'?1:-1);
   // 用户规则：Q1 顶/底在图表上都按对应“顶/底信号”显示（与 v2 信号相同的徽标/文案）。
   return {coord:[m.time,m.price],turningKind:m.kind==='bottom'?'底':'顶',value:m.kind==='bottom'?'底信号':'顶信号',
    observationKey:m.shape?.key,qualityKey:m.q1?.key,promotedBottom:!!m.promotedBottom,promotedTop:!!m.promotedTop,connectorDirection:layout.direction,connectorDistance:layout.distance,symbol:'circle',symbolSize:chosen?.kind===(m.kind==='bottom'?'底':'顶')&&chosen.time===m.time?6:3,
    itemStyle:{color,borderColor:'#fff',borderWidth:chosen?.kind===(m.kind==='bottom'?'底':'顶')&&chosen.time===m.time?2:m.q1?1:0},
    label:{show:true,position:layout.position,distance:layout.distance,formatter:m.kind==='bottom'?'底':'顶',
     color:'#fff',backgroundColor:m.kind==='bottom'?'#c92f53':'#008660',borderColor:color,borderWidth:.6,borderRadius:3,width:14,height:14,padding:0,align:'center',
     fontFamily:'"PingFang SC","Microsoft YaHei",sans-serif',fontSize:9,fontWeight:600,lineHeight:14}};
  });
  const volumeMarkers=marks.map(m=>{
   const layout=signalLayout(m.coord[1],-1,24);
   return {...m,symbol:'circle',symbolSize:chosen&&!chosen.kind&&m.coord[0]===chosen.time?5:3,connectorDirection:layout.direction,connectorDistance:layout.distance,
    itemStyle:{color:m.value==='开盘量'?'#8798b2':'#e9ad58'},
    label:m.value==='高'?{show:true,formatter:'高',position:layout.position,distance:layout.distance,offset:[-16,0],color:'#fff',backgroundColor:'#9b6b16',borderColor:'#e9ad58',borderWidth:.6,borderRadius:3,width:14,height:14,fontSize:9,fontWeight:600,lineHeight:14,padding:0,align:'center'}:{show:true,formatter:m.value,fontSize:8,color:'#a7b6cc',position:'top',distance:4}};
  });
  chart.setOption({backgroundColor:'transparent',animation:false,textStyle:{color:'#9dacc5',fontFamily:'sans-serif'},
   legend:{show:!isDay,data:['价格','均价',...(canOverlay?['上证走势']:[])],top:0,textStyle:{color:'#9dacc5',...(hasMacd?{fontSize:10}: {})},...(hasMacd?{itemWidth:16,itemHeight:8,itemGap:14}: {})},
   tooltip:{trigger:'axis',confine:false,enterable:false,className:'interactive-price-tooltip',transitionDuration:0,showDelay:0,hideDelay:100,axisPointer:{type:'cross',lineStyle:{color:'#a8bad1',type:'dashed'},crossStyle:{color:'#a8bad1',type:'dashed'}},backgroundColor:'#162238',borderColor:'#34465e',textStyle:{color:'#e7edf7'},
    extraCssText:(isDay?'padding:4px 7px;':'padding:7px 9px;')+'pointer-events:none;',position:(point:number[],_params:unknown,_dom:HTMLElement,_rect:unknown,size:{contentSize:number[];viewSize:number[]})=>{
     const canvas=chart.getDom(),bounds=canvas.getBoundingClientRect(),host=canvas.closest('.detail');
     const top=Math.max(8,(isDay?bounds.top:host?.getBoundingClientRect().top??bounds.top)+8);
     const [width,height]=size.contentSize,gap=16,left=8,right=Math.max(left,size.viewSize[0]-width-12);
     const x=point[0]>size.viewSize[0]/2?left:right;
     let y=top-bounds.top;
     // Very narrow panes may not have room beside the crosshair. Move vertically
     // as well in that case, always keeping the pointer outside the popup.
     if(point[0]>=x-gap&&point[0]<=x+width+gap&&point[1]>=y-gap&&point[1]<=y+height+gap){
      y=point[1]+gap+height<=window.innerHeight-bounds.top-8?point[1]+gap:point[1]-height-gap;
     }
     const minY=isDay?Math.max(8,8-bounds.top):8-bounds.top;
     const maxY=Math.min(window.innerHeight-bounds.top-height-8,isDay?size.viewSize[1]-height-8:Infinity);
     y=Math.max(minY,Math.min(y,maxY));
     return [x,y];
    },
    formatter:(params:unknown)=>{const first=(Array.isArray(params)?params[0]:params) as {dataIndex?:number}|undefined;const idx=first?.dataIndex??-1;if(idx>=0)refreshMacd.current?.(idx);const root=document.createElement('div');root.className='quote-tooltip docked-tooltip '+(isDay?'daily-tooltip':'minute-tooltip');
     if(observations.some(m=>m.time===aligned[idx]?.time)){root.style.maxWidth='min(580px, calc(100vw - 80px))';root.style.whiteSpace='normal';}
     const rows:string[]=[];if(isDay){const b=daily[idx];if(b){rows.push(view==='weekly'?`周K · ${'startDate' in b?b.startDate:b.date}—${b.date}${b.provisional?'（含盘中数据）':''}`:b.provisional?b.date+' · 盘中日K（未收盘）':b.date,`开盘：${price(b.open)} 元`,`收盘：${price(b.close)} 元`,`最高：${price(b.high)} 元`,`最低：${price(b.low)} 元`,`成交量：${wanShares(b.volume)} 万股`);for(const gap of gaps.filter(g=>g.date===b.date))rows.push(`${gap.provisional?'盘中':''}${gap.direction==='up'?'向上':'向下'}跳空：${price(gap.originalLow)}—${price(gap.originalHigh)} 元`,gap.filledOn?`已回补：${gap.filledOn}`:`未回补：${price(gap.low)}—${price(gap.high)} 元`);const n=events.filter(e=>view==='weekly'?e.trading_date>=(('startDate' in b?b.startDate:b.date) as string)&&e.trading_date<=b.date:e.trading_date===b.date).length;if(n)rows.push(`触发：${n} 次`);for(const n of ma.visible?ma.enabled:[]){const v=maValues.get(n)![idx];rows.push(`MA${n}：${v===null?'—':v.toFixed(2)+' 元'}`);}for(const signal of ma250Signals.filter(s=>s.date===b.date)){rows.push(`年线回踩${signal.strong?'（强）':''}：收 ${price(signal.close)} 元 / MA250 ${price(signal.ma250)} 元（${signal.distance_pct>=0?'+':''}${signal.distance_pct.toFixed(1)}%）`);rows.push(`回踩：${signal.touch_date} 低点 ${price(signal.touch_low)} 元（较年线 ${(-signal.touch_depth_pct).toFixed(1)}%）`);rows.push(`自高点回撤 ${signal.pullback_pct.toFixed(1)}% · 参考止损 ${price(signal.stop)} 元`);if(signal.atr20_pct!==undefined&&signal.atr20_pct!==null)rows.push(`波动：ATR20 ${signal.atr20_pct.toFixed(1)}%`);rows.push(signal.strong?'强信号：指数在年线上、回踩未破年线、未破前低、距年线≤7%':'强信号未满足：'+((signal.strong_reasons||[]).map(reason=>ma250Reason[reason]||reason).join('、')||'指数数据缺失'));}for(const item of ma250Breakouts.filter(item=>item.date===b.date)){rows.push('突破年线'+(item.quality?'（确认）':'（观察）')+'：收 '+price(item.close)+' 元 / MA250 '+price(item.ma250)+' 元（+'+item.margin_pct.toFixed(1)+'%）');rows.push('年线斜率60日 '+(item.slope60_pct===null?'—':(item.slope60_pct>=0?'+':'')+item.slope60_pct.toFixed(1)+'%')+' · 量比 '+(item.volume_ratio===null?'—':item.volume_ratio.toFixed(2))+' · 此前在年线下 '+item.days_below+' 日');}for(const item of e2Signals.filter(item=>item.date===b.date)){rows.push('E2确认 · 研究参考',`源强信号：${item.source_date} · 第${item.confirmation_day}个交易日确认`,`收盘 ${price(item.close)} 元 > 源信号高点 ${price(item.source_high)} 元`,`收盘仍在年线1%以上及MA5以上，沪深300在年线上`,`仅研究参考，不进入正式提醒或自动交易；后续入场需另行判断`);}rows.push(view==='weekly'?'双击查看该周最后交易日分时':'双击查看当天分时');}}
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
      // Q1 顶/底均按对应“顶/底信号”呈现；仅在来源不同时补一行“来源：Q1 质量点”。
      const label=point.kind==='bottom'?'底信号':'顶信号';
      rows.push(`${label}：${price(point.price)} 元`);
      if(point.shape&&Number.isFinite(point.shape.quality))rows.push(`质量分：${point.shape.quality!.toFixed(2)}`);
      rows.push(`候选点：${observation.candidateTime} · ${price(observation.candidatePrice)} 元`,
       `${point.shape?'发出时间':'确认时间'}：${point.time} · ${price(point.price)} 元`);
      if(!point.shape)rows.push('来源：Q1 质量点');
     }
     for(const t of tradesByTime.get(labels[idx])||[])rows.push(`模拟成交 ${t.value}：${t.buyShares?`买入${t.buyShares}股 · 均价${price(t.buyAmount/t.buyShares/100)}元`:''}${t.buyShares&&t.sellShares?'；':''}${t.sellShares?`卖出${t.sellShares}股 · 均价${price(t.sellAmount/t.sellShares/100)}元`:''}${t.value==='T'?'（当日有买有卖）':''}`);
     if(!isDay)for(const t of tradePoints.filter(t=>t.time===labels[idx]&&t.orderCount&&(t.fills>t.orderCount||t.orderCount>1))){
      rows.push(`委托累计 ${t.value}：${t.buyShares?'买入'+t.buyShares:'卖出'+t.sellShares}股 · 均价${price(t.price)}元（${t.orderCount}笔委托，${t.fills}次成交，${t.time}—${t.lastTime}）`);
     }
     const comparison=document.createElement('div');comparison.className='tooltip-comparison';
     for(const text of rows){
      const row=document.createElement('div');
      const split=text.indexOf('：');
      if(split>=0){const label=document.createElement('span');label.textContent=text.slice(0,split+1);const value=document.createElement('span');value.textContent=text.slice(split+1).trim();row.append(label,value);row.className='quote-detail';if(text.startsWith('涨停：'))value.style.color='#ed7d81';if(text.startsWith('跌停：'))value.style.color='#51c7aa';if(text.startsWith('涨跌幅：'))value.style.color=text.includes('：-')?'#51c7aa':text.includes('：+')?'#ed7d81':'#e7edf7';}else row.textContent=text;
      if(split<0||/^(基准|模拟成交|委托累计|买卖量为约值|个股量柱|指数量柱)/.test(text)||(isDay&&!/^(开盘|收盘|最高|最低|成交量|触发|MA\d+)：/.test(text)))row.classList.add('quote-wide');
      if(/^相对(触发|底|顶|位置)涨跌幅/.test(text)){row.className='trigger-change';row.style.color=text.includes('：-')?'#69d9ac':text.includes('：+')?'#ef8585':'#e7edf7';comparison.append(row);}else{if(text.startsWith('上证：'))row.classList.add('quote-index');root.append(row);}
     }
     if(comparison.childElementCount)root.append(comparison);
     refreshTrade.current=null;if(!isDay&&chosen&&aligned[idx])refreshTrade.current=appendTradeTooltip(root,chosen.price,+aligned[idx].close,()=>costsRef.current,aligned[idx].time<chosen.time,aligned[idx].time===chosen.time);return root;}
   },axisPointer:{link:[{xAxisIndex:'all'}]},grid:(hasMacd?minutePanels.grids:[{top:30,height:'55%'},{top:'72%',height:'17%'}]).map(grid=>({left:65,right:showPercent?72:35,...grid})),
   xAxis:[{type:'category',data:labels,boundaryGap:isDay,...timeGrid,axisLine:{lineStyle:{color:isDay?'#2a374c':'#69343f'}},axisPointer:{label:{show:!hasMacd}},axisLabel:{show:!hasMacd,hideOverlap:true,...(!isDay?{interval:timeTick,formatter:(t:string)=>t==='11:30'?'11:30/13:00':t}:{})}},{type:'category',gridIndex:1,data:labels,boundaryGap:isDay,...timeGrid,axisLabel:{show:false},axisPointer:{label:{show:false}},axisLine:{lineStyle:{color:isDay?'#2a374c':'#69343f'}}},...(hasMacd?[2,3,4].map(gridIndex=>({type:'category',gridIndex,data:labels,boundaryGap:false,...timeGrid,axisLabel:{show:gridIndex===4,hideOverlap:true,interval:timeTick,fontSize:10,margin:5,formatter:(t:string)=>t==='11:30'?'11:30/13:00':t},axisPointer:{label:{show:gridIndex===4}},axisLine:{lineStyle:{color:'#3b485b'}}})):[])],
   yAxis:[{scale:true,...priceScale,splitNumber:isDay?5:4,splitLine:{lineStyle:{color:isDay?'#202c40':'#69343f',opacity:isDay?1:.65,width:1}},axisLabel:{formatter:(n:number)=>n.toFixed(2)}},{scale:true,gridIndex:1,...(!isDay?{min:0,max:volumeMax}:{}),splitNumber:2,splitLine:{lineStyle:{color:isDay?'#202c40':'#69343f',opacity:isDay?1:.65,width:1}},axisLabel:{fontSize:hasMacd?10:12,formatter:(n:number)=>isDay?wan(n):volumeTick(n)}},...(showPercent?[{type:'value',gridIndex:0,position:'right',scale:true,...priceScale,splitLine:{show:false},axisLine:{show:false},axisTick:{show:false},axisPointer:{show:false},axisLabel:{margin:10,formatter:percentLabel,rich:{rise:{color:'#ed7d81',fontSize:11},fall:{color:'#51c7aa',fontSize:11},flat:{color:'#c8d5eb',fontSize:11}}}}]:[]),...(hasMacd?[
    {type:'value',gridIndex:2,...macdRange(stockMacd),splitNumber:2,axisLabel:{fontSize:10,formatter:macdNumber},splitLine:{lineStyle:{color:'#2c3a50',opacity:.65}},axisPointer:{label:{formatter:(p:{value:number})=>macdNumber(p.value)}}},
    {type:'value',gridIndex:3,min:0,max:indexVolumeMax,splitNumber:2,axisLabel:{fontSize:10,formatter:wan},axisPointer:{label:{formatter:(p:{value:number})=>wan(p.value)+' 万手'}},splitLine:{lineStyle:{color:'#2c3a50',opacity:.65}}},
    {type:'value',gridIndex:4,...macdRange(indexMacd),splitNumber:2,axisLabel:{fontSize:10,formatter:macdNumber},splitLine:{lineStyle:{color:'#2c3a50',opacity:.65}},axisPointer:{label:{formatter:(p:{value:number})=>macdNumber(p.value)}}}
   ]:[])],
   dataZoom:[{type:'inside',xAxisIndex:axisIndices,...zoom,...(isDay?{filterMode:'weakFilter',zoomLock:true,zoomOnMouseWheel:false,moveOnMouseWheel:false,moveOnMouseMove:true}:{})},{type:'slider',xAxisIndex:axisIndices,...zoom,bottom:1,height:hasMacd?10:18,borderColor:'#28354b',fillerColor:'rgba(82,138,230,.14)',...(isDay?{filterMode:'weakFilter',zoomLock:true,handleSize:0,brushSelect:false}: {})}],
   series:[isDay?{name:view==='weekly'?'周K':'日K',type:'candlestick',data:daily.map(b=>[+b.open,+b.close,+b.low,+b.high]),itemStyle:{color:'#ef6568',color0:'#36b898',borderColor:'#ef6568',borderColor0:'#36b898'},markArea:{silent:true,label:{fontSize:10,color:'#91a2bb',position:'insideTopRight',align:'right',padding:[2,4]},data:[...visibleGaps.map(g=>[{name:`${g.provisional?'盘中':''}${g.direction==='up'?'上':'下'}缺口 ${price(g.low)}—${price(g.high)}`,xAxis:daily[Math.max(0,daily.findIndex(b=>b.date===g.date)-1)].date,yAxis:g.low,itemStyle:{color:g.direction==='up'?'rgba(239,101,104,.035)':'rgba(54,184,152,.035)',borderColor:g.direction==='up'?'rgba(239,101,104,.24)':'rgba(54,184,152,.24)',borderWidth:.7,borderType:'solid'}},{xAxis:daily.at(-1)!.date,yAxis:g.high}]),...ma250Signals.map(s=>[{name:'年线回踩',xAxis:s.touch_date,label:{show:false},itemStyle:{color:'rgba(242,176,74,.05)',borderColor:'rgba(242,176,74,.22)',borderWidth:.7,borderType:'dashed'}},{xAxis:s.date}])]},markPoint:{data:tradeMarks},markLine:{data:[]}}:
    {name:'价格',type:'line',data:aligned.map(b=>b?+b.close:null),connectNulls:false,showSymbol:false,z:5,lineStyle:{color:'#8cbcff',width:1.2},markLine:{silent:true,symbol:'none',data:limitLines},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(83,139,230,.16)'},{offset:1,color:'rgba(83,139,230,0)'}])},markPoint:{symbol:'pin',symbolSize:38,itemStyle:{color:'#e9ad58'},label:{fontSize:10},data:[...tradeMarks,...observationMarks,...volumeMarkers,...buySignals.filter(e=>labels.includes(e.time)).map(e=>({coord:[e.time,e.price],value:'买研',symbol:'triangle',symbolSize:20,itemStyle:{color:'#69d9ac'},label:{position:'bottom',color:'#69d9ac',fontSize:10}}))]}},
    ...(!isDay?[{value:priceLimits.up,name:'涨停走势',color:'#ef6568'},{value:priceLimits.down,name:'跌停走势',color:'#36b898'}].filter(row=>row.value!==undefined).map(row=>({name:row.name,type:'line',data:aligned.map(b=>b&&Math.abs(+b.close-row.value!)<.000001?+b.close:null),connectNulls:false,showSymbol:true,symbol:'circle',symbolSize:3,z:7,silent:true,lineStyle:{color:row.color,width:2.8},itemStyle:{color:row.color}})):[]),
    ...(canOverlay?[{name:'上证走势',type:'line',data:indexLine,showSymbol:false,connectNulls:false,z:2,lineStyle:{color:'#929aa9',width:1.2,type:'dashed',opacity:0.8},itemStyle:{color:'#929aa9'}}]:[]),
    ...(!isDay?[{name:'均价',type:'line',data:averages,showSymbol:false,connectNulls:false,lineStyle:{color:'#e9b949',width:1.5},itemStyle:{color:'#e9b949'}}]:[]),
    ...(isDay?[{name:'成交量（万股）',type:'bar',xAxisIndex:1,yAxisIndex:1,data:volume.map((v,i)=>({value:v,itemStyle:{color:colors[i]}}))}]:[
     {name:'买盘量',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,barWidth:'85%',barMaxWidth:9,itemStyle:{color:'#ef6568'},data:splits.map(b=>b?b.buy/100:null)},
     {name:'卖盘量',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,itemStyle:{color:'#36b898'},data:splits.map(b=>b?b.sell/100:null)},
     {name:'中性 / 未分类量',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,itemStyle:{color:'#718096'},data:splits.map(b=>b?b.verified?(b.neutral+b.unknown)/100:0:null)},
     {name:'总成交量（回退）',type:'bar',stack:'minute-volume',xAxisIndex:1,yAxisIndex:1,itemStyle:{opacity:1,color:(params:{dataIndex:number})=>colors[params.dataIndex]},data:splits.map(b=>b?b.verified?0:b.total/100:null)}]),
    ...(isDay&&ma.visible?ma.periods.filter(n=>ma.enabled.includes(n)).map(n=>({name:`MA${n}`,type:'line',data:maValues.get(n)!,showSymbol:false,connectNulls:false,silent:true,z:4,lineStyle:{color:MA_COLORS[ma.periods.indexOf(n)],width:1.2},itemStyle:{color:MA_COLORS[ma.periods.indexOf(n)]}})):[]),
    ...(isDay&&ma250Signals.length?[{name:'年线回踩信号',type:'scatter',z:7,silent:true,symbol:'triangle',symbolSize:9,symbolOffset:[0,14],
     data:ma250Signals.map(s=>({value:[s.date,s.close],ma250Key:s.key||s.date,strong:!!s.strong,
      symbol:s.strong?'diamond':'triangle',symbolSize:s.strong?10:9,
      itemStyle:{color:s.strong?'#ffe08a':'#f2b04a',borderColor:s.strong?'#ffb300':'#f2b04a',borderWidth:s.strong?1:0},
      label:{show:true,formatter:s.strong?'年线回踩·强':'年线回踩',position:'bottom',distance:10,color:s.strong?'#fff3c4':'#ffd98a',backgroundColor:s.strong?'#5c4006':'#4a3410',borderColor:s.strong?'#ffb300':'#f2b04a',borderWidth:.6,borderRadius:3,padding:[2,4],fontSize:10}})),
     labelLayout:{hideOverlap:true}}]:[]),
    ...(isDay&&e2Signals.length?[{name:'E2研究参考',type:'scatter',z:8,silent:true,symbol:'rect',symbolSize:8,symbolOffset:[0,-16],
     data:e2Signals.map(s=>({value:[s.date,s.close],researchOnly:true,e2Key:s.key,
      itemStyle:{color:'#c6adff',borderColor:'#493568',borderWidth:1},
      label:{show:true,formatter:'E2·研究参考',position:'top',distance:11,color:'#e5d8ff',backgroundColor:'#302044',borderColor:'#9976c6',borderWidth:.6,borderRadius:3,padding:[2,4],fontSize:10}})),
     labelLayout:{hideOverlap:true}}]:[]),
    ...(isDay&&ma250Breakouts.length?[{name:'年线突破信号',type:'scatter',z:6,silent:true,symbol:'circle',symbolSize:8,
     data:ma250Breakouts.map(b=>({value:[b.date,b.close],breakoutKey:b.date,quality:!!b.quality,
      symbolSize:b.quality?9:7,
      itemStyle:{color:b.quality?'#7fd4ff':'#5aa9e6',borderColor:'#0b2a40',borderWidth:1},
      label:{show:true,formatter:b.quality?'突破·确认':'突破年线',position:'top',distance:9,color:b.quality?'#d9f4ff':'#b9e2f7',backgroundColor:'#0b2a40',borderColor:'#5aa9e6',borderWidth:.6,borderRadius:3,padding:[2,4],fontSize:10}})),
     labelLayout:{hideOverlap:true}}]:[]),
    ...(!isDay&&automatic.length?[
     {name:'自动委托连线',type:'custom',silent:true,z:8,clip:false,tooltip:{show:false},dimensions:['time','price','offset'],encode:{x:0,y:1},
      data:automatic.map(m=>({value:[m.time,m.price,m.offset],itemStyle:{color:m.color}})),renderItem:(_p:unknown,api:echarts.CustomSeriesRenderItemAPI)=>{const [x,y]=api.coord!([api.value(0),api.value(1)]);return {type:'line',shape:{x1:x,y1:y,x2:x,y2:y+Number(api.value(2))},style:{stroke:String(api.visual('color')),lineWidth:.8,lineDash:[2,2]},silent:true};}},
     {name:'自动委托',type:'scatter',z:10,clip:false,symbol:'roundRect',symbolSize:13,
      data:automatic.map(m=>({value:[m.time,m.price],autoTrade:m.point,symbolOffset:[0,m.offset],itemStyle:{color:m.color,opacity:m.opacity,borderColor:'#edf4ff',borderWidth:.6},label:{show:true,formatter:m.label,position:'inside',align:'center',verticalAlign:'middle',offset:tradeLabelOffset(m.label),color:'#fff',fontFamily:'Arial, sans-serif',fontSize:8,fontWeight:'bold',lineHeight:13,padding:0}})),
      tooltip:{trigger:'item',formatter:(params:unknown)=>{const p=(params as {data:{autoTrade:typeof automatic[number]['point']}}).data.autoTrade,root=document.createElement('div');root.className='auto-trade-tooltip';for(const line of autoTradeDetails(p)){const row=document.createElement('div');row.textContent=line;root.append(row);}return root;}}}
    ]:[]),
    ...(hasMacd?[{name:'指数成交量',type:'bar',xAxisIndex:3,yAxisIndex:macdYAxis+1,barWidth:'85%',barMaxWidth:9,data:indexVolume,itemStyle:{color:(p:{dataIndex:number})=>indexVolumeColors[p.dataIndex]}}]:[]),
    ...(hasMacd?[stockMacd,indexMacd].flatMap((points,i)=>[
     {name:(i?'指数':'个股')+' MACD',type:'bar',xAxisIndex:i?4:2,yAxisIndex:macdYAxis+(i?2:0),barWidth:'85%',barMaxWidth:9,data:points.map(p=>p?.histogram??null),itemStyle:{color:(p:{value:number})=>p.value>=0?'#ef6568':'#36b898'},markLine:{silent:true,symbol:'none',label:{show:false},lineStyle:{color:'#748197',width:1,type:'solid'},data:[{yAxis:0}]}},
     {name:(i?'指数':'个股')+' DIF',type:'line',xAxisIndex:i?4:2,yAxisIndex:macdYAxis+(i?2:0),data:points.map(p=>p?.dif??null),showSymbol:false,connectNulls:false,lineStyle:{color:'#ff9f43',width:1.3},itemStyle:{color:'#ff9f43'}},
     {name:(i?'指数':'个股')+' DEA',type:'line',xAxisIndex:i?4:2,yAxisIndex:macdYAxis+(i?2:0),data:points.map(p=>p?.dea??null),showSymbol:false,connectNulls:false,lineStyle:{color:'#57a6ff',width:1.3},itemStyle:{color:'#57a6ff'}}
    ]):[]),
    ...patternSeries,
    ...(tradeAnchors.length?[{name:'模拟成交标记连线',type:'custom',silent:true,z:6,clip:false,tooltip:{show:false},renderItem:renderPaperConnector,
     dimensions:['time','price','direction'],encode:{x:0,y:1},data:tradeAnchors.map(m=>[m.time,m.anchor,m.value==='B'?1:m.value==='S'?-1:-2])}]:[]),
    ...(!isDay?[{name:'高量标签连线',type:'custom',silent:true,z:6,clip:false,tooltip:{show:false},renderItem:renderHighVolumeConnector,
     dimensions:['time','price','direction','distance'],encode:{x:0,y:1},data:volumeMarkers.filter(m=>m.value==='高').map(m=>[m.coord[0],m.coord[1],m.connectorDirection,m.connectorDistance])}]:[]),
    ...(!isDay?[{name:'底顶标签连线',type:'custom',silent:true,z:6,clip:false,tooltip:{show:false},renderItem:renderTurningConnector,
     dimensions:['time','price','direction','distance'],encode:{x:0,y:1},data:observationMarks.filter(m=>m.label.show).map(m=>({value:[m.coord[0],m.coord[1],m.connectorDirection,m.connectorDistance],itemStyle:{color:m.itemStyle.color}}))}]:[])]
  },{notMerge:true});
  refreshMacd.current?.();
  // Refresh data under the cursor without jumping back to the selected day.
  // Explicit day/view navigation still takes priority over the previous hover.
  const sameScope=renderedScope.current===scope;renderedScope.current=scope;
  if(sameScope&&pointer.current?.scope===scope)chart.dispatchAction({type:'updateAxisPointer',currTrigger:'mousemove',x:pointer.current.x,y:pointer.current.y});
  else if(isDay&&selectedCandle){const index=labels.indexOf(selectedCandle);if(index>=0)chart.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:index});}
 },[contentKey]);
 useEffect(()=>{if(isCandleView(view))ref.current?.focus({preventScroll:true});},[view]);
 return <>{isCandleView(view)&&<CandleControls value={ma} onChange={updateMa} onZoom={zoomCandles}/>} {view==='daily'&&<div className="daily-pattern-controls" role="group" aria-label="日线形态显示选项">
  <label className="opening-volume-toggle"><input type="checkbox" checked={showDailyPatterns} onChange={e=>{setShowDailyPatterns(e.target.checked);try{localStorage.setItem('stock-monitor-show-daily-patterns-v1',String(e.target.checked));}catch{}}}/>显示日线形态</label>
  {showDailyPatterns&&<><span className="daily-pattern-mode">自动识别 · 同一区域择优显示</span><span className="daily-pattern-legend">{([...new Set(dayPatterns.map(p=>p.kind))]).map(kind=><span key={kind}><i style={{backgroundColor:dailyPatternColors[kind]}}/>{dayPatterns.find(p=>p.kind===kind)!.name}</span>)}</span></>}
 </div>}{!isCandleView(view)&&<TCostSettings value={costs} onChange={updateCosts} displayOptions={<div className="chart-display-options" role="group" aria-label="分时显示选项">
  <label className="opening-volume-toggle"><input type="checkbox" checked={showOpening} onChange={e=>{setShowOpening(e.target.checked);try{localStorage.setItem('stock-monitor-show-opening',String(e.target.checked));}catch{}}}/>开盘量</label>
  <label className="opening-volume-toggle"><input aria-label="高量" type="checkbox" checked={showTriggered} onChange={e=>{setShowTriggered(e.target.checked);try{localStorage.setItem('stock-monitor-show-trigger-volume',String(e.target.checked));window.dispatchEvent(new window.Event('turning-display-change'));}catch{}}}/>高量</label>
  <label className="opening-volume-toggle"><input aria-label="底/顶" type="checkbox" checked={showShapes} onChange={e=>{setShowShapes(e.target.checked);try{localStorage.setItem('stock-monitor-show-turning-shapes-v1',String(e.target.checked));window.dispatchEvent(new window.Event('turning-display-change'));}catch{}}}/>底/顶 {!fixedTurningMode&&<span className="turning-cap-count" data-testid="turning-cap-count">底 {turnCounts.bottom}/3 · 顶 {turnCounts.top}/3</span>}</label>
  {!fixedTurningMode&&<label className="turning-mode-select" title="自动下单与自动标注仍使用 v2.4 信号；v3 实验：顶多底少，相似度F0.5略升但底部覆盖/质量下降">顶底模式<select aria-label="顶底模式" value={turningMode} onChange={e=>updateTurningMode((['v3','stable','zhangle'].includes(e.target.value)?e.target.value:'zhangle') as TurningChartMode)}><option value="zhangle">贴近涨乐通 v2.4（默认）</option><option value="v3">贴近涨乐通 v3（实验：顶多底少）</option><option value="stable">稳健 v2.0</option></select></label>}

 </div>}/>}{tradeHint?.scope===scope&&<div className="chart-trade-hint" role="status">{tradeHint.text}</div>}<div className="chart-shell"><div className={'chart'+(compact?' compact-chart':'')+(hasMacd?' macd-chart':'')} ref={ref} onContextMenu={contextTrade} tabIndex={isCandleView(view)?0:undefined} onClick={()=>{if(isCandleView(view))ref.current?.focus();}} onKeyDown={e=>{if(isCandleView(view)&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();onMove?.(e.key==='ArrowLeft'?-1:1);}else if(isCandleView(view)&&(e.key==='ArrowUp'||e.key==='ArrowDown')){e.preventDefault();zoomCandles(e.key==='ArrowUp'?-1:1);}else if(isCandleView(view)&&e.key==='Enter'&&selectedDay)onOpenDay?.(selectedCandle||selectedDay);}} aria-label={view==='weekly'?'周K线及成交量':view==='daily'?'日K线及成交量':'分时价格及分钟成交量'}/>
 <div className="volume-panel-header" data-volume-grid="1" style={{top:hasMacd?minutePanels.headers[0]:'65%'}} ref={el=>{volumeHeaders.current[0]=el;}}><span>{isCandleView(view)?'成交量（万股）':'成交量（手）'}</span>{hasMacd&&<><span className="volume-value"/><time/></>}</div>
 {hasMacd&&<>
 <div className="volume-panel-header" data-volume-grid="3" style={{top:minutePanels.headers[2]}} ref={el=>{volumeHeaders.current[1]=el;}}><span>{macdIndex!.name}成交量（万手） · 总量</span><span className="volume-value"/><time/></div>
 {[stockName||'个股',macdIndex!.name].map((label,i)=><div key={i} className={'macd-panel-header'+(compact?' compact':'')} style={{top:minutePanels.headers[i?3:1]}} ref={el=>{macdHeaders.current[i]=el;}} role="group" aria-label={i?'指数MACD':'个股MACD'}>
  <div className="macd-panel-heading"><strong>{label} MACD<button type="button" className="macd-period-button" aria-label={label+' MACD周期设置'} title="修改MACD周期" onClick={()=>{instance.current?.dispatchAction({type:'hideTip'});setEditMacd(true);}}>({macdParameters.fast},{macdParameters.slow},{macdParameters.signal})</button></strong><span>1分钟</span><time data-macd="time"/></div>
  <div className="macd-panel-values"><span data-macd="histogram">MACD —</span><span className="macd-dif" data-macd="dif">DIF —</span><span className="macd-dea" data-macd="dea">DEA —</span></div>
 </div>)}
 {!macdDataReady&&<div className="macd-unavailable" style={{top:minutePanels.grids[4].top+minutePanels.grids[4].height/2}}>该日{macdIndex!.name}暂无可用分钟数据</div>}
 </>}</div>{editMacd&&<MacdSettings value={macdParameters} onChange={updateMacd} onClose={()=>setEditMacd(false)}/>} {isCandleView(view)&&<InfoNote label="图表操作">{Math.min(daily.length,candleSizes[view])}根{view==='weekly'?'周':'日'}K视窗 · ↑ 放大 / ↓ 缩小 · ← / → 移动 · 拖动浏览，边界按需加载</InfoNote>}</>;
}
