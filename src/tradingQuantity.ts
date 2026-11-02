export type QuantityRule={buy_mode:'lots'|'position';sell_mode:'lots'|'position';buy_lots:number;sell_lots:number;buy_percent:number;sell_percent:number};
function percentShares(position:number,percent:number){
 const [coefficient,exponent='0']=String(percent).toLowerCase().split('e');
 const [whole,fraction='']=coefficient.split('.'),scale=fraction.length-Number(exponent),digits=BigInt(whole+fraction);
 const numerator=scale<0?digits*10n**BigInt(-scale):digits,denominator=scale>0?10n**BigInt(scale):1n;
 return Number(BigInt(position)*numerator/(denominator*100n));
}
export function plannedQuantity(code:string,position:number,sellable:number,side:'buy'|'sell',rule:QuantityRule){
 const mode=side==='buy'?rule.buy_mode:rule.sell_mode,lots=side==='buy'?rule.buy_lots:rule.sell_lots,percent=side==='buy'?rule.buy_percent:rule.sell_percent;
 if(!Number.isInteger(position)||position<0||!Number.isInteger(sellable)||sellable<0||sellable>position)return 0;
 if(mode==='lots'&&(!Number.isInteger(lots)||lots<1))return 0;
 if(mode==='position'&&(!Number.isFinite(percent)||percent<=0||percent>100))return 0;
 let raw=mode==='lots'?lots*100:percentShares(position,percent);
 if(side==='sell'){
  if(mode==='lots'&&raw>sellable)return 0;
  raw=Math.min(raw,sellable);
  if(mode==='position'&&raw===sellable)return raw;
 }
 return code.startsWith('sh688')?(raw>=200?raw:0):Math.floor(raw/100)*100;
}
export function quantityDescription(side:'buy'|'sell',rule:QuantityRule){
 return rule[side+'_mode' as 'buy_mode'|'sell_mode']==='lots'?`每次 ${side==='buy'?rule.buy_lots:rule.sell_lots} 手`:`当前持仓的 ${side==='buy'?rule.buy_percent:rule.sell_percent}%`;
}
