import {weekStart} from './candleData';
import type {Daily} from './models';

export const DRAWING_LIMIT=200;
export const DRAWING_COLOR='#edbe63',DRAWING_WIDTH=1;
export type DrawingFrame='daily'|'weekly';
export type DrawingPoint={date:string;price:number};
export type Drawing={id:string;kind:'line'|'rect';color?:string;width?:number;points:[DrawingPoint,DrawingPoint]};
export type DrawingDocument={revision:number;items:Drawing[];conflict?:boolean};
export const drawingCode=(code:string)=>{const value=code.toLowerCase().replace(/^pool-/,'');return /^(sh|sz|bj)\d{6}$/.test(value)?value:'';};
// A weekly bar's last observed date changes during the week. Anchor to the
// calendar week instead, so adding Thursday/Friday never moves the drawing.
export const drawingDate=(row:Daily,frame:DrawingFrame)=>frame==='weekly'?weekStart(row.date):row.date;
const validDate=(value:unknown):value is string=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value+'T00:00:00Z'))&&new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value;
export function validDrawing(value:unknown):value is Drawing{
 const d=value as Drawing|undefined;
 if(!d||typeof d.id!=='string'||!/^[a-zA-Z0-9_-]{1,64}$/.test(d.id)||!['line','rect'].includes(d.kind)||!Array.isArray(d.points)||d.points.length!==2)return false;
 if(d.points.some(p=>!p||!validDate(p.date)||typeof p.price!=='number'||!Number.isFinite(p.price)||p.price<=0||p.price>1e9))return false;
 if(d.color!==undefined&&(typeof d.color!=='string'||!/^#[0-9a-fA-F]{6}$/.test(d.color)))return false;
 if(d.width!==undefined&&(typeof d.width!=='number'||!Number.isFinite(d.width)||d.width<1||d.width>6))return false;
 const [a,b]=d.points;
 return d.kind==='rect'?a.date!==b.date&&a.price!==b.price:a.date!==b.date||a.price!==b.price;
}
export function drawingDocument(value:unknown):DrawingDocument{
 const doc=value as DrawingDocument|undefined;
 if(!doc||!Number.isSafeInteger(doc.revision)||doc.revision<0||!Array.isArray(doc.items)||doc.items.length>DRAWING_LIMIT||!doc.items.every(validDrawing)||new Set(doc.items.map(d=>d.id)).size!==doc.items.length)throw Error('画线数据异常，请重试读取；原数据未覆盖');
 return {revision:doc.revision,items:doc.items,conflict:doc.conflict===true};
}
// Browser previews keep their own annotations. Desktop always uses SQLite RPC.
export function previewDrawings(method:string,args:Record<string,unknown>):DrawingDocument{
 const code=drawingCode(String(args.code||'')),frame=args.frame;
 if(!code||(frame!=='daily'&&frame!=='weekly'))throw Error('画线股票或周期无效');
 const key=`stock-monitor-drawings-preview-v1:${code}:${frame}`;
 const raw=localStorage.getItem(key),doc=raw?drawingDocument(JSON.parse(raw)):{revision:0,items:[]};
 if(method==='chart_drawings')return doc;
 const next=drawingDocument({revision:args.revision,items:args.items});
 if(next.revision!==doc.revision)return next.revision+1===doc.revision&&sameDrawings(next.items,doc.items)?doc:{...doc,conflict:true};
 const saved={revision:doc.revision+1,items:next.items};localStorage.setItem(key,JSON.stringify(saved));return saved;
}

export const sameDrawings=(a:Drawing[],b:Drawing[])=>a.length===b.length&&a.every((d,i)=>{
 const e=b[i];return d.id===e.id&&d.kind===e.kind&&(d.color||DRAWING_COLOR).toLowerCase()===(e.color||DRAWING_COLOR).toLowerCase()&&(d.width||DRAWING_WIDTH)===(e.width||DRAWING_WIDTH)&&d.points.every((p,j)=>p.date===e.points[j].date&&p.price===e.points[j].price);
});

// Small UI defaults only; annotation styles remain in the SQLite document.
export type DrawingStyle={color:string;width:number};
export function readDrawingStyle(kind:Drawing['kind']):DrawingStyle{
 try{
  const value=JSON.parse(localStorage.getItem(`stock-monitor-drawing-style-v1:${kind}`)||'null');
  if(value&&typeof value.color==='string'&&/^#[0-9a-fA-F]{6}$/.test(value.color)&&[1,2,3,4,6].includes(value.width))return {color:value.color,width:value.width};
 }catch{/* Invalid or unavailable preferences never block drawing access. */}
 return {color:DRAWING_COLOR,width:DRAWING_WIDTH};
}
export function writeDrawingStyle(kind:Drawing['kind'],style:DrawingStyle){
 try{localStorage.setItem(`stock-monitor-drawing-style-v1:${kind}`,JSON.stringify(style));}catch{/* Actual drawing saves continue through SQLite. */}
}
