import {useEffect,useRef,useState} from 'react';
import TradingFeedback from './TradingFeedback';
import InfoNote from './InfoNote';
import './brokerAccounts.css';

type Field={key:string;label:string;secret:boolean};
type Spec={id:string;name:string;package:string;fields:Field[];note:string;supports_order:boolean;supports_query:boolean;supports_cancel:boolean};
type Account={id:string;broker:string;broker_name:string;package:string;account:string;account_masked:string;label:string;enabled:boolean;is_default:boolean;password_saved:boolean;supports_order:boolean;supports_query:boolean;supports_cancel:boolean;supports_order_report?:boolean};
type OrderRow={kind:string;name:string;code:string;direction:string;side:'buy'|'sell'|null;date:string;time:string;price:number|null;quantity:number|null;filled:number|null;state:string;cancellable:boolean};
type OrderList={kind:string;date_range:string;cycle:string;count:number;cancellable_count:number;rows:OrderRow[]};
type Snapshot={funds:Record<string,string>;positions:Record<string,string|number>[]};
type Execution={request_id:string;status:string;created_at:string;order_id?:string;verification?:{origin:string;filled:number};reconciliation?:{message:string;at:string}};
type Api=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;

const SIDES=[['sell','卖出'],['buy','买入']] as const;
const QUERIES=[['today_orders','今日委托'],['today_trades','今日成交'],['history_orders','历史委托'],['history_trades','历史成交']] as const;
const FUND_LABELS:Array<[string,string]>=[['total_assets','总资产'],['available','可用'],['withdrawable','可取'],['market_value','总市值'],['position_ratio','总仓位'],['holding_profit','持仓收益'],['today_profit','今日盈亏']];
const POSITION_COLUMNS:Array<[string,string]>=[['name','名称'],['quantity','持仓'],['sellable','可用'],['price','现价'],['cost','成本'],['profit','持仓盈亏'],['market_value','市值']];

