type Stock={code:string;name:string};

export default function WatchStockSwitcher({previous,next,onMove}:{previous?:Stock;next?:Stock;onMove:(direction:-1|1)=>void}){
 return <div className="watch-stock-switcher" role="group" aria-label="自选股切换">
  <button type="button" aria-label="上一支自选股" title={previous?`上一支：${previous.name} ${previous.code.toUpperCase()}`:'已是第一支自选股'} disabled={!previous} onClick={()=>onMove(-1)}>
   <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 10l5-5 5 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>
  </button>
  <button type="button" aria-label="下一支自选股" title={next?`下一支：${next.name} ${next.code.toUpperCase()}`:'已是最后一支自选股'} disabled={!next} onClick={()=>onMove(1)}>
   <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 6l5 5 5-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>
  </button>
 </div>;
}
