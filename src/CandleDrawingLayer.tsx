import {memo,useEffect,useId,useMemo,useRef,useState,type PointerEvent as ReactPointerEvent,type RefObject} from 'react';
import {createPortal} from 'react-dom';
import type {ECharts} from 'echarts';
import type {Daily} from './models';
import type {Request} from './poolTableModel';
import {DRAWING_COLOR,DRAWING_WIDTH,DRAWING_LIMIT,drawingDate,drawingDocument,readDrawingStyle,writeDrawingStyle,sameDrawings,validDrawing,type Drawing,type DrawingDocument,type DrawingFrame,type DrawingPoint} from './candleDrawingModel';
import {readRecovery,writeRecovery,clearRecovery,type DrawingRecovery} from './candleDrawingRecovery';
import './candleDrawings.css';

type Geometry={left:number;top:number;width:number;height:number;x:number;dx:number;y:number;dy:number};
type Gesture={kind:'new'|'move'|'point';drawing:Drawing;start:[number,number];anchor:DrawingPoint;handle:number;pointerId:number};
const changeEvent='stock-monitor-chart-drawings-changed';
const copy=(items:Drawing[])=>items.map(d=>({...d,points:d.points.map(p=>({...p})) as Drawing['points']}));

// Stable saved shapes skip preview-only renders. Zoom/history changes still
// update all shapes through the shared geometry and date-index references.
const DrawingShape=memo(function DrawingShape({item,geometry,dateIndex,active,handles}:{item:Drawing;geometry:Geometry;dateIndex:Map<string,number>;active:boolean;handles:boolean}){
 const project=(p:DrawingPoint)=>{const i=dateIndex.get(p.date);return i===undefined?null:[geometry.x+i*geometry.dx,geometry.y+(p.price-1)*geometry.dy] as [number,number];};
 const a=project(item.points[0]),b=project(item.points[1]);if(!a||!b)return null;
 const shape=item.kind==='line'?{x1:a[0],y1:a[1],x2:b[0],y2:b[1]}:{x:Math.min(a[0],b[0]),y:Math.min(a[1],b[1]),width:Math.abs(a[0]-b[0]),height:Math.abs(a[1]-b[1])};
 const style={stroke:item.color||DRAWING_COLOR,strokeWidth:item.width||DRAWING_WIDTH},hitStyle={strokeWidth:Math.max(10,(item.width||DRAWING_WIDTH)+6)};
 return <g data-testid="manual-drawing" data-kind={item.kind} data-drawing-id={item.id} className={active?'selected':''}>
  {item.kind==='line'?<><line {...shape} className="drawing-shape" style={style}/><line {...shape} className="drawing-hit" data-drawing-id={item.id} style={hitStyle}/></>:<><rect {...shape} className="drawing-shape" style={style}/><rect {...shape} className="drawing-hit" data-drawing-id={item.id} style={hitStyle}/></>}
  {handles&&[a,b].map((p,i)=><circle key={i} cx={p[0]} cy={p[1]} r={3.5} className="drawing-handle" data-drawing-id={item.id} data-handle={i}/>)}
 </g>;
});

