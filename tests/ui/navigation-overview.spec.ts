import {test,expect} from '@playwright/test';

test('removed market overview stays absent regardless of the old saved collapse preference',async({page})=>{
 for(const collapsed of ['true','false']){
  await page.addInitScript(v=>localStorage.setItem('stock-monitor-overview-collapsed',v),collapsed);await page.goto('/');
  await expect(page.locator('.home-overview')).toHaveCount(0);await expect(page.locator('.market-header .overview-index')).toHaveCount(3);
  await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();await expect(page.getByRole('button',{name:/市场趋势/})).toHaveCount(0);
 }
});

test('menu navigation keeps loaded stock charts and breadth choices while remounting the index strip once',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/?sample=csi300');
 await expect(page.locator('.market-header .overview-index')).toHaveCount(3);await page.getByRole('button',{name:'日K',exact:true}).click();
 const chart=page.getByLabel('日K线及成交量',{exact:true});await expect(chart).toBeVisible();
 await page.evaluate(()=>{(window as any).__stockChart=document.querySelector('[aria-label="日K线及成交量"]');});
 await page.getByRole('button',{name:'大盘广度',exact:true}).click();const breadth=page.getByRole('region',{name:'市场趋势图'});await expect(breadth).toBeVisible();
 await breadth.getByRole('button',{name:'60日'}).click();await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await expect(page.locator('.market-header .overview-index')).toHaveCount(3);await expect(chart).toBeVisible();
 expect(await page.evaluate(()=>(window as any).__stockChart===document.querySelector('[aria-label="日K线及成交量"]'))).toBe(true);
 await page.getByRole('button',{name:'大盘广度',exact:true}).click();await expect(breadth.getByRole('button',{name:'60日'})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'数据管理',exact:true}).click();await expect(page.getByRole('heading',{name:'下载与本地缓存'})).toBeVisible();
 await page.getByRole('button',{name:'设置与通知',exact:true}).click();await expect(page.getByRole('heading',{name:'iPhone 锁屏通知'})).toBeVisible();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();await expect(chart).toBeVisible();expect(errors).toEqual([]);
});
