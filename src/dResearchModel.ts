export const researchScenarios={gross:'不计成本',fees:'仅手续费',primary:'手续费＋常规滑点',stress:'手续费＋压力滑点',delay:'常规滑点＋额外1分钟',delay_stress:'压力滑点＋额外1分钟'} as const;
export type ResearchScenario=keyof typeof researchScenarios;
export type ResearchSlot='D'|'U'|'S'|'S_L1'|'S_LQ';
export type SupplementSlot='S'|'S_L1'|'S_LQ';
export type ResearchMode='P'|'U'|'I';
export type ResearchMetric={n:number;win_rate:number|null;mean_net_pct:number|null;net_cny:number;dates?:number;mean_without_best_date_pct?:number|null};
export type ResearchTrade={status:string;signal_time:string;candidate_time:string;candidate_price:number;entry_time:string;exit_time:string|null;entry_index:number|null;exit_index:number|null;entry_reference:number|null;exit_reference:number|null;buy_fill:number|null;sell_fill:number|null;net_pct:number|null;net_cny:number|null;fees_cny:number|null;slippage_cny:number|null;opposite_confirmation:string|null;exit_reason:string|null;execution_flags:string[]|null};
export type ResearchFeature={index_known:boolean;index_5_pct:number|null;index_below_sma20:boolean|null;stock_5_pct:number;relative_5_pct_points:number|null;close_below_sma5:boolean;last2_volume_vs_precandidate5:number|null;current_minute_shares:number;prior5_mean_shares:number;known_through:string;index_last_observed:string|null};
export type ResearchDecision={time:string;key:string;c1:boolean;passed:boolean|null;lag:number;features:ResearchFeature};
export type ResearchAction={slot:string;index:number;time:string;side:'sell'|'buy';qty:number;fill:number;fee:number;cash_delta:number;sellable:number;holdings:number;cash:number};
export type ResearchAccount={initial_qty:number;net_cny:number|null;cash_buffer_needed:number;both_fills_within_1pct:boolean;actions:ResearchAction[]};
export type ResearchCase={id:string;code:string;name:string;day:string;tags:string[];price:number[];volume:number[];average:number[];previousClose:number|null;index:{previousClose:number;price:(number|null)[]}|null;
 shapes:{key:string;kind:'bottom'|'top';time:string;price:number;candidateTime:string;candidatePrice:number}[];
 decisions:ResearchDecision[];weakTimes:string[];oldJ:{signal:string|null;net_pct:number|null;cause:string;features:ResearchFeature}|null;
 selection:Record<string,{state:string;stop_time:string|null}>;
 trades:Record<ResearchSlot,Record<ResearchScenario,ResearchTrade|null>>;
 accounts:Record<string,Record<ResearchScenario,ResearchAccount>>};
export type ResearchBundle={schemaVersion:number;id:string;times:string[];meta:{date:string;start:string;end:string;stockdays:number;stocks:number;dates:number;caseCount:number;missingPreviousClose:number;normalizableStockdays:number;quantityPerSlot:number;newDates:number;frozen:boolean};
 metrics:Record<ResearchSlot,Record<ResearchScenario,ResearchMetric>>;daily:(ResearchMetric&{day:string;slot:ResearchSlot;scenario:ResearchScenario})[];
 resourceMetrics:Record<string,Record<ResearchScenario,{stockdays:number;normalizable_stockdays:number;net_cny:number;mean_fixed_stockday_inventory_pct:number;max_cash_buffer_per_stockday:number}>>;
 gates:Record<string,boolean>;verification:{D_primary_ge2pct_winners_preserved:number;shared_U_changes:number;shared_U_big_entries_changed:number;independent_costs:number;independent_timing:number};sources:Record<string,string>;cases:ResearchCase[]};

export function validateResearchBundle(value:unknown):asserts value is ResearchBundle{
 const b=value as ResearchBundle;
 if(b?.schemaVersion!==1||b.id!=='D-reserved-supplement-20261025'||b.meta?.frozen!==false||!Array.isArray(b.cases)||b.cases.length!==b.meta.caseCount||b.times?.length!==240)throw Error('研究快照版本或完整性不符');
 if(new Set(b.cases.map(c=>c.id)).size!==b.cases.length||b.cases.filter(c=>c.tags.includes('harm')).length!==14||b.cases.filter(c=>c.tags.includes('S')).length!==21)throw Error('重点样本数量不符');
 for(const c of b.cases){
  if([c.price,c.volume,c.average].some(a=>!Array.isArray(a)||a.length!==240||a.some(n=>!Number.isFinite(n)))||c.price.some(p=>p<=0)||c.volume.some(v=>v<0))throw Error('研究分时数据不完整');
  if(!c.accounts?.P||!c.accounts?.U||!c.accounts?.I)throw Error('库存对照缺失');
 }
}

