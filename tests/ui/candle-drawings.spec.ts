import {test,expect,type Page,type Locator} from '@playwright/test';
import {drawingDate,drawingDocument,type DrawingDocument} from '../../src/candleDrawingModel';

const tools=(page:Page)=>page.getByRole('group',{name:'手工画线工具',exact:true});
const chart=(page:Page)=>page.locator('.market-grid>.detail>.chart-shell>.chart');
const layer=(page:Page)=>page.locator('.market-grid>.detail>.chart-shell>.candle-drawings');
const items=(page:Page)=>layer(page).getByTestId('manual-drawing');
async function boot(page:Page){
 await page.addInitScript(()=>localStorage.setItem('stock-monitor-linked-minute-open','false'));
 await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
}
async function grid(page:Page){
 return chart(page).evaluate(async(el)=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),g=c.getModel().getComponent('grid',0).coordinateSystem.getRect(),r=el.getBoundingClientRect();
  return {x:r.x+g.x,y:r.y+g.y,width:g.width,height:g.height};
 });
}
async function drag(page:Page,kind:'画线段'|'画矩形',start=[.25,.65],end=[.65,.35]){
 const g=await grid(page);await tools(page).getByRole('button',{name:kind,exact:true}).click();
 await page.mouse.move(g.x+g.width*start[0],g.y+g.height*start[1]);await page.mouse.down();
 await page.mouse.move(g.x+g.width*end[0],g.y+g.height*end[1],{steps:20});await page.mouse.up();
 await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
}
async function saved(page:Page,frame='daily'):Promise<DrawingDocument>{
 return page.evaluate(frame=>JSON.parse(localStorage.getItem(`stock-monitor-drawings-preview-v1:sh603002:${frame}`)||'{"revision":0,"items":[]}'),frame);
}

test('segments and rectangles persist after reload, stay isolated by stock/period, and support delete/undo',async({page})=>{
 await boot(page);await drag(page,'画线段');await expect(items(page)).toHaveCount(1);
 await drag(page,'画矩形',[.35,.25],[.75,.55]);await expect(items(page)).toHaveCount(2);
 const original=await saved(page);expect(original.items.map(d=>d.kind)).toEqual(['line','rect']);
 await page.reload();await page.getByRole('button',{name:'日K',exact:true}).click();await expect(items(page)).toHaveCount(2);
 expect(await saved(page)).toEqual(original);
 await page.locator('.stock').filter({hasText:'海优新材'}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();await expect(items(page)).toHaveCount(0);
 await page.locator('.stock').filter({hasText:'宏昌电子'}).click();await expect(items(page)).toHaveCount(2);
 await page.getByRole('button',{name:'周K',exact:true}).click();await expect(items(page)).toHaveCount(0);
 await drag(page,'画线段');expect((await saved(page,'weekly')).items).toHaveLength(1);expect((await saved(page)).items).toHaveLength(2);
 await page.getByRole('button',{name:'日K',exact:true}).click();await expect(items(page)).toHaveCount(2);
 const line=items(page).filter({has:page.locator('line.drawing-hit')}).first();
 // Select using a real pointer at the line midpoint (not its bounding-box corner).
 const linePoints=await line.locator('line.drawing-hit').evaluate(el=>{const l=el as SVGLineElement,r=el.closest('svg')!.getBoundingClientRect();return {x:r.x+(l.x1.baseVal.value+l.x2.baseVal.value)/2,y:r.y+(l.y1.baseVal.value+l.y2.baseVal.value)/2};});
 await page.mouse.click(linePoints.x,linePoints.y);await expect(tools(page).getByRole('button',{name:'删除选中画线',exact:true})).toBeEnabled();
 await tools(page).getByRole('button',{name:'删除选中画线',exact:true}).click();await expect(items(page)).toHaveCount(1);
 await tools(page).getByRole('button',{name:'撤销上次画线操作',exact:true}).click();await expect(items(page)).toHaveCount(2);
 await page.mouse.move(0,0);await page.screenshot({path:'docs/candle-drawings-20261116/basic-drawings.png',fullPage:true});
});

test('drawing does not mutate chart series, writes once on release, and follows zoom/resize data coordinates',async({page})=>{
 await boot(page);
 await page.evaluate(()=>{const w=window as any;w.__drawingWrites=0;const set=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key.startsWith('stock-monitor-drawings-preview-v1:'))w.__drawingWrites++;return set.call(this,key,value);};});
 const before=await chart(page).evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);return JSON.stringify(e.getInstanceByDom(el).getOption().series);});
 const g=await grid(page);await tools(page).getByRole('button',{name:'画线段',exact:true}).click();
 await page.mouse.move(g.x+g.width*.35,g.y+g.height*.65);await page.mouse.down();await page.mouse.move(g.x+g.width*.55,g.y+g.height*.45,{steps:100});
 expect(await page.evaluate(()=>(window as any).__drawingWrites)).toBe(0);
 await page.mouse.up();await expect(items(page)).toHaveCount(1);await expect.poll(()=>page.evaluate(()=>(window as any).__drawingWrites)).toBe(1);
 const after=await chart(page).evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);return JSON.stringify(e.getInstanceByDom(el).getOption().series);});expect(after).toBe(before);
 const document=await saved(page);
 for(const width of [1100,1600]){
  await page.setViewportSize({width,height:1080});await page.getByRole('button',{name:'放大K线',exact:true}).click();
  await expect.poll(async()=>{
   const expected=await chart(page).evaluate(async(el,item)=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el);return item.points.map(p=>c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[p.date,p.price]));},document.items[0]);
   const actual=await items(page).first().locator('line.drawing-shape').evaluate(el=>{const l=el as SVGLineElement;return [[l.x1.baseVal.value,l.y1.baseVal.value],[l.x2.baseVal.value,l.y2.baseVal.value]];});
   return Math.max(...actual.flatMap((p,i)=>p.map((v,j)=>Math.abs(v-expected[i][j]))));
  }).toBeLessThan(.1);
 }
 expect(await saved(page)).toEqual(document);
});

