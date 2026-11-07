import type {Page} from '@playwright/test';

export async function openSimulation(page:Page){
  await page.getByRole('button',{name:'市场机会',exact:true}).click();
  const plans=page.locator('.mode-advanced');
  if(await plans.getAttribute('open')===null)await plans.locator(':scope > summary').click();
  await plans.getByRole('button',{name:'打开模拟交易',exact:true}).click();
}
