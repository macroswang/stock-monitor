import {useEffect,useRef,useState} from 'react';
import BrokerAccounts from './BrokerAccounts';
import {plannedQuantity,quantityDescription,type QuantityRule} from './tradingQuantity';
import {AccountFunds,SizingOutcome,formatted} from './SizingImpact';
import type {CashReserve} from './tradingSizing';
import TradingFeedback from './TradingFeedback';
import InfoNote from './InfoNote';
import TradePriceReview,{type PriceAudit} from './TradePriceReview';
import {submissionNote} from './autoTradeMarks';
import './liveTrading.css';

type Api=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
export type TradingRule=QuantityRule&{buy_enabled:boolean;sell_enabled:boolean;signal:string;revision:number;strategy_mode:'independent'|'paired_t';paired_enabled:boolean;t_lots:number;minimum_net_profit:number;commission_wan:number;minimum_commission:number;stamp_per_mille:number;transfer_per_mille:number;slippage_per_mille:number};
type Account={id:string;broker_name:string;account_masked:string;label:string;supports_order:boolean;supports_order_report:boolean;order_report_note:string;paused:boolean;sync_status:string;sync_error:string;last_success?:string;updated_at?:string;token?:string;unresolved:{name:string;quantity?:number;sellable?:number;reason:string}[];funds:Record<string,string>;funds_observed_at?:string};
type Position={account_id:string;code:string;name:string;active:boolean;position_verified:boolean;source:'holding'|'watchlist';watch_enabled:boolean;quantity:number;sellable:number;price?:number;cost?:number;updated_at?:string;rule:TradingRule};
type WatchStock={code:string;name:string;enabled:boolean};
type Plan={quantity:number;price:string;value:number;sizing_mode:'lots'|'position'|'paired_lots';lots:number;percent?:number;position_shares:number;account_id:string;code:string;side:string};
type Run={order_id?:string;receipt_accepted?:boolean;id:string;account_id:string;code:string;side:string;status:string;created_at:string;payload:PriceAudit&{mode:string;signal_source?:string;signal:{time:string;kind:string};plan?:Plan;message?:string;paired_t?:{cycle_id:string;leg:'sell'|'buy'};profit_gate?:{net:number;minimum_net_profit:number;allowed:boolean};verification?:{filled:number;order_id:string;note:string;origin?:string;at?:string;average?:string};reconciliation?:{at:string;ok:boolean;message:string};order_binding?:{order_id:string};result?:{order_id?:string;result?:{order_id?:string}}}};
type Cycle={id:string;account_id:string;code:string;state:string;quantity:number;first_run_id:string;second_run_id?:string;payload:{mode?:string;sell_price?:string;message?:string;profit_gate?:{net:number}}};
type View={settings:{paused:boolean;mode:'trial'|'live';signal:string;signal_label?:string;signal_notice?:string};accounts:Account[];positions:Position[];watchlist:WatchStock[];runs:Run[];cycles:Cycle[];cash_reserve?:CashReserve};
const money=formatted;
const time=(s?:string)=>s?s.slice(5,19).replace('T',' '):'尚未同步';
const statuses:Record<string,string>={never:'尚未同步',complete:'同步完整',partial:'待确认',failed:'同步失败',trial:'试运行 · 未下单',pending:'等待核验',processing:'核验中',sending:'提交中',accepted:'券商已受理',unknown:'未收到明确回执',partial_fill:'部分成交',filled:'已成交',cancelled:'已撤销',rejected:'已拒绝',not_sent:'已确认未发出',skipped:'已跳过',preview:'仅预览',failed_order:'提交前停止'};

type ManualEvidence={status:string;order_id:string;filled:number;average?:string;note:string};
function LegVerification({run,busy,onVerify}:{run:Run;busy:boolean;onVerify:(evidence:ManualEvidence)=>void}){
 const [status,setStatus]=useState('filled'),[order,setOrder]=useState(run.order_id||run.payload.verification?.order_id||''),[filled,setFilled]=useState(run.payload.verification?.filled??run.payload.plan?.quantity??0),[average,setAverage]=useState(run.payload.verification?.average||''),[note,setNote]=useState(''),[confirmed,setConfirmed]=useState(false);
 const locked=run.status==='filled';
 return <details className="trading-leg-verification"><summary>{run.side==='sell'?'首腿卖出':'回补买入'} · 人工核实</summary>
  <p>{time(run.created_at)} · {run.payload.plan?.quantity} 股 × {run.payload.plan?.price} 元。请按券商委托或成交明细填写。</p>
  <label>核实状态<select aria-label="核实状态" value={status} disabled={locked} onChange={e=>setStatus(e.target.value)}><option value="filled">全部成交</option><option value="partial">部分成交，委托仍有效</option><option value="cancelled">已撤销</option><option value="rejected">已拒绝</option></select></label>
  <label>券商委托号<input aria-label="券商委托号" value={order} disabled={locked} onChange={e=>setOrder(e.target.value)}/></label>
  <label>累计成交股数<input aria-label="累计成交股数" type="number" min="0" max={run.payload.plan?.quantity} step="1" value={filled} disabled={locked} onChange={e=>setFilled(Number(e.target.value))}/></label>
  <label>成交均价<input aria-label="成交均价" type="number" min="0.0001" step="any" value={average} onChange={e=>setAverage(e.target.value)}/></label>
  <label>核实依据<input aria-label="核实依据" value={note} onChange={e=>setNote(e.target.value)}/></label>
  <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>已在券商逐项核对本笔委托和成交明细</label>
  <button disabled={busy||!confirmed||!order.trim()||note.trim().length<4||(filled>0&&!(Number(average)>0))} onClick={()=>onVerify({status,order_id:order.trim(),filled,average:filled>0?average:undefined,note})}>保存核实结果</button>
 </details>;
}