test('storage failures remain visibly unsaved and retries preserve the final drawing',async({page})=>{
 await boot(page);
 await page.evaluate(()=>{const w=window as any;w.__failDrawingSave=true;const set=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key.startsWith('stock-monitor-drawings-preview-v1:')&&w.__failDrawingSave)throw Error('磁盘不可用');return set.call(this,key,value);};});
 const g=await grid(page);await tools(page).getByRole('button',{name:'画矩形',exact:true}).click();await page.mouse.move(g.x+g.width*.25,g.y+g.height*.3);await page.mouse.down();await page.mouse.move(g.x+g.width*.6,g.y+g.height*.6,{steps:8});await page.mouse.up();
 await expect(tools(page).getByRole('alert')).toContainText('保存状态未确认');await expect(tools(page).getByRole('status')).toHaveText('未保存');expect((await saved(page)).items).toHaveLength(0);
 await page.evaluate(()=>(window as any).__failDrawingSave=false);await tools(page).getByRole('button',{name:'重试保存',exact:true}).click();
 await expect(tools(page).getByRole('status')).toHaveText('1 / 200');expect((await saved(page)).items).toHaveLength(1);
});

test('weekly coordinates use a stable Monday and reject corrupted persisted documents',()=>{
 const row={date:'2026-11-16',open:'10',close:'11',high:'12',low:'9',volume:'100'};
 expect(drawingDate(row,'weekly')).toBe('2026-11-16');expect(drawingDate({...row,date:'2026-11-20'},'weekly')).toBe('2026-11-16');
 expect(()=>drawingDocument({revision:0,items:[{id:'a',kind:'line',points:[{date:'2026-02-30',price:1},{date:'2026-11-20',price:2}]}]})).toThrow();
});

test('selected endpoints and shapes can move, Escape cancels drafts, and normal keyboard zoom remains available',async({page})=>{
 await boot(page);await drag(page,'画线段');
 let old=await saved(page);
 const end=await items(page).first().locator('.drawing-handle').first().evaluate(el=>{const c=el as SVGCircleElement,r=el.closest('svg')!.getBoundingClientRect();return {x:r.x+c.cx.baseVal.value,y:r.y+c.cy.baseVal.value};});
 await page.mouse.move(end.x,end.y);await page.mouse.down();await page.mouse.move(end.x+20,end.y-10,{steps:5});await page.mouse.up();
 await expect.poll(async()=>(await saved(page)).revision).toBe(old.revision+1);let next=await saved(page);
 expect(next.items[0].points[0]).not.toEqual(old.items[0].points[0]);expect(next.items[0].points[1]).toEqual(old.items[0].points[1]);
 old=next;
 const mid=await items(page).first().locator('line.drawing-hit').evaluate(el=>{const l=el as SVGLineElement,r=el.closest('svg')!.getBoundingClientRect();return {x:r.x+(l.x1.baseVal.value+l.x2.baseVal.value)/2,y:r.y+(l.y1.baseVal.value+l.y2.baseVal.value)/2};});
 await page.mouse.move(mid.x,mid.y);await page.mouse.down();await page.mouse.move(mid.x+30,mid.y+10,{steps:5});await page.mouse.up();
 await expect.poll(async()=>(await saved(page)).revision).toBe(old.revision+1);next=await saved(page);
 expect(next.items[0].points[0]).not.toEqual(old.items[0].points[0]);expect(next.items[0].points[1]).not.toEqual(old.items[0].points[1]);
 const g=await grid(page);await tools(page).getByRole('button',{name:'画矩形',exact:true}).click();
 await page.mouse.move(g.x+g.width*.3,g.y+g.height*.3);await page.mouse.down();await page.mouse.move(g.x+g.width*.7,g.y+g.height*.7,{steps:5});await page.keyboard.press('Escape');await page.mouse.up();
 await expect(items(page)).toHaveCount(1);expect(await saved(page)).toEqual(next);
 await chart(page).focus();await page.keyboard.press('ArrowDown');expect(await saved(page)).toEqual(next);
});

test('a stale chart reloads the competing version instead of overwriting annotations',async({page})=>{
 await boot(page);await drag(page,'画线段');const doc=await saved(page);
 const external={...doc,revision:doc.revision+1,items:[...doc.items,{...doc.items[0],id:'another-view'}]};
 await page.evaluate(value=>localStorage.setItem('stock-monitor-drawings-preview-v1:sh603002:daily',JSON.stringify(value)),external);
 await drag(page,'画矩形',[.4,.25],[.7,.55]);
 await expect(tools(page).getByRole('alert')).toContainText('画线版本已变化');expect(await saved(page)).toEqual(external);
 await expect(items(page)).toHaveCount(2);await expect(items(page).filter({has:page.locator('rect.drawing-shape')})).toHaveCount(0);
});

