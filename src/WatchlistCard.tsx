import {useEffect,useId,useState,type ReactNode} from 'react';

const COLLAPSED_KEY='stock-monitor-watchlist-collapsed-v1';

export default function WatchlistCard({children}:{children:ReactNode}){
 const [collapsed,setCollapsed]=useState(()=>{try{return localStorage.getItem(COLLAPSED_KEY)==='true';}catch{return false;}});
 const contentId=useId();
 useEffect(()=>{try{localStorage.setItem(COLLAPSED_KEY,String(collapsed));}catch{}},[collapsed]);
 const label=collapsed?'展开我的自选':'折叠我的自选';
 return <div className={'card watchlist'+(collapsed?' is-collapsed':'')}>
  <button type="button" className="watchlist-toggle" aria-label={label} title={label} aria-expanded={!collapsed} aria-controls={contentId} onClick={()=>setCollapsed(value=>!value)}>
   <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d={collapsed?'M6 3l5 5-5 5':'M10 3L5 8l5 5'} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>
  </button>
  <div className="watchlist-content" id={contentId} hidden={collapsed}>{children}</div>
  {collapsed&&<span className="watchlist-collapsed-label" aria-hidden="true">我的自选</span>}
 </div>;
}
