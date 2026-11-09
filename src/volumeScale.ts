/** Fit every real volume on a linear scale, with headroom and a readable upper bound. */
export function volumeDisplayMaximum(values:readonly (number|null|undefined)[]):number|undefined{
 const maximum=values.reduce<number>((max,v)=>typeof v==='number'&&Number.isFinite(v)&&v>max?v:max,0);
 if(maximum<=0)return undefined;
 const reference=maximum*1.1;
 if(!Number.isFinite(reference))return undefined;
 const unit=10**Math.floor(Math.log10(reference));
 return [1,1.2,1.5,2,2.5,3,4,5,6,8,10].map(n=>n*unit).find(n=>n>=reference);
}