test('200 annotations do not cause saves, reloads or ECharts setOption calls while moving the pointer',async({page})=>{
 await page.addInitScript(()=>{
  const drawings=Array.from({length:200},(_,i)=>({id:'line'+i,kind:'line',points:[{date:'2026-10-15',price:15},{date:'2026-10-16',price:18}]}));
  localStorage.setItem('stock-monitor-drawings-preview-v1:sh603002:daily',JSON.stringify({revision:1,items:drawings}));
 });
 await boot(page);await expect(items(page)).toHaveCount(200);
 await chart(page).evaluate(async el=>{
  const w=window as any;w.__drawingWrites=0;w.__drawingReads=0;w.__chartOptionCalls=0;
  const set=Storage.prototype.setItem,get=Storage.prototype.getItem;
  Storage.prototype.setItem=function(key,value){if(key.startsWith('stock-monitor-drawings-'))w.__drawingWrites++;return set.call(this,key,value);};
  Storage.prototype.getItem=function(key){if(key.startsWith('stock-monitor-drawings-'))w.__drawingReads++;return get.call(this,key);};
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),option=c.setOption.bind(c);
  c.setOption=(...args:any[])=>{w.__chartOptionCalls++;return option(...args);};
 });
 const g=await grid(page);await page.mouse.move(g.x+g.width*.15,g.y+g.height*.2);await page.mouse.move(g.x+g.width*.7,g.y+g.height*.6,{steps:60});
 const counts=await page.evaluate(()=>({writes:(window as any).__drawingWrites,reads:(window as any).__drawingReads,options:(window as any).__chartOptionCalls}));
 expect(counts).toEqual({writes:0,reads:0,options:0});
 await tools(page).getByRole('button',{name:'画线段',exact:true}).click();await page.mouse.move(g.x+g.width*.3,g.y+g.height*.4);await page.mouse.down();await page.mouse.up();
 await expect(tools(page).getByRole('alert')).toContainText('最多200个');await expect(items(page)).toHaveCount(200);
});

async function harness(page:Page){
 await page.route('**/drawing-harness',r=>r.fulfill({contentType:'text/html',body:`<!doctype html><div id="root"></div><script type="module">import {injectIntoGlobalHook} from '/@react-refresh';injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;await import('/tests/ui/fixtures/drawingHarness.tsx');</script>`}));
 await page.goto('/drawing-harness');
}

test('a late drawing read cannot populate a different stock',async({page})=>{
 await page.addInitScript(()=>{
  (window as any).__holdDrawings={chart_drawings:'sh603002'};
  localStorage.setItem('stock-monitor-drawings-preview-v1:sh603002:daily',JSON.stringify({revision:1,items:[{id:'savedA',kind:'line',points:[{date:'2026-10-15',price:15},{date:'2026-10-16',price:18}]}]}));
 });
 await harness(page);await page.getByRole('button',{name:'股票B',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await page.evaluate(()=>{const w=window as any;w.__holdDrawings={};for(const task of w.__drawingReleases)task.resolve();});
 await expect(items(page)).toHaveCount(0);
 await page.getByRole('button',{name:'股票A',exact:true}).click();await expect(items(page)).toHaveCount(1);
});

test('a delayed save finishing after stock switching appears in the newly reopened chart',async({page})=>{
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await page.evaluate(()=>(window as any).__holdDrawings={chart_drawings_save:'sh603002'});
 const g=await grid(page);await tools(page).getByRole('button',{name:'画线段',exact:true}).click();
 await page.mouse.move(g.x+g.width*.25,g.y+g.height*.7);await page.mouse.down();await page.mouse.move(g.x+g.width*.65,g.y+g.height*.4,{steps:8});await page.mouse.up();
 await expect(tools(page).getByRole('status')).toHaveText('保存中…');
 await page.getByRole('button',{name:'股票B',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'股票A',exact:true}).click();await expect(tools(page).getByRole('status')).toHaveText('未保存');await expect(items(page)).toHaveCount(1);expect((await saved(page)).items).toHaveLength(0);
 await page.evaluate(()=>{const w=window as any;w.__holdDrawings={};for(const task of w.__drawingReleases)task.resolve();});
 await expect(items(page)).toHaveCount(1);expect((await saved(page)).items).toHaveLength(1);
});

test('line color and width can be set before drawing, edited on selection, persisted and undone',async({page})=>{
 await boot(page);
 const color=tools(page).getByLabel('线段颜色',{exact:true});
 await color.fill('#ff4d4f');await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('3');
 await drag(page,'画线段');let doc=await saved(page);
 expect(doc.items[0].color).toBe('#ff4d4f');expect(doc.items[0].width).toBe(3);
 await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke','rgb(255, 77, 79)');await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width','3px');
 await color.fill('#4d96ff');await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('6');
 expect(await saved(page)).toEqual(doc);
 await tools(page).getByRole('button',{name:'应用选中线段样式',exact:true}).click();
 await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke','rgb(77, 150, 255)');await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width','6px');
 await expect.poll(async()=>(await saved(page)).revision).toBe(doc.revision+1);doc=await saved(page);
 await tools(page).getByRole('button',{name:'撤销上次画线操作',exact:true}).click();
 await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke','rgb(255, 77, 79)');await expect(color).toHaveValue('#ff4d4f');
 await color.fill('#4d96ff');await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('6');await tools(page).getByRole('button',{name:'应用选中线段样式',exact:true}).click();
 await expect.poll(async()=>(await saved(page)).revision).toBe(doc.revision+2);doc=await saved(page);
 await page.reload();await page.getByRole('button',{name:'日K',exact:true}).click();await expect(items(page)).toHaveCount(1);expect(await saved(page)).toEqual(doc);
 await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke','rgb(77, 150, 255)');await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width','6px');
 await page.mouse.move(0,0);await page.screenshot({path:'docs/candle-drawings-20261116/line-styles.png',fullPage:true});
});

test('a save notification received during a slow read is applied after that read completes',async({page})=>{
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await page.evaluate(()=>{const w=window as any;w.__captureDrawingReads=true;w.__holdDrawings={chart_drawings:'sh603002'};});
 await page.getByRole('button',{name:'股票B',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'股票A',exact:true}).click();await expect(tools(page).getByRole('status')).toContainText('读取中');
 await page.evaluate(()=>{
  const doc={revision:1,items:[{id:'external',kind:'line',color:'#1122ff',width:4,points:[{date:'2026-10-15',price:15},{date:'2026-10-16',price:18}]}]};
  localStorage.setItem('stock-monitor-drawings-preview-v1:sh603002:daily',JSON.stringify(doc));
  window.dispatchEvent(new CustomEvent('stock-monitor-chart-drawings-changed',{detail:{code:'sh603002',frame:'daily',origin:'another-chart'}}));
  const w=window as any;w.__holdDrawings={};w.__drawingReleases.forEach((task:any)=>task.resolve());
 });
 await expect(items(page)).toHaveCount(1);
});

