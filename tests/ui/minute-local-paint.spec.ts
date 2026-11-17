import {test,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';

for(const deviceScaleFactor of [1,2])test.describe('DPR '+deviceScaleFactor,()=>{
test.use({deviceScaleFactor});
test('a stable-scale tail tick does not clear the visible canvas or resend static chart components',async({page})=>{
 await page.route('**/refresh-harness',r=>r.fulfill({contentType:'text/html',body:`<!doctype html><div id="root"></div><script type="module">import {injectIntoGlobalHook} from '/@react-refresh';injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;await import('/tests/ui/fixtures/minuteRefreshHarness.tsx');</script>`}));
 await page.goto('/refresh-harness');const chart=page.getByLabel('分时价格及分钟成交量',{exact:true});
 await expect(page.locator('[data-volume-grid="1"] time')).toHaveText('10:29');
 await page.getByRole('button',{name:'平稳坐标行情',exact:true}).click();
 await page.getByRole('button',{name:'只更新末端价格',exact:true}).click();
 await chart.evaluate(async el=>{
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const text=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(text.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]),c=e.getInstanceByDom(el),w=window as any;
  w.__paintChart=c;w.__paintStats={clears:[],backingClears:[],copies:[],patches:[],surfaceMs:[]};const clear=CanvasRenderingContext2D.prototype.clearRect,draw=CanvasRenderingContext2D.prototype.drawImage;
  const surface=await import(text.match(/from ["']([^"'\n]*canvasFrameSurface[^"'\n]*)["']/)![1]),prototype=surface.CanvasFrameSurface.prototype as any,present=prototype.present;
  prototype.present=function(){const started=performance.now();try{return present.call(this);}finally{w.__paintStats.surfaceMs.push(performance.now()-started);}};
  CanvasRenderingContext2D.prototype.clearRect=function(x,y,width,height){
   if(el.contains(this.canvas))(this.canvas.style.opacity==='0'?w.__paintStats.backingClears:w.__paintStats.clears).push({x,y,width,height,canvasWidth:this.canvas.width,canvasHeight:this.canvas.height});
   return clear.call(this,x,y,width,height);
  };
  CanvasRenderingContext2D.prototype.drawImage=function(...args:any[]){
   if(this.canvas.classList.contains('minute-frame-surface'))w.__paintStats.copies.push({width:args.length===9?args[7]:this.canvas.width,height:args.length===9?args[8]:this.canvas.height,canvasWidth:this.canvas.width,canvasHeight:this.canvas.height});
   return (draw as Function).apply(this,args);
  };
  const set=c.setOption.bind(c);c.setOption=(option:any,settings:any)=>{w.__paintStats.patches.push({keys:Object.keys(option),series:(option.series||[]).map((s:any)=>s.id||s.name),settings});return set(option,settings);};
 });
 await page.getByRole('button',{name:'只更新末端价格',exact:true}).click();
 const result=await chart.evaluate(async()=>{
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const w=window as any,c=w.__paintChart,o=c.getOption(),canvases=[...c.getDom().querySelectorAll('canvas')] as HTMLCanvasElement[];
  const visible=canvases.find(canvas=>canvas.classList.contains('minute-frame-surface'))!,raw=canvases.find(canvas=>canvas!==visible)!;
  const a=visible.getContext('2d')!.getImageData(0,0,visible.width,visible.height).data,b=raw.getContext('2d')!.getImageData(0,0,raw.width,raw.height).data;
  let mismatch=0,maxVisibleError=0;for(let i=0;i<a.length;i+=4){for(let channel=0;channel<3;channel++){
   if(a[i+channel]!==b[i+channel])mismatch++;
   // GPU texture copies can quantize unpremultiplied transparent RGB by one
   // display level. Verify actual visible colors on the app background.
   const background=[11,18,32][channel];
   maxVisibleError=Math.max(maxVisibleError,Math.abs((a[i+channel]*a[i+3]+background*(255-a[i+3]))/255-(b[i+channel]*b[i+3]+background*(255-b[i+3]))/255));
  }}
  return {...w.__paintStats,last:o.series.find((s:any)=>s.name==='价格').data[59],dirtyRect:c.getZr().painter._opts.useDirtyRect,mismatch,maxVisibleError};
 });
 await test.info().attach('actual-canvas-paint',{body:JSON.stringify(result,null,2),contentType:'application/json'});
 writeFileSync(test.info().outputPath('canvas-paint.json'),JSON.stringify(result,null,2));
 expect(result.clears).toHaveLength(0);
 expect(result.surfaceMs.length).toBeGreaterThan(0);
 expect(result.maxVisibleError).toBeLessThanOrEqual(1);
 expect(result.copies.length).toBeGreaterThan(0);
 expect(Math.max(...result.copies.map((r:any)=>r.width*r.height/(r.canvasWidth*r.canvasHeight)))).toBeLessThan(.3);
 expect(result.copies.reduce((sum:number,r:any)=>sum+r.width*r.height/(r.canvasWidth*r.canvasHeight),0)).toBeLessThan(.1);
 // A real MACD extremum can change its y-axis; grids, time axes, legend and zoom remain intact.
 expect(result.patches.every((p:any)=>!p.keys.some((k:string)=>['grid','xAxis','yAxis','legend','dataZoom'].includes(k)))).toBe(true);
});
});
