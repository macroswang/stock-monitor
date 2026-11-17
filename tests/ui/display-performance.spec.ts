import {test,expect} from '@playwright/test';

test('hidden retained charts skip parent snapshots and retain local state on return',async({page})=>{
 await page.goto('/');await page.evaluate(async()=>{const module=await import('/tests/ui/fixtures/pollingHarness.tsx');module.mountRetained();});
 await page.getByRole('button',{name:'本地图表状态',exact:true}).click();await expect(page.getByLabel('pane-local')).toHaveText('1');
 await page.getByRole('button',{name:'显示隐藏图表',exact:true}).click();const renders=await page.getByLabel('pane-renders').textContent();
 await page.getByRole('button',{name:'后台快照',exact:true}).click();await page.getByRole('button',{name:'后台快照',exact:true}).click();
 await expect(page.getByLabel('pane-renders')).toHaveText(renders!);await expect(page.getByLabel('pane-tick')).toHaveText('0');
 await page.getByRole('button',{name:'显示隐藏图表',exact:true}).click();await expect(page.getByLabel('pane-tick')).toHaveText('2');await expect(page.getByLabel('pane-local')).toHaveText('1');
});

test('display polling never overlaps, pauses hidden panels, and waits for old scopes',async({page})=>{
 await page.goto('/');
 await page.evaluate(async()=>{const module=await import('/tests/ui/fixtures/pollingHarness.tsx');module.mount();});
 const reads=page.getByLabel('reads');await expect(reads).toHaveText('1');
 await page.waitForTimeout(350);await expect(reads).toHaveText('1');
 await page.getByRole('button',{name:'切换股票',exact:true}).click();
 await page.waitForTimeout(200);await expect(reads).toHaveText('1');
 await page.getByRole('button',{name:'完成读取',exact:true}).click();await expect(reads).toHaveText('2');
 await page.getByRole('button',{name:'切换活动',exact:true}).click();
 await page.getByRole('button',{name:'完成读取',exact:true}).click();
 await page.waitForTimeout(350);await expect(reads).toHaveText('2');
 await page.getByRole('button',{name:'切换活动',exact:true}).click();await expect(reads).toHaveText('3');
});

test('read coalescing excludes all trading and write actions and separates symbols',async({page})=>{
 await page.goto('/');
 const result=await page.evaluate(async()=>{
  const {coalescedRead}=await import('/src/useDisplayPolling.ts');
  let reads=0,writes=0,finish!:()=>void;const gate=new Promise<void>(resolve=>finish=resolve);
  const read=()=>{reads++;return gate.then(()=>1);};
  const a=coalescedRead('history',{code:'a',start:'x'},read),b=coalescedRead('history',{start:'x',code:'a'},read),c=coalescedRead('history',{code:'b',start:'x'},read);
  const write=()=>{writes++;return Promise.resolve(1);};
  await Promise.all([coalescedRead('broker_submit',{},write),coalescedRead('broker_submit',{},write)]);
  finish();await Promise.all([a,b,c]);await coalescedRead('history',{code:'a',start:'x'},read);
  return {reads,writes,same:a===b,different:a!==c};
 });
 expect(result).toEqual({reads:3,writes:2,same:true,different:true});
});

test('leaving breadth stops all child overview and constituent reads',async({page})=>{
 await page.clock.install();
 const requests:string[]=[];
 page.on('request',r=>{if(/sector-|csi300-preview|pcr-preview|index-technical-preview/.test(r.url()))requests.push(r.url());});
 await page.goto('/');await page.getByRole('button',{name:'大盘广度',exact:true}).click();
 await expect(page.getByRole('region',{name:'市场全景',exact:true})).toBeVisible();
 await page.waitForTimeout(600);requests.length=0;await page.clock.runFor(16000);await page.waitForTimeout(150);expect(requests.length).toBeGreaterThan(0);
 await page.getByRole('button',{name:'设置与通知',exact:true}).click();
 await page.waitForTimeout(500);requests.length=0;
 await page.clock.runFor(31000);await page.waitForTimeout(300);
 expect(requests).toEqual([]);
});

test('unchanged revisions avoid repeated historical payloads and settings only read the snapshot',async({page})=>{
 await page.clock.install();
 let count=0;
 await page.route('**/preview.json',async route=>{
  count++;const response=await route.fetch(),data=await response.json();
  data.snapshot.data_revisions={code:data.snapshot.watch[0].code,history:[1],chart:[1,1,1],market:[1]};
  await route.fulfill({json:data});
 });
 await page.goto('/');await expect(page.locator('.detail h2')).toContainText('宏昌电子');
 await page.getByRole('button',{name:'日K',exact:true}).click();
 await page.waitForTimeout(500);count=0;
 await page.clock.runFor(6500);await page.waitForTimeout(300);
 // Snapshot + lightweight paper revision + order marks; no history/chart fan-out.
 expect(count).toBeLessThanOrEqual(7);
 await page.getByRole('button',{name:'设置与通知',exact:true}).click();
 await page.waitForTimeout(300);count=0;
 await page.clock.runFor(6500);await page.waitForTimeout(300);
 expect(count).toBeLessThanOrEqual(3);expect(count).toBeGreaterThan(0);
});
