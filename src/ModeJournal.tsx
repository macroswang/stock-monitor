import {useEffect, useState, type FormEvent} from 'react';
import './modeJournal.css';
import MarketOpportunity from './MarketOpportunity';
import type {BreadthDay} from './MarketBreadth';
import {breadthView} from './marketOverview';
import {requestWithTimeout} from './requestTimeout';

const templates = {
  '主线核心弱转强': '比较昨日分歧和今日同梯队表现。观察核心能否先于板块修复，并带动同方向个股。',
  '看高做低': '写出高位标杆与低位候选的业务关联，等待板块扩散和候选获得承接。',
  '首板与接力': '记录板块所处阶段、首板辨识度、换手和回封。跟风股退潮时重新评估。',
  '趋势回踩': '记录趋势依据、回踩支撑及恢复条件。持有期间用同一周期判断趋势是否破坏。',
  '恐慌后的反弹': '记录恐慌扩散是否已缓和、板块是否停止创新低、候选是否出现实际承接。单列反弹验证期限和再次走弱时的退出方案。',
  '隔夜交易': '记录尾盘确认、隔夜风险以及次日兑现窗口。次日按原计划检验。',
  '底仓做T': '写清可用底仓、往返成本、回补条件和失败处理，单独核算两腿。',
  '长期投资': '写出企业价值、估值与催化依据，用基本面证伪条件和投资期限复核。',
  '股息投资': '核对盈利和现金流能否覆盖分红，记录买入估值、分红可持续的前提及下次财报复核日。',
  '指数定投': '预先写下指数范围、投入频率、每期预算与资金使用期限。每个约定周期核对一次执行。',
  '组合再平衡': '记录各资产的目标权重、当前偏离、复核日期、费用和可调配资金，按原计划决定调整幅度。',
};
type Mode = keyof typeof templates;
type Stage = '等待'|'观察'|'试仓'|'确认'|'追加'|'减仓'|'失效待退出'|'退出'|'放弃'|'已复盘';
const transitions:Record<Stage, Stage[]> = {
  等待:['试仓','放弃'], 观察:['放弃'], 试仓:['确认','减仓','失效待退出','退出'],
  确认:['追加','减仓','失效待退出','退出'], 追加:['减仓','失效待退出','退出'],
  减仓:['失效待退出','退出'], 失效待退出:['退出'], 退出:['已复盘'], 放弃:['已复盘'], 已复盘:[],
};
type Plan = {mode:Mode; market:string; breadth?:string; evidence:string; theme:string; symbol:string; trigger:string;
  expectation:string; deadline:string; invalidation:string; sizing:string; budget:number};
type Entry = {id:string; step:number; at:string; stage:Stage; note:string; plan?:Plan};
let database:Promise<IDBDatabase>|undefined;
function openJournal() {
  if (!database) database = new Promise<IDBDatabase>((resolve,reject)=>{
    const req = indexedDB.open('guanliang-mode-journal',1);
    req.onupgradeneeded=()=>req.result.createObjectStore('entries',{keyPath:['id','step']});
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
  }).catch(error=>{database=undefined;throw error;});
  return database;
}
async function readEntries():Promise<Entry[]> {
  const db=await openJournal();
  return new Promise((resolve,reject)=>{
    const req=db.transaction('entries').objectStore('entries').getAll();
    req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
  });
}
async function append(entry:Entry) {
  const db=await openJournal();
  return new Promise<void>((resolve,reject)=>{
    const tx=db.transaction('entries','readwrite');
    tx.objectStore('entries').add(entry);
    tx.oncomplete=()=>resolve(); tx.onabort=()=>reject(tx.error);
  });
}
const stamp=(iso:string)=>new Date(iso).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
const fields = [
  ['evidence','市场依据','昨日强势股能否延续？热门板块的跌停是否扩散？'],
  ['theme','主线与参照标的','题材、核心股及与候选的关系'],
  ['symbol','候选标的','股票名称或代码'],
  ['trigger','入场确认','看到什么才参与？'],
  ['expectation','持有与追加条件','预期怎样发展？什么新证据出现才允许增加仓位？'],
  ['deadline','验证期限','例如次日开盘后首次分歧结束'],
  ['invalidation','失效与退出','哪些表现触发减仓或退出？无法成交如何处理？'],
  ['sizing','计划仓位','初始仓位和总仓位上限'],
] as const;

type BoardProps={onBreadth:()=>void;onPaper:()=>void;watch:string[];preview:boolean;active:boolean;
  request:<T>(method:string,args?:Record<string,unknown>)=>Promise<T>};
