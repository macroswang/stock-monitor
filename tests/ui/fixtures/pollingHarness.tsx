import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {coalescedRead,RetainedPane,useDisplayPolling} from '../../../src/useDisplayPolling';

export function mount(){
 const host=document.createElement('div');document.body.prepend(host);
 let finish:(()=>void)|undefined;
 function Harness(){
  const [active,setActive]=useState(true),[count,setCount]=useState(0),[scope,setScope]=useState('a');
  useDisplayPolling(active,()=>new Promise<void>(resolve=>{setCount(n=>n+1);finish=resolve;}),100,scope);
  return <div><output aria-label="reads">{count}</output><button onClick={()=>finish?.()}>完成读取</button><button onClick={()=>setActive(x=>!x)}>切换活动</button><button onClick={()=>setScope(s=>s==='a'?'b':'a')}>切换股票</button></div>;
 }
 createRoot(host).render(<Harness/>);
 return coalescedRead;
}

export function mountRetained(){
 const host=document.createElement('div');document.body.prepend(host);let renders=0;
 function ChartState({tick}:{tick:number}){
  const [local,setLocal]=useState(0);renders++;
  return <div><output aria-label="pane-renders">{renders}</output><output aria-label="pane-tick">{tick}</output><output aria-label="pane-local">{local}</output><button onClick={()=>setLocal(x=>x+1)}>本地图表状态</button></div>;
 }
 function Container(){
  const [shown,setShown]=useState(true),[tick,setTick]=useState(0);
  return <div><button onClick={()=>setShown(x=>!x)}>显示隐藏图表</button><button onClick={()=>setTick(x=>x+1)}>后台快照</button><RetainedPane shown={shown}><ChartState tick={tick}/></RetainedPane></div>;
 }
 createRoot(host).render(<Container/>);
}