export function accountKey(mode:ResearchMode,slot:SupplementSlot){return mode==='I'?{S:'I',S_L1:'I_L1',S_LQ:'I_LQ'}[slot]:mode;}
export function tradeStage(t:ResearchTrade|null,cursor:number,times:string[]):'none'|'future'|'pending'|'open'|'closed'|'unfilled'{
 // An empty full-day trade must not tell an early replay that no signal will
 // ever occur. Only the fixed 14:54 admission cutoff makes that knowable.
 if(!t)return cursor<233?'future':'none';
 if(times.indexOf(t.signal_time)>cursor)return 'future';
 if(t.status!=='price_proxy')return 'unfilled';
 if(t.entry_index===null||t.entry_index>cursor)return 'pending';
 return t.exit_index!==null&&t.exit_index<=cursor?'closed':'open';
}
export type ResearchMarker={time:string;price:number;label:string;detail:string;color:string;hollow:boolean;kind:'signal'|'fill'|'cover'|'rejected'};
export function researchMarkers(c:ResearchCase,scenario:ResearchScenario,mode:ResearchMode,slot:SupplementSlot,cursor:number,times:string[],showD=true,showS=true,showFills=false):ResearchMarker[]{
 const result:ResearchMarker[]=[];
 const d=c.trades.D[scenario],s=c.trades[slot][scenario],u=c.trades.U[scenario];
 function add(t:ResearchTrade|null,label:string,color:string,hollow:boolean,referenceOnly=false){
  if(!t||times.indexOf(t.signal_time)>cursor)return;
  result.push({time:t.signal_time,price:c.price[times.indexOf(t.signal_time)],label,detail:`${label} · 原确认 ${t.signal_time}；候选 ${t.candidate_time}`,color,hollow,kind:'signal'});
  if(referenceOnly)return;
  if(showFills&&t.entry_index!==null&&t.entry_index<=cursor)result.push({time:t.entry_time,price:c.price[t.entry_index],label:'卖出',detail:`${label} · 卖出价格代理 ${t.sell_fill?.toFixed(2)} 元`,color,hollow,kind:'fill'});
  if(t.exit_index!==null&&t.exit_index<=cursor)result.push({time:times[t.exit_index],price:c.price[t.exit_index],label:hollow?'影子回补':'回补',detail:`${label} · ${t.exit_reason==='scheduled_close'?'14:56计划回补':'原形态底回补'}；买入价格代理 ${t.buy_fill?.toFixed(2)} 元`,color,hollow,kind:'cover'});
 }
 const replaced=mode==='U'&&!!d&&u?.signal_time!==d.signal_time;
 if(showD)add(d,replaced?'D参考':'D顶确认','#8cbcff',replaced,replaced);
 if(showS){
  if(mode==='U'){
   if(u&&u.signal_time!==d?.signal_time)add(u,'补漏顶确认','#dfb466',false);
  }else add(s,mode==='P'?'补漏影子':'补漏顶确认','#dfb466',mode==='P');
 }
 for(const time of c.weakTimes){if(times.indexOf(time)<=cursor)result.push({time,price:c.price[times.indexOf(time)],label:'未加回',detail:'国科微弱顶对照：原C1拒绝，补漏大盘条件也不通过；仅对照标记',color:'#8995a8',hollow:true,kind:'rejected'});}
 // A shared cover minute is one dot, with both descriptions retained in hover.
 const merged=new Map<string,ResearchMarker>();
 for(const m of result){const key=m.time+'|'+m.price+'|'+m.kind;const old=merged.get(key);if(old){old.detail+='；'+m.detail;old.label=m.kind==='cover'?(old.hollow||m.hollow?'回补对照':'共同回补'):old.label;old.hollow=old.hollow&&m.hollow;}else merged.set(key,{...m});}
 return [...merged.values()];
}
