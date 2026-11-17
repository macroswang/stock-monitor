import {test,expect,type Page} from '@playwright/test';

const chart=(page:Page)=>page.getByLabel('分时价格及分钟成交量',{exact:true});
async function boot(page:Page){
 await page.route('**/refresh-harness',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><div id="root"></div><script type="module">import {injectIntoGlobalHook} from '/@react-refresh';injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;await import('/tests/ui/fixtures/minuteRefreshHarness.tsx');</script>`}));
 await page.goto('/refresh-harness');await expect(chart(page)).toBeVisible();
 await expect(page.locator('[data-volume-grid="1"] time')).toHaveText('10:29');
 await chart(page).evaluate(async el=>{
  const text=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(text.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]),c=e.getInstanceByDom(el);
  (window as any).__refreshChart=c;(window as any).__refreshStats={updates:0,resets:0,resizes:0};
  const set=c.setOption.bind(c),resize=c.resize.bind(c);
  c.setOption=(option:any,settings:any)=>{(window as any).__refreshStats.updates++;if(settings===true||settings?.notMerge)(window as any).__refreshStats.resets++;return set(option,settings);};
  c.resize=(...args:any[])=>{(window as any).__refreshStats.resizes++;return resize(...args);};
 });
}
async function state(page:Page){
 return chart(page).evaluate(el=>{
  const c=(window as any).__refreshChart,o=c.getOption(),series=c.getModel().getSeries();
  const r=el.getBoundingClientRect();
  return {stats:{...(window as any).__refreshStats},instance:c.id,uids:series.map((s:any)=>[s.name,s.uid]),legend:o.legend[0].selected,
   prices:o.series.find((s:any)=>s.name==='价格').data,volumes:o.series.find((s:any)=>s.name==='指数成交量')?.data,
   names:o.series.map((s:any)=>s.name),zoom:o.dataZoom.map((z:any)=>[z.start,z.end]),height:r.height,top:r.top};
 });
}

test('metadata-only refreshes do not rebuild or repaint unchanged minute charts',async({page})=>{
 await boot(page);const before=await state(page);
 for(let i=0;i<4;i++)await page.getByRole('button',{name:'只更新缓存时间',exact:true}).click();
 await expect(page.getByLabel('刷新批次')).toHaveText('4|0');
 const after=await state(page);expect(after.stats.updates-before.stats.updates).toBe(0);
 expect(after.uids).toEqual(before.uids);expect(after.height).toBe(before.height);expect(after.top).toBe(before.top);
});

test('real updates retain legend choices, model identity and zoom while updating actual values',async({page})=>{
 await boot(page);
 await chart(page).evaluate(()=>{const c=(window as any).__refreshChart;c.dispatchAction({type:'legendUnSelect',name:'均价'});c.dispatchAction({type:'dataZoom',start:0,end:60});});
 const before=await state(page);
 await page.getByRole('button',{name:'更新实际行情',exact:true}).click();
 await expect.poll(async()=>(await state(page)).prices).not.toEqual(before.prices);
 const after=await state(page);expect(after.legend['均价']).toBe(false);expect(after.uids).toEqual(before.uids);
 expect(after.zoom).toEqual(before.zoom);expect(after.stats.resets-before.stats.resets).toBe(0);
 expect(after.height).toBe(before.height);expect(after.top).toBe(before.top);
});

test('cache cutoffs still change reached stock/index values and a stock switch resets its chart scope',async({page})=>{
 await boot(page);
 await page.getByRole('button',{name:'收紧缓存截止',exact:true}).click();
 await expect.poll(async()=>(await state(page)).prices[59]).toBeNull();
 await page.getByRole('button',{name:'推进缓存截止',exact:true}).click();
 await expect.poll(async()=>(await state(page)).prices[59]).not.toBeNull();
 await page.getByRole('button',{name:'收紧指数截止',exact:true}).click();
 await expect.poll(async()=>(await state(page)).volumes[59]).toBeNull();
 await page.getByRole('button',{name:'推进指数截止',exact:true}).click();
 await expect.poll(async()=>(await state(page)).volumes[59]).not.toBeNull();
 await chart(page).evaluate(()=>{(window as any).__refreshChart.dispatchAction({type:'legendUnSelect',name:'均价'});});
 const before=await state(page);await page.getByRole('button',{name:'切换股票',exact:true}).click();
 await expect.poll(async()=>(await state(page)).stats.resets).toBeGreaterThan(before.stats.resets);
 expect((await state(page)).legend['均价']).not.toBe(false);
});

test('live refresh keeps the hovered minute and does not briefly replace its headers with the latest minute',async({page})=>{
 await boot(page);
 const pixel=await chart(page).evaluate(el=>{const c=(window as any).__refreshChart,r=el.getBoundingClientRect(),p=c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:45',10.1]);return {x:r.x+p[0],y:r.y+p[1]};});
 await page.mouse.move(pixel.x,pixel.y);
 await expect(page.locator('[data-volume-grid="1"] time')).toHaveText('09:45');
 await page.evaluate(()=>{
  const w=window as any;w.__headerTexts=[];
  w.__headerObserver=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)w.__headerTexts.push(node.textContent);});
  w.__headerObserver.observe(document.querySelector('[data-volume-grid="1"] time'),{childList:true,subtree:true});
 });
 const before=await state(page);
 // Dispatch the feed update without moving the user's pointer to a button.
 await page.getByRole('button',{name:'更新实际行情',exact:true}).evaluate(el=>(el as HTMLButtonElement).click());
 await expect.poll(async()=>(await state(page)).prices).not.toEqual(before.prices);
 await expect(page.locator('[data-volume-grid="1"] time')).toHaveText('09:45');
 expect(await page.evaluate(()=>(window as any).__headerTexts)).not.toContain('10:29');
 await page.mouse.move(0,0);
});

test('removed trade overlays leave no ghost series and future caches still hide unreached prices',async({page})=>{
 await boot(page);const before=await state(page),priceUID=before.uids.find((s:any)=>s[0]==='价格');
 await page.getByRole('button',{name:'切换成交标记',exact:true}).click();
 await expect.poll(async()=>(await state(page)).names.includes('自动委托')).toBe(true);
 await page.getByRole('button',{name:'切换成交标记',exact:true}).click();
 await expect.poll(async()=>(await state(page)).names.includes('自动委托')).toBe(false);
 expect((await state(page)).uids.find((s:any)=>s[0]==='价格')).toEqual(priceUID);
 await page.getByRole('button',{name:'切换未来缓存',exact:true}).click();
 await expect.poll(async()=>(await state(page)).prices.every((p:any)=>p===null)).toBe(true);
 await page.getByRole('button',{name:'切换未来缓存',exact:true}).click();
 await expect.poll(async()=>(await state(page)).prices).toEqual(before.prices);
 await page.screenshot({path:test.info().outputPath('stable-minute-chart.png'),fullPage:true});
});

test('hovering outside the data grids still refreshes the latest indicator headers',async({page})=>{
 await boot(page);
 const pixel=await chart(page).evaluate(el=>{const c=(window as any).__refreshChart,r=el.getBoundingClientRect(),p=c.convertToPixel({xAxisIndex:0,yAxisIndex:0},['09:45',10.1]);return {x:r.x+p[0],y:r.y+p[1],legendX:r.x+30,legendY:r.y+8};});
 await page.mouse.move(pixel.x,pixel.y);
 await expect(page.locator('[data-volume-grid="1"] time')).toHaveText('09:45');
 await page.mouse.move(pixel.legendX,pixel.legendY);
 await page.getByRole('button',{name:'更新实际行情',exact:true}).evaluate(el=>(el as HTMLButtonElement).click());
 await expect(page.locator('[data-volume-grid="1"] time')).toHaveText('10:29');
});
