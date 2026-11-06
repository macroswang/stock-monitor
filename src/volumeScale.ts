/** Keep isolated volume spikes from flattening an otherwise linear volume pane.
 * Values stay in their original units. Pane summaries and hover disclose clipped peaks.
 */
export function volumeDisplayMaximum(values:readonly (number|null|undefined)[]):number|undefined{
 const positive=values.filter((v):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>0).sort((a,b)=>a-b);
 if(positive.length<20)return undefined;
 const reference=positive[Math.ceil(positive.length*.95)-1]*1.25;
 const unit=10**Math.floor(Math.log10(reference));
 const maximum=[1,2,5,10].map(n=>n*unit).find(n=>n>=reference)!;
 return Number.isFinite(maximum)&&maximum>0&&positive.at(-1)!>maximum?maximum:undefined;
}
