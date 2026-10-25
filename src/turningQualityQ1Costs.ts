// Frozen Q1 research assumptions. Independent of the user's 做T calculator settings.
export const TURNING_Q1_COSTS=Object.freeze({shares:1000,commission:.0002,minCommission:5,stamp:.0005,transfer:.00001,slippage:.0005,minSlippage:.01});

// Decimal rational arithmetic preserves the original Python Decimal adverse-cent fills.
function adverseCents(value:number,buy:boolean):bigint{
 const [base,exponent='0']=String(value).toLowerCase().split('e');
 const [whole,fraction='']=base.split('.');
 let numerator=BigInt(whole+fraction),denominator=1n;
 const scale=fraction.length-Number(exponent);
 if(scale>=0)denominator=10n**BigInt(scale);else numerator*=10n**BigInt(-scale);
 let n:bigint,d:bigint;
 if(numerator*100n>=denominator*2000n){n=numerator*(buy?2001n:1999n)*100n;d=denominator*2000n;}
 else{n=numerator*100n+(buy?denominator:-denominator);d=denominator;}
 return buy?(n+d-1n)/d:n/d;
}
const halfUp=(n:bigint,d:bigint)=>(2n*n+d)/(2n*d);
export function q1CostSpace(buyReference:number,sellReference:number):{netCny:number;feesCny:number;buyFill:number;sellFill:number}|null{
 if(!Number.isFinite(buyReference)||!Number.isFinite(sellReference)||buyReference<=0||sellReference<=0)return null;
 const buy=adverseCents(buyReference,true),sell=adverseCents(sellReference,false);
 if(sell<=0n)return null;
 const purchase=buy*1000n,sale=sell*1000n;
 const buyCommission=halfUp(purchase,5000n),sellCommission=halfUp(sale,5000n);
 const fees=(buyCommission>500n?buyCommission:500n)+(sellCommission>500n?sellCommission:500n)
  +halfUp(sale,2000n)+halfUp(purchase,100000n)+halfUp(sale,100000n);
 return {netCny:Number(sale-purchase-fees)/100,feesCny:Number(fees)/100,buyFill:Number(buy)/100,sellFill:Number(sell)/100};
}