test('a failed save completed after switching away can be recovered with its style on return',async({page})=>{
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await tools(page).getByLabel('线段颜色',{exact:true}).fill('#ff1234');await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('4');
 await page.evaluate(()=>(window as any).__holdDrawings={chart_drawings_save:'sh603002'});
 const g=await grid(page);await tools(page).getByRole('button',{name:'画线段',exact:true}).click();await page.mouse.move(g.x+g.width*.3,g.y+g.height*.7);await page.mouse.down();await page.mouse.move(g.x+g.width*.6,g.y+g.height*.4,{steps:5});await page.mouse.up();
 await expect(tools(page).getByRole('status')).toHaveText('保存中…');await page.getByRole('button',{name:'股票B',exact:true}).click();
 await page.evaluate(()=>{const w=window as any;w.__failDrawingMethod='chart_drawings_save';w.__holdDrawings={};w.__drawingReleases.forEach((task:any)=>task.resolve());});
 await page.getByRole('button',{name:'股票A',exact:true}).click();
 await expect(tools(page).getByRole('button',{name:'重试保存',exact:true})).toBeVisible();
 await page.evaluate(()=>(window as any).__failDrawingMethod='');await tools(page).getByRole('button',{name:'重试保存',exact:true}).click();
 await expect(tools(page).getByRole('status')).toHaveText('1 / 200');const doc=await saved(page);expect(doc.items[0].color).toBe('#ff1234');expect(doc.items[0].width).toBe(4);
});


test('failed operations survive reload and cannot overwrite a newer saved version',async({page})=>{
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await tools(page).getByLabel('线段颜色',{exact:true}).fill('#1234ff');await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('6');
 await page.evaluate(()=>(window as any).__failDrawingMethod='chart_drawings_save');
 const g=await grid(page);await tools(page).getByRole('button',{name:'画线段',exact:true}).click();await page.mouse.move(g.x+g.width*.3,g.y+g.height*.7);await page.mouse.down();await page.mouse.move(g.x+g.width*.6,g.y+g.height*.4);await page.mouse.up();
 await expect(tools(page).getByRole('button',{name:'重试保存',exact:true})).toBeVisible();
 await page.reload();await expect(tools(page).getByRole('button',{name:'重试保存',exact:true})).toBeVisible();
 await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width','6px');await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke','rgb(18, 52, 255)');
 const remote={revision:1,items:[{id:'remote',kind:'rect',points:[{date:'2026-10-15',price:15},{date:'2026-10-16',price:18}]}]};
 await page.evaluate(doc=>localStorage.setItem('stock-monitor-drawings-preview-v1:sh603002:daily',JSON.stringify(doc)),remote);
 await tools(page).getByRole('button',{name:'重试保存',exact:true}).click();await expect(tools(page).getByRole('alert')).toContainText('版本已变化');expect(await saved(page)).toEqual(remote);
 await expect(items(page).locator('rect.drawing-shape')).toHaveCount(1);await expect(items(page).locator('line.drawing-shape')).toHaveCount(0);
});

test('notifications during a gesture do not clear its document and stale completion conflicts safely',async({page})=>{
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 const g=await grid(page);await tools(page).getByRole('button',{name:'画线段',exact:true}).click();await page.mouse.move(g.x+g.width*.3,g.y+g.height*.7);await page.mouse.down();await page.mouse.move(g.x+g.width*.6,g.y+g.height*.4);
 const remote={revision:1,items:[{id:'remote',kind:'rect',points:[{date:'2026-10-15',price:15},{date:'2026-10-16',price:18}]}]};
 await page.evaluate(doc=>{localStorage.setItem('stock-monitor-drawings-preview-v1:sh603002:daily',JSON.stringify(doc));window.dispatchEvent(new CustomEvent('stock-monitor-chart-drawings-changed',{detail:{code:'sh603002',frame:'daily',origin:'external'}}));},remote);
 await page.mouse.up();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();expect(await saved(page)).toEqual(remote);await expect(items(page).locator('rect.drawing-shape')).toHaveCount(1);
});


for(const frame of ['daily','weekly'] as const)test(`${frame} anchors track zoom/pan, resized grids and prepended history without drift`,async({page})=>{
 await harness(page);if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();
 await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();await drag(page,'画线段',[.55,.6],[.8,.4]);await drag(page,'画矩形',[.5,.3],[.75,.7]);
 const document=await saved(page,frame);
 const check=async()=>{
  await expect.poll(async()=>{
   const expected=await chart(page).evaluate(async(el,{document,frame})=>{
    const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),dates=c.getOption().xAxis[0].data;
    const week=(s:string)=>{const d=new Date(s+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));return d.toISOString().slice(0,10);};
    return document.items.map(item=>item.points.map(p=>c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[dates.findIndex((d:string)=>(frame==='weekly'?week(d):d)===p.date),p.price])));
   },{document,frame});
   const actual=await items(page).evaluateAll(elements=>elements.map(el=>{
    const l=el.querySelector('.drawing-shape')!;
    if(l.tagName==='line'){const a=l as SVGLineElement;return [[a.x1.baseVal.value,a.y1.baseVal.value],[a.x2.baseVal.value,a.y2.baseVal.value]];}
    const r=l as SVGRectElement;return [[r.x.baseVal.value,r.y.baseVal.value],[r.x.baseVal.value+r.width.baseVal.value,r.y.baseVal.value+r.height.baseVal.value]];
   }));
   return Math.max(...actual.flatMap((points,i)=>points.flatMap((p,j)=>p.map((v,k)=>Math.abs(v-(i===1?Math[j===0?'min':'max'](...expected[i].map(q=>q[k])):expected[i][j][k]))))));
  }).toBeLessThan(.1);
 };
 await check();await page.getByRole('button',{name:'补充历史',exact:true}).click();await check();
 for(const window of [[20,90],[40,100],[0,100]]){
  await chart(page).evaluate(async(el,window)=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);e.getInstanceByDom(el).dispatchAction({type:'dataZoom',start:window[0],end:window[1]});},window);
  await check();
 }
 await page.setViewportSize({width:1100,height:900});await check();
 if(frame==='weekly'){await page.getByRole('button',{name:'更新本周',exact:true}).click();await check();await page.getByRole('button',{name:'更新本周',exact:true}).click();await check();}
 expect(await saved(page,frame)).toEqual(document);
});

