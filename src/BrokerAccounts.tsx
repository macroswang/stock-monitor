import {useEffect,useRef,useState} from 'react';

type Field={key:string;label:string;secret:boolean};
type Spec={id:string;name:string;package:string;fields:Field[];note:string;supports_order:boolean;supports_query:boolean;supports_cancel:boolean};
type Account={id:string;broker:string;broker_name:string;package:string;account:string;account_masked:string;label:string;enabled:boolean;is_default:boolean;password_saved:boolean;supports_order:boolean;supports_query:boolean;supports_cancel:boolean};
type OrderRow={kind:string;name:string;code:string;direction:string;side:'buy'|'sell'|null;date:string;time:string;price:number|null;quantity:number|null;filled:number|null;state:string;cancellable:boolean};
type OrderList={kind:string;date_range:string;cycle:string;count:number;cancellable_count:number;rows:OrderRow[]};
type Snapshot={funds:Record<string,string>;positions:Record<string,string|number>[]};
type Execution={request_id:string;status:string;created_at:string};
type Api=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;

const SIDES=[['sell','卖出'],['buy','买入']] as const;
const QUERIES=[['today_orders','今日委托'],['today_trades','今日成交'],['history_orders','历史委托'],['history_trades','历史成交']] as const;
const FUND_LABELS:Array<[string,string]>=[['total_assets','总资产'],['available','可用'],['withdrawable','可取'],['market_value','总市值'],['position_ratio','总仓位'],['holding_profit','持仓收益'],['today_profit','今日盈亏']];
const POSITION_COLUMNS:Array<[string,string]>=[['name','名称'],['quantity','持仓'],['sellable','可用'],['price','现价'],['cost','成本'],['profit','持仓盈亏'],['market_value','市值']];

