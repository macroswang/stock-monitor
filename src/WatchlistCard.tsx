import {useEffect,useId,useMemo,useState,type ReactNode} from 'react';
import {quoteStats,type WatchQuote} from './watchQuote';

const COLLAPSED_KEY='stock-monitor-watchlist-collapsed-v1';
const ORDER_KEY='stock-monitor-watchlist-order-v1';
type Order={pinned:string[];ascending:boolean};

function readOrder():Order{
 try{
  const value=JSON.parse(localStorage.getItem(ORDER_KEY)||'null');
  if(Array.isArray(value?.pinned))return {pinned:value.pinned.filter((code:unknown)=>typeof code==='string'),ascending:value.ascending===true};
 }catch{}
 return {pinned:[],ascending:false};
}

export function useWatchlistOrder<T extends {code:string;quote?:WatchQuote}>(stocks?:T[]){
 const [order,setOrder]=useState(readOrder);
 useEffect(()=>{try{localStorage.setItem(ORDER_KEY,JSON.stringify(order));}catch{}},[order]);
 const list=useMemo(()=>{
  const pinnedRanks=new Map(order.pinned.map((code,i)=>[code,i]));
  const rows=(stocks||[]).map(stock=>({stock,rank:pinnedRanks.get(stock.code),percent:quoteStats(stock.quote).percent}));
  rows.sort((a,b)=>{
   if(a.rank!==undefined||b.rank!==undefined)return (a.rank??Infinity)-(b.rank??Infinity);
   if(a.percent===null||b.percent===null)return Number(a.percent===null)-Number(b.percent===null);
   return order.ascending?a.percent-b.percent:b.percent-a.percent;
  });
  return rows.map(row=>row.stock);
 },[stocks,order]);
 const setPinned=(code:string,pinned:boolean)=>setOrder(old=>{
  if(old.pinned.includes(code)===pinned)return old;
  return {...old,pinned:pinned?[...old.pinned,code]:old.pinned.filter(item=>item!==code)};
 });
 return {list,...order,setPinned,toggleSort:()=>setOrder(old=>({...old,ascending:!old.ascending}))};
}

export function WatchPin({name,pinned,onToggle}:{name:string;pinned:boolean;onToggle:()=>void}){
 const label=(pinned?'取消置顶':'置顶')+name;
 return <button type="button" className="watch-pin" title={label} aria-label={label} aria-pressed={pinned}
  onClick={event=>{event.stopPropagation();onToggle();}}>
  <svg width="13" height="13" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" fill={pinned?'currentColor':'none'} aria-hidden="true"><path d="M8 3h8l-1 7 4 4v1H5v-1l4-4zM12 15v7"/></svg>
  {pinned&&<span>置顶</span>}
 </button>;
}

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