test('a committed save with a lost reply is recognized on reload without another write',async({page})=>{
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await page.evaluate(()=>{const set=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){set.call(this,key,value);if(key.startsWith('stock-monitor-drawings-preview-v1:'))throw Error('提交后应答丢失');};});
 const g=await grid(page);await tools(page).getByRole('button',{name:'画线段',exact:true}).click();await page.mouse.move(g.x+g.width*.3,g.y+g.height*.7);await page.mouse.down();await page.mouse.move(g.x+g.width*.6,g.y+g.height*.4);await page.mouse.up();
 await expect(tools(page).getByRole('button',{name:'重试保存',exact:true})).toBeVisible();const committed=await saved(page);expect(committed.revision).toBe(1);
 await page.reload();await expect(tools(page).getByRole('status')).toHaveText('1 / 200');expect(await saved(page)).toEqual(committed);
 expect(await page.evaluate(()=>localStorage.getItem('stock-monitor-drawings-recovery-v1:sh603002:daily'))).toBeNull();
});


test('a newer in-memory recovery supersedes a stale disk copy when WebKit storage is full',async({page})=>{
 await harness(page);
 const result=await page.evaluate(async()=>{
  const {writeRecovery,readRecovery,clearRecovery}=await import('/src/candleDrawingRecovery.ts');
  const old={id:'old',revision:0,items:[],undo:false},next={...old,id:'new',revision:1};
  writeRecovery('sz000001','daily',old);
  const set=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('QuotaExceededError');};
  writeRecovery('sz000001','daily',next);Storage.prototype.setItem=set;
  const recovered=readRecovery('sz000001','daily');clearRecovery('sz000001','daily','old');const afterStaleAck=readRecovery('sz000001','daily');
  clearRecovery('sz000001','daily','new');return {recovered,afterStaleAck,cleared:readRecovery('sz000001','daily')};
 });
 expect(result.recovered?.id).toBe('new');expect(result.afterStaleAck?.id).toBe('new');expect(result.cleared).toBeNull();
});

test('endpoint handles disappear on chart blur, outside pointer and window blur, with no storage writes',async({page})=>{
 await boot(page);await tools(page).getByLabel('线段颜色',{exact:true}).fill('#1234ff');await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('4');await drag(page,'画线段');
 const handles=items(page).locator('.drawing-handle');await expect(handles).toHaveCount(2);const doc=await saved(page);
 await expect(handles.first()).toBeVisible();await tools(page).getByLabel('线段宽度',{exact:true}).focus();await expect(handles).toHaveCount(0);
 // A toolbar edit must retain its selected target even though the handles hide.
 await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('6');await tools(page).getByRole('button',{name:'应用选中线段样式',exact:true}).click();await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width','6px');
 const selectLine=async()=>{const p=await items(page).locator('line.drawing-hit').evaluate(el=>{const l=el as SVGLineElement,r=el.closest('svg')!.getBoundingClientRect();return {x:r.x+(l.x1.baseVal.value+l.x2.baseVal.value)/2,y:r.y+(l.y1.baseVal.value+l.y2.baseVal.value)/2};});await page.mouse.click(p.x,p.y);await expect(handles).toHaveCount(2);};
 await selectLine();await page.getByRole('heading',{name:'我的自选',exact:true}).click();await expect(handles).toHaveCount(0);
 await selectLine();await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await expect(handles).toHaveCount(0);
 const after=await saved(page);expect(after.revision).toBe(doc.revision+1);expect(after.items[0].points).toEqual(doc.items[0].points);
 await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke','rgb(18, 52, 255)');await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width','6px');
});

