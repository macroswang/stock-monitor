import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

const scan=JSON.parse(readFileSync('public/ma250-scan-preview.json','utf8'));
const stocks=[
 ['sh603938','三孚股份','29.56','31.17','31.70','29.46'],
 ['sz000981','山子高科','2.18','2.25','2.26','2.18'],
 ['sz002106','莱宝高科','8.99','9.24','9.38','8.98'],
 ['sh600714','金瑞矿业','13.68','14.24','14.48','13.48'],
 ['sz300364','中文在线','27.73','27.13','28.11','26.24'],
 ['sh603533','掌阅科技','28.88','29.55','30.50','28.47'],
 ['sz002639','雪人集团','14.42','15.23','15.29','14.38'],
];

async function setup(page:Page,failFirst=false){
 await page.addInitScript(({stocks,scan,failFirst})=>{
  const w=window as any,clone=(x:any)=>JSON.parse(JSON.stringify(x));
  const watch=stocks.map(([code,name,price,previous_close,high,low],i)=>({code,name,enabled:1,health:'非交易时段 · 已刷新缓存',candidates:[],
   quote:{code,name,price,previous_close,high,low,change:String((+price/+previous_close-1)*100),timestamp:'2026-11-13T16:14:58+08:00'},
   broker_sources:i<2?[{account_id:'fixture',broker_name:'测试账户',account_masked:'123***001',active:true}]:[]}));
  const rows=[{...scan.rows[0],code:'sh600392',name:'盛和资源'},
   {...scan.rows[0],code:'sh600392',name:'盛和资源',date:'2026-10-15'},
   {...scan.rows[0],code:'sh603533',name:'掌阅科技'}];
  const snapshot={watch,events:[],config:{monitor:true,trading_paused:true},now:'2026-11-13T16:14:58+08:00',market_open:false,data_dir:'/tmp/isolated-watch-ui',rule:'fixture'};
  let fail=failFirst,jobNumber=0;const jobs=new Map<string,{code:string;reads:number}>();w.__watchCalls=[];
  Object.assign(w,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
   metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
   async invoke(command:string,params:any){
    if(command!=='rpc')return command==='plugin:autostart|is_enabled'?false:0;
    const {method,args={}}=params;w.__watchCalls.push({method,args});
    switch(method){
     case 'snapshot':return clone(snapshot);
     case 'ma250_scan_start':return clone({...scan,rows,total:rows.length,filtered_total:rows.length,universe:args.universe});
     case 'add_job':{const job='add-'+(++jobNumber);jobs.set(job,{code:args.code,reads:0});return {job};}
     case 'job':{
      const job=jobs.get(args.job);if(!job)return {status:'done',result:null};
      if(job.reads++===0)return {status:'running'};
      jobs.delete(args.job);
      if(fail){fail=false;return {status:'failed',error:'测试行情暂不可用'};}
      if(!watch.some(s=>s.code===job.code))watch.push({...clone(watch[0]),code:job.code,name:'盛和资源',broker_sources:[]});
      return {status:'done',result:{code:job.code,name:'盛和资源'}};
     }
     case 'market':case 'market_overview':case 'index_minute':return {quotes:[],minute:null};
     case 'breadth':case 'option_pcr':return {days:[],running:false,error:''};
     case 'index_technical':return {daily:[],weekly:[],running:false,error:''};
     case 'csi300':case 'sources':return null;
     case 'sector_flow':return {snapshot:null,running:false,error:''};
     case 'chart':return [];
     case 'history':return {code:args.code,daily:[],days:[],events:[],source:{},minute_days:[]};
     case 'minute_ensure':case 'daily_load':return {job:'empty'};
     case 'paper_chart':return {points:[]};
     case 'trading_chart':return {code:args.code,day:args.day,accounts:[],points:[]};
     case 'volume_flow':return {code:args.code,day:args.day,status:'unavailable',minutes:[],message:''};
     case 'events':case 'messages':return {items:[],total:0};
     default:throw Error('未授权测试调用 '+method);
    }
   }
  }});
 },{stocks,scan,failFirst});
 await page.goto('/');await expect(page.getByRole('heading',{name:'我的自选',exact:true})).toBeVisible();
}

test('annual signals add a stock once, synchronize duplicate rows and appear in watchlist',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await setup(page);
 await page.getByRole('button',{name:'年线信号',exact:true}).click();
 await expect(page.getByRole('button',{name:'掌阅科技 已在自选',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'盛和资源 加入自选',exact:true}).first().click();
 await expect(page.getByRole('button',{name:'盛和资源 正在加入自选',exact:true})).toHaveCount(2);
 await expect(page.locator('tr.ma250-expand')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'盛和资源 已在自选',exact:true})).toHaveCount(2);
 await expect(page.getByRole('button',{name:'盛和资源 已在自选',exact:true}).first()).toBeDisabled();
 expect(await page.evaluate(()=>(window as any).__watchCalls.filter((c:any)=>c.method==='add_job'))).toEqual([{method:'add_job',args:{code:'sh600392'}}]);
 await page.screenshot({path:'outputs/annual-watch-added.png',fullPage:true});
 await page.getByRole('button',{name:'自选监控',exact:true}).click();
 await expect(page.locator('.stocks .stock').filter({hasText:'盛和资源'})).toHaveCount(1);
 await expect(page.locator('.watchlist .card-heading')).toContainText('8 只');
 expect(errors).toEqual([]);
});

