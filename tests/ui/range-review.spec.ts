import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {reachedPriceRange,cachedPriceRangeReference} from '../../src/pricePresentation';

const code='sh603002',day='2026-10-16';
function fixture(){
 const f=JSON.parse(readFileSync('public/preview.json','utf8'));
 f.snapshot.watch=[{code,name:'宏昌电子',enabled:1,quote:{code,price:'12',previous_close:'10',timestamp:day+'T10:29:00+08:00'},health:'测试',candidates:[]}];
 f.minutes[code][0].data={date:day,previous_close:'10',cached_at:day+'T10:30:00+08:00',bars:[{time:'10:29',close:'10',average:'10',volume:10000,complete:true}]};
 return f;
}
async function inspect(page:Page){
 return page.getByLabel('分时价格及分钟成交量',{exact:true}).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),o=c.getOption();
  return {id:el.getAttribute('_echarts_instance_'),range:c.getModel().getComponent('yAxis',0).axis.scale.getExtent(),price:o.series[0].data,average:o.series.find((s:any)=>s.name==='均价')?.data,averageWidth:o.series.find((s:any)=>s.name==='均价')?.lineStyle.width,marks:o.series[0].markPoint.data,updates:c.__reviewUpdates||0};
 });
}

test('a wrong-stock quote cannot expand the selected stock through its current price',async({page})=>{
 const f=fixture();f.snapshot.watch[0].quote.code='sz000981';await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');
 await expect.poll(async()=>(await inspect(page)).range).toEqual([9.9,10.1]);
});

test('a misleading date prefix cannot admit a quote from another Beijing date',async({page})=>{
 const f=fixture();f.snapshot.watch[0].quote.timestamp=day+'T00:30:00+14:00';await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');
 await expect.poll(async()=>(await inspect(page)).range).toEqual([9.9,10.1]);
});

test('conflicting cache dates cannot borrow a cumulative high even when trading_date matches',async({page})=>{
 const f=fixture();f.snapshot.watch[0].quote=null;Object.assign(f.minutes[code][0].data,{date:'2026-10-15',trading_date:day,symbol:'603002',day_high:'12',limit_reference_time:day+'T10:29:00+08:00'});
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');
 await expect.poll(async()=>(await inspect(page)).range).toEqual([9.9,10.1]);
});

test('same-price quote timestamp changes remove future bounds without recreating the chart',async({page})=>{
 await page.clock.install({time:new Date(day+'T10:32:00+08:00')});const f=fixture();let reads=0;
 await page.route('**/preview.json',r=>{reads++;return r.fulfill({json:f});});await page.goto('/');
 await expect.poll(async()=>(await inspect(page)).range).toEqual([8,12]);const before=await inspect(page);
 await page.getByLabel('分时价格及分钟成交量',{exact:true}).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),setOption=c.setOption.bind(c);c.__reviewUpdates=0;c.setOption=(...args:any[])=>{c.__reviewUpdates++;return setOption(...args);};
 });
 f.snapshot.watch[0].quote.timestamp=day+'T10:29:30+08:00';await page.clock.runFor(3300);await expect(page.locator('.detail-identity p')).toContainText('10:29:30');
 expect((await inspect(page)).updates).toBe(0);const readCount=reads;
 f.snapshot.watch[0].quote.timestamp=day+'T10:31:00+08:00';await page.clock.runFor(3300);await expect.poll(()=>reads).toBeGreaterThan(readCount);
 await expect.poll(async()=>(await inspect(page)).range).toEqual([9.9,10.1]);const after=await inspect(page);
 expect(after.id).toBe(before.id);expect(after.price).toEqual(before.price);expect(after.average).toEqual(before.average);expect(after.marks).toEqual(before.marks);
 expect(after.averageWidth).toBe(1);expect(after.updates).toBeGreaterThan(0);
});

test('range snapshots use the Beijing trading date and require unambiguous valid timestamps',()=>{
 const ref={code,day,timestamp:day+'T10:00:00+08:00',previousClose:10,high:11,low:9},cutoff=Date.parse(day+'T15:00:00+08:00');
 expect(reachedPriceRange({...ref,timestamp:day+'T00:30:00+14:00'},code,day,10,cutoff)).toEqual([]);
 expect(reachedPriceRange({...ref,timestamp:'2026-10-15T16:30:00Z'},code,day,10,cutoff)).toEqual([11,9]);
 expect(reachedPriceRange({...ref,timestamp:day+'T10:00:00'},code,day,10,cutoff)).toEqual([]);
 expect(reachedPriceRange(ref,code,day,10,NaN)).toEqual([]);
});

test('cached extrema preserve valid archived references and reject contradictory payload identity',()=>{
 const data={date:day,trading_date:day,symbol:'603002',previous_close:'10',day_high:'11',day_low:'9',limit_reference_time:day+'T16:00:00+08:00'};
 const reference=cachedPriceRangeReference(data,code,day);
 expect(reachedPriceRange(reference,code,day,10,Date.parse('2026-10-18T12:00:00+08:00'))).toEqual([11,9]);
 for(const changed of [{date:'2026-10-15'},{trading_date:'2026-10-15'},{symbol:'sz603002'},{symbol:'000981'},{date:undefined,trading_date:undefined}])expect(cachedPriceRangeReference({...data,...changed},code,day)).toBeUndefined();
});
