import {useEffect,useRef,useState} from 'react';
export type PaperPoint={code:string;name:string;stamp:string;origin:string;price?:number;side:'buy'|'sell'};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Account={id:string;name:string;initial:number;cash:number;clock:string;realized:number;revision?:number;fees:{commission_wan:string;minimum:number;slippage_bps:string}};
type Position={code:string;name:string;shares:number;available:number;frozen?:number;cost:number;market_value:number;price:number|null;price_time:string;unrealized:number;valuation:string};
type Order={id:string;code:string;name:string;stamp:string;side:'buy'|'sell';shares:number;price:number;amount:number;fees:number;commission:number;stamp_tax:number;transfer:number;realized:number;status:string;filled?:number;reason:string;origin:string;source:string;parent_id?:string;reference_price?:number;fee_settings?:Account['fees']};
type Snapshot={accounts:{id:string;name:string}[];account:Account|null;positions:Position[];orders:Order[];fills?:Order[];order_count?:number;fill_count?:number;history_limit?:number;day_pnl?:{date:string|null;profit:number|null;opening_equity:number|null;reason:string;basis?:string};available_cash?:number;frozen_cash?:number;equity?:number;profit?:number;market_value?:number;unrealized?:number;total_fees?:number};
type Quote={code:string;name:string;stamp:string;price:number;volume:number;source:string;token:string};
const money=(n:number|undefined)=>n===undefined?'—':(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
const statusLabel=(s:string)=>({open:'未成交',partial:'部分成交',filled:'已成交',cancelled:'已撤单',expired:'已到期',rejected:'已拒绝'} as Record<string,string>)[s]||s;
const signed=(n=0)=>(n>0?'+':'')+money(n);
const color=(n=0)=>n>0?'up':n<0?'down':'';
const executed=(o:Order)=>o.filled??(o.status==='filled'?o.shares:0);
function PaperRecordDetails({order:o,kind}:{order:Order;kind:'orders'|'fills'}){
 const [expanded,setExpanded]=useState(false);
 return <details className="paper-record-details" onToggle={e=>setExpanded(e.currentTarget.open)}><summary>详情</summary>{expanded&&<dl>
 <dt>委托编号</dt><dd>{o.parent_id||o.id}</dd>{kind==='fills'&&<><dt>成交编号</dt><dd>{o.id}</dd></>}
 <dt>数据来源</dt><dd>{o.source||'未记录'}</dd><dt>操作入口</dt><dd>{o.origin||'手动'}</dd>
 {o.reference_price!==undefined&&<><dt>参考价格</dt><dd>{money(o.reference_price)} 元</dd></>}
 {kind==='orders'&&executed(o)>0&&<><dt>成交均价</dt><dd>{money(o.amount/executed(o))} 元</dd></>}
 {kind==='orders'&&o.status==='cancelled'&&<><dt>撤销数量</dt><dd>{o.shares-executed(o)} 股</dd></>}
 <dt>佣金</dt><dd>{money(o.commission)} 元</dd><dt>印花税</dt><dd>{money(o.stamp_tax)} 元</dd><dt>过户费</dt><dd>{money(o.transfer)} 元</dd><dt>费用合计</dt><dd>{money(o.fees)} 元</dd>
 {o.fee_settings&&<><dt>佣金参数</dt><dd>万{o.fee_settings.commission_wan}，最低{money(o.fee_settings.minimum)}元</dd><dt>单边滑点</dt><dd>{o.fee_settings.slippage_bps} 基点</dd></>}
 {o.reason&&<><dt>说明</dt><dd>{o.reason}</dd></>}
 </dl>}</details>;
}
export default function PaperTrading({request,point,context,onClosePoint,onOpenStock,onAccountState}:{onAccountState?:(state:{id:string;revision:number}|null)=>void;request:Request;point:PaperPoint|null;context?:PaperPoint;onClosePoint:()=>void;onOpenStock:(code:string,day:string)=>void}){
 const [data,setData]=useState<Snapshot>({accounts:[],account:null,positions:[],orders:[]});
 const [historyLimit,setHistoryLimit]=useState(200);
 const [account,setAccount]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [create,setCreate]=useState(false),[name,setName]=useState('回放账户'),[cash,setCash]=useState(''),[commission,setCommission]=useState('2'),[minimum,setMinimum]=useState('5'),[slip,setSlip]=useState('0');
 const [seed,setSeed]=useState(false),[seedCode,setSeedCode]=useState(''),[seedShares,setSeedShares]=useState('1000'),[seedCost,setSeedCost]=useState('');
 const [replayStamp,setReplayStamp]=useState('');
 useEffect(()=>{if(context)setReplayStamp(context.stamp);},[context?.code,context?.stamp]);
 const [ticket,setTicket]=useState<PaperPoint|null>(null),[quote,setQuote]=useState<Quote|null>(null),[limitPrice,setLimitPrice]=useState(''),[shares,setShares]=useState('1000'),[tab,setTab]=useState('positions'),[filter,setFilter]=useState('');
 const id=useRef(''),sequence=useRef(0),ticketSeq=useRef(0);
 const refresh=async(selected=account)=>{const seq=++sequence.current;const d=await request<Snapshot>('paper_snapshot',selected?{account:selected,history_limit:historyLimit}:{});if(seq!==sequence.current)return;setData(d);onAccountState?.(d.account?{id:d.account.id,revision:d.account.revision||0}:null);if(d.account&&d.account.id!==selected)setAccount(d.account.id);};
 useEffect(()=>{refresh().catch(e=>setError(String(e)));},[account,historyLimit]);
 const open=async(p:PaperPoint)=>{const seq=++ticketSeq.current;setTicket(p);setQuote(null);setError('');id.current=crypto.randomUUID();try{const q=await request<Quote>('paper_quote',{code:p.code,stamp:p.stamp});if(seq===ticketSeq.current){setQuote(q);setLimitPrice(String(p.price||q.price/100));}}catch(e){if(seq===ticketSeq.current)setError(String(e));}};
 useEffect(()=>{if(point)void open(point);},[point]);
 const close=()=>{ticketSeq.current++;setTicket(null);setQuote(null);onClosePoint();};
 const run=async(work:()=>Promise<void>)=>{if(busy)return;setBusy(true);setError('');setNotice('');try{await work();}catch(e){setError(String(e));}finally{setBusy(false);}};
 const submit=()=>run(async()=>{if(!ticket||!quote||!data.account)throw Error('请先创建账户，并等待分钟报价');const result=await request<Order>('paper_order',{account:data.account.id,id:id.current,code:quote.code,stamp:quote.stamp,token:quote.token,side:ticket.side,shares:Number(shares),limit_price:limitPrice,origin:ticket.origin});await refresh(data.account.id);if(result.status==='rejected'){id.current=crypto.randomUUID();throw Error(result.reason);}setNotice(`委托已受理：${result.side==='buy'?'买入':'卖出'} ${result.name} ${result.shares}股，限价${money(result.price)}元，等待后续分钟撮合`);close();});
 const exportCSV=()=>run(async()=>{if(!data.account)return;const exported=await request<Order[]>('paper_export',{account:data.account.id,kind:tab==='fills'?'fills':'orders'});const rows=[['日期时间','股票代码','名称','方向','股数','价格元','金额元','费用元','已实现盈亏元','状态','原因','来源','入口'],...exported.map(o=>[o.stamp,o.code,o.name,o.side==='buy'?'买入':'卖出',o.shares,(o.price/100).toFixed(2),(o.amount/100).toFixed(2),(o.fees/100).toFixed(2),(o.realized/100).toFixed(2),statusLabel(o.status),o.reason,o.source,o.origin])];const text='\ufeff'+rows.map(r=>r.map(v=>'"'+String(v).replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"').join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='模拟交易明细.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 const a=data.account,position=ticket?data.positions.find(p=>p.code===ticket.code):undefined;
 const n=Number(shares);
 
 const amount=Math.round(Number(limitPrice)*100*n),feeEstimate=quote&&a&&n>0?Math.max(Math.round(amount*Number(a.fees.commission_wan)/10000),a.fees.minimum)+Math.round(amount*.00001)+(ticket?.side==='sell'?Math.round(amount*.0005):0):0;
 const orders=(tab==='fills'?(data.fills||[]).filter(o=>o.status==='filled'):data.orders).filter(o=>!filter||`${o.code} ${o.name} ${o.stamp}`.includes(filter));
 return <section className="paper-panel card" aria-label="历史回放模拟交易">
 <div className="paper-heading"><div><h2>模拟交易 <span className="chip amber">历史回放</span></h2><small>账户时间 {a?.clock||'尚未开始'} · 限价委托 · 后续分钟撮合</small></div><div className="paper-actions"><select aria-label="模拟账户" value={a?.id||''} onChange={e=>{setAccount(e.target.value);close();}}>{data.accounts.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select><button onClick={()=>setCreate(!create)}>新建账户</button><button disabled={!a||!!a.clock||data.orders.length>0} onClick={()=>setSeed(!seed)}>期初持仓</button><button onClick={()=>run(()=>refresh())} disabled={busy}>刷新</button></div></div>
 {error&&<div className="notice paper-error" role="alert">{error}</div>}{notice&&<div className="notice" role="status">{notice}</div>}
 {(create||!a)&&<form className="paper-form" onSubmit={e=>{e.preventDefault();void run(async()=>{const d=await request<Account>('paper_create',{name,cash,commission_wan:commission,minimum,slippage_bps:slip});setAccount(d.id);setCreate(false);setCash('');await refresh(d.id);});}}><label>账户名称<input aria-label="模拟账户名称" value={name} onChange={e=>setName(e.target.value)} required maxLength={40}/></label><label>初始资金（元）<input aria-label="模拟初始资金" type="number" min="0.01" max="1000000000" step="0.01" required placeholder="由你填写" value={cash} onChange={e=>setCash(e.target.value)}/></label><label>佣金（万分之）<input aria-label="模拟佣金" type="number" min="0" max="100" step="0.1" value={commission} onChange={e=>setCommission(e.target.value)} required/></label><label>每笔最低佣金（元）<input type="number" min="0" step="0.01" value={minimum} onChange={e=>setMinimum(e.target.value)} required/></label><label>单边滑点（基点，1=0.01%）<input type="number" min="0" max="100" step="0.1" value={slip} onChange={e=>setSlip(e.target.value)} required/></label><button className="primary" disabled={busy}>创建模拟账户</button><small>卖出印花税万5、双边过户费十万1；按含规费佣金试算。参数在本账户内固定，调整请新建账户。</small></form>}
 {a&&<><div className="paper-totals" aria-label="账户概览">{[
 {label:'总资产',value:money(data.equity)},
 {label:'可用资金',value:money(data.available_cash??a.cash),hint:data.frozen_cash?`冻结 ${money(data.frozen_cash)} 元`:undefined},
 {label:'持仓市值',value:money(data.market_value)},
 {label:'当日盈亏',value:data.day_pnl?.profit==null?'暂无':signed(data.day_pnl.profit),change:data.day_pnl?.profit??undefined,title:data.day_pnl?.reason||`回放日期：${data.day_pnl?.date||'尚未开始'}`},
 {label:'累计盈亏',value:signed(data.profit),change:data.profit}
 ].map(card=><div key={card.label} title={card.title||card.value}><span>{card.label}</span><strong className={color(card.change)}>{card.value}</strong>{card.hint&&<small>{card.hint}</small>}</div>)}</div>
 <details className="paper-profit-details"><summary>盈亏详情</summary><div className="paper-profit-grid">
 <span>初始资金 <b>{money(a.initial)} 元</b></span><span>已实现盈亏 <b className={color(a.realized)}>{signed(a.realized)} 元</b></span>
 <span>浮动盈亏 <b className={color(data.unrealized)}>{signed(data.unrealized)} 元</b></span><span>累计费用 <b>{money(data.total_fees)} 元</b></span>
 <span>回放日期 <b>{data.day_pnl?.date||'尚未开始'}</b></span><span>当日期初资产 <b>{data.day_pnl?.opening_equity==null?'暂无':money(data.day_pnl.opening_equity)+' 元'}</b></span>
 </div><p>{data.day_pnl?.reason||data.day_pnl?.basis||'当前账户尚未开始回放'}</p><p>当日盈亏＝当前总资产－当日期初资产；包含交易费用，期初持仓按回放日昨收估值。累计盈亏＝当前总资产－初始资金；卖出按FIFO含买入费用成本计算。</p></details>

 {seed&&<form className="paper-form" onSubmit={e=>{e.preventDefault();void run(async()=>{await request('paper_seed',{account:a.id,code:seedCode,shares:Number(seedShares),cost:seedCost});setSeed(false);await refresh();});}}><label>期初股票代码<input aria-label="期初股票代码" placeholder="sh600000 / sz000001" value={seedCode} onChange={e=>setSeedCode(e.target.value)} required/></label><label>股数<input aria-label="期初股数" type="number" min="1" step="1" value={seedShares} onChange={e=>setSeedShares(e.target.value)} required/></label><label>每股成本（元）<input aria-label="期初成本" type="number" min="0.01" step="0.01" value={seedCost} onChange={e=>setSeedCost(e.target.value)} required/></label><button disabled={busy}>加入期初持仓</button><small>从初始资金按成本扣除，作为回放前已持有的可卖股票；开始回放后不能再补录。</small></form>}
 <div className="paper-toolbar"><div className="tabs"><button className={tab==='positions'?'chosen':''} onClick={()=>setTab('positions')}>持仓明细</button><button className={tab==='orders'?'chosen':''} onClick={()=>setTab('orders')}>委托记录（{data.order_count??data.orders.length}）</button><button className={tab==='fills'?'chosen':''} onClick={()=>setTab('fills')}>成交明细（{data.fill_count??data.fills?.filter(o=>o.status==='filled').length??0}）</button></div><div className="paper-actions">{context&&<><label className="paper-replay-time">回放分钟<input aria-label="模拟回放分钟" type="datetime-local" step="60" value={replayStamp.replace(' ','T')} onChange={e=>setReplayStamp(e.target.value.replace('T',' '))}/></label><button onClick={()=>open({...context,stamp:replayStamp||context.stamp,side:'buy'})}>模拟买入当前股票</button><button onClick={()=>open({...context,stamp:replayStamp||context.stamp,side:'sell'})}>模拟卖出当前股票</button><button disabled={busy} onClick={()=>run(async()=>{await request('paper_advance',{account:a.id,code:context.code,stamp:replayStamp||context.stamp});await refresh();setNotice('已推进账户时间并更新持仓估值');})}>推进账户时间</button></>}<button disabled={!data.orders.length} onClick={exportCSV}>导出明细</button></div></div>
 {tab==='positions'?<div className="table-scroll"><table className="paper-positions"><thead><tr>{['股票','持仓 / 可卖','成本价 / 现价','市值','浮动盈亏','操作'].map(t=><th key={t}>{t}</th>)}</tr></thead><tbody>{data.positions.map(p=><tr key={p.code}>
 <td><button className="paper-stock-link" title="查看分时" onClick={()=>onOpenStock(p.code,a.clock.slice(0,10))}>{p.name}</button><small className="table-code">{p.code.toUpperCase()}</small></td>
 <td>{p.shares} / {p.available}{!!p.frozen&&<small className="table-code">冻结 {p.frozen} 股</small>}</td>
 <td title={`估值时点：${p.price_time||'回放前，按成本暂估'}`}><span>{money(p.cost/p.shares)}</span><small className="table-code">{p.price===null?'现价暂无':`现价 ${money(p.price)}`}</small></td>
 <td>{money(p.market_value)}{p.valuation==='cost_fallback'&&<small className="table-code">按成本暂估</small>}</td>
 <td className={color(p.unrealized)}>{signed(p.unrealized)}<small className="paper-pnl-percent">{p.cost?`${p.unrealized>0?'+':''}${(p.unrealized/p.cost*100).toFixed(2)}%`:'—'}</small></td>
 <td>{context?<div className="paper-actions"><button onClick={()=>open({...context,stamp:replayStamp||context.stamp,code:p.code,name:p.name,side:'buy',origin:'持仓买入'})}>买入</button><button onClick={()=>open({...context,stamp:replayStamp||context.stamp,code:p.code,name:p.name,side:'sell',origin:'持仓卖出'})}>卖出</button></div>:<button onClick={()=>onOpenStock(p.code,a.clock.slice(0,10))}>查看分时</button>}</td>
 </tr>)}</tbody></table>{!data.positions.length&&<p className="paper-empty">暂无持仓。可设置期初持仓，或从分时任意位置发起模拟委托。</p>}</div>:<>
 <input className="paper-search" aria-label="筛选模拟成交" placeholder="股票名称、代码或日期" value={filter} onChange={e=>setFilter(e.target.value)}/>
 <div className="table-scroll"><table className="paper-record-table"><thead><tr>{(tab==='fills'?['时间','股票','方向','成交价 / 数量','成交金额 / 费用','已实现盈亏']:['时间','股票','方向','委托价格','委托 / 已成 / 未成','状态','操作']).map(t=><th key={t}>{t}</th>)}</tr></thead>
 <tbody>{orders.map(o=><tr key={o.id}>
 <td title={o.stamp}>{o.stamp.slice(11)}<small className="table-code">{o.stamp.slice(0,10)}</small></td>
 <td>{o.name}<small className="table-code">{o.code.toUpperCase()}</small>{tab==='fills'&&<PaperRecordDetails order={o} kind="fills"/>}</td>
 <td className={o.side==='buy'?'up':'down'}>{o.side==='buy'?'买入':'卖出'}</td>
 {tab==='fills'?<><td>{money(o.price)}<small className="table-code">{o.shares} 股</small></td><td>{money(o.amount)}<small className="table-code">费用 {money(o.fees)}</small></td><td className={color(o.realized)}>{o.side==='sell'?signed(o.realized):'—'}</td></>:<>
 <td>{money(o.price)}</td><td>{o.shares} / {executed(o)} / {o.shares-executed(o)}</td>
 <td title={o.reason}>{statusLabel(o.status)}</td>
 <td><div className="paper-actions">{['open','partial'].includes(o.status)&&<button disabled={busy} onClick={()=>run(async()=>{await request('paper_cancel',{account:a.id,id:o.id});await refresh();setNotice('已撤销未成交部分，冻结资源已释放');})}>撤单</button>}<PaperRecordDetails order={o} kind="orders"/></div></td>
 </>}
 </tr>)}</tbody></table>{!orders.length&&<p className="paper-empty">暂无记录</p>}</div></>}
 </>}
 {a&&tab!=='positions'&&Math.max(data.order_count||0,data.fill_count||0)>historyLimit&&<div className="paper-history-more"><span>当前最多显示最近{historyLimit}条，导出包含全部历史。</span><button disabled={busy||historyLimit>=5000} onClick={()=>setHistoryLimit(n=>Math.min(5000,n+200))}>加载更多</button></div>}
 <details className="paper-rules-details"><summary>交易口径</summary><p className="paper-footnote">独立模拟账户，不接实盘。任意已结束分钟可挂限价单；提交后下一分钟起按收盘价加滑点判断，单分钟最多参与该成交量1%，优先价格更优的委托。支持部分成交、撤单及当日到期；尾盘集合竞价不撮合，14:57—15:00不接受撤单。缺逐笔盘口，模拟成交不保证真实可成交。回放时间不可倒退，持仓仅用该时点之前的缓存估值；估值时间较早或缺失时请核对。所有记录保存在本机。</p></details>
 {ticket&&<div className="modal-overlay"><section className="card paper-ticket" role="dialog" aria-modal="true" aria-label="模拟买卖确认"><h2>{ticket.side==='buy'?'模拟买入':'模拟卖出'} · {ticket.name}</h2><p>{ticket.code.toUpperCase()} · {ticket.stamp} · {ticket.origin}</p><div className="paper-actions"><button aria-pressed={ticket.side==='buy'} className={ticket.side==='buy'?'primary':''} onClick={()=>{setTicket({...ticket,side:'buy'});id.current=crypto.randomUUID();}}>买入</button><button aria-pressed={ticket.side==='sell'} className={ticket.side==='sell'?'primary':''} onClick={()=>{setTicket({...ticket,side:'sell'});id.current=crypto.randomUUID();}}>卖出</button></div><p>参考分钟价 <strong>{quote?money(quote.price):'读取中…'}</strong> 元 · 后续收盘价满足限价才撮合</p><label>委托限价（元）<input aria-label="模拟委托限价" type="number" min="0.01" step="0.01" value={limitPrice} onChange={e=>{setLimitPrice(e.target.value);id.current=crypto.randomUUID();}}/></label><label>模拟股数<input aria-label="模拟交易股数" type="number" min="1" step="100" value={shares} onChange={e=>{setShares(e.target.value);id.current=crypto.randomUUID();}}/></label><div className="paper-actions">{[100,500,1000].map(n=><button key={n} onClick={()=>{setShares(String(n));id.current=crypto.randomUUID();}}>{n}股</button>)}{ticket.side==='sell'&&<button onClick={()=>{setShares(String(position?.available||0));id.current=crypto.randomUUID();}}>全部可卖</button>}</div><p>可用资金 {money(data.available_cash??a?.cash)} 元 · 当前可卖 {position?.available||0} 股</p><p>冻结预算 {money(amount)} 元 · 费用约 {money(feeEstimate)} 元</p><p className="muted">当日有效；挂单不会立即成交。买入按100股整数倍；零股仅全部卖出。{ticket.stamp<a?.clock!?'所选时间早于账户时间，提交将被拒绝。':''}</p>{!a&&<p>请先关闭交易单，在面板填写初始资金创建账户。</p>}{error&&<div role="alert" className="paper-error">{error}</div>}<div className="paper-actions"><button disabled={busy} onClick={close}>取消</button><button className="primary" disabled={busy||!a||!quote||!Number.isSafeInteger(n)||n<=0} onClick={submit}>{busy?'记账中…':'提交模拟委托'}</button></div></section></div>}
 </section>;
}
