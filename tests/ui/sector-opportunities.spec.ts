import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

test.beforeEach(async({page})=>{await page.clock.install({time:new Date('2026-10-31T10:00:00Z')});});

test('显示可核对的行业、概念和独立外围报价',async({page})=>{
 await page.goto('/?panel=breadth&sample=csi300');
 const panel=page.getByRole('region',{name:'板块机会观察'});
 await expect(panel.getByText('酿酒行业',{exact:true})).toBeVisible();
 await expect(panel.getByText('白酒概念',{exact:true})).toBeVisible();
 await expect(panel.getByText('新浪行业资金流',{exact:false})).toBeVisible();
 await expect(panel.getByText('日期推定',{exact:false}).first()).toBeVisible();
 await expect(panel.getByText('纳斯达克',{exact:true})).toBeVisible();
 await expect(panel.getByText('纽约黄金',{exact:true})).toBeVisible();
 await expect(panel.getByText('时区与延迟未核实',{exact:false})).toBeVisible();
 await expect(panel.getByText('2026-10-30 17:15:59',{exact:true})).toBeVisible();
 await expect(page.getByRole('region',{name:'市场趋势图'})).toBeVisible();
});

test('筛选条件可解释，缺失外围报价不伪造佐证',async({page})=>{
 const industry=JSON.parse(await readFile('public/sector-flow-preview.json','utf8'));
 industry.snapshot.inflow=[{code:'A',name:'电子信息',net_yuan:100000000,change_percent:1.5},{code:'B',name:'流入跌板块',net_yuan:200000000,change_percent:-1}];
 industry.snapshot.measure='大单及超大单净额';industry.snapshot.date_inferred=false;industry.snapshot.quote_time='2026-10-30T15:00:00+08:00';
 await page.route('**/sector-flow-preview.json',route=>route.fulfill({json:industry}));
 await page.route('**/external-market-preview.json',route=>route.fulfill({json:{snapshot:null,error:'',running:false}}));
 await page.goto('/?panel=breadth&sample=csi300');
 const panel=page.getByRole('region',{name:'板块机会观察'});
 await expect(panel.getByText('电子信息',{exact:true})).toBeVisible();
 await expect(panel.getByText('大单净流入',{exact:false}).first()).toBeVisible();
 await expect(panel.getByText('流入但未上涨：流入跌板块。')).toBeVisible();
 await expect(panel.getByText('外围行情暂不可用。')).toBeVisible();
 await expect(panel.getByText('外围对照',{exact:false})).toHaveCount(0);
});

test('外围对照保留来源时间并不改变板块筛选',async({page})=>{
 const industry=JSON.parse(await readFile('public/sector-flow-preview.json','utf8'));
 industry.snapshot.inflow=[{code:'A',name:'电子信息',net_yuan:100000000,change_percent:1.5}];
 await page.route('**/sector-flow-preview.json',route=>route.fulfill({json:industry}));
 await page.goto('/?panel=breadth&sample=csi300');
 const panel=page.getByRole('region',{name:'板块机会观察'});
 await expect(panel.getByText('外围对照：纳斯达克 -2.86%',{exact:false})).toBeVisible();
 await expect(panel.getByText('2026-10-30 17:15:59',{exact:true})).toBeVisible();
 await expect(panel.getByText('时间未对齐时不合并判断',{exact:false})).toBeVisible();
});
