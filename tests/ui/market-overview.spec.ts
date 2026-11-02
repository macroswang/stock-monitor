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
 await home.getByText('数据详情',{exact:true}).click();
 await expect(home.getByText('新浪概念资金流',{exact:false})).toBeVisible();
 await expect(home.getByText('融资融券',{exact:true})).toBeVisible();
 await expect(home.getByText('概念之间可有重叠',{exact:false})).toBeVisible();
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

test('transient minute errors and transport failures retain a labelled chart, then recover',async({page})=>{
 const market=JSON.parse(await readFile('public/market-overview-preview.json','utf8'));
 await page.goto('/?sample=csi300');const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('2026-10-30 · 截至 15:00',{exact:true})).toBeVisible();
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:{...market,error:'上证分时暂时不可用'}}));
 await page.clock.fastForward(15500);
 await expect(home.getByText('2026-10-30 · 截至 15:00 · 缓存',{exact:true})).toBeVisible();
 await page.unroute('**/market-overview-preview.json');await page.route('**/market-overview-preview.json',route=>route.abort());
 await page.clock.fastForward(15500);
 await expect(home.getByText('2026-10-30 · 截至 15:00 · 缓存',{exact:true})).toBeVisible();
 await expect(home.getByText('分时数据暂不可用')).toHaveCount(0);
 await page.unroute('**/market-overview-preview.json');await page.route('**/market-overview-preview.json',route=>route.fulfill({json:market}));
 await page.clock.fastForward(15500);await expect(home.getByText('2026-10-30 · 截至 15:00',{exact:true})).toBeVisible();
});

test('pending next-minute label is withheld while confirmed index history stays visible',async({page})=>{
 const market=JSON.parse(await readFile('public/market-overview-preview.json','utf8'));
 market.quotes=market.quotes.map((q:any)=>({...q,timestamp:'2026-10-30T10:30:20+08:00'}));
 market.minute.bars=market.minute.bars.filter((b:any)=>b.time<='10:31');
 market.minute.cached_at='2026-10-30T10:30:20+08:00';market.collected_at='2026-10-30T10:30:20+08:00';
 await page.clock.setFixedTime(new Date(market.collected_at));
 await page.route('**/market-overview-preview.json',route=>route.fulfill({json:market}));
 await page.goto('/?sample=csi300');const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('2026-10-30 · 截至 10:30',{exact:true})).toBeVisible();
 await expect(home.getByText('分时数据暂不可用')).toHaveCount(0);
});

test('sector transport failure preserves prior values as delayed data, and expiry is visibly cached',async({page})=>{
 const sector=JSON.parse(await readFile('public/sector-flow-preview.json','utf8'));
 await page.goto('/?sample=csi300');const panel=page.getByRole('region',{name:'行业资金观察'});
 await expect(panel.getByText('酿酒行业',{exact:true})).toBeVisible();
 await page.route('**/sector-flow-preview.json',route=>route.abort());
 await page.clock.fastForward(5500);
 await expect(panel.getByText('酿酒行业',{exact:true})).toBeVisible();await expect(panel).toContainText('延迟');
 await page.unroute('**/sector-flow-preview.json');
 await page.route('**/sector-flow-preview.json',route=>route.fulfill({json:{snapshot:null,cached_snapshot:sector.snapshot,stale:true,error:'已过期',refresh_seconds:30}}));
 await page.clock.fastForward(5500);await expect(panel.getByText('酿酒行业',{exact:true})).toBeVisible();
 await expect(panel.getByText('更新延迟',{exact:true})).toBeVisible();
 await panel.getByText('数据详情',{exact:true}).click();
 await expect(panel).toContainText('当前为上次快照');
 await expect(panel).not.toContainText('可先观察');
});

test('partial sector coverage is explicit and missing outflow is not described as no outflow',async({page})=>{
 const sector=JSON.parse(await readFile('public/sector-flow-preview.json','utf8'));
 sector.snapshot={...sector.snapshot,verified_count:39,total:48,excluded_count:9,outflow:[]};
 await page.route('**/sector-flow-preview.json',route=>route.fulfill({json:sector}));
 await page.goto('/?sample=csi300');const panel=page.getByRole('region',{name:'行业资金观察'});
 await expect(panel.getByText('部分数据',{exact:true})).toBeVisible();
 await expect(panel.getByText('暂无数据',{exact:true})).toBeVisible();
 await expect(panel.getByText('39 / 48',{exact:true})).not.toBeVisible();
 await panel.getByText('数据详情',{exact:true}).click();
 await expect(panel.getByText('39 / 48',{exact:true})).toBeVisible();
 await expect(panel).not.toContainText('当前没有符合方向');await expect(panel).not.toContainText('可先观察');
});

test('technical page notes stay collapsed while current data status stays visible',async({page})=>{
 await page.goto('/?sample=csi300');
 await expect(page.getByText('模拟成交：B买 / S卖',{exact:false})).toHaveCount(0);
 await expect(page.getByText('白字彩底为已确认形态',{exact:false})).toHaveCount(0);
 await expect(page.getByText('仅展示已核对板块',{exact:false})).toHaveCount(0);
 const home=page.getByRole('region',{name:'首页市场趋势'});
 await expect(home.getByText('日期推定',{exact:true})).toBeVisible();
 await expect(home.locator('.info-note').first()).not.toHaveAttribute('open','');
 await expect(home.getByText('新浪行业资金流',{exact:true})).not.toBeVisible();
 await home.getByText('数据详情',{exact:true}).click();
 await expect(home.getByText('新浪行业资金流',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'大盘广度',exact:true}).click();
 const breadth=page.getByRole('region',{name:'市场趋势图'});
 await expect(breadth).toBeVisible();
 const notes=page.locator('.info-note:visible');expect(await notes.count()).toBeGreaterThanOrEqual(2);
 for(const note of await notes.all())await expect(note).not.toHaveAttribute('open','');
});
