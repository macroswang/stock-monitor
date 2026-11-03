/** Read-only annotations. Signal/plan/acknowledgement/fill remain distinct. */
export type AutoTradeAccount={id:string;broker_name:string;account_masked:string;buy_enabled:boolean;sell_enabled:boolean};
export type AutoTradePoint={id:string;account_id:string;broker_name:string;account_masked:string;code:string;day:string;side:'buy'|'sell';status:string;mode:string;signal_key?:string;signal_time?:string;reference_price?:number|string;created_at:string;ordered_at?:string;order_price?:number|string;quantity?:number;order_id?:string;filled?:number;fill_price?:number|string;message:string;attempted:boolean;receipt_message?:string;reconciliation?:{ok:boolean;message:string};admission?:{allowed:boolean;reason:string}};
export type AutoTradeChart={code:string;day:string;accounts:AutoTradeAccount[];points:AutoTradePoint[]};
export const autoTradeStatus:Record<string,string>={pending:'等待核验，尚未下单',processing:'核验中，尚未下单',sending:'提交中，结果待核实',accepted:'已受理，尚未确认成交',unknown:'提交结果待核实',partial:'已核实部分成交',filled:'已核实成交',cancelled:'已核实撤销',rejected:'已拒绝',skipped:'已跳过，未下单',trial:'试运行，未下单',not_sent:'已核实未发出',unrecorded:'没有执行记录'};
export const autoTradePrice=(n:unknown)=>n!==null&&n!==undefined&&Number.isFinite(Number(n))&&Number(n)>0?Number(n):null;
export function autoTradeMarks(data:AutoTradeChart|undefined,shapes:ReadonlyArray<{key:string;kind:string;time:string;price:number}>,day:string){
 if(!data||data.day!==day)return [];
 const points=[...data.points.filter(p=>p.day===day&&p.code===data.code)];
 // Legacy gaps are explicitly unknown; they must never look like submitted orders.
 for(const s of shapes)for(const a of data.accounts){
  const side=s.kind==='bottom'?'buy':'sell';
  if(!a[side==='buy'?'buy_enabled':'sell_enabled']||points.some(p=>p.account_id===a.id&&p.signal_key===s.key))continue;
  points.push({id:`missing|${a.id}|${s.key}`,account_id:a.id,broker_name:a.broker_name,account_masked:a.account_masked,code:data.code,day,side,status:'unrecorded',mode:'live',signal_key:s.key,signal_time:s.time,reference_price:s.price,created_at:day+'T'+s.time+':00',message:'该信号没有对应执行记录，历史跳过原因未保存。',attempted:false});
 }
 const lanes=new Map<string,number>();
 return points.flatMap(p=>{
  const submitted=p.attempted&&['sending','accepted','unknown','partial','filled','cancelled','rejected'].includes(p.status)&&p.mode==='live';
  const orderPrice=autoTradePrice(p.order_price),fillPrice=submitted&&['filled','partial','cancelled'].includes(p.status)?autoTradePrice(p.fill_price):null;
  const price=(submitted?fillPrice||orderPrice:null)||autoTradePrice(p.reference_price);if(price===null)return [];
  const time=(submitted?p.ordered_at?.slice(11,16):null)||p.signal_time||p.created_at.slice(11,16);
  if(!/^\d{2}:\d{2}$/.test(time))return [];
  const side=p.side==='buy'?'买':'卖',kind=p.mode==='trial'?'演练':p.status==='unrecorded'?'无记录':p.status==='skipped'||p.status==='not_sent'?'跳过':p.status==='rejected'?'拒绝':p.status==='cancelled'?'撤销':p.status==='filled'?'成':p.status==='partial'?'部成':p.status==='accepted'?'单':p.status==='unknown'?'?':p.status==='sending'?'…':'待';
  const label=side+kind+(['单','成','部成','?','…'].includes(kind)?` ${price.toFixed(2)}${['成','部成'].includes(kind)&&fillPrice===null?'限':''}`:'');
  const color=kind==='?'||kind==='…'?'#e8b85e':kind==='成'||kind==='部成'?'#63d2b7':kind==='单'?'#8bbcff':'#9baac0';
  const key=time+'|'+p.side,lane=lanes.get(key)||0;lanes.set(key,lane+1);
  return [{point:p,time,price,orderPrice,fillPrice,label,color,offset:(p.side==='buy'?-1:1)*(26+lane*20)}];
 });
}
export function autoTradeDetails(p:AutoTradePoint){
 const order=autoTradePrice(p.order_price),fill=autoTradePrice(p.fill_price),submitted=p.attempted&&p.mode==='live'&&['sending','accepted','unknown','partial','filled','cancelled','rejected'].includes(p.status);
 return [`${p.broker_name} ${p.account_masked} · 自动${p.side==='buy'?'买入':'卖出'}`,
  `状态：${autoTradeStatus[p.status]||p.status}`,
  ...(order?[`${submitted?'委托限价':'计划限价'}：${order.toFixed(2)} 元${p.quantity?` · ${p.quantity} 股`:''}`]:[]),
  ...(p.signal_time?[`信号确认：${p.signal_time}${p.reference_price?` · ${Number(p.reference_price).toFixed(2)} 元`:''}`]:[]),
  ...(submitted?[`提交核验：${p.ordered_at?.slice(11,19)||'时间待核实'}`]:[]),
  ...(p.order_id?[`委托编号：${p.order_id}`]:[]),
  ...(submitted&&['filled','partial','cancelled'].includes(p.status)&&p.filled!==undefined&&p.filled>0?[`已核实成交：${p.filled} 股 · ${fill?'均价 '+fill.toFixed(2)+' 元':'成交均价未记录'}`]:[]),
  ...(p.message?[`说明：${p.message}`]:[]),
  ...(p.receipt_message?[`券商回包：${p.receipt_message}`]:[]),
  ...(p.reconciliation&&!p.reconciliation.ok?[`回报核实：${p.reconciliation.message}`]:[])];
}
