import {tProfit} from './tCosts';
import type {TCosts} from './tCosts';
export function appendTradeTooltip(root:HTMLElement,sell:number,buy:number,read:()=>TCosts,earlier:boolean,sameMinute:boolean){
 const output=document.createElement('div');output.className='tooltip-trade-result';
 (root.querySelector('.tooltip-comparison')||root).append(output);
 const refresh=()=>{
  const p=read();
  output.replaceChildren();
  const row=(text:string,color?:string)=>{const el=document.createElement('div');el.textContent=text;if(color){el.className='trigger-change';el.style.color=color;const split=text.indexOf('：');if(split>=0){const label=document.createElement('span');label.textContent=text.slice(0,split+1);const value=document.createElement('span');value.textContent=text.slice(split+1).trim();el.replaceChildren(label,value);}}output.append(el);};
  if(earlier){row('早于基准时间，仅比较价格');return;}
  const result=tProfit(sell,buy,p);if(!result){row('请填写有效股数和佣金参数');return;}
  row(`扣费后预计${result.net>=0?'盈利':'亏损'}（${p.shares}股）：${result.net>0?'+':''}${result.net.toFixed(2)} 元`,result.net>0?'#ef8585':result.net<0?'#69d9ac':'#e7edf7');
  if(result.gross>0&&result.net<=0)row('价差不足以覆盖费用');
  if(sameMinute)row('同分钟仅价差示意，不代表可执行顺序');
 };
 refresh();return refresh;
}