function CycleRecovery({cycle,runs,busy,onClose,onVerify}:{cycle:Cycle;runs:Run[];busy:boolean;onClose:(note:string)=>void;onVerify:(r:Run,e:ManualEvidence)=>void}){
 const [note,setNote]=useState(''),[confirmed,setConfirmed]=useState(false);
 const legs=runs.filter(r=>r.id===cycle.first_run_id||r.id===cycle.second_run_id);
 const blocked=legs.some(r=>['pending','processing','sending','unknown','accepted','partial'].includes(r.status));
 const labels:Record<string,string>={sell_pending:'首腿待核实',waiting_buy:'等待回补',buy_pending:'回补待核实',needs_review:'需人工处理'};
 return <section className="trading-cycle-review" aria-label={`${cycle.code} 成对T周期`}>
  <strong>{cycle.code.toUpperCase()} · {labels[cycle.state]} · {cycle.quantity} 股 · {cycle.payload.mode==='trial'?'试运行':'实盘'}</strong>
  {cycle.payload.message&&<p>{cycle.payload.message}</p>}
  {legs.filter(r=>r.payload.reconciliation?.ok===false).map(r=><p role="status" key={r.id}>回报核实失败：{r.payload.reconciliation?.message}</p>)}
  {legs.filter(r=>r.payload.mode==='live'&&r.payload.plan&&(['unknown','accepted','partial'].includes(r.status)||(cycle.state==='needs_review'&&r.status==='filled'&&r.payload.verification?.origin==='manual'))).map(r=><LegVerification key={r.id+':'+r.status+':'+r.payload.verification?.at} run={r} busy={busy} onVerify={e=>onVerify(r,e)}/>)}
  <details><summary>人工结案</summary><p>在券商中核对并处理本轮剩余仓位后，可记录结案依据。结案会释放本轮限制；此操作仅记录结果。</p>
   <input aria-label={`${cycle.code} 结案依据`} placeholder="填写券商处理情况及依据" value={note} onChange={e=>setNote(e.target.value)}/>
   <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>已核对券商委托并处理本轮剩余仓位</label>
   <button disabled={busy||blocked||!confirmed||note.trim().length<4} onClick={()=>onClose(note)}>确认结案</button>
   {blocked&&<p>仍有未结束或未知委托，请先刷新券商回报。</p>}
  </details>
 </section>;
}

function QuantityEditor({code,side,rule,onChange}:{code:string;side:'buy'|'sell';rule:TradingRule;onChange:(changes:Partial<TradingRule>)=>void}){
 const label=side==='buy'?'买入':'卖出',mode=side==='buy'?rule.buy_mode:rule.sell_mode,minimum=code.startsWith('sh688')?2:1;
 return <>
  <div className="trading-quantity-fields">
   <label>数量方式<select aria-label={label+'数量方式'} value={mode} onChange={e=>onChange({[side+'_mode']:e.target.value})}><option value="lots">固定手数</option><option value="position">当前持仓百分比</option></select></label>
   {mode==='lots'?<label>每次手数<input aria-label={'每次'+label+'手数（手）'} type="number" min={minimum} max="1000000" step="1" required value={side==='buy'?rule.buy_lots:rule.sell_lots} onChange={e=>onChange({[side+'_lots']:Number(e.target.value)})}/></label>:<label>持仓比例（%）<input aria-label={label+'持仓比例（%）'} type="number" min="0.01" max="100" step="0.01" required value={side==='buy'?rule.buy_percent:rule.sell_percent} onChange={e=>onChange({[side+'_percent']:Number(e.target.value)})}/></label>}
  </div>
  <small className="trading-quantity-hint">{mode==='lots'?`1手＝100股${minimum>1?'，该股至少2手':''}`:'按执行时本账户这只股票的持仓股数计算'}</small>
  <div className="trading-quantity-shortcuts" aria-label={label+'数量快捷比较'}><span>快捷比较</span><button type="button" aria-pressed={mode==='lots'&&rule[side+'_lots' as 'buy_lots'|'sell_lots']===minimum} onClick={()=>onChange({[side+'_mode']:'lots',[side+'_lots']:minimum})}>{minimum}手</button>{[25,50,100].map(percent=><button type="button" key={percent} aria-pressed={mode==='position'&&rule[side+'_percent' as 'buy_percent'|'sell_percent']===percent} onClick={()=>onChange({[side+'_mode']:'position',[side+'_percent']:percent})}>{percent}%</button>)}</div>
 </>;
}

