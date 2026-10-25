/** Maximum board-lot buy quantity at the limit price, including buy-side fees.
 * All amounts/prices are cents; commissionWan is the account's per-10,000 rate.
 */
export function maxBuyShares(cash:number,price:number,commissionWan:number,minimum:number):number{
 if(![cash,price,minimum].every(Number.isSafeInteger)||cash<=0||price<=0||minimum<0||!Number.isFinite(commissionWan)||commissionWan<0||commissionWan>100)return 0;
 // Exact half-up cents, matching the ledger rather than binary float fees.
 const [mantissa,exponent='0']=String(commissionWan).toLowerCase().split('e'),fraction=mantissa.split('.')[1]?.length||0;
 const power=Number(exponent)-fraction,raw=BigInt(mantissa.replace('.',''));
 const numerator=power>0?raw*10n**BigInt(power):raw,denominator=10000n*(power<0?10n**BigInt(-power):1n);
 const budget=BigInt(cash),floorFee=BigInt(minimum);
 let lo=0,hi=Math.min(1_000_000,Math.floor(cash/price/100));
 while(lo<hi){const mid=Math.ceil((lo+hi)/2),amount=BigInt(mid*100)*BigInt(price);
  const commission=(amount*numerator+denominator/2n)/denominator;
  const cost=amount+(commission>floorFee?commission:floorFee)+(amount+50000n)/100000n;
  if(cost<=budget)lo=mid;else hi=mid-1;
 }
 return lo*100;
}
export function fractionShares(available:number,divisor:number):number{
 if(!Number.isSafeInteger(available)||available<0||![1,2,3,4].includes(divisor))return 0;
 return divisor===1?available:Math.floor(available/divisor/100)*100;
}
