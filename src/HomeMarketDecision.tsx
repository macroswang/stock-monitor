import React,{useEffect,useState} from 'react';
import type {BreadthDay} from './MarketBreadth';
import type {MarketData} from './models';
import {requestWithTimeout} from './requestTimeout';
import {breadthView,marketObservation,quoteView} from './marketOverview';
import HomeIndexTrend from './HomeIndexTrend';
import HomeSectorFlow from './HomeSectorFlow';

type Report={days:BreadthDay[];error:string};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const codes=[['sh000001','上证指数'],['sz399001','深证成指'],['sz399006','创业板指']] as const;
const emptyMarket:MarketData={quotes:[],minute:null,error:'市场行情暂不可用'};

export default function HomeMarketDecision({request,onOpen,preview=false}:{request:Request;onOpen:()=>void;preview?:boolean}){
 const [collapsed,setCollapsed]=useState(()=>{try{return localStorage.getItem('stock-monitor-overview-collapsed')==='true';}catch{return false;}});
 const toggleCollapsed=()=>setCollapsed(old=>{const next=!old;try{localStorage.setItem('stock-monitor-overview-collapsed',String(next));}catch{}return next;});
 const [report,setReport]=useState<Report>({days:[],error:''}),[market,setMarket]=useState<MarketData>(emptyMarket),[,setClock]=useState(()=>Date.now());
 useEffect(()=>{let alive=true,reading=false;const load=async()=>{if(reading)return;reading=true;const [breadth,quotes]=await Promise.allSettled([requestWithTimeout(request<Report>('breadth')),requestWithTimeout(request<MarketData>('market_overview'))]);if(alive){setReport(breadth.status==='fulfilled'?breadth.value:{days:[],error:'市场数据更新失败'});setMarket(quotes.status==='fulfilled'?quotes.value:emptyMarket);}reading=false;};void load();const timer=setInterval(load,15000);return()=>{alive=false;clearInterval(timer);};},[request]);
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),15000);return()=>clearInterval(timer);},[]);
 const now=Date.now(),day=report.days.at(-1),breadth=breadthView(day,report.error,now);
 const indexes=codes.map(([code,name])=>({code,name,view:quoteView(market.quotes.find(q=>q.code===code),market.error,now)}));
 const index=indexes[0].view,summary=marketObservation(index,breadth);
 return <section className="home-overview card" aria-label="首页市场趋势">
  <div className="overview-heading"><strong>市场趋势</strong><span>{preview?'静态预览':'当前行情 · 数据按各自时间更新'}</span><div className="overview-actions"><button type="button" onClick={onOpen}>查看大盘广度</button><button type="button" className="overview-toggle" aria-label={collapsed?'展开市场趋势':'收起市场趋势'} aria-expanded={!collapsed} aria-controls="home-overview-content" onClick={toggleCollapsed}>{collapsed?'展开':'收起'} <span aria-hidden="true">{collapsed?'⌄':'⌃'}</span></button></div></div>
  <div id="home-overview-content" hidden={collapsed}>
  <div className="overview-indexes" aria-label="三大指数">{indexes.map(({code,name,view})=><div className="overview-index" key={code}><span>{name}</span>{view?<><strong className={Number(view.quote.change)>0?'up':Number(view.quote.change)<0?'down':''}>{Number(view.quote.price).toFixed(2)}</strong><b className={Number(view.quote.change)>0?'up':Number(view.quote.change)<0?'down':''}>{Number(view.quote.change)>0?'+':''}{Number(view.quote.change).toFixed(2)} · {Number(view.quote.percent)>0?'+':''}{Number(view.quote.percent).toFixed(2)}%</b><small>{view.kind==='live'?'盘中采样':view.kind==='closed'?'收盘参考':'缓存'} {view.quote.timestamp.slice(5,19).replace('T',' ')}</small></>:<small>行情暂不可用</small>}</div>)}</div>
  <div className="overview-market-row"><HomeIndexTrend market={market} index={index} now={now}/><div className="overview-breadth" aria-label="当日市场涨跌">
   <div className="overview-chart-heading"><strong>全市场涨跌</strong><span>{breadth?`${breadth.day.date} · ${breadth.kind==='live'?`盘中 ${breadth.live!.last.slice(11,19)}`:'收盘参考'}`:'数据暂不可用'}</span></div>
   {breadth?<><div className="overview-counts"><span className="up">上涨 <b>{breadth.day.advance}</b></span><span className="down">下跌 <b>{breadth.day.decline}</b></span><span>平盘 <b>{breadth.day.flat}</b></span></div><div className="overview-breadth-extra">上涨股票 {breadth.day.advancing_percent!.toFixed(1)}% · TRIN（成交额） {breadth.trin==null?'—':breadth.trin.toFixed(3)}</div></>:<p>等待完整的当日行情。</p>}
   <div className="overview-observation"><span>操作参考 · 本机规则</span> {summary}</div>
  </div></div>
  <HomeSectorFlow request={request} preview={preview} embedded/>
  </div>
 </section>;
}