export default function BrokerAccounts({api,onRestartCore,onManagePositions}:{api:Api;onRestartCore?:()=>Promise<unknown>;onManagePositions?:(id:string)=>void}){
 const [specs,setSpecs]=useState<Spec[]>([]);
 const [accounts,setAccounts]=useState<Account[]>([]);
 const [error,setError]=useState('');
 const [note,setNote]=useState('');
 const [busy,setBusy]=useState(false);
 const [editor,setEditor]=useState<Account|'new'|null>(null);
 const [progress,setProgress]=useState('');
 const [broker,setBroker]=useState('');
 const [account,setAccount]=useState('');
 const [label,setLabel]=useState('');
 const [values,setValues]=useState<Record<string,string>>({});
 const [selected,setSelected]=useState('');
 const [side,setSide]=useState<'buy'|'sell'>('sell');
 const [code,setCode]=useState('');
 const [quantity,setQuantity]=useState('');
 const [price,setPrice]=useState('');
 const [maxValue,setMaxValue]=useState('1000');
 const [realOrder,setRealOrder]=useState(false);
 const [query,setQuery]=useState<typeof QUERIES[number][0]>('today_orders');
 const [orders,setOrders]=useState<OrderRow[]>([]);
 const [listInfo,setListInfo]=useState('');
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
 const [detail,setDetail]=useState('');
 const errorRef=useRef<HTMLDivElement|null>(null);
 const [confirmDelete,setConfirmDelete]=useState('');
 const [executions,setExecutions]=useState<Execution[]>([]);
 const running=useRef(false);
 const submitIntent=useRef<{payload:string;id:string}|null>(null);

 const currentSpec=specs.find(s=>s.id===broker);

 async function load(){
  try{
   const [s,a]=await Promise.all([api<Spec[]>('broker_specs'),api<Account[]>('broker_accounts')]);
   setSpecs(s);setAccounts(a);setError('');
   if(!broker&&s.length)setBroker(s[0].id);
   setSelected(old=>a.some(item=>item.id===old)?old:a[0]?.id||'');
  }catch(e){setError(String(e));}
 }
 useEffect(()=>{load();},[]);
 useEffect(()=>{if(error)errorRef.current?.scrollIntoView({block:'center',behavior:'smooth'});},[error]);
 useEffect(()=>{
  setOrders([]);setSnapshot(null);setListInfo('');setDetail('');setRealOrder(false);setExecutions([]);
  if(!selected)return;
  let active=true;
  api<Execution[]>('broker_requests',{id:selected}).then(r=>{if(active)setExecutions(r);}).catch(e=>{if(active)setError(String(e));});
  return()=>{active=false;};
 },[selected]);

 async function run(fn:()=>Promise<unknown>,ok:string){
  if(running.current)return;
  running.current=true;
  setBusy(true);setError('');setNote('');
  try{
   await fn();
   if(ok)setNote(ok);
   // 刷新也属于本次操作，避免旧刷新覆盖新操作的错误或账号状态。
   await load();
  }
  catch(e){setError(String(e));}
  finally{setBusy(false);setProgress('');running.current=false;}
 }
 async function waitJob<T>(method:string,args:Record<string,unknown>,timeoutMs=600000):Promise<T>{
  const started=Date.now();
  const task=await api<{job:string}>(method,args);
  for(;;){
   const state=await api<{status:string;error?:string;result?:T}>('job',{job:task.job});
   if(state.status==='failed')throw Error(state.error);
   if(state.status==='done')return state.result as T;
   if(Date.now()-started>timeoutMs)throw Error(`等待超时（${Math.round(timeoutMs/1000)} 秒），后台任务可能仍在运行，请稍后刷新确认`);
   await new Promise(r=>setTimeout(r,400));
  }
 }

 const closeEditor=()=>{if(running.current)return;setEditor(null);setValues({});setConfirmDelete('');setError('');};
 const openEditor=(item?:Account)=>{
  setEditor(item||'new');setBroker(item?.broker||specs[0]?.id||'');setAccount(item?.account||'');setLabel(item?.label||'');setValues({});setConfirmDelete('');setError('');
 };
 useEffect(()=>{
  if(!editor)return;
  const prior=document.activeElement as HTMLElement|null;
  const frame=requestAnimationFrame(()=>document.querySelector<HTMLElement>('.broker-editor input,.broker-editor select')?.focus());
  const key=(e:KeyboardEvent)=>{
   if(e.key==='Escape'&&!running.current)closeEditor();
   if(e.key==='Tab'){
    const items=Array.from(document.querySelectorAll<HTMLElement>('.broker-editor button:not(:disabled),.broker-editor input:not(:disabled),.broker-editor select:not(:disabled)'));
    const first=items[0],last=items.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
   }
  };
  document.addEventListener('keydown',key);
  return()=>{cancelAnimationFrame(frame);document.removeEventListener('keydown',key);prior?.focus();};
 },[!!editor]);
 const save=()=>run(async()=>{
  const updating=editor!=='new';
  if(!updating&&accounts.some(item=>item.broker===broker&&item.account===account))throw Error('该账户已绑定，请在“管理”中更新信息');
  await api('broker_account_save',{broker,account,label,values});
  setEditor(null);setAccount('');setLabel('');setValues({});
  setNote(updating?'账户信息已更新':'账户已添加，可前往持仓与策略同步持仓');
 },'');
 const remove=(item:Account)=>{
  if(confirmDelete!==item.id){setConfirmDelete(item.id);return;}
  void run(async()=>{
   await api('broker_account_delete',{id:item.id});
   setEditor(null);setValues({});setConfirmDelete('');
  },'已解除账户绑定');
 };
 const verifyConnection=(item:Account)=>run(async()=>{
  setProgress('正在连接并核对账户…');
  const r=await waitJob<{account_verified?:boolean;logged_in?:boolean}>('broker_ready',{id:item.id},120000);
  if(r.account_verified!==true||r.logged_in===false)throw Error('账户尚未通过核对，请在券商App中检查登录状态');
  setNote(`${item.broker_name} ${item.account_masked} · 连接正常，账户已核对`);
 },'');
 const preview=()=>run(async()=>{
  const r=await waitJob<Record<string,unknown>>('broker_preview',{id:selected,side,code,quantity:Number(quantity),price:price||undefined});
  setDetail(JSON.stringify(r,null,1));setNote('委托预览已完成，未提交');
 },'');
 const submit=()=>run(async()=>{
  if(!realOrder)throw Error('请先勾选“我确认这是真实委托”');
  const args={id:selected,side,code,quantity:Number(quantity),price:price||undefined,max_value:Number(maxValue),confirm:true};
  if(!Number.isFinite(args.max_value)||args.max_value<=0)throw Error('请输入有效的金额上限');
  const payload=JSON.stringify(args);
  // 请求返回前保持同一个请求号；断连后不生成新委托号重发。
  if(!submitIntent.current||submitIntent.current.payload!==payload)submitIntent.current={payload,id:crypto.randomUUID()};
  try{
   const r=await waitJob<Record<string,unknown>>('broker_submit',{...args,request_id:submitIntent.current.id});
   const names:Record<string,string>={accepted:'券商已受理',rejected:'券商已拒绝',unknown:'结果待核实，未重复提交',failed:'提交前已停止'};
   const detail=r.message||(r.result as {message?:string}|undefined)?.message;
   setNote(`委托结果：${names[String(r.status)]||String(r.status)}${detail?` · ${detail}`:''}`);
   if(['accepted','rejected','failed'].includes(String(r.status)))submitIntent.current=null;
  }finally{
   setRealOrder(false);
   setExecutions(await api<Execution[]>('broker_requests',{id:selected}));
  }
 },'');
 const reconcile=(item:Execution)=>run(async()=>{
  const id=item.order_id||window.prompt('请输入这笔委托的券商唯一编号。将按所选账户核对已有记录，不发出交易。');
  if(!id)return;
  const result=await waitJob<{message:string}>('broker_reconcile',{account_id:selected,request_id:item.request_id,order_id:id});
  setNote(result.message);setExecutions(await api<Execution[]>('broker_requests',{id:selected}));
 },'');
 const resolve=(item:Execution)=>run(async()=>{
  const orderId=window.prompt('核对券商今日委托后，输入券商委托号；确认未发出则输入“未发出”。');
  if(!orderId)return;
  const explanation=window.prompt('请填写核对依据（至少4字）。');
  if(!explanation)return;
  if(!window.confirm('确认已经在券商核实该请求？此操作仅更新观量执行记录，不会下单或撤单。'))return;
  await waitJob('broker_request_resolve',{request_id:item.request_id,outcome:orderId==='未发出'?'not_sent':'accepted',order_id:orderId==='未发出'?'':orderId,note:explanation,confirm:true});
  submitIntent.current=null;
  setExecutions(await api<Execution[]>('broker_requests',{id:selected}));
 },'核实结果已保存');

 async function fetchOrders():Promise<OrderList>{
  const method=query.endsWith('trades')?'broker_trades':'broker_orders';
  const kind=query.startsWith('history')?'history':'today';
  return waitJob<OrderList>(method,{id:selected,kind});
 }
 function describe(r:OrderList){
  const name=QUERIES.find(q=>q[0]===query)?.[1]||'';
  return `${name} · ${r.count} 条${r.date_range?` · ${r.date_range}`:''}${r.cycle?` · ${r.cycle}`:''} · 可撤 ${r.cancellable_count}`;
 }
 const loadOrders=()=>run(async()=>{
  const r=await fetchOrders();
  setOrders(r.rows);setListInfo(describe(r));setDetail('');
 },'');
 const loadSnapshot=()=>run(async()=>{
  const r=await waitJob<Snapshot>('broker_snapshot',{id:selected});
  setSnapshot(r);
  setListInfo(`资金与持仓已更新 · ${r.positions.length} 个持仓`);
 },'');
 const cancelOne=(row:OrderRow)=>{
  if(!window.confirm(`确认撤销 ${row.name} ${row.direction} ${row.quantity} 股 @${row.price}？`))return;
  run(async()=>{
   const r=await waitJob<Record<string,unknown>>('broker_cancel',{id:selected,code:row.code,side:row.side,dry_run:false,confirm:true});
   setDetail(JSON.stringify(r,null,1));
   const list=await fetchOrders();
   setOrders(list.rows);setListInfo(describe(list));
  },'撤单已提交并复核');
 };
 const cancelAll=()=>{
  if(!window.confirm('确认撤销今天所有可撤委托？'))return;
  run(async()=>{
   const r=await waitJob<Record<string,unknown>>('broker_cancel',{id:selected,scope:'all',dry_run:false,confirm:true});
   setDetail(JSON.stringify(r,null,1));
   const list=await fetchOrders();
   setOrders(list.rows);setListInfo(describe(list));
  },'全部撤单已提交并复核');
 };

 const orderAccount=accounts.find(a=>a.id===selected);
 return <section className="broker-workspace" aria-label="证券账户管理">
  <div className="broker-heading"><div><h2>已绑定账户 <span>{accounts.length}</span></h2><p>管理证券账户与登录信息</p></div><button className="primary" disabled={busy||!specs.length} onClick={()=>openEditor()}>＋ 添加账户</button></div>
  <div className="trading-toast-stack"><TradingFeedback message={note}/>{!editor&&<TradingFeedback message={error} error/>}</div>
  {progress&&!editor&&<div className="broker-operation" role="status">{progress}</div>}
  {accounts.length===0?<div className="card broker-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="40" height="40" aria-hidden="true"><path d="m3 9 9-6 9 6M4 10h16M6 10v9m6-9v9m6-9v9M3 21h18"/></svg><h3>还没有绑定证券账户</h3><p>添加后即可同步持仓、设置自动买卖</p><button className="primary" disabled={!specs.length} onClick={()=>openEditor()}>添加第一个账户</button></div>:<div className="broker-account-grid">{accounts.map(item=><article className="card broker-account-card" key={item.id} aria-label={item.broker_name+' '+item.account_masked}>
   <div className="broker-card-top"><span className={'broker-avatar '+item.broker} aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="23" height="23"><path d="m3 8 9-5 9 5M4 9h16M6 10v8m6-8v8m6-8v8M3 21h18M4 18h16"/></svg></span><div><h3>{item.broker_name}</h3><span className="broker-account-number">{item.account_masked}</span></div><span className={'broker-binding-status '+(!item.password_saved?'needs-attention':'')}>{!item.enabled?'已停用':item.password_saved?'已绑定':'待完善登录信息'}</span></div>
   <div className="broker-card-meta"><span>{item.label||'未设置备注'}</span><span>{item.password_saved?'登录信息已保存':'请补充交易密码'}</span></div>
   <div className="broker-card-actions">{onManagePositions&&<button disabled={busy} onClick={()=>onManagePositions(item.id)}>查看持仓</button>}<button disabled={busy} onClick={()=>openEditor(item)}>管理</button></div>
  </article>)}</div>}
  <InfoNote label="连接帮助" className="broker-help"><div className="broker-help-grid"><div><strong>检查连接</strong><span>打开券商App，核对并按需恢复这个账户的登录</span></div>{onRestartCore&&<div><strong>恢复本机连接</strong><span>页面一直加载或连接中断时使用</span><button disabled={busy} onClick={()=>run(()=>onRestartCore(),'本机连接已恢复')}>恢复本机连接</button></div>}</div></InfoNote>
  {editor&&<div className="modal-overlay"><form className="card broker-editor" role="dialog" aria-modal="true" aria-labelledby="broker-editor-title" onSubmit={e=>{e.preventDefault();void save();}}>
   <div className="broker-editor-heading"><div><h2 id="broker-editor-title">{editor==='new'?'添加证券账户':'管理账户'}</h2><p>{editor==='new'?'选择券商，填写资金账号与交易密码':editor.broker_name+' · '+editor.account_masked}</p></div><button type="button" aria-label="关闭账户窗口" disabled={busy} onClick={closeEditor}>×</button></div>
   {editor==='new'&&<><label>证券公司<select aria-label="券商" disabled={busy} value={broker} onChange={e=>{setBroker(e.target.value);setValues({});}}>{specs.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{currentSpec?.fields.filter(f=>!f.secret).map(f=><label key={f.key}>{f.label}<input required pattern="[0-9]{4,20}" inputMode="numeric" aria-label={f.label} placeholder="请输入资金账号" disabled={busy} value={account} onChange={e=>setAccount(e.target.value.replace(/\D/g,''))} autoComplete="off"/></label>)}</>}
   <label>账户备注<span className="broker-optional">选填</span><input aria-label="备注" maxLength={40} placeholder="如：长期持仓账户" disabled={busy} value={label} onChange={e=>setLabel(e.target.value)}/></label>
   {currentSpec?.fields.filter(f=>f.secret).map(f=><label key={f.key}>{f.label}<input aria-label={f.label} type="password" autoComplete="new-password" required={editor==='new'||!editor.password_saved} placeholder={editor==='new'?'请输入'+f.label:'已保存，留空保留'} disabled={busy} value={values[f.key]||''} onChange={e=>setValues(old=>({...old,[f.key]:e.target.value}))}/></label>)}
   {editor!=='new'&&<div className="broker-connection-tools"><div><strong>账户连接</strong><span>打开券商App，核对并按需恢复此账户登录</span></div><div><button type="button" disabled={busy||!editor.password_saved} onClick={()=>verifyConnection(editor)}>检查连接</button></div></div>}
   {progress&&<div className="broker-operation" role="status">{progress}</div>}
   {error&&<div className="broker-error" ref={errorRef} role="alert">{error}</div>}
   {editor!=='new'&&confirmDelete===editor.id&&<div className="broker-unbind-confirm"><strong>解除 {editor.account_masked} 的绑定？</strong><p>将移除观量中的登录信息，不影响券商账户和资产。</p><button type="button" disabled={busy} onClick={()=>remove(editor)}>确认解除绑定</button><button type="button" disabled={busy} onClick={()=>setConfirmDelete('')}>保留绑定</button></div>}
   <div className="broker-editor-actions">{editor!=='new'&&confirmDelete!==editor.id&&<button type="button" className="broker-unbind" disabled={busy} onClick={()=>remove(editor)}>解除绑定</button>}<button type="button" disabled={busy} onClick={closeEditor}>取消</button><button className="primary" disabled={busy||!account}>{busy?'处理中…':editor==='new'?'添加账户':'保存更改'}</button></div>
  </form></div>}
  <details className="trading-manual-tools"><summary>其他工具 <span>手动委托与查询</span></summary>
  <h3>下单（默认只预览）</h3>
  <div className="form-row" style={{flexWrap:'wrap'}}>
   <select aria-label="账号" disabled={busy} value={selected} onChange={e=>setSelected(e.target.value)}>
    {accounts.map(a=><option key={a.id} value={a.id}>{a.broker_name} {a.account_masked}</option>)}
   </select>
   <select aria-label="方向" value={side} onChange={e=>setSide(e.target.value as 'buy'|'sell')}>
    {SIDES.map(([id,text])=><option key={id} value={id}>{text}</option>)}
   </select>
   <input aria-label="股票代码" placeholder="6 位代码" value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,'').slice(0,6))}/>
   <input aria-label="数量" placeholder="数量（股）" value={quantity} onChange={e=>setQuantity(e.target.value.replace(/\D/g,''))}/>
   <input aria-label="价格" placeholder="价格（留空用现价）" value={price} onChange={e=>setPrice(e.target.value)}/>
  </div>
  <div className="form-row">
   <button disabled={busy||!orderAccount||!code||!quantity} onClick={preview}>预览（不提交）</button>
   <label className="setting"><span>单笔金额上限（元）</span><input aria-label="金额上限" value={maxValue} onChange={e=>setMaxValue(e.target.value.replace(/[^\d.]/g,''))}/></label>
  </div>
  <label className="setting"><span>我确认这是真实委托<small>提交前核对账号、方向、价格、数量及金额上限；结果不明时停止重复提交</small></span>
   <input type="checkbox" checked={realOrder} onChange={e=>setRealOrder(e.target.checked)}/></label>
  <button className="primary" disabled={busy||!realOrder||!orderAccount?.supports_order||!code||!quantity||executions.some(e=>['prepared','sending','unknown'].includes(e.status))} onClick={submit}>真实提交</button>
  {executions.length>0&&<div className="table-scroll"><table><thead><tr><th>执行时间</th><th>请求号</th><th>状态</th><th>核实</th></tr></thead><tbody>{executions.map(e=><tr key={e.request_id}><td>{e.created_at}</td><td>{e.request_id}</td><td>{({prepared:'已登记，需核实',sending:'已开始提交，待核实',unknown:'结果未知',accepted:'已受理',rejected:'已拒绝',failed:'提交前停止',not_sent:'人工确认未发出',preview:'仅预览',filled:'已成交',partial:'部分成交',cancelled:'已撤销'} as Record<string,string>)[e.status]||e.status}{e.order_id&&<small>委托号 {e.order_id}</small>}{e.verification&&<small>{e.verification.origin==='broker_auto'?'券商自动核实':'人工核实'} · 成交 {e.verification.filled} 股</small>}{e.reconciliation&&<small>{e.reconciliation.message}</small>}</td><td>{orderAccount?.supports_order_report!==false&&['accepted','unknown','partial'].includes(e.status)&&<button disabled={busy} onClick={()=>reconcile(e)}>刷新券商回报</button>}{['prepared','sending','unknown'].includes(e.status)&&<button disabled={busy} onClick={()=>resolve(e)}>人工核实</button>}</td></tr>)}</tbody></table></div>}

  <h3>委托 / 成交 / 持仓</h3>
  <p>查询读取交易主页当前可见列表。自动撤单暂不可用，请在券商 App 内选择具体委托撤销。</p>
  <div className="form-row" style={{flexWrap:'wrap'}}>
   <select aria-label="查询类型" disabled={busy} value={query} onChange={e=>{setQuery(e.target.value as typeof QUERIES[number][0]);setOrders([]);setListInfo('');}}>
    {QUERIES.map(([id,text])=><option key={id} value={id}>{text}</option>)}
   </select>
   <button disabled={busy||!orderAccount||!orderAccount.supports_query} onClick={loadOrders}>查询</button>
   <button disabled={busy||!orderAccount||!orderAccount.supports_query} onClick={loadSnapshot}>资金与持仓</button>
   {orderAccount?.supports_cancel&&<button disabled={busy||!orders.some(r=>r.cancellable)} onClick={cancelAll}>全部撤单</button>}
  </div>
  {orderAccount&&!orderAccount.supports_query&&<p className="muted">{orderAccount.broker_name} 的委托/成交/撤单还没适配，暂时只能登录。</p>}
  {listInfo&&<p className="muted">{listInfo}</p>}
  {orders.length>0&&<div className="table-scroll"><table>
   <thead><tr><th>时间</th><th>名称</th><th>代码</th><th>方向</th><th>价格</th><th>数量 / 成交</th><th>状态</th><th>操作</th></tr></thead>
   <tbody>{orders.map((row,index)=><tr key={`${row.code}-${row.time}-${index}`} style={{cursor:'default'}}>
    <td className="amounts">{row.date} {row.time}</td>
    <td>{row.name}</td>
    <td className="amounts">{row.code}</td>
    <td>{row.direction}</td>
    <td className="amounts">{row.price??'—'}</td>
    <td className="amounts">{row.quantity??'—'}{row.kind==='order'&&row.filled!=null?` / ${row.filled}`:''}</td>
    <td>{row.state||'—'}</td>
    <td>{row.cancellable&&orderAccount?.supports_cancel?<button disabled={busy} onClick={()=>cancelOne(row)}>撤单</button>:'—'}</td>
   </tr>)}</tbody>
  </table></div>}
  {snapshot&&<>
   <div className="form-row" style={{flexWrap:'wrap',gap:18}}>
    {FUND_LABELS.map(([key,text])=><span key={key} className="chip">{text} {snapshot.funds[key]||'—'}</span>)}
   </div>
   <div className="table-scroll"><table>
    <thead><tr>{POSITION_COLUMNS.map(([key,text])=><th key={key}>{text}</th>)}</tr></thead>
    <tbody>{snapshot.positions.map((row,index)=><tr key={index} style={{cursor:'default'}}>
     {POSITION_COLUMNS.map(([key])=><td key={key} className="amounts">{row[key]??'—'}</td>)}
    </tr>)}</tbody>
   </table></div>
   <p className="muted">持仓列表不显示 6 位代码（App 这一列显示的是市值），需要代码请看委托或成交记录。</p>
  </>}
  {detail&&<InfoNote label="操作详情"><pre>{detail}</pre></InfoNote>}
  </details>

 </section>;
}
