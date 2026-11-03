export type PriceCheck={stage?:string;policy?:string;allowed:boolean;reference_price?:string|number|null;quote_price?:string|number|null;signed_deviation_pct?:number;adverse_deviation_pct?:number;maximum_pct?:number;boundary_price?:string;checked_at?:string;quote_at?:string;order_price?:string;order_allowed?:boolean;error?:string};
export type PriceAudit={price_checks?:Record<string,PriceCheck>;timings?:{queue_ms?:number;holdings_ms?:number;gateway_ms?:number;elapsed_ms?:number;holdings_scope?:string}};
const price=(v:unknown)=>v!==null&&v!==undefined&&Number.isFinite(Number(v))?Number(v).toFixed(2):'—';
const seconds=(v:number|undefined)=>typeof v==='number'&&Number.isFinite(v)?(v/1000).toFixed(1)+'秒':'—';
const stages=[['before_holdings','核验前'],['after_holdings','核验后'],['before_submit','提交前']] as const;
export default function TradePriceReview({audit,side}:{audit:PriceAudit;side:string}){
 const entries=stages.flatMap(([key,label])=>audit.price_checks?.[key]?[{key,label,check:audit.price_checks[key]}]:[]);
 if(!entries.length)return null;
 const last=entries.at(-1)!.check,t=audit.timings;
 return <details className="trading-price-audit"><summary>价格核验 {price(last.reference_price)} → {price(last.quote_price)}{last.adverse_deviation_pct!==undefined?` · 不利偏离 ${last.adverse_deviation_pct.toFixed(3)}%`:''}{t?.holdings_ms!==undefined?` · 持仓核验 ${seconds(t.holdings_ms)}`:''}</summary>
  <dl>{entries.map(({key,label,check})=><div key={key}><dt>{label} · {check.allowed?'价格通过':'价格拦截'}</dt><dd>参考 {price(check.reference_price)} 元 → 校验 {price(check.quote_price)} 元{check.adverse_deviation_pct!==undefined?` · 不利偏离 ${check.adverse_deviation_pct.toFixed(3)}% / 上限 ${check.maximum_pct}%`:''}<small>报价 {check.quote_at?.slice(11,19)||'未知'} · 校验 {check.checked_at?.slice(11,19)||'未知'}{check.order_price?` · 委托限价 ${price(check.order_price)} 元`:''}</small>{check.error&&<small>{check.error}</small>}</dd></div>)}</dl>
  {last.boundary_price&&<p>{side==='sell'?'本次最低卖价':'本次最高买价'} {last.boundary_price} 元；价格向有利方向变化不受此阈值限制。</p>}
  {t&&<p>排队 {seconds(t.queue_ms)} · 持仓核验 {seconds(t.holdings_ms)}{t.holdings_scope?`（${({target:'目标股票',complete:'全部持仓',cached:'近期已核验快照'} as Record<string,string>)[t.holdings_scope]||t.holdings_scope}）`:''} · 委托准备 {seconds(t.gateway_ms)} · 自信号确认 {seconds(t.elapsed_ms)}</p>}
 </details>;
}
