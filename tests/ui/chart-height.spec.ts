import {test,expect,type Page} from '@playwright/test';

async function bounds(page:Page){
 return page.locator('.market-grid>.detail').evaluate(el=>{
  const chart=el.querySelector(':scope>.chart-shell>.chart')!;
  const rect=chart.getBoundingClientRect(),detail=el.getBoundingClientRect();
  return {height:rect.height,bottom:detail.bottom+scrollY,padding:parseFloat(getComputedStyle(el.closest('.workspace')!).paddingBottom),viewport:document.documentElement.clientHeight};
 });
}

test('primary minute, daily and weekly charts fill the freed viewport and follow resizing',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-linked-minute-open','false'));
 await page.setViewportSize({width:1500,height:1180});await page.goto('/');
 for(const tab of ['分时','日K','周K']){
  await page.getByRole('button',{name:tab,exact:true}).click();
  await expect(page.locator('.market-grid>.detail>.chart-shell>.chart')).toBeVisible();
  await expect.poll(async()=>{const b=await bounds(page);return Math.abs(b.viewport-b.bottom-b.padding);}).toBeLessThan(2);
  const tall=await bounds(page);expect(tall.height).toBeGreaterThan(460);
  // A transient popup must float above the workspace without consuming chart
  // height or causing the chart to resize.
  await page.evaluate(()=>{const note=document.createElement('div');note.className='app-message-layer';note.id='test-history-notice';note.textContent='历史数据补充提示';document.body.append(note);});
  await expect.poll(async()=>{const b=await bounds(page);return Math.abs(b.viewport-b.bottom-b.padding);}).toBeLessThan(2);
  expect((await bounds(page)).height).toBe(tall.height);
  await page.evaluate(()=>document.querySelector('#test-history-notice')!.remove());
  await expect.poll(async()=>Math.abs((await bounds(page)).height-tall.height)).toBeLessThan(2);

  await page.setViewportSize({width:1500,height:980});
  await expect.poll(async()=>Math.abs(tall.height-(await bounds(page)).height-200)).toBeLessThan(2);
  await page.getByRole('button',{name:'大盘广度',exact:true}).click();
  await page.setViewportSize({width:1500,height:1080});
  await page.getByRole('button',{name:'自选监控',exact:true}).click();
  await expect.poll(async()=>{const b=await bounds(page);return Math.abs(b.viewport-b.bottom-b.padding);}).toBeLessThan(2);
  await page.setViewportSize({width:1500,height:1180});
  await page.mouse.move(0,0);await page.screenshot({path:`docs/production-0.6.142/chart-${tab}.png`,fullPage:true});
 }
 expect(errors).toEqual([]);
});

test('short windows keep readable charts and expanded linked minutes scroll without shrinking the main chart',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-linked-minute-open','false'));
 await page.setViewportSize({width:1380,height:1080});await page.goto('/');
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect.poll(async()=>{const b=await bounds(page);return Math.abs(b.viewport-b.bottom-b.padding);}).toBeLessThan(2);
 const before=(await bounds(page)).height;
 await page.getByRole('button',{name:'展开当日分时',exact:true}).click();
 await expect(page.locator('.linked-minute #linked-minute-content')).toBeVisible();
 await expect.poll(async()=>(await bounds(page)).height).toBe(before);
 await page.evaluate(()=>window.scrollTo(0,200));
 await page.waitForTimeout(150);expect((await bounds(page)).height).toBe(before);
 await page.getByRole('button',{name:'收起当日分时',exact:true}).click();
 await page.evaluate(()=>window.scrollTo(0,0));await page.setViewportSize({width:1000,height:540});
 await expect.poll(async()=>(await bounds(page)).height).toBe(460);
 expect(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight)).toBe(true);
 expect(errors).toEqual([]);
});