/** Separate SVG layer: pointer movement never sets an ECharts option or writes SQL. */
export default function CandleDrawings({code,frame,rows,chartRef,nodeRef,toolbar,request}:{
 code:string;frame:DrawingFrame;rows:Daily[];chartRef:RefObject<ECharts|null>;nodeRef:RefObject<HTMLDivElement|null>;toolbar:HTMLDivElement|null;request:Request;
}){
 const [doc,setDoc]=useState<DrawingDocument|null>(null),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const [mode,setMode]=useState<'browse'|'line'|'rect'>('browse'),[selected,setSelected]=useState('');
 const [preview,setPreview]=useState<Drawing|null>(null),[pending,setPending]=useState<DrawingRecovery|null>(null);
 const [drawingStyle,setDrawingStyle]=useState(()=>readDrawingStyle('line'));
 const [handleFocus,setHandleFocus]=useState(false);
 const [geometry,setGeometry]=useState<Geometry|null>(null),[history,setHistory]=useState<Drawing[][]>([]);
 const alive=useRef(true),generation=useRef(0),busy=useRef(false),gesture=useRef<Gesture|null>(null),draft=useRef<Drawing|null>(null),paintFrame=useRef(0),svg=useRef<SVGSVGElement>(null);
 const instanceId=useId(),clipId=useId().replace(/:/g,'');
 const requestRef=useRef(request);requestRef.current=request;
 const dates=useMemo(()=>rows.map(row=>drawingDate(row,frame)),[rows,frame]);
 const dateIndex=useMemo(()=>new Map(dates.map((day,i)=>[day,i])),[dates]);
 const rowsRef=useRef(dates);rowsRef.current=dates;
 const pendingRef=useRef(pending);pendingRef.current=pending;
 const queued=useRef(false);
 const setPendingSafe=(value:DrawingRecovery|null)=>{pendingRef.current=value;setPending(value);};
 const drain=()=>{if(alive.current&&queued.current&&!busy.current&&!gesture.current&&!pendingRef.current){queued.current=false;loadRef.current();}};
 const loadRef=useRef<()=>void>(()=>{});
 const load=async()=>{
  const seq=++generation.current;setError('');setDoc(null);busy.current=true;
  try{const result=drawingDocument(await requestRef.current('chart_drawings',{code,frame}));if(alive.current&&seq===generation.current){
   const recovery=readRecovery(code,frame);
   if(recovery&&result.revision===recovery.revision+1&&sameDrawings(result.items,recovery.items)){clearRecovery(code,frame,recovery.id);setPendingSafe(null);}
   else {setPendingSafe(recovery);if(recovery)setError('上次画线保存状态未确认，请重试保存或放弃修改');}
   setDoc(result);setHistory([]);setSelected('');
  }}
  catch(e){if(alive.current&&seq===generation.current)setError(String(e));}
  finally{if(alive.current&&seq===generation.current){busy.current=false;drain();}}
 };
 loadRef.current=()=>{void load();};
 useEffect(()=>{
  alive.current=true;void load();
  const sync=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail?.code!==code||detail.frame!==frame||detail.origin===instanceId)return;
   if(detail.operation===pendingRef.current?.id){setPendingSafe(null);}
   queued.current=true;drain();
  };
  window.addEventListener(changeEvent,sync);
  return()=>{alive.current=false;generation.current++;cancelAnimationFrame(paintFrame.current);window.removeEventListener(changeEvent,sync);};
 },[code,frame]);
 useEffect(()=>{
  const protect=(e:BeforeUnloadEvent)=>{if(pendingRef.current){e.preventDefault();e.returnValue='';}};
  window.addEventListener('beforeunload',protect);return()=>window.removeEventListener('beforeunload',protect);
 },[]);

 // Keep selection while editing its toolbar style, but only show handles
 // while the SVG has input focus. Safari may leave SVG focus on toolbar clicks,
 // so an outside pointer also hides the handles without clearing selection.
 useEffect(()=>{
  const blur=()=>setHandleFocus(false);
  const outside=(event:PointerEvent)=>{if(!svg.current?.contains(event.target as Node))blur();};
  window.addEventListener('blur',blur);document.addEventListener('pointerdown',outside,true);
  return()=>{window.removeEventListener('blur',blur);document.removeEventListener('pointerdown',outside,true);};
 },[]);

 useEffect(()=>{
  let raf=0,detached=()=>{},stopped=false,signature='';
  const bind=()=>{
   raf=0;
   const chart=chartRef.current;if(stopped)return;if(!chart){raf=requestAnimationFrame(bind);return;}
   const update=()=>{
    raf=0;if(stopped)return;
    if(!rowsRef.current.length){signature='';setGeometry(null);return;}
    try{
     // Hover also emits "rendered". Inspect model extents first; only a changed
     // grid/axis transform needs DOM visibility checks and pixel conversion.
     const model=(chart as any).getModel(),grid=model?.getComponent('grid',0)?.coordinateSystem?.getRect();
     const x=model?.getComponent('xAxis',0)?.axis,y=model?.getComponent('yAxis',0)?.axis;
     if(!grid||!x||!y)return;
     const key=[grid.x,grid.y,grid.width,grid.height,...x.scale.getExtent(),...y.scale.getExtent(),...x.getExtent(),...y.getExtent(),rowsRef.current.length].join('|');
     if(key===signature||!nodeRef.current?.getClientRects().length)return;
     const a=chart.convertToPixel({xAxisIndex:0,yAxisIndex:0},[0,1]) as number[];
     const b=chart.convertToPixel({xAxisIndex:0,yAxisIndex:0},[rowsRef.current.length>1?1:0,2]) as number[];
     if(!a||!b)return;
     const next={left:grid.x,top:grid.y,width:grid.width,height:grid.height,x:a[0],dx:rowsRef.current.length>1?b[0]-a[0]:1,y:a[1],dy:b[1]-a[1]};
     if(!Object.values(next).every(Number.isFinite)||!next.dx||!next.dy)return;
     signature=key;setGeometry(next);
    }catch{/* No usable axes yet; wait for the next chart render. */}
   };
   const schedule=()=>{if(!raf)raf=requestAnimationFrame(update);};
   chart.on('rendered',schedule);chart.on('datazoom',schedule);schedule();
   detached=()=>{chart.off('rendered',schedule);chart.off('datazoom',schedule);};
  };bind();return()=>{stopped=true;cancelAnimationFrame(raf);detached();};
 },[chartRef,nodeRef]);

 const cancel=()=>{
  cancelAnimationFrame(paintFrame.current);paintFrame.current=0;
  const active=gesture.current;gesture.current=null;draft.current=null;setPreview(null);setMode('browse');
  if(active&&svg.current?.hasPointerCapture(active.pointerId))svg.current.releasePointerCapture(active.pointerId);
  queueMicrotask(drain);
 };
 const closeDrawing=()=>{cancel();setSelected('');setHandleFocus(false);};
 // An empty/reloading history must not leave a live draft or usable old axes.
 useEffect(()=>{if(!dates.length)closeDrawing();},[dates.length]);
 const persist=async(items:Drawing[],undo=false,retry?:DrawingRecovery)=>{
  if(!doc||busy.current)return;
  const prior=copy(doc.items),operation=retry||{id:crypto.randomUUID(),revision:doc.revision,items:copy(items),undo};
  writeRecovery(code,frame,operation);busy.current=true;setSaving(true);setError('');setPendingSafe(operation);
  try{
   const result=drawingDocument(await requestRef.current('chart_drawings_save',{code,frame,revision:operation.revision,items:operation.items}));
   // A save can finish after switching stocks. Notify any newly mounted
   // chart for this scope even when the originating component has gone away.
   clearRecovery(code,frame,operation.id);
   window.dispatchEvent(new CustomEvent(changeEvent,{detail:{code,frame,origin:instanceId,operation:operation.id}}));
   if(!alive.current)return;
   if(result.conflict){setDoc(result);setHistory([]);setPendingSafe(null);setSelected('');setError('画线版本已变化，已读取最新数据；请核对后重试');}
   else{
    const item=result.items.find(d=>d.id===selected);if(item)setDrawingStyle({color:item.color||DRAWING_COLOR,width:item.width||DRAWING_WIDTH});
    setDoc(result);setPendingSafe(null);setSelected(old=>result.items.some(item=>item.id===old)?old:'');setHistory(old=>undo?old.slice(0,-1):[...old.slice(-19),prior]);
   }
   cancel();
  }catch(e){if(alive.current){setError('画线保存状态未确认，请重试保存：'+String(e));gesture.current=null;draft.current=null;setPreview(null);setMode('browse');}}
  finally{if(alive.current){busy.current=false;setSaving(false);drain();}}
 };
 const point=(x:number,y:number):DrawingPoint|null=>{
  if(!geometry||!dates.length)return null;
  const index=Math.max(0,Math.min(dates.length-1,Math.round((x-geometry.x)/geometry.dx)));
  const price=Number((1+(y-geometry.y)/geometry.dy).toFixed(6));
  return Number.isFinite(price)&&price>0&&price<=1e9?{date:dates[index],price}:null;
 };
 const local=(event:ReactPointerEvent)=>{const box=svg.current!.getBoundingClientRect();return [event.clientX-box.left,event.clientY-box.top] as [number,number];};
 const within=([x,y]:[number,number])=>!!geometry&&x>=geometry.left&&x<=geometry.left+geometry.width&&y>=geometry.top&&y<=geometry.top+geometry.height;
 const clamped=([x,y]:[number,number]):[number,number]=>[Math.max(geometry!.left,Math.min(geometry!.left+geometry!.width,x)),Math.max(geometry!.top,Math.min(geometry!.top+geometry!.height,y))];
 const updateDraft=(xy:[number,number])=>{
  const g=gesture.current,p=point(...clamped(xy));if(!g||!p)return;
  let points=g.drawing.points.map(a=>({...a})) as Drawing['points'];
  if(g.kind==='move'){
   const indices=points.map(a=>dateIndex.get(a.date));if(indices.some(i=>i===undefined))return;
   const delta=Math.max(-Math.min(...indices as number[]),Math.min(dates.length-1-Math.max(...indices as number[]),(dateIndex.get(p.date)??0)-(dateIndex.get(g.anchor.date)??0)));
   const dp=Math.max(.000001-Math.min(...points.map(a=>a.price)),Math.min(1e9-Math.max(...points.map(a=>a.price)),p.price-g.anchor.price));
   points=points.map((a,i)=>({date:dates[indices[i]!+delta],price:Number((a.price+dp).toFixed(6))})) as Drawing['points'];
  }else points[g.kind==='new'?1:g.handle]=p;
  draft.current={...g.drawing,points};
 };
 const down=(event:ReactPointerEvent<SVGSVGElement>)=>{
  if(event.button!==0||busy.current||!doc||pending||!geometry||!dates.length)return;
  const xy=local(event);if(!within(xy))return;
  const anchor=point(...xy);if(!anchor)return;
  const target=event.target as SVGElement,id=target.dataset.drawingId;
  if(mode==='browse'&&!id)return;
  let item=doc.items.find(d=>d.id===id);
  if(mode!=='browse'){
   if(doc.items.length>=DRAWING_LIMIT){setError(`每个股票周期最多${DRAWING_LIMIT}个图形，请先删除部分画线`);return;}
   item={id:crypto.randomUUID(),kind:mode,points:[anchor,{...anchor}],...drawingStyle};
  }
  if(!item)return;
  event.preventDefault();event.stopPropagation();event.currentTarget.focus({preventScroll:true});event.currentTarget.setPointerCapture(event.pointerId);
  setHandleFocus(true);setDrawingStyle({color:item.color||DRAWING_COLOR,width:item.width||DRAWING_WIDTH});
  setSelected(item.id);setError('');draft.current={...item,points:item.points.map(p=>({...p})) as Drawing['points']};
  gesture.current={kind:mode!=='browse'?'new':target.dataset.handle!==undefined?'point':'move',drawing:copy([item])[0],start:xy,anchor,handle:Number(target.dataset.handle)||0,pointerId:event.pointerId};
  setPreview(draft.current);
 };
 const move=(event:ReactPointerEvent<SVGSVGElement>)=>{
  if(!gesture.current)return;if(!geometry||!dates.length){closeDrawing();return;}event.preventDefault();updateDraft(local(event));
  if(!paintFrame.current)paintFrame.current=requestAnimationFrame(()=>{paintFrame.current=0;setPreview(draft.current);});
 };
 const up=(event:ReactPointerEvent<SVGSVGElement>)=>{
  const g=gesture.current;if(!g)return;
  event.preventDefault();event.stopPropagation();if(!geometry||!dates.length){closeDrawing();return;}updateDraft(local(event));cancelAnimationFrame(paintFrame.current);paintFrame.current=0;
  const next=draft.current;gesture.current=null;draft.current=null;setPreview(null);
  if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  if(!next||Math.hypot(...local(event).map((v,i)=>v-g.start[i]) as [number,number])<3||!validDrawing(next)){setMode('browse');drain();return;}
  if(!doc)return;
  void persist(doc.items.some(d=>d.id===next.id)?doc!.items.map(d=>d.id===next.id?next:d):[...doc!.items,next]);
 };
 const remove=()=>{if(selected&&doc?.items.some(item=>item.id===selected))void persist(doc.items.filter(d=>d.id!==selected));};
 const keyboard=(event:React.KeyboardEvent)=>{
  if((event.target as HTMLElement).closest('input,textarea,select,[contenteditable=true]'))return;
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeDrawing();}
  if((event.key==='Delete'||event.key==='Backspace')&&selected&&!gesture.current&&mode==='browse'&&!busy.current&&!pending){event.preventDefault();event.stopPropagation();remove();}
 };
 const shown=pending?.items||doc?.items||[];
 const painted=preview?[...shown.filter(d=>d.id!==preview.id),preview]:shown;
 const ready=!!doc&&!!geometry&&dates.length>0&&!saving&&!pending;
 const selectedItem=doc?.items.find(item=>item.id===selected),styleDisabled=!ready;
 const styleTarget=selectedItem?.kind==='rect'||mode==='rect'?'矩形边框':'线段';
 const styleChanged=selectedItem&&((selectedItem.color||DRAWING_COLOR)!==drawingStyle.color||(selectedItem.width||DRAWING_WIDTH)!==drawingStyle.width);
 const changeStyle=(patch:Partial<typeof drawingStyle>)=>{const next={...drawingStyle,...patch};setDrawingStyle(next);writeDrawingStyle(selectedItem?.kind||(mode==='rect'?'rect':'line'),next);};
 const tools=<div className="candle-drawing-tools" role="group" aria-label="手工画线工具" onKeyDown={keyboard}>
  <span className="drawing-label">画线</span>
  <button type="button" aria-label="关闭画线" disabled={!ready||(mode==='browse'&&!preview)} onClick={closeDrawing} title="取消未完成的图形并退出画线（Esc）；保留已保存图形">关闭</button>
  {(['line','rect'] as const).map(tool=><button type="button" key={tool} aria-label={tool==='line'?'画线段':'画矩形'} aria-pressed={mode===tool} disabled={!ready} onClick={()=>{cancel();setMode(tool);setSelected('');setDrawingStyle(readDrawingStyle(tool));}} title="在价格区按住鼠标拖动绘制；关闭或Esc取消"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" aria-hidden="true">{tool==='line'?<path d="M2 10 10 2"/>:<rect x="1.5" y="2.5" width="9" height="7"/>}</svg>{tool==='line'?'线段':'矩形'}</button>)}
  <label className="drawing-style-label" title="设置线段或矩形边框颜色；选中图形后点击应用样式保存"><span>颜色</span><input type="color" aria-label={styleTarget+'颜色'} disabled={styleDisabled} value={drawingStyle.color} onChange={e=>changeStyle({color:e.target.value})}/></label>
  <label className="drawing-style-label"><span>线宽</span><select aria-label={styleTarget+'宽度'} disabled={styleDisabled} value={drawingStyle.width} onChange={e=>changeStyle({width:Number(e.target.value)})}>{[1,2,3,4,6].map(n=><option key={n} value={n}>{n}px</option>)}</select></label>
  {selectedItem&&<button type="button" disabled={!ready||!styleChanged} aria-label={selectedItem.kind==='rect'?'应用选中矩形样式':'应用选中线段样式'} onClick={()=>void persist(doc!.items.map(item=>item.id===selected?{...item,...drawingStyle}:item))}>应用样式</button>}
  <button type="button" aria-label="删除选中画线" disabled={!ready||!selectedItem} onClick={remove}>删除</button>
  <button type="button" aria-label="撤销上次画线操作" disabled={!ready||!history.length} onClick={()=>void persist(copy(history.at(-1)!),true)}>撤销</button>
  <small role="status" title="按股票和日K／周K分别保存；仅手工标注">{saving?'保存中…':pending?'未保存':!doc?(error?'读取失败':'读取中…'):(!geometry||!dates.length)?'等待K线':mode!=='browse'?'拖动绘制 · Esc取消':`${doc.items.length} / ${DRAWING_LIMIT}`}</small>
  {error&&<span className="drawing-error" role="alert">{error}{pending?<><button type="button" disabled={saving} onClick={()=>void persist(pending.items,pending.undo,pending)}>重试保存</button><button type="button" disabled={saving} onClick={()=>{clearRecovery(code,frame,pending.id);setPendingSafe(null);setError('');drain();}}>放弃修改</button></>:!doc&&<button type="button" onClick={()=>loadRef.current()}>重新读取</button>}</span>}
 </div>;
 return <>{toolbar&&createPortal(tools,toolbar)}<svg ref={svg} className={'candle-drawings'+(mode!=='browse'?' is-drawing':'')} aria-label="手工画线标注" tabIndex={0} onFocus={()=>setHandleFocus(true)} onBlur={()=>setHandleFocus(false)} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={cancel} onLostPointerCapture={()=>{if(gesture.current)cancel();}} onKeyDown={keyboard} onClick={e=>e.stopPropagation()} onDoubleClick={e=>e.stopPropagation()} onContextMenu={e=>{e.preventDefault();e.stopPropagation();}}>
  {geometry&&dates.length>0&&<><defs><clipPath id={clipId}><rect x={geometry.left} y={geometry.top} width={geometry.width} height={geometry.height}/></clipPath></defs>
   <g clipPath={`url(#${clipId})`}>
    <rect className="drawing-capture" x={geometry.left} y={geometry.top} width={geometry.width} height={geometry.height} style={{pointerEvents:mode!=='browse'&&ready?'all':'none'}}/>
    {painted.map(item=><DrawingShape key={item.id} item={item} geometry={geometry} dateIndex={dateIndex} active={selected===item.id} handles={selected===item.id&&handleFocus}/>)}
   </g>
  </>}
 </svg></>;
}
