import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

async function setup(page:Page,failFirst=false){
 const scan=JSON.parse(readFileSync('public/ma250-scan-preview.json','utf8'));
 await page.addInitScript(({scan,failFirst})=>{
  const w=window as any,clone=(v:any)=>JSON.parse(JSON.stringify(v));let repaired=false,fail=failFirst,jobReads=0;
  w.__qualityCalls=[];
  Object.assign(w,{isTauri:true,__TAURI_EVENT_PLUGIN_INTERNALS__:{unregisterListener(){}},__TAURI_INTERNALS__:{
   metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback(){},
   async invoke(command:string,params:any){
    if(command!=='rpc')return command==='plugin:autostart|is_enabled'?false:'0.6.104';
    const {method,args={}}=params;w.__qualityCalls.push({method,args});
    switch(method){
     case 'snapshot':return {watch:[],events:[],config:{monitor:true,trading_paused:true},now:'2026-11-13T16:15:00+08:00',market_open:false,rule:'fixture'};
     case 'ma250_scan_start':{
      await new Promise(resolve=>setTimeout(resolve,100));
      return clone({...scan,universe:args.universe,codes:3,scanned:repaired?3:2,
       coverage:{ready:repaired?3:2,insufficient:0,quality_blocked:repaired?0:1,invalid:0},
       data_issues:repaired?[]:[{code:'sz300118',name:'东方日升',state:'quality_blocked',bars:511,minimum_bars:310,
        reasons:['2025-11-14至2026-10-12间隔332天，超过45天'],suggestion:'补齐后重新计算指标和历史信号。',
        repair_ranges:[{start:'2025-11-15',end:'2026-10-11',kind:'gap'}]}]});
     }
     case 'daily_load':jobReads=0;return {job:'repair'};
     case 'job':
      if(jobReads++<2)return {status:'running'};
      if(fail){fail=false;return {status:'failed',error:'测试来源暂不可用'};}
      repaired=true;return {status:'done',result:['2025-11-17','2025-11-18']};
     case 'market':case 'market_overview':case 'index_minute':return {quotes:[],minute:null};
     case 'breadth':case 'option_pcr':return {days:[],running:false,error:''};
     case 'index_technical':return {daily:[],weekly:[],running:false,error:''};
     case 'csi300':case 'sources':return null;
     case 'sector_flow':return {snapshot:null,running:false,error:''};
     case 'events':case 'messages':return {items:[],total:0};
     default:throw Error('未授权测试调用 '+method);
    }
   }
  }});
 },{scan,failFirst});
 await page.goto('/');await page.getByRole('button',{name:'年线信号',exact:true}).click();
 await expect(page.locator('.ma250-coverage summary')).toContainText('1只待核');
}

test('data issues are folded by default and never trigger an automatic repair',async({page})=>{
 await setup(page);await expect(page.locator('.ma250-coverage-body')).toBeHidden();
 expect(await page.evaluate(()=>(window as any).__qualityCalls.filter((c:any)=>c.method==='daily_load'))).toEqual([]);
 await page.locator('.ma250-coverage summary').click();
 await expect(page.locator('.ma250-data-item')).toContainText('东方日升');
 await expect(page.locator('.ma250-data-item')).toContainText('332天');
 await expect(page.locator('.ma250-coverage-body')).toContainText('补齐日线会重算指标和历史信号');
});

test('manual gap repair uses only its missing interval and refreshes the current scope',async({page})=>{
 await setup(page);await page.locator('.ma250-coverage summary').click();
 await page.getByRole('button',{name:'补缺口',exact:true}).click();
 await expect(page.getByRole('button',{name:'补充中…',exact:true})).toBeDisabled();
 await page.getByLabel('扫描范围').selectOption('watch');
 await expect(page.locator('.ma250-repair-status')).toContainText('补入2根日线');
 await expect(page.locator('.ma250-coverage')).toHaveCount(0);
 const calls=await page.evaluate(()=>(window as any).__qualityCalls);
 expect(calls.filter((c:any)=>c.method==='daily_load')).toEqual([{method:'daily_load',args:{code:'sz300118',start:'2025-11-15',end:'2026-10-11'}}]);
 expect(calls.filter((c:any)=>c.method==='ma250_scan_start').at(-1).args.universe).toBe('watch');
 expect(calls.some((c:any)=>/order|trading|config|add_job/.test(c.method))).toBe(false);
});

test('failed repair keeps diagnostics visible and permits a retry',async({page})=>{
 await setup(page,true);await page.locator('.ma250-coverage summary').click();
 await page.getByRole('button',{name:'补缺口',exact:true}).click();
 await expect(page.locator('.ma250-repair-status')).toContainText('测试来源暂不可用');
 await expect(page.getByRole('button',{name:'补缺口',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'补缺口',exact:true}).click();
 await expect(page.locator('.ma250-repair-status')).toContainText('补入2根日线');
 await expect(page.locator('.ma250-coverage')).toHaveCount(0);
});
