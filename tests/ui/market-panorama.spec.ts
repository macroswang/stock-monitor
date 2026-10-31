import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.clock.install({time:new Date('2026-10-31T13:00:00Z')});});

test('国内指数全景与数据缺失状态，保留市场历史',async({page})=>{
 await page.goto('/?panel=breadth&sample=csi300');
 const view=page.getByRole('region',{name:'市场全景'});
 await expect(view.getByRole('img',{name:'上证当日分时涨跌幅'})).toBeVisible();
 await expect(view.getByRole('img',{name:'创业板当日分时涨跌幅'})).toBeVisible();
 await expect(view.getByText('2026-10-30 · 截至 15:00').first()).toBeVisible();
 await expect(view.getByText('暂无可核对的盘中异动',{exact:false})).toBeVisible();
 await expect(view.getByText('相关自选股：',{exact:false})).toBeVisible();
 await expect(page.getByText('恒生指数',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('region',{name:'市场趋势图'})).toBeVisible();
});

test('事件可选择并显示同来源板块采样曲线',async({page})=>{
 const points=[{time:'2026-10-30T10:00:00+08:00',change:0,net:100},{time:'2026-10-30T10:06:00+08:00',change:0.4,net:200}];
 await page.route('**/sector-intraday-preview.json',route=>route.fulfill({json:{date:'2026-10-30',events:[{code:'BK0001',name:'演示行业',time:points[1].time,start:points[0].time,label:'启动观察',change:.4,net:100}],series:{BK0001:{name:'演示行业',points}},status:'测试样本'}}));
 await page.goto('/?panel=breadth&sample=csi300');
 const view=page.getByRole('region',{name:'市场全景'});
 const event=view.getByRole('button',{name:/演示行业/}).first();await expect(event).toBeVisible();await event.click();
 await expect(view.getByLabel('选择板块')).toHaveValue('0:BK0001');
 await expect(view.getByRole('img',{name:'板块涨跌幅和资金采样走势'})).toBeVisible();
 await expect(view.getByText('2 个采样点',{exact:false})).toBeVisible();
});

test('新浪板块成分与自选匹配后可跳转个股',async({page})=>{
 await page.route('**/sector-members-preview.json',route=>route.fulfill({json:{new_ljhy:{collected_at:'2026-10-31T10:00:00+08:00',members:[{code:'sh603002',name:'宏昌电子'}]}}}));
 await page.goto('/?panel=breadth&sample=csi300');
 const view=page.getByRole('region',{name:'市场全景'});
 const match=view.getByRole('button',{name:'宏昌电子'});await expect(match).toBeVisible();await match.click();
 await expect(page.getByRole('heading',{name:'自选监控'})).toBeVisible();
 await expect(page.getByRole('heading',{name:/宏昌电子/})).toBeVisible();
});

test('成分股报价显示覆盖和来源时间，不冒充板块资金',async({page})=>{
 await page.goto('/?panel=breadth&sample=csi300');
 const panel=page.getByRole('region',{name:'板块详情'});
 await expect(panel.getByText('成分股：上涨',{exact:false})).toBeVisible();
 await expect(panel.getByText('覆盖 32/33',{exact:false})).toBeVisible();
 await expect(panel.getByText('腾讯报价 2026-10-30',{exact:false})).toBeVisible();
 await expect(panel.getByText('新浪快照未提供板块统计时间',{exact:false})).toBeVisible();
});

test('示例模式可以查看异动和曲线，退出后不混入真实数据',async({page})=>{
 await page.goto('/?panel=breadth&sample=csi300');
 const panel=page.getByRole('region',{name:'市场全景'});
 await expect(panel.getByText('暂无可核对的盘中异动',{exact:false})).toBeVisible();
 await panel.getByRole('button',{name:'查看效果示例'}).click();
 await expect(panel.getByText('以下板块异动和板块详情为虚构示例',{exact:false})).toBeVisible();
 await expect(panel.getByRole('button',{name:/半导体.*启动观察/})).toBeVisible();
 await expect(panel.getByRole('button',{name:/医药.*持续走强/})).toBeVisible();
 await panel.getByRole('button',{name:/医药.*持续走强/}).click();
 await expect(panel.getByLabel('选择板块')).toHaveValue('demo:1');
 await expect(panel.getByRole('img',{name:'板块涨跌幅和资金采样走势'})).toBeVisible();
 await expect(panel.getByText('示例模式不匹配真实自选股',{exact:false})).toBeVisible();
 await panel.getByRole('button',{name:'返回真实数据'}).click();
 await expect(panel.getByText('暂无可核对的盘中异动',{exact:false})).toBeVisible();
 await expect(panel.getByText('以下板块异动和板块详情为虚构示例',{exact:false})).toHaveCount(0);
});
