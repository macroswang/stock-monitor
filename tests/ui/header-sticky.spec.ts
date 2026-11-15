import {test,expect} from '@playwright/test';

test('watch header stays above scrolling charts in all three views and both sidebar widths',async({page},info)=>{
 await page.setViewportSize({width:1380,height:680});await page.goto('/');
 const header=page.locator('.market-header');await expect(header.locator('.overview-index')).toHaveCount(3);
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:680});
  for(const view of ['分时','日K','周K']){
   await page.evaluate(()=>window.scrollTo(0,0));await page.getByRole('button',{name:view,exact:true}).click();
   const before=(await header.boundingBox())!;
   await page.evaluate(()=>window.scrollTo(0,400));
   await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBeGreaterThan(12);
   await expect.poll(async()=>Math.abs((await header.boundingBox())!.y)).toBeLessThan(1);
   const after=(await header.boundingBox())!;expect(after.height).toBe(before.height);expect(after.width).toBeCloseTo(before.width,1);
   expect(await header.evaluate(el=>{const b=el.getBoundingClientRect();return document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)?.closest('.market-header')===el;})).toBe(true);
   expect(await header.evaluate(el=>getComputedStyle(el).backgroundColor)).toBe('rgb(11, 18, 32)');
   await expect(header.getByRole('checkbox',{name:'持续监控'})).toBeInViewport({ratio:1});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.evaluate(()=>window.scrollTo(0,0));await expect.poll(async()=>(await header.boundingBox())!.y).toBeGreaterThan(0);
  }
 }
 await page.evaluate(()=>window.scrollTo(0,300));await page.screenshot({path:info.outputPath('watch-header-pinned.png')});
 await page.getByRole('button',{name:'大盘广度',exact:true}).click();
 expect(await page.locator('.workspace>header').evaluate(el=>getComputedStyle(el).position)).toBe('static');
});

test('index header remains available with a folded watchlist and stays below modal dialogs',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-sidebar-collapsed','true'));
 await page.setViewportSize({width:1280,height:680});await page.goto('/');
 await page.getByRole('button',{name:'日K',exact:true}).click();await page.evaluate(()=>window.scrollTo(0,300));
 const header=page.locator('.market-header');await expect.poll(async()=>Math.abs((await header.boundingBox())!.y)).toBeLessThan(1);
 await expect(header.locator('.overview-index')).toHaveCount(3);
 await page.getByRole('button',{name:'宏昌电子 MACD周期设置',exact:true}).click();await expect(page.getByRole('dialog')).toBeVisible();
 expect(await header.evaluate(el=>{const b=el.getBoundingClientRect();return !!document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)?.closest('.modal-overlay');})).toBe(true);
 await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
});
