import {test,expect} from '@playwright/test';

test('slow application bundle shows loading and timeout feedback, then recovers without a reload',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.route(/\/(?:src\/main\.tsx|assets\/index-[^/]+\.js)(?:\?|$)/,async route=>{await gate;await route.continue();});
 await page.clock.install();
 try{
  await page.goto('/',{waitUntil:'commit'});
  await expect(page.locator('#startup-status')).toContainText('观量正在启动');
  await expect(page.locator('#startup-retry')).toBeHidden();
  await page.clock.fastForward(8500);
  await expect(page.locator('#startup-status')).toContainText('界面加载未完成');
  await expect(page.locator('#startup-retry')).toBeVisible();
  release();
  await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();
  await expect(page.locator('#startup-status')).toHaveCount(0);
 }finally{release();}
});

test('missing application bundle offers a manual retry and does not clear saved preferences',async({page})=>{
 let missing=true;
 await page.addInitScript(()=>localStorage.setItem('startup-retention-check','keep'));
 await page.route(/\/(?:src\/main\.tsx|assets\/index-[^/]+\.js)(?:\?|$)/,route=>missing?route.abort('failed'):route.continue());
 await page.goto('/');
 await expect(page.locator('#startup-status')).toContainText('界面加载未完成');
 expect(await page.evaluate(()=>localStorage.getItem('startup-retention-check'))).toBe('keep');
 missing=false;
 await page.getByRole('button',{name:'重新加载界面'}).click();
 await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();
 expect(await page.evaluate(()=>localStorage.getItem('startup-retention-check'))).toBe('keep');
});

test('a committed interface never gets a late startup overlay or an automatic reload',async({page})=>{
 let navigations=0;page.on('framenavigated',frame=>{if(frame===page.mainFrame())navigations++;});
 await page.clock.install();await page.goto('/');
 await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();
 await expect(page.locator('#startup-status')).toHaveCount(0);
 await page.clock.fastForward(15000);
 await page.evaluate(()=>window.dispatchEvent(new ErrorEvent('error',{message:'late synthetic error'})));
 await expect(page.locator('#startup-status')).toHaveCount(0);
 expect(navigations).toBe(1);
});

test('a missing startup helper cannot leave its loading screen over a working interface',async({page})=>{
 await page.route('**/startup.js',route=>route.abort('failed'));
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();
 await expect(page.locator('#startup-status')).toHaveCount(0);
});
