import {test,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
for(const deviceScaleFactor of [1,2])test.describe('DPR '+deviceScaleFactor,()=>{
 test.use({deviceScaleFactor});
 test('keyed stock mounts never stretch the retained bitmap while the viewport height settles',async({page})=>{
  await page.route('**/stock-switch-harness',r=>r.fulfill({contentType:'text/html',body:`<!doctype html><div id="root"></div><script type="module">
   import {injectIntoGlobalHook} from '/@react-refresh';injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),surfacePath=source.split('from "').slice(1).map(s=>s.split('"')[0]).find(p=>p.includes('canvasFrameSurface'));
   const {CanvasFrameSurface}=await import(surfacePath);const p=CanvasFrameSurface.prototype,original=p.present;window.switchFrames=[];
   p.present=function(){const result=original.call(this),c=this.canvas,h=c.parentElement;if(h&&c.style.visibility!=='hidden'&&c.width&&c.height){const r=c.getBoundingClientRect();window.switchFrames.push({code:h.closest('[data-stock]').dataset.stock,width:c.width,height:c.height,cssWidth:r.width,cssHeight:r.height,hostHeight:h.clientHeight,distortion:Math.abs((r.width/c.width)/(r.height/c.height)-1)});}return result;};
   await import('/tests/ui/fixtures/minuteSwitchHarness.tsx');</script>`}));
  await page.goto('/stock-switch-harness');await expect(page.getByLabel('分时价格及分钟成交量',{exact:true})).toBeVisible();
  for(const name of ['三孚股份','山子高科','三孚股份','山子高科']){await page.getByRole('button',{name,exact:true}).click();await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(r)))));}
  const frames=await page.evaluate(()=>(window as any).switchFrames);
  writeFileSync(test.info().outputPath('switch-frames.json'),JSON.stringify(frames,null,2));
  expect(frames.length).toBeGreaterThan(4);expect(frames.some((f:any)=>f.code==='sh603938')).toBe(true);
  expect(frames.filter((f:any)=>f.distortion>.005)).toEqual([]);
  expect(frames.every((f:any)=>Math.abs(f.cssHeight-f.hostHeight)<1)).toBe(true);
 });
});
