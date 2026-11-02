import {plannedQuantity, type QuantityRule} from './tradingQuantity';

export type CashReserve = {rate:number; fixed:number};
export const defaultCashReserve:CashReserve = {rate:0.003, fixed:5};

export function amount(value:unknown):number|null {
 if ((typeof value!=='number' && typeof value!=='string') || String(value).trim()==='') return null;
 const n=Number(String(value).replace(/,/g,''));
 return Number.isFinite(n)?n:null;
}

export function sizingEstimate(
 code:string, position:number, sellable:number, side:'buy'|'sell', rule:QuantityRule,
 rawPrice:unknown, rawCash:unknown, rawAssets:unknown, reserve:CashReserve=defaultCashReserve,
) {
 const mode=rule[side+'_mode' as 'buy_mode'|'sell_mode'];
 const input=mode==='lots'?rule[side+'_lots' as 'buy_lots'|'sell_lots']:rule[side+'_percent' as 'buy_percent'|'sell_percent'];
 const valid=Number.isFinite(input) && input>0 && (mode==='lots'?Number.isInteger(input)&&input<=1000000:input<=100);
 const requested=valid?(mode==='lots'?input*100:position*input/100):null;
 const quantity=valid?plannedQuantity(code,position,sellable,side,rule):0;
 const parsedPrice=amount(rawPrice),cashValue=amount(rawCash),assetsValue=amount(rawAssets);
 const price=parsedPrice!==null&&parsedPrice>0?Math.floor(parsedPrice*100+1e-8)/100:null;
 const cash=cashValue!==null&&cashValue>=0?cashValue:null;
 const assets=assetsValue!==null&&assetsValue>0?assetsValue:null;
 const value=price!==null&&price>0?Math.round(quantity*price*100)/100:null;
 // Same reserve parameters supplied by the backend's actual buy cash check.
 const fee=value!==null?value*reserve.rate+reserve.fixed:null;
 const required=value!==null?value*(1+reserve.rate)+reserve.fixed:null;
 const minimum=code.startsWith('sh688')?200:100;
 const increment=code.startsWith('sh688')?1:100;
 let maxBuyQuantity=cash!==null&&price!==null&&price>0
  ?Math.max(0,Math.floor((cash-reserve.fixed)/(price*(1+reserve.rate))/increment+1e-10)*increment):null;
 if(maxBuyQuantity!==null&&cash!==null&&price!==null){
  const candidateValue=Math.round(maxBuyQuantity*price*100)/100;
  if(candidateValue*(1+reserve.rate)+reserve.fixed>cash)maxBuyQuantity=Math.max(0,maxBuyQuantity-increment);
 }
 if(maxBuyQuantity!==null&&maxBuyQuantity<minimum)maxBuyQuantity=0;
 const positionAfter=position+(side==='buy'?quantity:-quantity);
 const effectivePercent=position>0?quantity/position*100:null;
 const weight=assets!==null&&price!==null?position*price/assets*100:null;
 const weightAfter=assets!==null&&price!==null?positionAfter*price/assets*100:null;
 const cashAfter=cash!==null&&value!==null&&required!==null
  ?cash+(side==='buy'?-required:value):null;
 let blockedReason='';
 if(!valid)blockedReason='请填写有效的手数或持仓比例。';
 else if(side==='sell'&&mode==='lots'&&requested!==null&&requested>sellable)blockedReason=`设定 ${requested} 股超过可卖 ${sellable} 股，执行时会跳过。`;
 else if(!quantity)blockedReason=sellable===0&&side==='sell'?'当前没有可卖股数。':`取整后不足最低 ${minimum} 股，执行时会跳过。`;
 else if(price===null||price<=0)blockedReason='缺少有效价格，请同步账户后再查看金额。';
 else if(side==='buy'&&cash===null)blockedReason='尚未读到本账户可用资金，无法判断能否买入。';
 else if(side==='buy'&&cash!==null&&required!==null&&required>cash)blockedReason='按当前可用资金，该数量资金不足，执行时会跳过。';
 return {mode,input,requested,quantity,price,cash,assets,value,fee,required,maxBuyQuantity,positionAfter,effectivePercent,weight,weightAfter,cashAfter,blockedReason};
}