export default function BrokerAccounts({api,onRestartCore}:{api:Api;onRestartCore?:()=>Promise<unknown>}){
 const [specs,setSpecs]=useState<Spec[]>([]);
 const [accounts,setAccounts]=useState<Account[]>([]);
 const [error,setError]=useState('');
 const [note,setNote]=useState('');
 const [busy,setBusy]=useState(false);
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
   if(!selected&&a.length)setSelected(a[0].id);
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
  finally{setBusy(false);running.current=false;}
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

 const save=()=>run(async()=>{
  await api('broker_account_save',{broker,account,label,values});
  setAccount('');setLabel('');setValues({});
 },'账号已保存，密码已存入本机凭据文件');
 const remove=(item:Account)=>{
  if(confirmDelete!==item.id){setConfirmDelete(item.id);return;}
  setConfirmDelete('');
  // Drop the row immediately so the list reflects the change even if the
  // refresh is slow or fails.
  setAccounts(old=>old.filter(a=>a.id!==item.id));
  run(async()=>{await api('broker_account_delete',{id:item.id});},'账号已删除');
 };
 const login=(item:Account)=>run(async()=>{
  setNote(`正在打开 ${item.broker_name}，核对当前账号与交易登录状态…`);
  const r=await waitJob<Record<string,unknown>>('broker_login',{id:item.id},120000);
  setNote(`登录结果：${JSON.stringify(r)}`);
 },'');
 const ready=(item:Account)=>run(async()=>{
  const r=await waitJob<Record<string,unknown>>('broker_ready',{id:item.id},120000);
  setNote(`交易状态：${JSON.stringify(r)}`);
 },'');
 const preview=()=>run(async()=>{
  const r=await waitJob<Record<string,unknown>>('broker_preview',{id:selected,side,code,quantity:Number(quantity),price:price||undefined});
  setNote(`预览（未提交）：${JSON.stringify(r)}`);
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
 return <section className="card form-card">
  <h2>券商账号（模拟器自动交易）</h2>
  <p>为每个券商添加一个账号。账号和券商信息保存在本地数据库，密码保存在本机数据目录（文件权限 600，仅当前用户可读），界面只显示是否已保存。</p>
  {onRestartCore&&<div className="form-row"><button disabled={busy} onClick={()=>run(()=>onRestartCore(),"监控进程已重启")}>重启监控进程</button><span className="muted">登录一直转圈、或收到“监控已中断”通知时点这里</span></div>}
  {error&&<div className="notice" ref={errorRef}>{error}</div>}

  <h3>已添加的账号</h3>
  {accounts.length===0&&<p className="muted">还没有账号。选择券商后填写账号和密码。</p>}
  {accounts.map(item=><div key={item.id} className="form-row" style={{alignItems:'center',gap:8,flexWrap:'wrap'}}>
   <strong>{item.broker_name}</strong>
   <span>{item.account_masked}</span>
   {item.label&&<span className="muted">{item.label}</span>}
   <span className={item.password_saved?'chip':'chip'} style={{opacity:item.password_saved?1:.6}}>{item.password_saved?'密码已保存':'密码未保存'}</span>
   {!item.password_saved&&<button disabled={busy} onClick={()=>{setBroker(item.broker);setAccount(item.account);setLabel(item.label);}}>重设密码</button>}
   <button disabled={busy||!item.password_saved} onClick={()=>login(item)}>测试登录</button>
   <button disabled={busy||!item.password_saved} onClick={()=>ready(item)}>检查交易页</button>
   {confirmDelete===item.id
    ?<><button className="primary" disabled={busy} onClick={()=>remove(item)}>确认删除</button><button disabled={busy} onClick={()=>setConfirmDelete('')}>取消</button></>
    :<button disabled={busy} onClick={()=>remove(item)}>删除</button>}
  </div>)}

  <h3>新增账号</h3>
  <div className="form-row" style={{flexWrap:'wrap'}}>
   <select aria-label="券商" value={broker} onChange={e=>{setBroker(e.target.value);setValues({});}}>
    {specs.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
   </select>
   <input aria-label="备注" placeholder="备注（可选）" value={label} onChange={e=>setLabel(e.target.value)} autoComplete="off"/>
  </div>
  {currentSpec&&<>
   <p className="muted">{currentSpec.name} · {currentSpec.package}{currentSpec.note?` · ${currentSpec.note}`:''}</p>
   <div className="form-row">
    {currentSpec.fields.filter(f=>!f.secret).map(f=><input key={f.key} aria-label={f.label} placeholder={f.label}
      value={account} onChange={e=>setAccount(e.target.value.replace(/\D/g,''))} autoComplete="off"/>)}
    {currentSpec.fields.filter(f=>f.secret).map(f=><input key={f.key} aria-label={f.label} type="password" placeholder={f.label} autoComplete="off"
      value={values[f.key]||''} onChange={e=>setValues(old=>({...old,[f.key]:e.target.value}))}/>)}
    <button disabled={busy||!account} onClick={save}>保存账号</button>
   </div>
  </>}

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
  {executions.length>0&&<div className="table-scroll"><table><thead><tr><th>执行时间</th><th>请求号</th><th>状态</th><th>核实</th></tr></thead><tbody>{executions.map(e=><tr key={e.request_id}><td>{e.created_at}</td><td>{e.request_id}</td><td>{({prepared:'已登记，需核实',sending:'已开始提交，待核实',unknown:'结果未知',accepted:'已受理',rejected:'已拒绝',failed:'提交前停止',not_sent:'人工确认未发出',preview:'仅预览'} as Record<string,string>)[e.status]||e.status}</td><td>{['prepared','sending','unknown'].includes(e.status)&&<button disabled={busy} onClick={()=>resolve(e)}>人工核实</button>}</td></tr>)}</tbody></table></div>}

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
  {detail&&<div className="notice"><pre style={{margin:0,whiteSpace:'pre-wrap',fontSize:11}}>{detail}</pre></div>}
  {note&&<div className="notice">{note}</div>}
  <p className="muted">只支持已适配的券商；未适配的券商无法登录或下单。首次使用请先用“测试登录”确认模拟器和 App 都正常。</p>
 </section>;
}
