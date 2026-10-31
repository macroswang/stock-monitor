import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.clock.install({time:new Date('2026-10-31T08:00:00Z')});});

test('市场趋势可收起、展开并记住选择',async({page})=>{
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('3599.02')).toBeVisible();
 const collapse=home.getByRole('button',{name:'收起市场趋势'});
 await expect(collapse).toHaveAttribute('aria-expanded','true');
 await collapse.click();
 await expect(home.getByRole('button',{name:'展开市场趋势'})).toHaveAttribute('aria-expanded','false');
 await expect(home.getByText('3599.02')).toBeHidden();
 await expect(page.getByRole('heading',{name:'我的自选'})).toBeVisible();
 await page.reload();
 await expect(home.getByRole('button',{name:'展开市场趋势'})).toBeVisible();
 await home.getByRole('button',{name:'展开市场趋势'}).click();
 await expect(home.getByText('3599.02')).toBeVisible();
});

test('菜单来回切换保留已加载页面、图表与选择',async({page})=>{
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('3599.02')).toBeVisible();
 await home.getByRole('button',{name:'概念',exact:true}).click();
 await expect(home.getByText('新浪概念资金流',{exact:false})).toBeVisible();
 await page.evaluate(()=>{(window as any).__homeNode=document.querySelector('[aria-label="首页市场趋势"]');(window as any).__chartNode=document.querySelector('[aria-label="上证当日分时涨跌幅"]');});
 await page.getByRole('button',{name:'大盘广度',exact:true}).click();
 const breadth=page.getByRole('region',{name:'市场趋势图'});
 await expect(breadth).toBeVisible();
 await breadth.getByRole('button',{name:'60日'}).click();
 await expect(breadth.getByRole('button',{name:'60日'})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await expect(home.getByText('3599.02')).toBeVisible();
 await expect(home.getByRole('button',{name:'概念',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect.poll(()=>home.getByRole('img',{name:'上证当日分时涨跌幅'}).locator('canvas').first().evaluate((el:HTMLCanvasElement)=>el.width)).toBeGreaterThan(0);
 expect(await page.evaluate(()=>({home:(window as any).__homeNode===document.querySelector('[aria-label="首页市场趋势"]'),chart:(window as any).__chartNode===document.querySelector('[aria-label="上证当日分时涨跌幅"]')}))).toEqual({home:true,chart:true});
 await page.getByRole('button',{name:'大盘广度',exact:true}).click();
 await expect(breadth.getByRole('button',{name:'60日'})).toHaveAttribute('aria-pressed','true');
 await expect(breadth.locator('canvas').first()).toBeVisible();
 await page.getByRole('button',{name:'数据管理',exact:true}).click();
 await expect(page.getByRole('heading',{name:'下载与本地缓存'})).toBeVisible();
 await page.getByRole('button',{name:'设置与通知',exact:true}).click();
 await expect(page.getByRole('heading',{name:'iPhone 锁屏通知'})).toBeVisible();
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await expect(home.getByRole('button',{name:'概念',exact:true})).toHaveAttribute('aria-pressed','true');
});
