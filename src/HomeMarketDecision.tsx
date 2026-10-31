import React,{useEffect,useState} from 'react';
import MarketDecision from './MarketDecision';
import {breadthCountsConsistent,closedSnapshotReady} from './intradayMarket';
import type {BreadthDay} from './MarketBreadth';
import type {MarketData} from './models';
import {requestWithTimeout} from './requestTimeout';
import HomeMarketTrend from './HomeMarketTrend';

type Report={days:BreadthDay[];error:string};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;

export default function HomeMarketDecision({request,market,byAmount,onOpen,preview=false}:{request:Request;market:MarketData;byAmount:boolean;onOpen:()=>void;preview?:boolean}){
 const [report,setReport]=useState<Report>({days:[],error:''});
 useEffect(()=>{let alive=true,reading=false;const load=async()=>{if(reading)return;reading=true;try{const data=await requestWithTimeout(request<Report>('breadth'));if(alive)setReport(data);}catch{if(alive)setReport({days:[],error:'市场数据获取失败'});}finally{reading=false;}};void load();const timer=setInterval(load,30000);return()=>{alive=false;clearInterval(timer);};},[request]);
 const rows=report.days,raw=rows.at(-1),previous=rows.at(-2);
 const day=raw&&closedSnapshotReady(raw,Date.now())&&breadthCountsConsistent(raw)?raw:undefined;
 return <><MarketDecision request={request} day={day} previous={previous} byAmount={true} market={market} stage="unknown" feedError={report.error} compact onOpen={onOpen} preview={preview}/><HomeMarketTrend days={rows} byAmount={byAmount}/></>;
}
