import {test,expect} from '@playwright/test';

test('minute direction buttons and cost summary use smaller text and heights while saved values and direction remain usable',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-t-costs-v4',JSON.stringify({shares:2300,commissionWan:2,minimum:5,stampPerMille:.5,transferPerMille:.01,transferIncluded:false,slippagePerMille:0,direction:'sell-buy'})));
 await page.goto('/');const group=page.getByRole('group',{name:'做T方向',exact:true}),summary=page.locator('.minute-detail .t-cost-settings>summary');
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:980});
  for(const button of await group.getByRole('button').all()){
   await expect(button).toBeVisible();expect(await button.evaluate(el=>getComputedStyle(el).fontSize)).toBe('8px');expect((await button.boundingBox())!.height).toBe(16);
  }
  expect(await summary.evaluate(el=>getComputedStyle(el).fontSize)).toBe('9px');expect((await summary.boundingBox())!.height).toBe(14);
  await expect(summary).toContainText('2300股');await expect(summary).toContainText('佣金万2');
  expect((await page.locator('.minute-detail .minute-chart-controls').boundingBox())!.height).toBe(37);
  await page.getByRole('button',{name:'先买后卖',exact:true}).click();await expect(page.getByRole('button',{name:'先买后卖',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'先卖后买',exact:true}).click();await expect(page.getByRole('button',{name:'先卖后买',exact:true})).toHaveAttribute('aria-pressed','true');
 }
 await summary.click();await expect(page.getByRole('spinbutton',{name:'试算股数',exact:true})).toHaveValue('2300');
 await page.screenshot({path:'outputs/compact-t-controls.png',fullPage:true});
});
