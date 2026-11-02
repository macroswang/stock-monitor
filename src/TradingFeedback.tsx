import {useEffect,useState} from 'react';

export default function TradingFeedback({message,error=false}:{message?:string;error?:boolean}) {
 const [visible,setVisible]=useState(!!message);
 useEffect(()=>{
  setVisible(!!message);
  const timer=setTimeout(()=>setVisible(false),5000);
  return()=>clearTimeout(timer);
 },[message]);
 if(!message||!visible)return null;
 return <div className={'trading-feedback trading-toast'+(error?' error':'')} role={error?'alert':'status'}>
  <span>{message}</span><button type="button" aria-label="关闭提示" onClick={()=>setVisible(false)}>×</button>
 </div>;
}
