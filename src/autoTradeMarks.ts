/** Read-only annotations. Signal/plan/acknowledgement/fill remain distinct. */
export type AutoTradeAccount={id:string;broker_name:string;account_masked:string;buy_enabled:boolean;sell_enabled:boolean};
export type AutoTradePoint={id:string;source?:'automatic'|'broker_cache'|'manual';account_id:string;broker_name:string;account_masked:string;code:string;day:string;side:'buy'|'sell';status:string;mode:string;signal_key?:string;signal_time?:string;reference_price?:number|string;created_at:string;ordered_at?:string;order_price?:number|string;quantity?:number;order_id?:string;filled?:number;fill_price?:number|string;message:string;attempted:boolean;receipt_accepted?:boolean;receipt_message?:string;cache_observed_at?:string;broker_state?:string;reconciliation?:{ok:boolean;message:string};admission?:{allowed:boolean;reason:string}};
export type AutoTradeChart={code:string;day:string;accounts:AutoTradeAccount[];points:AutoTradePoint[]};
export const autoTradeStatus:Record<string,string>={pending:'等待核验，尚未下单',processing:'核验中，尚未下单',sending:'提交中',accepted:'券商已受理，成交尚未回报',unknown:'未收到明确回执',partial:'已核实部分成交',filled:'已核实成交',cancelled:'已核实撤销',rejected:'已拒绝',skipped:'已跳过，未下单',trial:'试运行，未下单',not_sent:'已核实未发出',unrecorded:'没有执行记录'};
export const autoTradePrice=(n:unknown)=>n!==null&&n!==undefined&&Number.isFinite(Number(n))&&Number(n)>0?Number(n):null;
const hasLegacyReceipt=(p:AutoTradePoint)=>p.status==='unknown'&&p.receipt_accepted===true&&!!p.order_id;
export const autoTradeState=(p:AutoTradePoint)=>p.source==='manual'&&p.status==='unknown'?'委托已发送，待手动同步':hasLegacyReceipt(p)?'券商回执已受理，成交尚未回报':autoTradeStatus[p.status]||p.status;
export const submissionNote=(message:string)=>/未完成或待核实委托|此账号有未核实的委托/.test(message)?'旧版本因历史委托状态跳过；此限制现已移除':message;
export function autoTradeRecords(data:AutoTradeChart|undefined,shapes:ReadonlyArray<{key:string;kind:string;time:string;price:number}>,day:string){
 if(!data||data.day!==day)return [];
 const points=[...data.points.filter(p=>p.day===day&&p.code===data.code)];
 // Legacy gaps are explicitly unknown; they must never look like submitted orders.
 for(const s of shapes)for(const a of data.accounts){
  const side=s.kind==='bottom'?'buy':'sell';
  if(!a[side==='buy'?'buy_enabled':'sell_enabled']||points.some(p=>p.account_id===a.id&&p.signal_key===s.key))continue;
  points.push({id:`missing|${a.id}|${s.key}`,account_id:a.id,broker_name:a.broker_name,account_masked:a.account_masked,code:data.code,day,side,status:'unrecorded',mode:'live',signal_key:s.key,signal_time:s.time,reference_price:s.price,created_at:day+'T'+s.time+':00',message:'该信号没有对应执行记录，历史跳过原因未保存。',attempted:false});
 }
 return points.flatMap(p=>{
  const submitted=p.attempted&&['sending','accepted','unknown','partial','filled','cancelled','rejected'].includes(p.status)&&p.mode==='live';
  const brokerFill=p.source==='broker_cache',orderPrice=autoTradePrice(p.order_price),fillPrice=(submitted||brokerFill)&&['filled','partial','cancelled'].includes(p.status)?autoTradePrice(p.fill_price):null;
  const price=((submitted||brokerFill)?fillPrice||orderPrice:null)||autoTradePrice(p.reference_price);if(price===null)return [];
  const recordedTime=((submitted||brokerFill)?p.ordered_at?.slice(11,16):null)||p.signal_time||p.created_at.slice(11,16);
  if(!/^\d{2}:\d{2}$/.test(recordedTime))return [];
  // The minute chart uses 09:30 and 13:01 as its session anchors. Keep the
  // broker's exact time in the tooltip while anchoring auction/opening fills.
  const time=recordedTime>='09:15'&&recordedTime<'09:30'?'09:30':recordedTime==='13:00'?'13:01':recordedTime;
  return [{point:p,time,price,orderPrice,fillPrice}];
 });
}
/** B/S marks every live automatic submission plus verified broker-side fills; status stays in details. */
export function autoTradeMarks(data:AutoTradeChart|undefined,shapes:ReadonlyArray<{key:string;kind:string;time:string;price:number}>,day:string){
 const lanes=new Map<string,number>();
 return autoTradeRecords(data,shapes,day).filter(m=>m.point.source==='broker_cache'||(m.point.mode==='live'&&m.point.attempted&&['sending','accepted','unknown','partial','filled','cancelled','rejected'].includes(m.point.status)&&m.orderPrice!==null)).map(m=>{
  const key=m.time+'|'+m.point.side,lane=lanes.get(key)||0;lanes.set(key,lane+1);
  const confirmed=m.point.source==='broker_cache'||['accepted','partial','filled','cancelled'].includes(m.point.status)||hasLegacyReceipt(m.point);
  return {...m,label:m.point.side==='buy'?'B':'S',color:m.point.side==='buy'?'#ed6d79':'#4c9fff',opacity:confirmed?1:.55,offset:(m.point.side==='buy'?-1:1)*(26+lane*20)};
 });
}
export function autoTradeDetails(p:AutoTradePoint){
 const order=autoTradePrice(p.order_price),fill=autoTradePrice(p.fill_price),submitted=p.attempted&&p.mode==='live'&&['sending','accepted','unknown','partial','filled','cancelled','rejected'].includes(p.status);
 return [`${p.broker_name} ${p.account_masked} · ${p.source==='broker_cache'?'券商成交':p.source==='manual'?'手动委托':'自动'}${p.side==='buy'?'买入':'卖出'}`,
  `状态：${autoTradeState(p)}`,
  ...(order?[`${p.source==='broker_cache'?'委托价格':submitted?'委托限价':'计划限价'}：${order.toFixed(2)} 元${p.quantity?` · ${p.quantity} 股`:''}`]:p.quantity?[`委托数量：${p.quantity} 股`]:[]),
  ...(p.signal_time?[`信号时间：${p.signal_time}${p.reference_price?` · ${Number(p.reference_price).toFixed(2)} 元`:''}`]:[]),
  ...(p.source==='broker_cache'?[`成交时间：${p.ordered_at?.slice(11,19)||'未记录'}`]:submitted?[`提交时间：${p.ordered_at?.slice(11,19)||'未记录'}`]:[]),
  ...(p.order_id?[`委托编号：${p.order_id}`]:[]),
  ...((submitted||p.source==='broker_cache')&&['filled','partial','cancelled'].includes(p.status)&&p.filled!==undefined&&p.filled>0?[`已核实成交：${p.filled} 股 · ${fill?'均价 '+fill.toFixed(2)+' 元':'成交均价未记录'}`]:[]),
  ...(p.source==='broker_cache'&&p.cache_observed_at?[`缓存更新：${p.cache_observed_at.slice(11,19)}`]:[]),
  ...(p.message?[`说明：${submissionNote(p.message)}`]:[]),
  ...(p.receipt_message?[`券商回包：${p.receipt_message}`]:[]),
 ];
}
