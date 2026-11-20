import {usePageVisible} from './useDisplayPolling';
import React,{useEffect,useId,useState} from 'react';
import type {MarketData} from './models';
import {quoteView} from './marketOverview';
import {indexSparkline} from './indexSparkline';
import {requestWithTimeout} from './requestTimeout';
import {PRICE_UP,PRICE_DOWN,PRICE_FLAT} from './pricePresentation';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
export const indexes=[['sh000001','上证指数'],['sz399001','深证成指'],['sz399006','创业板指']] as const;
const empty:MarketData={quotes:[],minute:null};

export default function MarketIndexStrip({request,onSelect,selected,onData}:{request:Request;onSelect?:(code:string,market:MarketData)=>void;selected?:string;onData?:(data:Record<string,MarketData>)=>void}){
 const [data,setData]=useState<Record<string,MarketData>>({}),[now,setNow]=useState(()=>Date.now()),id=useId();
 const visible=usePageVisible();
 useEffect(()=>{if(selected&&data[selected])onData?.({[selected]:data[selected]});},[data[selected||''],selected,onData]);
 useEffect(()=>{
  if(!visible)return;let alive=true,reading=false;
  const load=async()=>{if(reading)return;reading=true;
   await Promise.all(indexes.map(async([code])=>{try{
    const value=await requestWithTimeout(request<MarketData>('index_minute',{code,include_leading:true}));
    if(!value||!Array.isArray(value.quotes)||value.minute&&(!Array.isArray(value.minute.bars)||typeof value.minute!=='object'))throw new Error('指数缓存格式异常');
    if(alive)setData(old=>({...old,[code]:{...value,quotes:value.quotes.filter(q=>q&&typeof q==='object')}}));
   }catch{if(alive)setData(old=>({...old,[code]:{...(old[code]||empty),error:'行情连接暂时中断，显示上次数据'}}));}}));
   if(alive)setNow(Date.now());reading=false;
  };
  void load();const timer=setInterval(()=>{setNow(Date.now());void load();},15000);
  return()=>{alive=false;clearInterval(timer);};
 },[request,visible]);
 return <div className="overview-indexes" aria-label="三大指数">{indexes.map(([code,name])=>{
  const market=data[code]||empty,view=quoteView(market.quotes.find(q=>q.code===code),market.error,now),spark=indexSparkline(market,code,now,view),gradient=id+'-'+code;
  return <button type="button" className="overview-index" key={code} aria-label={'查看'+name+'行情'} aria-pressed={selected===code} onClick={()=>onSelect?.(code,market)}>
   <span className="index-name">{name}</span>
   {spark?<svg className="index-sparkline" viewBox="0 0 160 40" preserveAspectRatio="none" role="img" aria-label={`${name}当日缩略分时`}>
    <title>{`${name} ${spark.day} · 截至 ${spark.until}${spark.stale?' · 缓存':''}`}</title>
    <defs><linearGradient id={gradient} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="40"><stop offset="0%" stopColor={PRICE_UP} stopOpacity=".22"/><stop offset="50%" stopColor={PRICE_UP} stopOpacity=".02"/><stop offset="50%" stopColor={PRICE_DOWN} stopOpacity=".02"/><stop offset="100%" stopColor={PRICE_DOWN} stopOpacity=".22"/></linearGradient>
     <linearGradient id={gradient+'-line'} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="40"><stop offset="50%" stopColor={PRICE_UP}/><stop offset="50%" stopColor={PRICE_DOWN}/></linearGradient></defs>
    <path className="index-spark-area" d={spark.area} fill={`url(#${gradient})`}/>
    <path d="M2,20 H158" fill="none" stroke="#718096" strokeWidth=".65" strokeDasharray="3 3" vectorEffect="non-scaling-stroke"/>
    <path className="index-spark-line" d={spark.line} fill="none" stroke={`url(#${gradient+'-line'})`} strokeWidth="1.2" vectorEffect="non-scaling-stroke"/>
    <path d={spark.flatLine} fill="none" stroke={PRICE_FLAT} strokeWidth="1.2" vectorEffect="non-scaling-stroke"/>
   </svg>:<span className="index-spark-empty">暂无分时</span>}
   <div className="index-quote">{view?<><strong className={Number(view.quote.change)>0?'up':Number(view.quote.change)<0?'down':''}>{Number(view.quote.price).toFixed(2)}</strong><b className={Number(view.quote.change)>0?'up':Number(view.quote.change)<0?'down':''}>{Number(view.quote.change)>0?'+':''}{Number(view.quote.change).toFixed(2)} · {Number(view.quote.percent)>0?'+':''}{Number(view.quote.percent).toFixed(2)}%</b><small>{view.kind==='live'?'盘中采样':view.kind==='closed'?'收盘参考':'缓存'} {view.quote.timestamp.slice(5,19).replace('T',' ')}</small></>:<small>行情暂不可用</small>}</div>
  </button>;
 })}</div>;
}
