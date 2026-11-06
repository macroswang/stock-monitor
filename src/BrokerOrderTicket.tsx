import {useEffect,useRef,useState} from 'react';
import type {PaperPoint} from './PaperTrading';
import {maxBuyShares,fractionShares} from './paperTicket';
import {amount} from './tradingSizing';
import {defaultTCosts} from './tCosts';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Account={id:string;broker_name:string;account_masked:string;enabled:boolean;supports_order:boolean};
type Result={status:string;submitted:boolean;request_id:string;message?:string;order_id?:string;result?:{message?:string;order_id?:string}};
type CapacityView={accounts:{id:string;sync_status:string;funds:Record<string,string>;funds_observed_at?:string}[];positions:{account_id:string;code:string;position_verified:boolean;sellable:number;updated_at?:string;rule:{commission_wan:number;minimum_commission:number}}[]};

/** A manual intent sent through the existing durable broker gateway. */
export default function BrokerOrderTicket({request,point,initialPrice,visible=true,onSide,onBusy,onAccepted}:{request:Request;point:PaperPoint;initialPrice:string;visible?:boolean;onSide:(side:'buy'|'sell')=>void;onBusy:(busy:boolean)=>void;onAccepted:(message:string)=>void}){
 const sources=point.brokerSources||[],fixedSource=sources.length===1?sources[0]:undefined;
 const [accounts,setAccounts]=useState<Account[]>([]),[account,setAccount]=useState(fixedSource?.account_id||''),[loading,setLoading]=useState(true);
 const side=point.side;
 const [price,setPrice]=useState(initialPrice),[quantity,setShares]=useState<string|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Result|null>(null);
 const running=useRef(false),intent=useRef<{id:string;args:Record<string,unknown>}|null>(null);
 const [capacity,setCapacity]=useState<{account:string;data:CapacityView}|null>(null),[syncing,setSyncing]=useState(false);
 const capacitySeq=useRef(0),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;capacitySeq.current++;};},[]);
 useEffect(()=>{let active=true;request<Account[]>('broker_accounts').then(rows=>{if(active){setAccounts(rows.filter(a=>a.enabled&&a.supports_order&&(!sources.length||sources.some(s=>s.account_id===a.id))));setLoading(false);}}).catch(e=>{if(active){setError(String(e));setLoading(false);}});return()=>{active=false;};},[request]);
 const selected=accounts.find(a=>a.id===account),cents=Math.round(Number(price)*100);
 const validPrice=Number.isSafeInteger(cents)&&cents>0&&Number(price)===cents/100;
 const locked=busy||intent.current!==null;
 const edit=(change:()=>void)=>{if(locked)return;change();setError('');setResult(null);};
 const readCapacity=async()=>{
  if(!mounted.current)return;
  const seq=++capacitySeq.current;
  try{const data=await request<CapacityView>('trading_view');if(mounted.current&&seq===capacitySeq.current)setCapacity({account,data});}catch{/* Keep the last successful snapshot; an unavailable balance is not zero. */}
 };
 useEffect(()=>{setCapacity(null);capacitySeq.current++;if(!selected||!visible)return;void readCapacity();const timer=setInterval(()=>void readCapacity(),5000);return()=>{capacitySeq.current++;clearInterval(timer);};},[account,!!selected,visible]);
 const view=capacity?.account===account?capacity.data:null,accountData=view?.accounts.find(a=>a.id===account),position=view?.positions.find(p=>p.account_id===account&&p.code===point.code);
 const cash=amount(accountData?.funds.available),cashCents=cash!==null&&cash>=0?Math.round(cash*100):null;
 const increment=point.code.startsWith('sh688')?1:100,minimumShares=increment===1?200:100;
 const sellable=position?.position_verified?(Number.isSafeInteger(position.sellable)&&position.sellable>=0?position.sellable:null):accountData?.sync_status==='complete'?0:null;
 const available=!selected?null:side==='sell'?sellable:cashCents!==null&&validPrice?maxBuyShares(cashCents,cents,position?.rule.commission_wan??defaultTCosts.commissionWan,Math.round((position?.rule.minimum_commission??defaultTCosts.minimum)*100),increment,minimumShares):null;
 // Until explicitly edited, default to this account's available quantity.
 const shares=quantity??(available===null?'':String(available)),n=Number(shares);
 const validAmount=Number.isSafeInteger(n)&&n>0&&validPrice&&Number.isSafeInteger(cents*n);
 const valid=!!selected&&validAmount;
 const syncCapacity=async()=>{
  if(!selected||syncing||locked)return;setSyncing(true);setError('');
  try{const task=await request<{job:string}>('trading_sync',{account_id:account}),start=Date.now();for(;;){if(!mounted.current)return;const state=await request<{status:string;error?:string}>('job',{job:task.job});if(state.status==='failed')throw Error(state.error||'账户同步失败');if(state.status==='done'){await readCapacity();break;}if(Date.now()-start>600000)throw Error('账户同步仍未结束，请稍后核对');await new Promise(resolve=>setTimeout(resolve,400));}}
  catch(e){if(mounted.current)setError(String(e));}finally{if(mounted.current)setSyncing(false);}
 };
 const submit=async()=>{
  if(running.current||!valid||intent.current)return;
  running.current=true;setBusy(true);onBusy(true);setError('');setResult(null);setShares(shares);
  // Freeze both parameters and identity before the first IPC call. A lost
  // response must never turn the same click into another broker request.
  const args={id:account,side,code:point.code.slice(2),quantity:n,price:(cents/100).toFixed(2),max_value:cents*n/100,confirm:true,dry_run:false};
  const pending={id:crypto.randomUUID(),args};intent.current=pending;
  try{
   const task=await request<{job:string}>('broker_submit',{...pending.args,request_id:pending.id});
   const started=Date.now();
   for(;;){
    const state=await request<{status:string;error?:string;result?:Result}>('job',{job:task.job});
    if(state.status==='failed')throw Error(state.error||'后台委托任务失败');
    if(state.status==='done'){
     let outcome=state.result;if(!outcome)throw Error('未收到委托结果');
     if(outcome.status==='accepted'&&outcome.submitted!==true)outcome={...outcome,status:'unknown'};
     setResult(outcome);
     if(outcome.status==='accepted'&&outcome.submitted===true){
      onAccepted(`真实委托：${selected!.broker_name} ${selected!.account_masked} · ${side==='buy'?'买入':'卖出'} ${point.name} ${n} 股，限价 ${(cents/100).toFixed(2)} 元 · 券商已受理，成交待回报`);
     }else if(['failed','rejected'].includes(outcome.status)){
      intent.current=null;
     }
     break;
    }
    if(Date.now()-started>600000)throw Error('等待委托结果超时');
    await new Promise(resolve=>setTimeout(resolve,400));
   }
  }catch(e){setError(`${String(e)}；结果待核实，请在证券账户的委托记录中核对，不要重复提交。请求号：${pending.id}`);}
  finally{running.current=false;setBusy(false);onBusy(false);}
 };
 const direction=side==='buy'?'买入':'卖出';
 return <div className={side==='buy'?'ticket-buy':'ticket-sell'}>
  {fixedSource?<div className="ticket-row"><span className="ticket-label">账户</span><span className="ticket-account" aria-label="真实委托券商账户">{fixedSource.broker_name} {fixedSource.account_masked}</span></div>:<div className="ticket-row"><label className="ticket-label" htmlFor="broker-ticket-account">账户</label><select id="broker-ticket-account" aria-label="真实委托券商账户" value={account} disabled={locked||syncing} onChange={e=>edit(()=>{setAccount(e.target.value);setShares(null);})}><option value="">请选择券商账户</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.broker_name} {a.account_masked}</option>)}</select></div>}
  {!loading&&!accounts.length&&!error&&<div className="ticket-warning">{sources.length?'来源账户已停用或暂不支持下单，请核对证券账户。':'暂无可下单的券商账户，请先在证券账户中绑定。'}</div>}
  <div className="ticket-row"><span className="ticket-label">方向</span><div className="ticket-direction">{(['buy','sell'] as const).map(value=><button key={value} aria-pressed={side===value} disabled={locked} onClick={()=>edit(()=>{if(value!==side){onSide(value);setShares(null);}})}>{value==='buy'?'买入':'卖出'}</button>)}</div></div>
  <div className="ticket-row"><span className="ticket-label">股票</span><div className="ticket-stock"><strong>{point.code.slice(2)}</strong><span>{point.name}</span></div></div>
  <div className="ticket-row"><label className="ticket-label" htmlFor="broker-ticket-price">价格</label><div className="ticket-stepper"><button aria-label="降低委托价格" disabled={locked||cents<=1||!Number.isFinite(cents)} onClick={()=>edit(()=>setPrice(((cents-1)/100).toFixed(2)))}>−</button><input id="broker-ticket-price" autoFocus aria-label="真实委托限价" type="number" min="0.01" step="0.01" value={price} disabled={locked} onChange={e=>edit(()=>setPrice(e.target.value))}/><button aria-label="提高委托价格" disabled={locked||!Number.isFinite(cents)} onClick={()=>edit(()=>setPrice(((cents+1)/100).toFixed(2)))}>＋</button></div></div>
  <div className="ticket-available" aria-label="可买卖数量" title={`按本账户最近同步数据${accountData?.funds_observed_at?' · '+accountData.funds_observed_at.slice(0,19).replace('T',' '):''}${cash!==null?' · 可用资金 '+cash.toFixed(2)+' 元':''}`}><span>{side==='buy'?'可买':'可卖'} <strong>{!selected?'待选账户':available!==null?available.toLocaleString('zh-CN')+' 股':side==='buy'&&!validPrice?'待填写价格':'待同步'}</strong></span><button className="ticket-capacity-refresh" aria-label="同步可买卖数量" title="同步本券商账户" disabled={!selected||syncing||locked} onClick={()=>void syncCapacity()}>{syncing?'同步中…':'↻'}</button></div>
  <div className="ticket-row"><label className="ticket-label" htmlFor="broker-ticket-shares">数量</label><div className="ticket-stepper"><button aria-label="减少委托数量" disabled={locked||n<=100} onClick={()=>edit(()=>setShares(String(Math.max(100,Math.floor(n/100)*100-100))))}>−</button><input id="broker-ticket-shares" aria-label="真实委托股数" type="number" min="1" step="100" value={shares} disabled={locked} onChange={e=>edit(()=>setShares(e.target.value))}/><button aria-label="增加委托数量" disabled={locked} onClick={()=>edit(()=>setShares(String(Math.max(100,Math.floor((n||0)/100)*100+100))))}>＋</button></div></div>
  <div className="ticket-fractions">{[[1,'全仓'],[2,'1/2仓'],[3,'1/3仓'],[4,'1/4仓']].map(([divisor,label])=><button key={divisor} disabled={locked||syncing||available===null||fractionShares(available,Number(divisor),increment,minimumShares)<=0} onClick={()=>edit(()=>setShares(String(fractionShares(available!,Number(divisor),increment,minimumShares))))}>{label}</button>)}</div>
  <div className="ticket-estimate">委托金额 <b>{validAmount?`${(cents*n/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})} 元`:'待填写'}</b></div>
  {result&&<div role="status" className="ticket-warning">{({accepted:'券商已受理，成交待回报',rejected:'券商已拒绝',failed:'提交前已停止',unknown:'未收到明确回执，请到证券账户核对，不要重复提交'} as Record<string,string>)[result.status]||'委托结果待核实，请到证券账户核对'}{(result.message||result.result?.message)&&`：${result.message||result.result?.message}`}</div>}
  {error&&<div role="alert" className="paper-error ticket-warning">{error}</div>}
  <div className="ticket-submit-row"><span/><button className="ticket-submit" disabled={locked||!valid} onClick={()=>void submit()}>{busy?'提交中…':`确认${direction}`}</button></div>
 </div>;
}
