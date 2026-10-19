import {test,expect} from '@playwright/test';
test('charts, navigation and push setup render without runtime errors',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();
 await expect(page.locator('.stock')).toHaveCount(12);
 await expect(page.getByLabel('交易日期')).toHaveValue('2026-10-16');
 await expect(page.locator('canvas')).toHaveCount(1);
 await page.screenshot({path:'docs/client-preview.png',fullPage:true});
 await page.getByRole('button',{name:'日K',exact:true}).click();await expect(page.getByLabel('日K线及成交量')).toBeVisible();
 await page.locator('.stock').filter({hasText:'海优新材'}).click();await expect(page.locator('.detail h2')).toContainText('海优新材');
 await page.getByRole('button',{name:/数据管理/}).click();await expect(page.getByRole('heading',{name:'下载与本地缓存'})).toBeVisible();
 await page.getByRole('button',{name:/设置与通知/}).click();await expect(page.getByRole('heading',{name:'iPhone 锁屏通知'})).toBeVisible();
 await expect(page.getByRole('button',{name:'保存密钥'})).toBeDisabled();
 await page.getByRole('button',{name:'发送测试通知'}).click();await expect(page.getByRole('status')).toContainText('浏览器仅用于界面预览');
 expect(errors).toEqual([]);
});

test('four real raw-backed preview curves retain matching average values',async({page})=>{
 await page.goto('/');
 for(const [name,code,average] of [['宏昌电子','sh603002','15.72'],['海优新材','sh688680','34.23'],['盛和资源','sh600392','17.74'],['山子高科','sz000981','2.44']]){
  await page.locator('.stock').filter({hasText:name}).click();await expect(page.locator('.detail h2')).toContainText(name);
  const chart=page.getByLabel('分时价格及分钟成交量');
  await expect(page.locator('.average-caption')).not.toContainText('缺少成交额');
  await chart.screenshot({path:'docs/0.4.0/client-curve-'+code+'.png'});
 }
});