export default function ModeJournal({onBreadth,onPaper,watch,request,preview,active}:BoardProps) {
  const [rows,setRows]=useState<Entry[]>([]), [mode,setMode]=useState<Mode>('主线核心弱转强');
  const [market,setMarket]=useState('试错'),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [notes,setNotes]=useState<Record<string,string>>({});
  const [breadth,setBreadth]=useState(''),[reading,setReading]=useState(false);
  async function captureBreadth() {
    setReading(true);setError('');setBreadth('');
    try {
      const report=await requestWithTimeout(request<{days:BreadthDay[];error:string}>('breadth'));
      const view=breadthView(report.days.at(-1),report.error,Date.now());
      if(!view)throw Error('当前缺少完整的市场广度，可填写人工观察。');
      const {day}=view;
      setBreadth([preview?'静态预览':'观量大盘广度',day.date,view.live?.last||'收盘',
        '上涨 '+day.advance,'下跌 '+day.decline,'平盘 '+day.flat].join(' · '));
    }catch(e){setError(e instanceof Error?e.message:'广度读取失败');}
    finally{setReading(false);}
  }
  useEffect(()=>{readEntries().then(setRows).catch(()=>setError('本地计划记录读取失败，请重新打开板块。'));},[]);
  async function save(entry:Entry,done:()=>void) {
    setBusy(true);setError('');
    try {await append(entry);done();setRows(await readEntries());}
    catch {setError('记录状态待核对，请重新打开板块并检查最新一步。');try {setRows(await readEntries());}catch{}}
    finally {setBusy(false);}
  }
  function create(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form=event.currentTarget, data=new FormData(form);
    const values=Object.fromEntries(fields.map(([key])=>[key,String(data.get(key)||'').trim()])) as Record<typeof fields[number][0],string>;
    if(Object.values(values).some(v=>!v)){setError('请填写每项计划依据。');return;}
    const plan:Plan={...values,mode,market,breadth,budget:Number(data.get('budget'))};
    void save({id:crypto.randomUUID(),step:0,stage:market==='防守'?'观察':'等待',at:new Date().toISOString(),note:'已保存盘前判断',plan},()=>{
      form.querySelectorAll('input').forEach(input=>{input.value='';});setBreadth('');
    });
  }
  const plans=rows.filter(e=>e.plan).sort((a,b)=>b.at.localeCompare(a.at));
  return <div className="mode-journal">
    {active&&<MarketOpportunity request={request} preview={preview}/>}
    <details className="mode-advanced"><summary>详细交易计划{plans.length?'（已保存 '+plans.length+' 条）':''}</summary>
    <section className="card"><h2>BAOBAOLI 模式计划</h2>
      <p>先看强势股延续和板块亏钱效应，再选一种手法。记录当时的依据，收盘核对执行。此处操作只写入本机研究日志。</p>
      <button onClick={onBreadth}>查看大盘广度与板块</button> <button onClick={onPaper}>打开模拟交易</button>
      {' '}<button disabled={reading||busy} onClick={captureBreadth}>引用当前广度</button>
      {breadth&&<p>{breadth}</p>}
      <form onSubmit={create}><div className="mode-fields">
        <label>市场环境<select value={market} onChange={e=>setMarket(e.target.value)}>{['进攻','试错','防守'].map(v=><option key={v}>{v}</option>)}</select></label>
        <label>操作模式<select value={mode} onChange={e=>setMode(e.target.value as Mode)}>{Object.keys(templates).map(v=><option key={v}>{v}</option>)}</select></label>
        <p className="mode-hint">{templates[mode]}</p>
        {fields.map(([key,label,hint])=><label key={key}>{label}<input name={key} list={key==='symbol'?'mode-watch':undefined} required maxLength={350} placeholder={mode==='组合再平衡'&&key==='theme'?'资产组合与目标权重':mode==='指数定投'&&key==='trigger'?'计划扣款日期、额度与资金条件':hint}/></label>)}
        <datalist id="mode-watch">{watch.map(v=><option key={v} value={v}/>)}</datalist>
        <label>单笔风险预算（元）<input required name="budget" type="number" min={market==='防守'?0:0.01} step="0.01"/></label>
      </div><button disabled={busy||reading} className="primary">{market==='防守'?'保存观察计划':'保存盘前计划'}</button></form>
    </section>
    {error&&<p role="alert">{error}</p>}
    <section className="card"><h2>计划与执行记录</h2>
    {!plans.length&&<p>保存首张计划卡后，可在这里记录确认、退出与复盘。</p>}
    {plans.map(first=>{
      const plan=first.plan!,history=rows.filter(e=>e.id===first.id),last=history[history.length-1];
      return <article key={first.id}><h3>{plan.symbol} · {plan.mode} <small>{last.stage}</small></h3>
        <details><summary>盘前计划 · {stamp(first.at)}</summary><dl><dt>市场环境</dt><dd>{plan.market}</dd>{fields.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{plan[key]}</dd></div>)}<dt>单笔风险预算</dt><dd>{plan.budget} 元</dd></dl></details>
        {plan.breadth&&<p>原计划广度　{plan.breadth}</p>}
        <ol>{history.slice(1).map(row=><li key={row.step}>{stamp(row.at)}　{row.stage} · {row.note}</li>)}</ol>
        {transitions[last.stage].length>0&&<><label>实际观察或复盘依据<input maxLength={500} placeholder={last.stage==='失效待退出'?'核对实际成交后记录退出时间和价格':'记录当时看到的表现、实际动作及与计划的偏差'} value={notes[first.id]||''} onChange={e=>setNotes({...notes,[first.id]:e.target.value})}/></label>
        {transitions[last.stage].map(stage=><button key={stage} disabled={busy||!notes[first.id]?.trim()} onClick={()=>void save({id:first.id,step:last.step+1,stage,note:notes[first.id].trim(),at:new Date().toISOString()},()=>setNotes(prev=>({...prev,[first.id]:''})))}>{stage==='已复盘'?'保存复盘':'记录'+stage}</button>)}</>}
      </article>;
    })}</section></details>
  </div>;
}
