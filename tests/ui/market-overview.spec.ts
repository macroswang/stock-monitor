import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

test.beforeEach(async({page})=>{await page.clock.install({time:new Date('2026-10-31T08:00:00Z')});});

test('首页展示当前行情与行业概念，历史对比留在大盘广度',async({page})=>{
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('3599.02')).toBeVisible();
 await expect(home.getByText('10833.78')).toBeVisible();
 await expect(home.getByText('2413.63')).toBeVisible();
 await expect(home.getByText('指数下跌、个股跌多涨少', {exact:false})).toBeVisible();
 await expect(home.getByText('2026-10-30 · 截至 15:00')).toBeVisible();
 await expect(home.getByText('酿酒行业',{exact:true})).toBeVisible();
 await expect(home.getByText('日期推定',{exact:false})).toBeVisible();
 await home.getByRole('button',{name:'概念',exact:true}).click();
 await expect(home.getByText('新浪概念资金流',{exact:false})).toBeVisible();
 await expect(home.getByText('融资融券',{exact:true})).toBeVisible();
 await expect(home.getByText('概念板块可能重叠',{exact:false})).toBeVisible();
 await expect(page.getByRole('region',{name:'首页市场判断'})).toHaveCount(0);
 await expect(home.getByRole('button',{name:'30日'})).toHaveCount(0);
 await home.getByRole('button',{name:'查看大盘广度'}).click();
 await expect(page.getByRole('region',{name:'市场趋势图'})).toBeVisible();
 await expect(page.getByRole('region',{name:'市场趋势图'}).getByRole('button',{name:'30日'})).toBeVisible();
});

test('缺失或不一致的数据不生成操作建议',async({page})=>{
 const market=JSON.parse(await readFile('public/market-overview-preview.json','utf8'));
 market.quotes[0].price=Number(market.quotes[0].price)+100;
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:market}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('行情暂不可用').first()).toBeVisible();
 await expect(home.getByText('市场数据暂未同步，先等待更新。')).toBeVisible();
 await expect(home.getByText('分时数据暂不可用')).toBeVisible();
 await expect(home.getByText('暂缓加仓',{exact:false})).toHaveCount(0);
});

test('未来采集的缓存不能冒充当前行情',async({page})=>{
 const market=JSON.parse(await readFile('public/market-overview-preview.json','utf8'));
 market.collected_at='2026-11-01T09:00:00+08:00';
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:market}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('行情暂不可用').first()).toBeVisible();
 await expect(home.getByText('市场数据暂未同步，先等待更新。')).toBeVisible();
});

test('盘中快照同步才给出判断，过期后不继续使用',async({page})=>{
 const capture=JSON.parse(await readFile('fixtures/market-core-rpc-20261030.json','utf8'));
 await page.clock.setFixedTime(new Date(capture.finished_at));
 const market={quotes:[capture.quote],minute:null,error:'',collected_at:capture.finished_at};
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:market}));
 await page.route('**/breadth-csi300-preview.json',route=>route.fulfill({json:{days:[capture.day],running:false,error:''}}));
 await page.goto('/?sample=csi300');
 const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('盘中采样',{exact:false})).toBeVisible();
 await expect(home.getByText('指数下跌、个股跌多涨少',{exact:false})).toBeVisible();
 await page.clock.setFixedTime(new Date(Date.parse(capture.finished_at)+8*60*1000));
 await page.reload();
 await expect(home.getByText('市场数据暂未同步，先等待更新。')).toBeVisible();
 await expect(home.getByText('盘中采样',{exact:false})).toHaveCount(0);
});
