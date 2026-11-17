import {createElement,memo,useEffect,useRef,useState,type ReactNode} from 'react';

/** Keep local chart/form state, while skipping parent-driven hidden renders. */
export const RetainedPane=memo(function RetainedPane({shown,children}:{shown:boolean;children:ReactNode}){
 return createElement('div',{hidden:!shown},children);
},(before,after)=>!before.shown&&!after.shown);

export function usePageVisible(){
 const [visible,setVisible]=useState(()=>document.visibilityState!=='hidden');
 useEffect(()=>{const update=()=>setVisible(document.visibilityState!=='hidden');document.addEventListener('visibilitychange',update);return()=>document.removeEventListener('visibilitychange',update);},[]);
 return visible;
}

/** Display reads only: wait for settlement, pause hidden pages, refresh on return. */
export function useDisplayPolling(active:boolean,read:()=>Promise<unknown>|void,delay:number,scope=''){
 const visible=usePageVisible(),latest=useRef(read),flight=useRef<Promise<unknown>|undefined>(undefined);
 latest.current=read;
 useEffect(()=>{
  if(!active||!visible)return;
  let alive=true,timer:ReturnType<typeof setTimeout>|undefined;
  const run=async()=>{
   if(flight.current)await flight.current.catch(()=>{});
   if(!alive)return;
   const work=Promise.resolve().then(()=>latest.current());flight.current=work;
   try{await work;}catch{/* Caller owns its error presentation. */}finally{if(flight.current===work)flight.current=undefined;}
   if(alive)timer=setTimeout(()=>void run(),delay);
  };
  void run();return()=>{alive=false;clearTimeout(timer);};
 },[active,visible,delay,scope]);
}

const pending=new Map<string,Promise<unknown>>();
const reads=new Set(['snapshot','history','chart','market','index_minute','trading_chart','sector_intraday','paper_account_state']);
export function coalescedRead<T>(method:string,args:Record<string,unknown>,read:()=>Promise<T>):Promise<T>{
 if(!reads.has(method))return read();
 const key=method+'|'+JSON.stringify(Object.entries(args).sort(([a],[b])=>a.localeCompare(b)));
 const prior=pending.get(key);if(prior)return prior as Promise<T>;
 const work=read();pending.set(key,work);
 void work.finally(()=>{if(pending.get(key)===work)pending.delete(key);}).catch(()=>{});
 return work;
}