export default function LiveTrading({api,onRestartCore,onOpenStock,setupStock}:{api:Api;onRestartCore?:()=>Promise<unknown>;onOpenStock?:(code:string)=>void;setupStock?:{code:string;name:string}}){
 const [data,setData]=useState<View|null>(null),[tab,setTab]=useState('positions'),[selected,setSelected]=useState('');
 const [pauseBusy,setPauseBusy]=useState(false),[preparing,setPreparing]=useState(false);
 const [busy,setBusy]=useState(false),[progress,setProgress]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [filter,setFilter]=useState(''),[enabledOnly,setEnabledOnly]=useState(false);
 const [edit,setEdit]=useState<{position:Position;rule:TradingRule;account:Account}|null>(null);
 const [mapping,setMapping]=useState<{account:Account;name:string;code:string}|null>(null);
 const [target,setTarget]=useState<{account_id:string;code:string;name?:string;configure?:boolean}|null>(null);
 const [liveConfirm,setLiveConfirm]=useState(false);
 const running=useRef(false),sequence=useRef(0),mounted=useRef(true);
 useEffect(()=>{
  if(!setupStock)return;
  setTab('positions');setEdit(null);setMapping(null);setLiveConfirm(false);
  setTarget({account_id:'',code:setupStock.code,name:setupStock.name,configure:true});
 },[setupStock]);
 useEffect(()=>{
  if(!edit&&!mapping&&!target&&!liveConfirm)return;
  setError('');
  const prior=document.activeElement as HTMLElement|null;
  const frame=requestAnimationFrame(()=>document.querySelector<HTMLElement>('[role="dialog"] input,[role="dialog"] select,[role="dialog"] button')?.focus());
  const onKey=(e:KeyboardEvent)=>{
   if(e.key==='Escape'&&!running.current){setEdit(null);setMapping(null);setTarget(null);setLiveConfirm(false);}
   if(e.key==='Tab'){
    const items=Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"] button:not(:disabled),[role="dialog"] input:not(:disabled),[role="dialog"] select:not(:disabled)'));
    const first=items[0],last=items.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
   }
  };
  document.addEventListener('keydown',onKey);
  return()=>{cancelAnimationFrame(frame);document.removeEventListener('keydown',onKey);prior?.focus();};
 },[!!edit,!!mapping,!!target,liveConfirm]);
 const load=async()=>{const seq=++sequence.current;const d=await api<View>('trading_view');if(mounted.current&&seq===sequence.current)setData(d);};
 useEffect(()=>{mounted.current=true;let loading=false;const refresh=async()=>{if(loading||running.current)return;loading=true;try{await load();}catch(e){if(mounted.current)setError(String(e));}finally{loading=false;}};void refresh();const timer=setInterval(refresh,5000);return()=>{mounted.current=false;sequence.current++;clearInterval(timer);};},[]);
 async function run(fn:()=>Promise<unknown>,message=''){
  if(running.current)return;
  running.current=true;setBusy(true);setError('');setNotice('');
  try{await fn();await load();if(message)setNotice(message);}catch(e){setError(String(e));try{await load();}catch{/* Keep the actionable operation error. */}}finally{running.current=false;setBusy(false);setProgress('');}
 }
 async function job<T>(method:string,args:Record<string,unknown>={}):Promise<T>{
  const task=await api<{job:string}>(method,args),start=Date.now();
  for(;;){const state=await api<{status:string;result?:T;error?:string}>('job',{job:task.job});if(state.status==='done')return state.result as T;if(state.status==='failed')throw Error(state.error||'操作失败');if(Date.now()-start>600000)throw Error('等待超时，后台可能仍在运行，请刷新核对结果');await new Promise(r=>setTimeout(r,400));}
 }
 async function pauseNow(accountId?:string){
  if(pauseBusy)return;
  setPauseBusy(true);setError('');
  try{await api(accountId?'trading_pause_account':'trading_config',accountId?{account_id:accountId,paused:true}:{paused:true});await load();setNotice(accountId?'该账户自动执行已暂停。':'全部自动执行已暂停。');}catch(e){setError(String(e));}finally{setPauseBusy(false);}
 }
 async function startExecution(){
  setPreparing(true);
  try{await run(async()=>{setProgress('正在准备账户并同步持仓…');await job('trading_start');},'已启动，仅处理此后新确认的“底／顶”信号：独立规则底买、顶卖；成对T顶卖后按净收益门槛回补；不补下历史信号。');}finally{setPreparing(false);}
 }
 const orderId=(r:Run)=>r.order_id||r.payload.verification?.order_id||r.payload.order_binding?.order_id||r.payload.result?.order_id||r.payload.result?.result?.order_id||'';
 const refreshReport=(r:Run,id='')=>run(async()=>{setProgress('正在核对该账户的委托编号和成交回报…');const result=await job<{message:string}>('trading_reconcile',{id:r.id,order_id:id});setNotice(result.message);});
 const account=(id:string)=>data?.accounts.find(a=>a.id===id);
 const accountName=(id:string)=>{const a=account(id);return a?`${a.broker_name} · ${a.account_masked}${a.label?` · ${a.label}`:''}`:'已移除账户 · '+id.slice(0,8);};
 const sync=()=>run(async()=>{setProgress(selected?'正在核验所选账户并读取全部持仓…':'正在逐个核验账户并同步持仓…');const result=await job<{results?:{account_id:string;status:string;error?:string}[];status?:string}>((selected?'trading_sync':'trading_sync_all'),selected?{account_id:selected}:{});if(result.results?.some(r=>r.status!=='complete'))setNotice('同步已结束；部分账户失败或有持仓待确认，请查看各账户提示。');else setNotice(result.status==='partial'?'持仓已读取，部分代码待确认，已核验股票可按各自规则执行。':'同步完成，原有交易规则已保留。');});
 const toggle=(p:Position,side:'buy'|'sell',enabled:boolean)=>{if(running.current)return;sequence.current++;setData(old=>old?{...old,positions:old.positions.map(row=>row.account_id===p.account_id&&row.code===p.code?{...row,rule:{...row.rule,[side+'_enabled']:enabled}}:row)}:old);void run(async()=>{await api('trading_rule_save',{account_id:p.account_id,code:p.code,revision:p.rule.revision,changes:{[side+'_enabled']:enabled}});},`${p.name} · ${accountName(p.account_id)} · 自动${side==='buy'?'买入':'卖出'}已${enabled?'开启':'关闭'}`);};
 const togglePaired=(p:Position,enabled:boolean)=>{if(running.current)return;sequence.current++;setData(old=>old?{...old,positions:old.positions.map(row=>row.account_id===p.account_id&&row.code===p.code?{...row,rule:{...row.rule,paired_enabled:enabled}}:row)}:old);void run(async()=>{await api('trading_rule_save',{account_id:p.account_id,code:p.code,revision:p.rule.revision,changes:{paired_enabled:enabled}});},`${p.name} · ${accountName(p.account_id)} · 成对T已${enabled?'开启':'关闭'}`);};
 const preview=(p:Position,side:string)=>run(async()=>{const r=await api<Plan>('trading_preview',{account_id:p.account_id,code:p.code,side});setNotice(`${accountName(p.account_id)}｜${p.name} ${p.code.toUpperCase()}｜试算${side==='buy'?'买入':'卖出'} ${r.quantity}股 × ${r.price}元 ≈ ${money(r.value)}元。仅按当前数据试算，未发出委托；实时执行还会核验账户、资金及信号。`);});
 const availableTargets=(accountId:string)=>data?.watchlist.filter(w=>!data.positions.some(p=>p.account_id===accountId&&p.code===w.code))||[];
 const openTarget=()=>{const accountId=selected||data?.accounts[0]?.id||'';setTarget({account_id:accountId,code:availableTargets(accountId)[0]?.code||''});};
 const submitTarget=async()=>{
  if(!target)return;
  const request=target;
  await run(async()=>{
   await api('trading_target_add',{account_id:request.account_id,code:request.code});
   if(request.configure){
    const latest=await api<View>('trading_view');
    const position=latest.positions.find(p=>p.account_id===request.account_id&&p.code===request.code);
    const selectedAccount=latest.accounts.find(a=>a.id===request.account_id);
    if(!position||!selectedAccount)throw Error('账户或股票已变化，请重新选择。');
    setSelected(request.account_id);setFilter('');setEnabledOnly(false);
    setEdit({position,rule:{...position.rule},account:selectedAccount});
   }
   setTarget(null);
  },request.configure?'':'自选股已关联到所选账户；规则默认关闭，请在列表中配置并开启。');
 };
 const filtered=data?.positions.filter(p=>(!selected||p.account_id===selected)&&(!enabledOnly||p.rule.buy_enabled||p.rule.sell_enabled||p.rule.paired_enabled)&&(!filter||`${p.name} ${p.code}`.toLowerCase().includes(filter.toLowerCase())))||[];
 const visibleAccounts=data?.accounts.filter(a=>!selected||a.id===selected)||[];
 const runs=data?.runs.filter(r=>!selected||r.account_id===selected)||[];
 return <div className="trading-workspace">
  <div className="trading-hero"><div><div className="trading-heading"><h2>{tab==='accounts'?'证券账户':tab==='runs'?'执行记录':'自动交易股票'}</h2><span className={'chip '+(data?.settings.mode==='live'?'amber':'')}>{data?.settings.mode==='live'?'实盘模式':'试运行 · 不下单'}</span></div><p>{tab==='accounts'?'绑定账户，管理登录信息':tab==='runs'?'查看自动交易的计划与结果':'信号源：图中已确认的顶／底 · 支持持仓股票和指定账户的自选股'}</p></div><div className="trading-execution"><span className={data?.settings.paused?'paused':'active'}>{data?.settings.paused?'自动执行已暂停':'自动执行运行中'}</span><button className={data?.settings.paused?'primary':'trading-stop'} aria-pressed={!!data&&!data.settings.paused} disabled={pauseBusy||!data||(data.settings.paused&&!preparing&&(busy||!data.positions.some(p=>p.rule.buy_enabled||p.rule.sell_enabled||p.rule.paired_enabled)))} onClick={()=>preparing||!data!.settings.paused?void pauseNow():void startExecution()}>{preparing?'取消启动':data?.settings.paused?`启动${data.settings.mode==='live'?'实盘执行':'试运行'}`:'暂停全部自动交易'}</button></div></div>
  <div className="trading-tabs tabs" role="tablist" aria-label="自动交易管理">{[['positions','持仓与策略'],['runs','执行记录'],['accounts','证券账户']].map(([id,label])=><button role="tab" aria-selected={tab===id} className={tab===id?'chosen':''} disabled={busy} key={id} onClick={()=>setTab(id)}>{label}</button>)}</div>
  <div className="trading-toast-stack"><TradingFeedback message={data?.settings.signal_notice}/><TradingFeedback message={error} error/><TradingFeedback message={notice}/></div>
  {progress&&<div className="trading-progress" role="status">{progress}</div>}
  {tab==='accounts'?<BrokerAccounts api={api} onRestartCore={onRestartCore} onManagePositions={id=>{setSelected(id);setTab('positions');}}/>:<>
   <div className="card trading-toolbar"><label>证券账户<select aria-label="管理证券账户" disabled={busy||!!edit||!!mapping||!!target} value={selected} onChange={e=>setSelected(e.target.value)}><option value="">全部账户</option>{data?.accounts.map(a=><option key={a.id} value={a.id}>{accountName(a.id)}</option>)}</select></label><label className="trading-mode-label">执行模式<select aria-label="执行模式" disabled={busy} value={data?.settings.mode||'trial'} onChange={e=>e.target.value==='live'?setLiveConfirm(true):void run(()=>api('trading_config',{mode:'trial'}),'已切换试运行并暂停；规则保留。')}><option value="trial">试运行（不下单）</option><option value="live">实盘执行</option></select></label><div className="trading-toolbar-actions"><button disabled={busy||!data} onClick={()=>run(load)}>刷新</button>{tab==='positions'&&<><button disabled={busy||!data?.accounts.length||!data.watchlist.length} onClick={openTarget}>添加自选股</button><button className="primary" disabled={busy||!data?.accounts.length} onClick={sync}>{busy&&progress?'同步中…':selected?'同步当前账户':'一键同步全部持仓'}</button></>}</div></div>
   {tab==='positions'?<>

    <div className="trading-filter"><input aria-label="搜索股票" placeholder="搜索股票名称或代码" value={filter} onChange={e=>setFilter(e.target.value)}/><label><input type="checkbox" checked={enabledOnly} onChange={e=>setEnabledOnly(e.target.checked)}/>只看已开启规则</label><span>{filtered.length} 条账户股票</span></div>
    {data&&data.accounts.length===0&&<section className="card trading-empty"><h3>先连接你的证券账户</h3><p>添加账户后，一键读取已建仓股票；同步本身不会开启自动买卖。</p><button className="primary" onClick={()=>setTab('accounts')}>添加证券账户</button></section>}
    {visibleAccounts.map(a=><section className="card trading-account" key={a.id} aria-label={accountName(a.id)}>
     <div className="trading-account-heading"><div><strong>{a.broker_name}</strong><span>{a.account_masked}{a.label?' · '+a.label:''}</span><span className={'chip '+(a.sync_status!=='complete'?'amber':'')}>{statuses[a.sync_status]||a.sync_status}</span>{a.paused&&<span className="chip amber">账户已暂停</span>}</div><button disabled={pauseBusy||(busy&&a.paused)} onClick={()=>!a.paused?void pauseNow(a.id):void run(()=>api('trading_pause_account',{account_id:a.id,paused:false}),'账户已恢复，仅接收新信号。')}>{a.paused?'恢复账户':'暂停账户'}</button></div>
     <div className="trading-account-meta">最近完整同步 {time(a.last_success)}{a.updated_at&&a.updated_at!==a.last_success?` · 最近尝试 ${time(a.updated_at)}`:''}{!a.supports_order&&<span> · 该券商目前支持查询与试运行，实盘下单尚未适配</span>}</div>
     <AccountFunds funds={a.funds}/>
     <InfoNote label="成交核实说明">{a.order_report_note}</InfoNote>
     {a.sync_error&&<p className="trading-inline-warning">{a.sync_error}</p>}
     {a.unresolved?.length>0&&<div className="trading-unresolved"><strong>以下持仓需要确认股票代码</strong><p>券商列表没有提供代码。确认后仅为本账户保存对应关系，下次同步会复用。</p>{a.unresolved.map((p,i)=><div key={i}><span>{p.name} · 持仓 {money(p.quantity)} 股</span><button disabled={busy||!a.token} onClick={()=>setMapping({account:a,name:p.name,code:''})}>确认代码</button></div>)}</div>}
     <div className="table-scroll"><table className="trading-position-table"><thead><tr>{['股票','持仓 / 可卖','自动买入','自动卖出','规则与操作'].map(s=><th key={s}>{s}</th>)}</tr></thead><tbody>{filtered.filter(p=>p.account_id===a.id).map(p=>{
      const paired=p.rule.strategy_mode==='paired_t',cycle=data?.cycles?.find(c=>c.account_id===p.account_id&&c.code===p.code&&['sell_pending','waiting_buy','buy_pending','needs_review'].includes(c.state));
      return <tr key={p.code} className={p.position_verified&&!p.active?'trading-inactive':''}><td><button className="trading-stock-link" onClick={()=>onOpenStock?.(p.code)}>{p.name}</button><small>{p.code.toUpperCase()} · {p.position_verified?(p.active?'券商持仓':'已清仓'):'自选股配置'}{paired?' · 成对T':''}</small></td><td><strong>{p.position_verified?`${money(p.quantity)} / ${money(p.sellable)}`:'待持仓同步'}</strong><small>成本 {money(p.cost)} · 现价 {money(p.price)}</small></td><td>{paired?<><strong>仅成对回补</strong><small>{cycle?.state==='waiting_buy'?'首腿已成交，等待满足门槛的底信号':cycle?'本轮处理中':'顶信号先卖出后才允许买回'}<br/>不会独立买入</small></>:<><label className="trading-switch"><input aria-label={`${a.account_masked} ${p.name} 自动买入`} type="checkbox" checked={p.rule.buy_enabled} disabled={busy||(data?.settings.mode==='live'&&!a.supports_order)} onChange={e=>toggle(p,'buy',e.target.checked)}/>{p.rule.buy_enabled?'已开启':'已关闭'}</label><small>{quantityDescription('buy',p.rule)}<br/>预计 {money(plannedQuantity(p.code,p.quantity,p.sellable,'buy',p.rule))} 股 · 约 {p.price?money(plannedQuantity(p.code,p.quantity,p.sellable,'buy',p.rule)*p.price):'—'} 元</small></>}</td><td>{paired?<><label className="trading-switch"><input aria-label={`${a.account_masked} ${p.name} 成对T`} type="checkbox" checked={p.rule.paired_enabled} disabled={busy||(data?.settings.mode==='live'&&!a.supports_order)} onChange={e=>togglePaired(p,e.target.checked)}/>{p.rule.paired_enabled?'已开启':'已关闭'}</label><small>每轮 {p.rule.t_lots} 手 · 净收益至少 {money(p.rule.minimum_net_profit)} 元<br/>{cycle?`当前：${{sell_pending:'首腿待核实',waiting_buy:'等待回补',buy_pending:'回补待核实',needs_review:'需人工处理'}[cycle.state]||cycle.state}`:'完成后可继续下一轮'}</small></>:<><label className="trading-switch"><input aria-label={`${a.account_masked} ${p.name} 自动卖出`} type="checkbox" checked={p.rule.sell_enabled} disabled={busy||(data?.settings.mode==='live'&&!a.supports_order)} onChange={e=>toggle(p,'sell',e.target.checked)}/>{p.rule.sell_enabled?'已开启':'已关闭'}</label><small>{quantityDescription('sell',p.rule)}<br/>预计 {money(p.active?plannedQuantity(p.code,p.quantity,p.sellable,'sell',p.rule):0)} 股 · 约 {p.price?money((p.active?plannedQuantity(p.code,p.quantity,p.sellable,'sell',p.rule):0)*p.price):'—'} 元</small></>}</td><td><div className="trading-row-actions"><button disabled={busy} onClick={()=>setEdit({position:p,rule:{...p.rule},account:a})}>配置规则</button><button disabled={busy} onClick={()=>preview(p,'buy')}>试算买入</button><button disabled={busy} onClick={()=>preview(p,'sell')}>试算卖出</button></div></td></tr>;
     })}</tbody></table></div>
     {!filtered.some(p=>p.account_id===a.id)&&<p className="trading-empty-row">{a.sync_status==='never'?'尚未同步持仓，也可以先添加自选股。':'没有符合条件的账户股票。'}</p>}
     {data?.cycles?.filter(c=>c.account_id===a.id&&['sell_pending','waiting_buy','buy_pending','needs_review'].includes(c.state)).map(c=><CycleRecovery key={c.id} cycle={c} runs={data.runs} busy={busy} onVerify={(r,evidence)=>void run(()=>api('trading_resolve',{id:r.id,...evidence}),'核实结果已保存，周期状态已更新。')} onClose={note=>void run(()=>api('trading_cycle_close',{id:c.id,note,confirm:true}),'已记录人工结案，可按单股开关接收之后的新信号。')}/>)}
    </section>)}
   </>:<section className="card trading-runs"><div className="trading-account-heading"><strong>信号与执行结果</strong><span>最近200条 · 独立规则逐信号执行，成对T逐轮串行</span></div><div className="table-scroll"><table><thead><tr>{['时间 / 账户','股票 / 信号','计划委托','执行状态','操作'].map(s=><th key={s}>{s}</th>)}</tr></thead><tbody>{runs.map(r=><tr key={r.id}><td>{time(r.created_at)}<small>{accountName(r.account_id)}</small></td><td>{data?.positions.find(p=>p.account_id===r.account_id&&p.code===r.code)?.name||r.code}<small>{r.code.toUpperCase()} · {r.payload.signal_source==='shape-v1'?'':'Q1'}{r.side==='buy'?'底':'顶'} {r.payload.signal?.time}{r.payload.paired_t?` · 成对T${r.payload.paired_t.leg==='sell'?'首腿':'回补'}`:''}</small></td><td>{r.payload.plan?`${r.side==='buy'?'买入':'卖出'} ${r.payload.plan.quantity}股 × ${r.payload.plan.price}元`:'—'}<small>{r.payload.mode==='trial'?'试运行':'实盘'}{r.payload.profit_gate?` · 预计净收益 ${money(r.payload.profit_gate.net)} / 门槛 ${money(r.payload.profit_gate.minimum_net_profit)} 元`:''}</small></td><td><strong>{r.receipt_accepted?'券商已受理':r.status==='partial'?'部分成交':r.status==='failed'?'提交前停止':statuses[r.status]||r.status}</strong>{!r.payload.verification&&<small>{r.status==='unknown'?(r.receipt_accepted?'券商已返回提交成功回执':r.payload.paired_t?'该请求不自动重发；成对T会锁定本轮':'该请求不自动重发，不影响后续新信号'):submissionNote(r.payload.message||'已记录')}</small>}<TradePriceReview audit={r.payload} side={r.side}/>{r.payload.verification&&<small>{r.payload.verification.origin==='broker_auto'?'券商回报自动核实':'人工核实'} · 委托号 {r.payload.verification.order_id} · 已成交 {r.payload.verification.filled} 股</small>}{r.payload.reconciliation?.ok&&<small>回报更新 {time(r.payload.reconciliation.at)}{!r.payload.reconciliation.ok?' · '+r.payload.reconciliation.message:''}</small>}</td><td>{['unknown','accepted','partial'].includes(r.status)&&!!orderId(r)&&account(r.account_id)?.supports_order_report!==false&&<button disabled={busy} onClick={()=>void refreshReport(r,orderId(r))}>刷新券商回报</button>}</td></tr>)}</tbody></table></div>{runs.length===0&&<div className="trading-empty"><h3>还没有执行记录</h3><p>开启单股规则并启动试运行后，新确认的实时顶／底信号会在这里留下计划或未执行原因。</p></div>}</section>}
  </>}
  {edit&&<div className="modal-overlay"><form className="card trading-dialog trading-rule-dialog" role="dialog" aria-modal="true" aria-labelledby="trading-rule-title" onSubmit={e=>{e.preventDefault();void run(async()=>{await api('trading_rule_save',{account_id:edit.position.account_id,code:edit.position.code,revision:edit.rule.revision,changes:Object.fromEntries(Object.entries(edit.rule).filter(([k])=>!['revision','armed_at'].includes(k)))});setEdit(null);},'规则已保存，仅对之后的新信号生效。');}}>
   <h2 id="trading-rule-title">{edit.position.name} · 自动交易</h2><p className="trading-dialog-account"><span>{accountName(edit.position.account_id)}</span><span>{edit.position.code.toUpperCase()} · 图中确认顶／底信号</span></p>
   <div className="trading-current-position"><div><span>当前持仓 / 可卖</span><strong>{edit.position.position_verified?`${money(edit.position.quantity)} / ${money(edit.position.sellable)} 股`:'待持仓同步'}</strong></div><div><span>本账户可用资金</span><strong>{money(edit.account.funds.available)} 元</strong></div><div><span>当前价格</span><strong>{money(edit.position.price)} 元</strong></div></div><p className="trading-estimate-basis">持仓读取 {time(edit.position.updated_at)} · 资金读取 {time(edit.account.funds_observed_at||edit.account.last_success)}。执行时会重新读取账户数据。</p>
   <label className="trading-strategy-mode">交易方式<select aria-label="交易方式" value={edit.rule.strategy_mode} onChange={e=>setEdit({...edit,rule:{...edit.rule,strategy_mode:e.target.value as TradingRule['strategy_mode']}})}><option value="independent">独立买卖（原有方式）</option><option value="paired_t">成对T（先卖后买）</option></select></label>
   {edit.rule.strategy_mode==='independent'?<><div className="trading-form-grid">{(['buy','sell'] as const).map(side=><fieldset className="trading-sizing-panel" key={side}><label className="trading-switch"><input type="checkbox" checked={side==='buy'?edit.rule.buy_enabled:edit.rule.sell_enabled} onChange={e=>setEdit({...edit,rule:{...edit.rule,[side+'_enabled']:e.target.checked}})}/>自动{side==='buy'?'买入':'卖出'}</label><QuantityEditor code={edit.position.code} side={side} rule={edit.rule} onChange={changes=>setEdit({...edit,rule:{...edit.rule,...changes}})}/><SizingOutcome code={edit.position.code} position={edit.position.quantity} sellable={edit.position.sellable} side={side} rule={edit.rule} price={edit.position.price} funds={edit.account.funds} reserve={data?.cash_reserve}/></fieldset>)}</div><InfoNote label="计算说明">按执行时本账户持仓计算，买卖分别估算。费用及实际可买数量以券商为准。</InfoNote></>:<fieldset className="trading-paired-panel"><label className="trading-switch"><input aria-label="启用成对T" type="checkbox" checked={edit.rule.paired_enabled} onChange={e=>setEdit({...edit,rule:{...edit.rule,paired_enabled:e.target.checked}})}/>启用成对T</label><div className="trading-paired-grid"><label>每轮手数（手）<input aria-label="成对T每轮手数（手）" type="number" min={edit.position.code.startsWith('sh688')?2:1} max="1000000" step="1" required value={edit.rule.t_lots} onChange={e=>setEdit({...edit,rule:{...edit.rule,t_lots:Number(e.target.value)}})}/></label><label>最低净收益（元）<input aria-label="最低净收益（元）" type="number" min="0" step="0.01" required value={edit.rule.minimum_net_profit} onChange={e=>setEdit({...edit,rule:{...edit.rule,minimum_net_profit:Number(e.target.value)}})}/></label></div><InfoNote label="成对规则">顶信号先卖出；只有券商确认首腿全部成交，且底信号按下列费用估算后的净收益达到门槛，才按相同股数买回。未知、部分成交或待回补期间不会开始下一轮；一轮完成后可继续下一轮，不限制每日轮次。</InfoNote><details className="trading-more-settings"><summary>手续费与滑点参数</summary><div className="trading-fee-grid"><label>佣金（万分）<input aria-label="佣金（万分）" type="number" min="0" step="0.01" value={edit.rule.commission_wan} onChange={e=>setEdit({...edit,rule:{...edit.rule,commission_wan:Number(e.target.value)}})}/></label><label>单边最低佣金（元）<input aria-label="单边最低佣金（元）" type="number" min="0" step="0.01" value={edit.rule.minimum_commission} onChange={e=>setEdit({...edit,rule:{...edit.rule,minimum_commission:Number(e.target.value)}})}/></label><label>印花税（‰）<input aria-label="印花税（‰）" type="number" min="0" step="0.001" value={edit.rule.stamp_per_mille} onChange={e=>setEdit({...edit,rule:{...edit.rule,stamp_per_mille:Number(e.target.value)}})}/></label><label>过户费（‰）<input aria-label="过户费（‰）" type="number" min="0" step="0.001" value={edit.rule.transfer_per_mille} onChange={e=>setEdit({...edit,rule:{...edit.rule,transfer_per_mille:Number(e.target.value)}})}/></label><label>预估滑点（‰）<input aria-label="预估滑点（‰）" type="number" min="0" max="999" step="0.01" value={edit.rule.slippage_per_mille} onChange={e=>setEdit({...edit,rule:{...edit.rule,slippage_per_mille:Number(e.target.value)}})}/></label></div></details></fieldset>}
   {error&&<p role="alert" className="trading-inline-warning">{error}</p>}<div className="trading-dialog-actions"><button type="button" disabled={busy} onClick={()=>setEdit(null)}>取消</button><button className="primary" disabled={busy}>保存规则</button></div>
  </form></div>}
  {target&&<div className="modal-overlay"><form className="card trading-dialog trading-dialog-small" role="dialog" aria-modal="true" aria-labelledby="trading-target-title" onSubmit={e=>{e.preventDefault();void submitTarget();}}>
   <h2 id="trading-target-title">{target.configure?'设置自动下单':'添加自选股自动交易'}</h2>
   {target.configure&&<p className="trading-dialog-account">{target.name} · {target.code.toUpperCase()}</p>}
   <label>证券账户<select aria-label="选择自选股证券账户" required disabled={busy} value={target.account_id} onChange={e=>{const accountId=e.target.value;setTarget({...target,account_id:accountId,code:target.configure?target.code:availableTargets(accountId)[0]?.code||''});}}><option value="" disabled>请选择证券账户</option>{data?.accounts.map(a=><option key={a.id} value={a.id}>{accountName(a.id)}</option>)}</select></label>
   {!target.configure&&<><label>自选股<select aria-label="选择自动交易自选股" required value={target.code} onChange={e=>setTarget({...target,code:e.target.value})}><option value="" disabled>请选择</option>{availableTargets(target.account_id).map(w=><option key={w.code} value={w.code}>{w.name} · {w.code.toUpperCase()}{w.enabled?'':' · 监控已暂停'}</option>)}</select></label>{availableTargets(target.account_id).length===0&&<p>该账户已添加全部自选股。</p>}</>}
   {data?.accounts.length===0?<p>请先<button type="button" onClick={()=>{setTarget(null);setTab('accounts');}}>添加证券账户</button>，再设置自动下单。</p>:<p>{target.configure?'选择账户后配置规则；已有规则会保留，新关联默认关闭买卖。':'关联后买卖开关保持关闭；配置规则并开启后，只处理之后新确认的顶／底信号。'}</p>}
   {error&&<p role="alert" className="trading-inline-warning">{error}</p>}
   <div className="trading-dialog-actions"><button type="button" disabled={busy} onClick={()=>setTarget(null)}>取消</button><button className="primary" disabled={busy||!target.code||!target.account_id}>{target.configure?'配置规则':'添加'}</button></div>
  </form></div>}
  {mapping&&<div className="modal-overlay"><form className="card trading-dialog trading-dialog-small" role="dialog" aria-modal="true" aria-labelledby="trading-map-title" onSubmit={e=>{e.preventDefault();void run(async()=>{await job('trading_map',{account_id:mapping.account.id,token:mapping.account.token,name:mapping.name,code:mapping.code});setMapping(null);},'股票代码已核对并关联到所选账户。');}}><h2 id="trading-map-title">确认 {mapping.name} 的股票代码</h2><p>{accountName(mapping.account.id)}</p><p>请输入券商中的6位股票代码。观量会核对代码对应名称，相符后仅关联到此账户。</p><input aria-label="持仓股票代码" required pattern="[0-9]{6}" placeholder="6位股票代码" value={mapping.code} onChange={e=>setMapping({...mapping,code:e.target.value.replace(/\D/g,'').slice(0,6)})}/>{error&&<p role="alert" className="trading-inline-warning">{error}</p>}<div className="trading-dialog-actions"><button type="button" disabled={busy} onClick={()=>setMapping(null)}>取消</button><button className="primary" disabled={busy}>核对并关联</button></div></form></div>}
  {liveConfirm&&<div className="modal-overlay"><section className="card trading-dialog trading-dialog-small" role="dialog" aria-modal="true" aria-labelledby="trading-live-title"><h2 id="trading-live-title">切换到实盘执行</h2><p>之后启动执行时，已开启的单股规则会向对应证券账户发送真实委托。</p><p>切换后保持暂停。请核对每个账户的买卖开关和下单数量，再启动实盘。</p><div className="trading-dialog-actions"><button disabled={busy} onClick={()=>setLiveConfirm(false)}>保留试运行</button><button disabled={busy} onClick={()=>run(async()=>{await api('trading_config',{mode:'live',confirm_live:true});setLiveConfirm(false);},'已切换实盘模式，目前仍暂停。')}>确认切换，保持暂停</button></div></section></div>}
 </div>;
}
