export type WatchQuote={price:string;change?:string;timestamp:string;previous_close?:string;high?:string;low?:string};
export function quoteStats(q?:WatchQuote){
 const read=(v?:string)=>v!==undefined&&v.trim()!==''&&Number.isFinite(+v)?+v:null;
 const current=read(q?.price),previous=read(q?.previous_close),high=read(q?.high),low=read(q?.low);
 const base=previous!==null&&previous>0?previous:null;
 const change=current!==null&&current>0&&base!==null?current-base:null;
 return {change,percent:change!==null&&base!==null?change/base*100:null,amplitude:base!==null&&high!==null&&low!==null&&high>=low&&low>0?(high-low)/base*100:null};
}
const signed=(v:number|null,suffix:string)=>v===null?'—':`${v>0?'+':''}${(Math.abs(v)<.005?0:v).toFixed(2)}${suffix}`;
export default function WatchQuoteDetails({quote}:{quote?:WatchQuote}){
 const s=quoteStats(quote),color=s.change===null?'':s.change>0?'up':s.change<0?'down':'';
 return <div className="watch-quote-details" title={quote?`行情时间 ${quote.timestamp.slice(0,19).replace('T',' ')}；涨跌额及幅度以昨收计算，振幅＝（最高－最低）÷昨收。`:'暂无报价'}>
 <div className="watch-metric" aria-label="涨跌额"><strong className={color}>{signed(s.change,'')}</strong><span>涨跌额</span></div><div className="watch-metric" aria-label="涨跌幅"><strong className={color}>{signed(s.percent,'%')}</strong><span>涨跌幅</span></div><div className="watch-metric" aria-label="振幅"><strong>{s.amplitude===null?'—':s.amplitude.toFixed(2)+'%'}</strong><span>振幅</span></div>
 </div>;
}
