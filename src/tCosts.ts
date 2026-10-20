export type TCosts={shares:number;commissionWan:number;minimum:number;stampPerMille:number;transferPerMille:number;slippagePerMille:number;transferIncluded:boolean};
export const defaultTCosts:TCosts={shares:1000,commissionWan:2,minimum:5,stampPerMille:.5,transferPerMille:.01,slippagePerMille:0,transferIncluded:false};
const round=(n:number)=>Math.round((n+Number.EPSILON)*100)/100;
export function tProfit(sell:number,buy:number,p:TCosts){
 if(!Number.isFinite(sell)||!Number.isFinite(buy)||sell<=0||buy<=0||!Number.isSafeInteger(p.shares)||p.shares<=0||![p.commissionWan,p.minimum,p.stampPerMille,p.transferPerMille,p.slippagePerMille].every(n=>Number.isFinite(n)&&n>=0)||p.slippagePerMille>=1000)return null;
 const sale=sell*(1-p.slippagePerMille/1000)*p.shares,purchase=buy*(1+p.slippagePerMille/1000)*p.shares;
 const commission=round(Math.max(sale*p.commissionWan/10000,p.minimum))+round(Math.max(purchase*p.commissionWan/10000,p.minimum));
 const stamp=round(sale*p.stampPerMille/1000);
 const transfer=p.transferIncluded?0:round(sale*p.transferPerMille/1000)+round(purchase*p.transferPerMille/1000);
 const gross=round((sell-buy)*p.shares),slippage=round((sell*p.shares-sale)+(purchase-buy*p.shares));
 const fees=round(commission+stamp+transfer),cost=round(fees+slippage),net=round(gross-cost);
 return {gross,commission:round(commission),stamp,transfer,slippage,fees,cost,net,percent:net/(sell*p.shares)*100};
}
