import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

async function fixture(page:Page){
 const data=JSON.parse(readFileSync('public/preview.json','utf8')),code='sh603002',history=data.history[code];
 const source=history.daily.at(-15),confirm=history.daily.at(-12),close=+confirm.close;
 const signal={key:'fixture-e2',date:confirm.date,source_date:source.date,source_high:close*.99,confirmation_day:3,
  close,ma250:close*.94,ma5:close*.97,distance_pct:6.38,stop:close*.9,research_only:true};
 history.e2={signals:[signal],research_only:true,rule_id:'fixture-e2',error:null};
 history.ma250={signals:[{date:source.date,close:+source.close,ma250:+source.close*.95,ma5:+source.close*.98,
  distance_pct:5.2,touch_date:history.daily.at(-20).date,touch_low:close*.9,touch_depth_pct:0,pullback_pct:12,
  stop:close*.89,strong:true,strong_reasons:[],market_above:true}],breakouts:[]};
 const scan=JSON.parse(readFileSync('public/ma250-scan-preview.json','utf8'));
 const formal={...scan.rows[0],date:source.date};
 scan.rows=[formal,{...formal,...signal,code,name:'宏昌电子',kind:'e2',strong:false,strong_reasons:[],quality:false}];
 scan.total=2;scan.trading_days=[source.date,confirm.date];
 await page.route('**/preview.json',route=>route.fulfill({json:data}));
 await page.route('**/ma250-scan-preview.json',route=>route.fulfill({json:scan}));
 await page.goto('/');
 return {signal,source};
}

async function markers(chart:any){
 return chart.evaluate(async(el:HTMLElement)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());
  const echarts=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  const option=echarts.getInstanceByDom(el).getOption();
  return Object.fromEntries(option.series.filter((s:any)=>['E2研究参考','年线回踩信号'].includes(s.name)).map((s:any)=>[s.name,{dates:s.data.map((p:any)=>p.value[0]),labels:s.data.map((p:any)=>p.label.formatter),silent:s.silent}]));
 });
}

test('daily markers stay enabled despite old preferences, hide controls and never enter minute or weekly charts',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{localStorage.setItem('stock-monitor-show-ma250-pullback-v1','false');localStorage.setItem('stock-monitor-show-e2-research-v1','false');});
 const {signal,source}=await fixture(page);
 await page.getByRole('button',{name:'日K',exact:true}).click();const chart=page.getByLabel('日K线及成交量');
 await expect.poll(async()=>(await markers(chart))['E2研究参考']?.dates).toEqual([signal.date]);
 expect((await markers(chart))['年线回踩信号'].dates).toEqual([source.date]);
 expect((await markers(chart))['E2研究参考'].labels).toEqual(['E2·研究参考']);
 expect((await markers(chart))['E2研究参考'].silent).toBe(true);
 const point=await chart.evaluate(async(el:HTMLElement,args:any)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text());const echarts=await import(source.match(/from "([^"]*echarts\.js[^"]*)"/)![1]);
  return echarts.getInstanceByDom(el).convertToPixel({xAxisIndex:0,yAxisIndex:0},[args.date,args.close]);
 },signal);
 const box=(await chart.boundingBox())!;await page.mouse.move(box.x+point[0],box.y+point[1]);
 await expect(chart.locator('.quote-tooltip')).toContainText('E2确认 · 研究参考');
 await expect(chart.locator('.quote-tooltip')).toContainText(signal.source_date);
 await expect(chart.locator('.quote-tooltip')).toContainText('不进入正式提醒或自动交易');
 await page.mouse.move(0,0);
 await page.screenshot({path:'outputs/e2-daily-research.png',fullPage:true});
 await expect(page.getByRole('checkbox',{name:'E2研究参考',exact:true})).toHaveCount(0);
 await expect(page.getByRole('checkbox',{name:'年线信号',exact:true})).toHaveCount(0);
 await expect(page.locator('.daily-pattern-controls')).not.toContainText('E2研究参考');
 await expect(page.locator('.daily-pattern-controls')).not.toContainText('收盘确认');
 await expect(page.locator('.daily-pattern-controls')).not.toContainText('年线信号');
 await page.getByRole('button',{name:'周K',exact:true}).click();
 expect((await markers(page.getByLabel('周K线及成交量')))['E2研究参考']).toBeUndefined();
 await page.getByRole('button',{name:'分时',exact:true}).click();
 const minute=await markers(page.getByLabel('分时价格及分钟成交量'));
 expect(minute['E2研究参考']).toBeUndefined();expect(minute['年线回踩信号']).toBeUndefined();
 await expect(page.locator('.daily-pattern-controls')).toHaveCount(0);
 expect(errors).toEqual([]);
});

test('annual E2 filter exposes research provenance and opens its confirmation-day chart',async({page})=>{
 const {signal}=await fixture(page);await page.getByRole('button',{name:'年线信号',exact:true}).click();
 await page.getByLabel('只看强回踩').check();
 await expect(page.locator('tr.ma250-signal-row')).toHaveCount(1);
 await page.getByLabel('信号类型').selectOption('e2');
 await expect(page.getByLabel('只看强回踩')).not.toBeChecked();
 await expect(page.getByLabel('只看强回踩')).toBeDisabled();
 const row=page.getByRole('row').filter({hasText:'E2·研究参考'});
 await expect(row).toHaveCount(1);await expect(row).toContainText(signal.date);
 await expect(row).toContainText('源强信号 '+signal.source_date);
 await expect(page.getByText('E2仅研究参考，不进入提醒或自动交易',{exact:false})).toBeVisible();
 await page.getByLabel('信号时间范围').selectOption('250');
 await expect(page.getByLabel('信号时间范围')).toHaveValue('250');
 await row.getByRole('button',{name:/展开.*E2·研究参考图表/}).click();
 const expand=page.locator('tr.ma250-expand');
 await expect(expand).toContainText('信号日 '+signal.date);
 await expect.poll(async()=>(await markers(expand.getByLabel('日K线及成交量')))['E2研究参考']?.dates).toEqual([signal.date]);
 await page.screenshot({path:'outputs/e2-annual-research.png',fullPage:true});
});