for(const frame of ['daily','weekly'] as const)test(`${frame} rectangle border style can be created, edited, reloaded and undone`,async({page})=>{
 await harness(page);if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画矩形',exact:true})).toBeEnabled();
 await tools(page).getByRole('button',{name:'画矩形',exact:true}).click();await expect(tools(page).getByLabel('矩形边框颜色',{exact:true})).toBeEnabled();
 await tools(page).getByLabel('矩形边框颜色',{exact:true}).fill('#ff1234');await tools(page).getByLabel('矩形边框宽度',{exact:true}).selectOption('4');
 const g=await grid(page);await page.mouse.move(g.x+g.width*.3,g.y+g.height*.3);await page.mouse.down();await page.mouse.move(g.x+g.width*.65,g.y+g.height*.6,{steps:10});await page.mouse.up();
 const shape=items(page).locator('rect.drawing-shape');await expect(shape).toHaveCSS('stroke','rgb(255, 18, 52)');await expect(shape).toHaveCSS('stroke-width','4px');
 let doc=await saved(page,frame);expect(doc.items[0].color).toBe('#ff1234');expect(doc.items[0].width).toBe(4);const points=doc.items[0].points;
 await tools(page).getByLabel('矩形边框颜色',{exact:true}).fill('#1234ff');await tools(page).getByLabel('矩形边框宽度',{exact:true}).selectOption('6');await tools(page).getByRole('button',{name:'应用选中矩形样式',exact:true}).click();
 await expect(shape).toHaveCSS('stroke','rgb(18, 52, 255)');await expect(shape).toHaveCSS('stroke-width','6px');
 await tools(page).getByRole('button',{name:'撤销上次画线操作',exact:true}).click();await expect(shape).toHaveCSS('stroke','rgb(255, 18, 52)');await expect(shape).toHaveCSS('stroke-width','4px');
 await tools(page).getByLabel('矩形边框颜色',{exact:true}).fill('#1234ff');await tools(page).getByLabel('矩形边框宽度',{exact:true}).selectOption('6');await tools(page).getByRole('button',{name:'应用选中矩形样式',exact:true}).click();await expect(shape).toHaveCSS('stroke-width','6px');doc=await saved(page,frame);
 await page.reload();if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();await expect(shape).toHaveCSS('stroke','rgb(18, 52, 255)');await expect(shape).toHaveCSS('stroke-width','6px');expect(await saved(page,frame)).toEqual(doc);expect(doc.items[0].points).toEqual(points);await expect(items(page).locator('.drawing-handle')).toHaveCount(0);
 await tools(page).getByRole('button',{name:'画矩形',exact:true}).click();await expect(tools(page).getByLabel('矩形边框颜色',{exact:true})).toHaveValue('#1234ff');await expect(tools(page).getByLabel('矩形边框宽度',{exact:true})).toHaveValue('6');
});

for(const frame of ['daily','weekly'] as const)test(`${frame} close cancels armed mode and unfinished line/rectangle without changing saved drawings`,async({page})=>{
 await harness(page);if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();
 const close=tools(page).getByRole('button',{name:'关闭画线',exact:true});await expect(close).toBeDisabled();await expect(tools(page).getByRole('button',{name:'浏览K线',exact:true})).toHaveCount(0);
 await drag(page,'画线段');const original=await saved(page,frame);await expect(close).toBeDisabled();
 for(const kind of ['画线段','画矩形'] as const){
  await tools(page).getByRole('button',{name:kind,exact:true}).click();await expect(close).toBeEnabled();await close.click();await expect(close).toBeDisabled();await expect(layer(page)).not.toHaveClass(/is-drawing/);
  await tools(page).getByRole('button',{name:kind,exact:true}).click();const g=await grid(page);
  await page.mouse.move(g.x+g.width*.35,g.y+g.height*.3);await page.mouse.down();await page.mouse.move(g.x+g.width*.7,g.y+g.height*.6,{steps:8});await expect(items(page)).toHaveCount(2);
  // Activate the real close button by keyboard while the drawing pointer is
  // still held; releasing it afterwards must not submit the cancelled draft.
  await close.focus();await page.keyboard.press('Enter');await expect(items(page)).toHaveCount(1);await expect(close).toBeDisabled();await page.mouse.up();
  await expect(layer(page)).not.toHaveClass(/is-drawing/);expect(await saved(page,frame)).toEqual(original);await expect(items(page).locator('.drawing-handle')).toHaveCount(0);
 }
 await page.reload();if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();await expect(items(page)).toHaveCount(1);expect(await saved(page,frame)).toEqual(original);
});

test('close during an existing shape drag restores its saved coordinates',async({page})=>{
 await boot(page);await drag(page,'画线段');const original=await saved(page);
 const mid=await items(page).locator('line.drawing-hit').evaluate(el=>{const l=el as SVGLineElement,r=el.closest('svg')!.getBoundingClientRect();return {x:r.x+(l.x1.baseVal.value+l.x2.baseVal.value)/2,y:r.y+(l.y1.baseVal.value+l.y2.baseVal.value)/2};});
 await page.mouse.move(mid.x,mid.y);await page.mouse.down();await page.mouse.move(mid.x+30,mid.y+25,{steps:5});const close=tools(page).getByRole('button',{name:'关闭画线',exact:true});await expect(close).toBeEnabled();await close.focus();await page.keyboard.press('Enter');await page.mouse.up();await expect(close).toBeDisabled();expect(await saved(page)).toEqual(original);
 await expect(tools(page).getByRole('button',{name:'删除选中画线',exact:true})).toBeDisabled();await expect(items(page)).toHaveCount(1);
});

test('hover-only chart renders reuse the existing drawing geometry',async({page},info)=>{
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();const g=await grid(page);
 await page.mouse.move(0,0);
 await chart(page).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),original=c.convertToPixel.bind(c),w=window as any;
  w.__geometryConversions=0;w.__hoverRenders=0;c.on('rendered',()=>w.__hoverRenders++);c.convertToPixel=(...args:any[])=>{w.__geometryConversions++;return original(...args);};
 });
 await page.mouse.move(g.x+g.width*.2,g.y+g.height*.4);await page.mouse.move(g.x+g.width*.8,g.y+g.height*.5,{steps:60});await page.mouse.move(0,0);
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 const result=await page.evaluate(()=>({conversions:(window as any).__geometryConversions,renderEvents:(window as any).__hoverRenders}));
 await (await import('node:fs/promises')).writeFile(`docs/candle-drawings-performance-20261116/hover-${process.env.DRAWING_PERF_PHASE||'after'}.json`,JSON.stringify(result,null,2));
 expect(result.renderEvents).toBeGreaterThan(10);expect(result.conversions).toBe(0);
});

