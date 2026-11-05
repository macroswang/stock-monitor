import {amount, sizingEstimate, type CashReserve} from './tradingSizing';
import type {QuantityRule} from './tradingQuantity';

export const formatted=(n:unknown)=>{
 const value=amount(n);
 return value===null?'—':value.toLocaleString('zh-CN',{maximumFractionDigits:2});
};

export function AccountFunds({funds}:{funds:Record<string,string>}) {
 return <div className="trading-funds">{[
  ['可用资金',funds.available],['股票市值',funds.market_value],['总资产',funds.total_assets],
 ].map(([label,value])=><div key={label}><span>{label}</span><strong>{formatted(value)}<small> 元</small></strong></div>)}</div>;
}

export function SizingOutcome({code,position,sellable,side,rule,price,funds,reserve}:{
 code:string;position:number;sellable:number;side:'buy'|'sell';rule:QuantityRule;
 price?:number;funds:Record<string,string>;reserve?:CashReserve;
}) {
 const s=sizingEstimate(code,position,sellable,side,rule,price,funds.available,funds.total_assets,reserve);
 const label=side==='buy'?'买入':'卖出';
 const capped=side==='sell'&&s.requested!==null?Math.min(s.requested,sellable):s.requested;
 return <section className="trading-sizing-outcome" aria-label={label+'结果试算'} aria-live="polite">
  <div className="trading-estimate-head"><strong>每次{label} {formatted(s.quantity)} 股</strong><span>约 {formatted(s.value)} 元<small>未扣费</small></span></div>
  {s.mode==='position'&&s.requested!==null&&<p className="trading-rounding">
   {formatted(position)} 股 × {formatted(s.input)}% = {formatted(s.requested)} 股。
   {side==='sell'&&s.requested>sellable&&<>可卖仅 {formatted(sellable)} 股，按可卖数量计算。</>}
   {capped!==null&&Math.abs(capped-s.quantity)>1e-8&&<>按{code.startsWith('sh688')?'最低200股、整数股':'100股申报单位'}向下取整为 {formatted(s.quantity)} 股。</>}
  </p>}
  {s.quantity>0&&<>
   <p>相当于当前持仓的 {formatted(s.effectivePercent)}%</p>
   <dl>
    <div><dt>成交后持仓</dt><dd>{formatted(position)} → {formatted(s.positionAfter)} 股</dd></div>
    {s.weight!==null&&<div><dt>该股占账户总资产</dt><dd>{formatted(s.weight)}% → {formatted(s.weightAfter)}%</dd></div>}
    {side==='buy'&&s.required!==null&&<div><dt>预计占用资金</dt><dd>{formatted(s.required)} 元<small>未扣费</small></dd></div>}
    {s.cashAfter!==null&&(side==='sell'||!s.blockedReason)&&<div><dt>成交后可用资金</dt><dd>{formatted(s.cashAfter)} 元{side==='sell'&&<small>未扣费</small>}</dd></div>}
   </dl>
  </>}
  {side==='buy'&&<p className="trading-affordable">按本账户可用资金，估算最多可买 {code.startsWith('sh688')?<>{formatted(s.maxBuyQuantity)} 股</>:<>{s.maxBuyQuantity===null?'—':formatted(s.maxBuyQuantity/100)} 手{s.maxBuyQuantity!==null&&<>（{formatted(s.maxBuyQuantity)} 股）</>}</>}。</p>}
  {s.blockedReason&&<p className="trading-sizing-warning" role="status">{s.blockedReason}</p>}
 </section>;
}
