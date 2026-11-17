import {test,expect} from '@playwright/test';

async function blank(page:import('@playwright/test').Page){
 await page.route('**/surface-harness',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
 await page.goto('/surface-harness');
}
test('a host resize cannot stretch the previous frame while the backing layer is still at its old size',async({page})=>{
 await blank(page);
 const result=await page.evaluate(async()=>{
  const {CanvasFrameSurface}=await import('/src/canvasFrameSurface.ts');
  const host=document.createElement('div');Object.assign(host.style,{position:'relative',width:'320px',height:'160px'});document.body.append(host);
  const raw=document.createElement('canvas');raw.width=640;raw.height=320;Object.assign(raw.style,{width:'320px',height:'160px'});host.append(raw);
  const surface=new CanvasFrameSurface(host),tick=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  raw.getContext('2d')!.fillRect(0,0,20,20);surface.rendered();await tick();
  host.style.height='320px';surface.rendered();await tick();
  const pending={width:surface.canvas.style.width,height:surface.canvas.style.height};
  raw.height=640;raw.style.height='320px';raw.getContext('2d')!.fillRect(0,0,20,20);surface.rendered();await tick();
  const settled={width:surface.canvas.style.width,height:surface.canvas.style.height};surface.dispose();return {pending,settled};
 });
 expect(result.pending).toEqual({width:'320px',height:'160px'});
 expect(result.settled).toEqual({width:'320px',height:'320px'});
});
test('frame patches erase transparent pixels, resize correctly and release their buffers on disposal',async({page})=>{
 await blank(page);
 const result=await page.evaluate(async()=>{
  const {CanvasFrameSurface}=await import('/src/canvasFrameSurface.ts');
  const host=document.createElement('div');Object.assign(host.style,{position:'relative',width:'320px',height:'160px'});document.body.append(host);
  const raw=document.createElement('canvas');raw.width=640;raw.height=320;raw.style.opacity='.85';host.append(raw);
  const ctx=raw.getContext('2d')!,surface=new CanvasFrameSurface(host),tick=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  ctx.fillStyle='#f00';ctx.fillRect(20,20,20,20);surface.rendered();await tick();
  surface.update(()=>{ctx.clearRect(20,20,20,20);ctx.fillStyle='#0f0';ctx.fillRect(100,20,20,20);});await tick();
  const visible=surface.canvas.getContext('2d')!;
  const erased=[...visible.getImageData(25,25,1,1).data],fresh=[...visible.getImageData(105,25,1,1).data];
  raw.width=800;raw.height=400;ctx.fillStyle='#00f';ctx.fillRect(700,300,20,20);surface.rendered();await tick();
  const resized={width:surface.canvas.width,height:surface.canvas.height,pixel:[...visible.getImageData(705,305,1,1).data]};
  surface.rendered();surface.dispose();await tick();
  return {erased,fresh,resized,restoredOpacity:raw.style.opacity,connected:surface.canvas.isConnected,buffers:[surface.canvas.width,surface.canvas.height]};
 });
 expect(result.erased).toEqual([0,0,0,0]);expect(result.fresh).toEqual([0,255,0,255]);
 expect(result.resized).toEqual({width:800,height:400,pixel:[0,0,255,255]});
 expect(result.restoredOpacity).toBe('0.85');expect(result.connected).toBe(false);expect(result.buffers).toEqual([0,0]);
});

test('pointer frames avoid pixel readbacks and a copy failure falls back to the current renderer without stale frames',async({page})=>{
 await blank(page);
 const result=await page.evaluate(async()=>{
  const {CanvasFrameSurface}=await import('/src/canvasFrameSurface.ts');
  const host=document.createElement('div');Object.assign(host.style,{position:'relative',width:'320px',height:'160px'});document.body.append(host);
  const raw=document.createElement('canvas');raw.width=320;raw.height=160;host.append(raw);
  const ctx=raw.getContext('2d')!,surface=new CanvasFrameSurface(host),tick=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  ctx.fillStyle='#f00';ctx.fillRect(0,0,20,20);surface.rendered();await tick();
  let reads=0;const read=ctx.getImageData.bind(ctx);ctx.getImageData=(...args:Parameters<typeof read>)=>{reads++;return read(...args);};
  for(let i=0;i<8;i++){host.dispatchEvent(new MouseEvent('mousemove',{bubbles:true}));ctx.fillRect(30+i,30,1,1);surface.rendered();await tick();}
  const pointerReads=reads;
  surface.update(()=>{ctx.fillStyle='#0f0';ctx.fillRect(60,60,10,10);});await tick();
  const feedReads=reads-pointerReads,visible=surface.canvas.getContext('2d')!,draw=visible.drawImage;
  visible.drawImage=()=>{throw Error('simulated compositor loss');};
  surface.update(()=>{ctx.fillStyle='#00f';ctx.fillRect(70,70,10,10);});await tick();
  const fallback={opacity:raw.style.opacity,visibility:surface.canvas.style.visibility};
  visible.drawImage=draw;surface.update(()=>{ctx.fillStyle='#0f0';ctx.fillRect(80,80,10,10);});await tick();
  const recovered={opacity:raw.style.opacity,visibility:surface.canvas.style.visibility,pixel:[...visible.getImageData(85,85,1,1).data]};
  surface.dispose();return {pointerReads,feedReads,fallback,recovered};
 });
 expect(result.pointerReads).toBe(0);expect(result.feedReads).toBeLessThanOrEqual(2);
 expect(result.fallback).toEqual({opacity:'',visibility:'hidden'});
 expect(result.recovered).toEqual({opacity:'0',visibility:'',pixel:[0,255,0,255]});
});

test('minute option patches send only changed series and remove stale overlays without changing user zoom',async({page})=>{
 await blank(page);
 const result=await page.evaluate(async()=>{
  const {MinuteOptionPatch}=await import('/src/minuteOptionPatch.ts');
  const option={grid:[{top:20}],xAxis:[{data:['09:30']}],yAxis:[{min:9,max:11}],dataZoom:[{start:0,end:100}],series:[{id:'price',data:[10]},{id:'volume',data:[100]}]};
  const cache=new MinuteOptionPatch(option,{});
  const same=cache.next(structuredClone(option),{});
  const changed=cache.next({...option,dataZoom:[{start:20,end:60}],series:[{id:'price',data:[10.1]},option.series[1]]},{});
  const removed=cache.next({...option,series:[{id:'price',data:[10.1]}]},{});
  return {same,changed,removed};
 });
 expect(result.same.option).toEqual({});expect(result.changed.option).toEqual({series:[{id:'price',data:[10.1]}]});
 expect(result.changed.replaceSeries).toBe(false);expect(result.removed.replaceSeries).toBe(true);
 expect(result.removed.option).toEqual({series:[{id:'price',data:[10.1]}]});
});