test('dragging one of 200 drawings only reprojects the edited drawing',async({page})=>{
 await page.addInitScript(()=>{
  const items=Array.from({length:200},(_,i)=>({id:'perf'+i,kind:i%2?'rect':'line',points:[{date:'2026-01-05',price:9+i*.001},{date:'2026-01-08',price:10+i*.001}]}));
  localStorage.setItem('stock-monitor-drawings-preview-v1:sh603002:daily',JSON.stringify({revision:1,items}));
 });
 await harness(page);await expect(items(page)).toHaveCount(200);
 const hit=items(page).filter({has:page.locator('rect.drawing-hit')}).last().locator('rect.drawing-hit');
 const p=await hit.evaluate(el=>{const a=el as SVGRectElement,r=el.closest('svg')!.getBoundingClientRect();return {x:r.x+a.x.baseVal.value+a.width.baseVal.value/2,y:r.y+a.y.baseVal.value};});
 await page.mouse.move(p.x,p.y);await page.mouse.down();await expect(items(page).locator('.drawing-handle')).toHaveCount(2);
 const before=await saved(page);
 await page.evaluate(()=>{const w=window as any,original=Map.prototype.get;w.__staticDateLookups=0;Map.prototype.get=function(key){if(key==='2026-01-05'||key==='2026-01-08')w.__staticDateLookups++;return original.call(this,key);};});
 await page.mouse.move(p.x+35,p.y-25,{steps:40});await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 const lookups=await page.evaluate(()=>(window as any).__staticDateLookups);
 await (await import('node:fs/promises')).writeFile(`docs/candle-drawings-performance-20261116/drag-${process.env.DRAWING_PERF_PHASE||'after'}.json`,JSON.stringify({staticDateLookups:lookups,shapes:200,pointerSteps:40},null,2));
 // Release/cancel only after measuring the live preview. No write is allowed.
 await tools(page).getByRole('button',{name:'关闭画线',exact:true}).focus();await page.keyboard.press('Enter');await page.mouse.up();expect(await saved(page)).toEqual(before);expect(lookups).toBeLessThan(800);
});

test('switching stocks repeatedly does not accumulate drawing window/document listeners',async({page})=>{
 await page.addInitScript(()=>{
  const w=window as any,tracked=new Map<string,Set<any>>(),add=EventTarget.prototype.addEventListener,remove=EventTarget.prototype.removeEventListener;
  const key=(target:any,type:string,options:any)=>target===window||target===document?`${target===window?'window':'document'}:${type}:${typeof options==='boolean'?options:!!options?.capture}`:'';
  const types=new Set(['stock-monitor-chart-drawings-changed','beforeunload','blur','pointerdown']);
  EventTarget.prototype.addEventListener=function(type,callback,options){const k=types.has(type)?key(this,type,options):'';if(k){if(!tracked.has(k))tracked.set(k,new Set());tracked.get(k)!.add(callback);}return add.call(this,type,callback,options);};
  EventTarget.prototype.removeEventListener=function(type,callback,options){const k=types.has(type)?key(this,type,options):'';if(k)tracked.get(k)?.delete(callback);return remove.call(this,type,callback,options);};
  w.__drawingListenerCounts=()=>Object.fromEntries([...tracked].map(([k,set])=>[k,set.size]));
 });
 await harness(page);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 const original=await page.evaluate(()=>(window as any).__drawingListenerCounts());
 for(let i=0;i<8;i++)for(const name of ['股票B','股票A']){await page.getByRole('button',{name,exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();}
 const final=await page.evaluate(()=>(window as any).__drawingListenerCounts());expect(final).toEqual(original);
 await (await import('node:fs/promises')).writeFile('docs/candle-drawings-performance-20261116/listeners.json',JSON.stringify({stockSwitches:16,before:original,after:final},null,2));
});

// Compare every endpoint with the chart's current mapping, including dates
// that move to a different category index without changing the bar count.
async function checkDrawingProjection(page:Page,document:DrawingDocument,frame:'daily'|'weekly'){
 await expect(items(page)).toHaveCount(document.items.length);
 await expect.poll(async()=>{
  const expected=await chart(page).evaluate(async(el,{document,frame})=>{
   const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),dates=c.getOption().xAxis[0].data;
   const week=(s:string)=>{const d=new Date(s+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));return d.toISOString().slice(0,10);};
   return document.items.map(item=>item.points.map(p=>{const index=dates.findIndex((d:string)=>(frame==='weekly'?week(d):d)===p.date);return index<0?null:c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[index,p.price]);}));
  },{document,frame});
  const actual=await items(page).evaluateAll(elements=>elements.map(el=>{
   const s=el.querySelector('.drawing-shape')!;if(s.tagName==='line'){const l=s as SVGLineElement;return [[l.x1.baseVal.value,l.y1.baseVal.value],[l.x2.baseVal.value,l.y2.baseVal.value]];}
   const r=s as SVGRectElement;return [[r.x.baseVal.value,r.y.baseVal.value],[r.x.baseVal.value+r.width.baseVal.value,r.y.baseVal.value+r.height.baseVal.value]];
  }));
  if(expected.some(points=>points.some(p=>!p)))return Infinity;
  return Math.max(...actual.flatMap((points,i)=>points.flatMap((p,j)=>p.map((v,k)=>Math.abs(v-(document.items[i].kind==='rect'?Math[j===0?'min':'max'](...expected[i].map(q=>q![k])):expected[i][j]![k]))))));
 }).toBeLessThan(.1);
}

