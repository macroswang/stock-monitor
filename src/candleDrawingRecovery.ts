import {drawingDocument,type Drawing,type DrawingFrame} from './candleDrawingModel';

export type DrawingRecovery={id:string;revision:number;items:Drawing[];undo:boolean};
const prefix='stock-monitor-drawings-recovery-v1:';
// Memory fallback still allows a normal SQLite save if WebKit storage is full.
const memory=new Map<string,DrawingRecovery>();
const key=(code:string,frame:DrawingFrame)=>`${prefix}${code}:${frame}`;
export function readRecovery(code:string,frame:DrawingFrame):DrawingRecovery|null{
 const scope=key(code,frame);
 if(memory.has(scope))return memory.get(scope)!;
 try{
  const raw=localStorage.getItem(scope);if(!raw)return memory.get(scope)||null;
  const value=JSON.parse(raw);const doc=drawingDocument(value);
  if(typeof value.id!=='string'||!value.id||typeof value.undo!=='boolean')throw Error('未确认的画线备份异常');
  return {id:value.id,revision:doc.revision,items:doc.items,undo:value.undo};
 }catch(e){if(memory.has(scope))return memory.get(scope)!;throw e;}
}
export function writeRecovery(code:string,frame:DrawingFrame,value:DrawingRecovery){
 memory.set(key(code,frame),value);
 try{localStorage.setItem(key(code,frame),JSON.stringify(value));}catch{/* RPC remains available. */}
}
export function clearRecovery(code:string,frame:DrawingFrame,id:string){
 const current=readRecovery(code,frame);if(current?.id!==id)return;
 memory.delete(key(code,frame));try{localStorage.removeItem(key(code,frame));}catch{/* Keep the idempotent recovery copy for the next launch. */}
}
