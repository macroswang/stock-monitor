type Rect={x:number;y:number;width:number;height:number};

/** Retained visible pixels. ECharts may repaint its backing canvas, but it must
 * never clear the user's visible frame between market-data updates. */
export class CanvasFrameSurface {
 readonly canvas=document.createElement('canvas');
 private context:CanvasRenderingContext2D;
 private originals=new Map<HTMLCanvasElement,string>();
 private frame=0;
 private feeding=false;
 private compare=false;
 private exact=true;
 private composite:HTMLCanvasElement|null=null;
 private previousPixels:ImageData|null=null;
 private disposed=false;
 constructor(private host:HTMLElement){
  this.canvas.className='minute-frame-surface';this.canvas.setAttribute('aria-hidden','true');
  Object.assign(this.canvas.style,{position:'absolute',left:'0',top:'0',pointerEvents:'none',zIndex:'0'});
  const context=this.canvas.getContext('2d');
  if(!context)throw Error('Canvas frame context unavailable');this.context=context;
  this.host.appendChild(this.canvas);
  this.host.addEventListener('mousemove',this.interacted,{passive:true,capture:true});
  this.host.addEventListener('pointerdown',this.interacted,{passive:true,capture:true});
  this.host.addEventListener('wheel',this.interacted,{passive:true,capture:true});
 }
 private interacted=()=>{if(!this.compare&&!this.feeding){this.exact=false;this.previousPixels=null;}};
 /** Public renderer event callback; coalesce data and pointer work in one frame. */
 rendered=()=>{
  if(this.disposed)return;
  if(!this.frame)this.frame=requestAnimationFrame(()=>{this.frame=0;this.present();});
 };
 update(work:()=>void){
  if(!this.previousPixels){
   if(this.frame){cancelAnimationFrame(this.frame);this.frame=0;this.present();}
   const source=this.source();
   if(source){try{this.previousPixels=source.getContext('2d')?.getImageData(0,0,source.width,source.height)||null;}catch{}}
  }
  this.feeding=true;this.exact=true;this.compare=true;
  try{work();}finally{this.feeding=false;this.compare=true;this.rendered();}
 }
 private source(){
  const layers=[...this.host.querySelectorAll('canvas')].filter(c=>c!==this.canvas);
  if(!layers.length)return null;
  for(const layer of layers){
   if(!this.originals.has(layer))this.originals.set(layer,layer.style.opacity);
  }
  for(const layer of this.originals.keys())if(!this.host.contains(layer))this.originals.delete(layer);
  if(layers.length===1)return layers[0];
  // Multiple zlevels are uncommon here, but must retain their compositing order.
  const buffer=this.composite||(this.composite=document.createElement('canvas'));
  const {width,height}=layers[0];
  if(buffer.width!==width||buffer.height!==height){buffer.width=width;buffer.height=height;}
  const ctx=buffer.getContext('2d');if(!ctx)return null;
  ctx.clearRect(0,0,width,height);
  for(const layer of layers)ctx.drawImage(layer,0,0,width,height);
  return buffer;
 }
 private changedRects(before:ImageData,after:ImageData){
  const {width,height}=after,a=before.data,b=after.data;
  const old=new Uint32Array(a.buffer,a.byteOffset,a.byteLength/4),next=new Uint32Array(b.buffer,b.byteOffset,b.byteLength/4);
  const rects:Rect[]=[],previous=new Map<string,Rect>();
  const size=32;
  for(let y=0;y<height;y+=size){
   const bottom=Math.min(y+size,height),row:Rect[]=[];
   for(let x=0;x<width;x+=size){
    const right=Math.min(x+size,width);let changed=false;
    for(let iy=y;iy<bottom&&!changed;iy++)for(let ix=x;ix<right;ix++)if(old[iy*width+ix]!==next[iy*width+ix]){changed=true;break;}
    if(changed){const last=row.at(-1);if(last&&last.x+last.width===x)last.width=right-last.x;else row.push({x,y,width:right-x,height:bottom-y});}
   }
   for(const rect of row){
    const key=rect.x+'|'+rect.width,above=previous.get(key);
    if(above&&above.y+above.height===y)above.height+=rect.height;
    else{rects.push(rect);previous.set(key,rect);}
   }
  }
  return rects;
 }
 private copy(source:HTMLCanvasElement,rect:Rect){
  const {x,y,width,height}=rect,ctx=this.context;
  // 'copy' replaces transparent pixels too. Clip first because this composite
  // mode would otherwise erase pixels outside the updated rectangle.
  ctx.save();
  try{ctx.beginPath();ctx.rect(x,y,width,height);ctx.clip();ctx.globalCompositeOperation='copy';
   ctx.drawImage(source,x,y,width,height,x,y,width,height);
  }finally{ctx.restore();}
 }
 private present(){
  if(this.disposed||this.feeding||!this.host.getClientRects().length)return;
  const source=this.source();if(!source||!source.width||!source.height){this.restoreBacking();return;}
  const {width,height}=source,resized=this.canvas.width!==width||this.canvas.height!==height;
  if(resized){this.canvas.width=width;this.canvas.height=height;}
  // Host layout can advance one frame before ECharts resizes its backing layer.
  // Present at the backing layer's own logical dimensions; stretching its old
  // pixels to the new host size turns circles/text into ellipses on stock switches.
  const backing=source===this.composite?this.originals.keys().next().value:source;
  const logicalWidth=backing?.style.width.endsWith('px')?parseFloat(backing.style.width):this.host.clientWidth;
  const logicalHeight=backing?.style.height.endsWith('px')?parseFloat(backing.style.height):logicalWidth*height/width;
  const cssWidth=logicalWidth+'px',cssHeight=logicalHeight+'px';
  if(this.canvas.style.width!==cssWidth)this.canvas.style.width=cssWidth;
  if(this.canvas.style.height!==cssHeight)this.canvas.style.height=cssHeight;
  let rects:Rect[]|null=null;
  if(this.exact){try{
   const next=source.getContext('2d')?.getImageData(0,0,width,height);
   if(next){if(!resized&&this.previousPixels?.width===width&&this.previousPixels.height===height)rects=this.changedRects(this.previousPixels,next);this.previousPixels=next;}
  }catch{this.previousPixels=null;/* Tainted canvases fall back to an atomic copy. */}}
  this.compare=false;
  const area=rects?.reduce((sum,r)=>sum+r.width*r.height,0)||0;
  if(!rects||rects.length>128||area>width*height*.65)rects=[{x:0,y:0,width,height}];
  try{
   for(const rect of rects)this.copy(source,rect);
   this.canvas.style.visibility='';
   for(const layer of this.originals.keys())if(layer.style.opacity!=='0')layer.style.opacity='0';
  }catch{this.restoreBacking();}
 }
 private restoreBacking(){
  for(const [layer,opacity] of this.originals)layer.style.opacity=opacity;
  this.canvas.style.visibility='hidden';this.previousPixels=null;
 }
 dispose(){
  this.disposed=true;cancelAnimationFrame(this.frame);
  for(const [layer,opacity] of this.originals)layer.style.opacity=opacity;
  this.originals.clear();this.canvas.remove();if(this.composite){this.composite.width=0;this.composite.height=0;}this.composite=null;this.previousPixels=null;
  this.host.removeEventListener('mousemove',this.interacted,true);this.host.removeEventListener('pointerdown',this.interacted,true);this.host.removeEventListener('wheel',this.interacted,true);
  this.canvas.width=0;this.canvas.height=0;
 }
}