for(const frame of ['daily','weekly'] as const)test(`${frame} empty history disables stale geometry and recovers saved styles and anchors`,async({page})=>{
 await harness(page);if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();
 await tools(page).getByLabel('线段颜色',{exact:true}).fill('#1234ff');await tools(page).getByLabel('线段宽度',{exact:true}).selectOption('4');await drag(page,'画线段');await drag(page,'画矩形');const original=await saved(page,frame);await checkDrawingProjection(page,original,frame);
 await page.getByRole('button',{name:'切换空行情',exact:true}).click();await expect(items(page)).toHaveCount(0);await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeDisabled();await expect(tools(page).getByRole('status')).toContainText('等待K线');expect(await saved(page,frame)).toEqual(original);
 await page.getByRole('button',{name:'切换空行情',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();await checkDrawingProjection(page,original,frame);await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width','4px');expect(await saved(page,frame)).toEqual(original);
});

for(const frame of ['daily','weekly'] as const)test(`${frame} cached shapes follow replaced dates, price ranges, prepended history and external styles`,async({page})=>{
 await harness(page);if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();await drag(page,'画线段',[.35,.65],[.7,.4]);await drag(page,'画矩形',[.4,.3],[.65,.55]);const original=await saved(page,frame);
 await checkDrawingProjection(page,original,frame);
 await page.getByRole('button',{name:'等长更新行情',exact:true}).click();await checkDrawingProjection(page,original,frame);
 await page.getByRole('button',{name:'改变价格范围',exact:true}).click();await checkDrawingProjection(page,original,frame);
 await chart(page).evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);e.getInstanceByDom(el).dispatchAction({type:'dataZoom',start:25,end:85});});await checkDrawingProjection(page,original,frame);
 await page.getByRole('button',{name:'补充历史',exact:true}).click();await checkDrawingProjection(page,original,frame);expect(await saved(page,frame)).toEqual(original);
 const remote={revision:original.revision+1,items:original.items.map(item=>({...item,color:'#ff1234',width:6}))};
 await page.evaluate(({doc,frame})=>{localStorage.setItem(`stock-monitor-drawings-preview-v1:sh603002:${frame}`,JSON.stringify(doc));window.dispatchEvent(new CustomEvent('stock-monitor-chart-drawings-changed',{detail:{code:'sh603002',frame,origin:'another-view'}}));},{doc:remote,frame});
 for(const selector of ['line.drawing-shape','rect.drawing-shape']){await expect(items(page).locator(selector)).toHaveCSS('stroke','rgb(255, 18, 52)');await expect(items(page).locator(selector)).toHaveCSS('stroke-width','6px');}
 await checkDrawingProjection(page,remote,frame);expect(await saved(page,frame)).toEqual(remote);
});

for(const frame of ['daily','weekly'] as const)test(`${frame} a reused parent chart isolates identical drawing IDs across stocks`,async({page})=>{
 const fixture=JSON.parse(await (await import('node:fs/promises')).readFile('public/preview.json','utf8'));
 const a=fixture.history.sh603002.daily,b=fixture.history.sh688680.daily,common=a.filter((r:any)=>b.some((s:any)=>s.date===r.date)),left=common[Math.floor(common.length*.4)],right=common[Math.floor(common.length*.7)];
 const documents=['sh603002','sh688680'].map((code,i)=>({code,doc:{revision:1,items:[{id:'shared-id',kind:'line',color:i?'#ff1234':'#1234ff',width:i?6:4,points:[{date:drawingDate(left,frame),price:Number(fixture.history[code].daily.find((r:any)=>r.date===left.date).close)},{date:drawingDate(right,frame),price:Number(fixture.history[code].daily.find((r:any)=>r.date===right.date).close)}]}]}}));
 await page.addInitScript(({documents,frame})=>{(window as any).__reuseDrawingChart=true;for(const {code,doc} of documents)localStorage.setItem(`stock-monitor-drawings-preview-v1:${code}:${frame}`,JSON.stringify(doc));},{documents,frame});
 await harness(page);if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();
 for(const i of [0,1,0,1,0]){
  await page.getByRole('button',{name:i?'股票B':'股票A',exact:true}).click();await expect(items(page)).toHaveCount(1);
  await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke',i?'rgb(255, 18, 52)':'rgb(18, 52, 255)');await expect(items(page).locator('line.drawing-shape')).toHaveCSS('stroke-width',i?'6px':'4px');await checkDrawingProjection(page,documents[i].doc as DrawingDocument,frame);
 }
 const persisted=await page.evaluate(({documents,frame})=>documents.map(({code})=>JSON.parse(localStorage.getItem(`stock-monitor-drawings-preview-v1:${code}:${frame}`)!)),{documents,frame});expect(persisted).toEqual(documents.map(item=>item.doc));
});

for(const frame of ['daily','weekly'] as const)test(`${frame} history becoming empty during a gesture cancels its draft without writing`,async({page})=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await harness(page);if(frame==='weekly')await page.getByRole('button',{name:'切换周期',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();await drag(page,'画线段');const original=await saved(page,frame);
 const g=await grid(page);await tools(page).getByRole('button',{name:'画矩形',exact:true}).click();await page.mouse.move(g.x+g.width*.3,g.y+g.height*.3);await page.mouse.down();await page.mouse.move(g.x+g.width*.7,g.y+g.height*.6,{steps:8});await expect(items(page)).toHaveCount(2);
 // Trigger the real fixture's asynchronous-history replacement without first
 // releasing the captured drawing pointer.
 await page.getByRole('button',{name:'切换空行情',exact:true}).focus();await page.keyboard.press('Enter');await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeDisabled();await page.mouse.move(g.x+g.width*.6,g.y+g.height*.5);await page.mouse.up();expect(await saved(page,frame)).toEqual(original);
 await page.getByRole('button',{name:'切换空行情',exact:true}).click();await expect(tools(page).getByRole('button',{name:'画线段',exact:true})).toBeEnabled();await checkDrawingProjection(page,original,frame);expect(await saved(page,frame)).toEqual(original);expect(errors).toEqual([]);await expect(tools(page).getByRole('button',{name:'关闭画线',exact:true})).toBeDisabled();
});