test('a failed annual addition reports the error and allows a retry',async({page})=>{
 await setup(page,true);await page.getByRole('button',{name:'年线信号',exact:true}).click();
 await page.getByRole('button',{name:'盛和资源 加入自选',exact:true}).first().click();
 await expect(page.getByRole('alert')).toContainText('加入自选失败 · 盛和资源：测试行情暂不可用');
 await expect(page.getByRole('button',{name:'盛和资源 加入自选',exact:true}).first()).toBeEnabled();
 await page.getByRole('button',{name:'盛和资源 加入自选',exact:true}).first().click();
 await expect(page.getByRole('button',{name:'盛和资源 已在自选',exact:true})).toHaveCount(2);
 await expect(page.getByRole('alert')).toHaveCount(0);
});

test('compact watch rows keep identity, origin, metrics and status in their requested positions',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await setup(page);
 const card=page.locator('.watchlist');
 for(const width of [1380,1000]){
  await page.setViewportSize({width,height:980});
  await expect(card.locator('.stock')).toHaveCount(7);
  for(const row of await card.locator('.stock').all()){
   const boxes=await row.evaluate(el=>{
    const rect=(selector:string)=>{const node=el.querySelector(selector)!;const r=node.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,font:parseFloat(getComputedStyle(node).fontSize),marginTop:parseFloat(getComputedStyle(node).marginTop),marginBottom:parseFloat(getComputedStyle(node).marginBottom),overflow:node.scrollWidth>node.clientWidth+1};};
    return {name:rect('.watch-stock-title>strong'),code:rect('.watch-stock-title>small'),source:rect('.trading-source'),metrics:rect('.watch-quote-details'),right:rect('.stock-right'),price:rect('.stock-right>strong'),status:rect('.stock-right>small'),values:[...el.querySelectorAll('.watch-metric strong')].map((_,i)=>rect(`.watch-metric:nth-child(${i+1}) strong`)),labels:[...el.querySelectorAll('.watch-metric>span')].map((_,i)=>rect(`.watch-metric:nth-child(${i+1})>span`)),row:el.getBoundingClientRect().toJSON()};
   });
   expect(boxes.name.overflow).toBe(false);
   expect(boxes.code.x-boxes.name.right).toBeCloseTo(5,1);
   expect(Math.abs((boxes.code.y+boxes.code.height/2)-(boxes.name.y+boxes.name.height/2))).toBeLessThan(1);
   expect(boxes.source.bottom+3).toBeLessThanOrEqual(boxes.name.y);
   expect(boxes.source.marginTop).toBe(3);expect(boxes.source.marginBottom).toBe(3);
   expect(Math.abs((boxes.price.y+boxes.status.bottom)/2-(boxes.row.y+boxes.row.height/2))).toBeLessThan(1);
   expect(boxes.metrics.x).toBeGreaterThan(boxes.code.right);
   expect(boxes.metrics.right).toBeLessThanOrEqual(boxes.right.x+1);
   expect(boxes.row.height).toBeLessThanOrEqual(36);
   expect(boxes.name.font).toBe(11);
   expect(boxes.code.font).toBe(6);expect(boxes.source.font).toBe(6);
   expect(boxes.price.font).toBe(9);expect(boxes.status.font).toBe(6);
   for(let i=0;i<3;i++){
    expect(boxes.values[i].font).toBe(8);expect(boxes.labels[i].font).toBe(6);
    expect(boxes.values[i].overflow).toBe(false);
    expect(boxes.values[i].y).toBe(boxes.values[0].y);
    expect(boxes.labels[i].y).toBe(boxes.labels[0].y);
    expect(boxes.labels[i].y).toBeGreaterThanOrEqual(boxes.values[i].bottom);
    if(i>0)expect(boxes.values[i].x).toBeGreaterThan(boxes.values[i-1].x);
   }
  }
  await expect(card.getByLabel('涨跌额').first()).toContainText('-1.61');
  await expect(card.getByLabel('涨跌幅').first()).toContainText('-5.17%');
  await card.screenshot({path:`outputs/watchlist-dense-${width}.png`});
 }
 await page.locator('.stocks .stock').filter({hasText:'中文在线'}).click();
 await expect(page.locator('.detail h2')).toContainText('中文在线');
 expect(errors).toEqual([]);
});
