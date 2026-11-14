import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

test('annual-line menu shows 5-day signals and expands charts in the row',async({page})=>{
 const scan=JSON.parse(readFileSync('public/ma250-scan-preview.json','utf8'));
 await page.route('**/ma250-scan-preview.json',route=>route.fulfill({json:scan}));
 await page.goto('/');
 await page.getByRole('button',{name:'年线信号'}).click();
 await expect(page.getByRole('heading',{name:'年线信号台'})).toBeVisible();
 await expect(page.getByText('2026-10-12 至 2026-10-16').first()).toBeVisible();
 const row=page.getByRole('row',{name:/宏昌电子/}).first();
 await expect(row).toBeVisible();
 await expect(page.getByText('回踩·强')).toBeVisible();
 await expect(page.getByText('突破·确认')).toBeVisible();
 await row.click();
 const expand=page.locator('tr.ma250-expand');
 await expect(expand).toBeVisible();
 const chart=expand.getByLabel('日K线及成交量');
 await expect(chart).toBeVisible({timeout:15000});
 await expect(expand.getByRole('tab',{name:'分时'})).toBeVisible();
 await expect(expand.getByRole('tab',{name:'周K'})).toBeVisible();
 await page.getByLabel('信号类型').selectOption('breakout');
 await expect(page.getByText('突破·确认')).toBeVisible();
 await expect(page.getByRole('row',{name:/海优新材/})).toHaveCount(0);
 await page.getByLabel('信号类型').selectOption('pullback');
 await page.getByLabel('只看强回踩').check();
 await expect(page.getByRole('row',{name:/海优新材/})).toHaveCount(0);
 await expect(page.getByText('回踩·强')).toBeVisible();
});

test('search and strong filters cover records beyond the first 300 with server paging',async({page})=>{
 const scan=JSON.parse(readFileSync('public/ma250-scan-preview.json','utf8'));
 const base=scan.rows[0];
 scan.rows=Array.from({length:405},(_,i)=>({...base,code:'sh'+String(600000+i),name:'测试股票'+i,strong:i===404}));
 scan.total=405;
 await page.route('**/ma250-scan-preview.json',route=>route.fulfill({json:scan}));
 await page.goto('/');await page.getByRole('button',{name:'年线信号'}).click();
 await expect(page.getByRole('navigation',{name:'信号分页'})).toContainText('第 1 / 5 页');
 await expect(page.locator('tr.ma250-signal-row')).toHaveCount(100);
 await page.getByRole('button',{name:'下一页',exact:true}).click();
 await expect(page.getByRole('navigation',{name:'信号分页'})).toContainText('第 2 / 5 页');
 await page.getByLabel('搜索年线信号').fill('测试股票404');
 await expect(page.locator('tr.ma250-signal-row')).toHaveCount(1);
 await expect(page.getByRole('row',{name:/测试股票404/})).toBeVisible();
 await expect(page.getByRole('navigation',{name:'信号分页'})).toHaveCount(0);
 await page.getByLabel('搜索年线信号').fill('');await page.getByLabel('只看强回踩').check();
 await expect(page.locator('tr.ma250-signal-row')).toHaveCount(1);
 await expect(page.getByRole('row',{name:/测试股票404/})).toBeVisible();
});

test('missing volume and stale index remain explicit in a narrow layout',async({page})=>{
 const scan=JSON.parse(readFileSync('public/ma250-scan-preview.json','utf8'));
 scan.rows=[{...scan.rows.find((r:any)=>r.kind==='breakout'),volume_ratio:null}];scan.total=1;scan.market.stale=true;
 scan.coverage={ready:2,insufficient:1,quality_blocked:1,invalid:0};
 await page.route('**/ma250-scan-preview.json',route=>route.fulfill({json:scan}));
 await page.setViewportSize({width:1000,height:850});await page.goto('/');
 await page.getByRole('button',{name:'年线信号'}).click();
 await expect(page.getByText('突破·观察',{exact:true})).toBeVisible();
 await expect(page.getByText('量能待核',{exact:true})).toBeVisible();
 await expect(page.getByText('待更新',{exact:true})).toBeVisible();
 await expect(page.getByText(/历史不足 1 只 · 窗口不可用 1 只/)).toBeVisible();
 await expect(page.getByRole('button',{name:'刷新扫描'})).toBeEnabled();
});
