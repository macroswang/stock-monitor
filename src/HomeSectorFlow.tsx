import React,{useEffect,useRef,useState} from 'react';
import {requestWithTimeout} from './requestTimeout';
import InfoNote from './InfoNote';

type Sector={code:string;name:string;net_yuan:number;change_percent:number};
type Snapshot={date:string;source:string;source_url:string;quote_time:string|null;collected_at:string;measure?:string;date_inferred?:boolean;verified_count?:number;total?:number;excluded_count?:number;inflow:Sector[];outflow:Sector[]};
type Report={snapshot:Snapshot|null;cached_snapshot?:Snapshot|null;stale?:boolean;refresh_seconds?:number;running:boolean;error:string;source_url:string};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const url='https://data.eastmoney.com/bkzj/hy.html';
const amount=(value:number)=>`${value>0?'+':'−'}${Math.abs(value)>=1e8?(Math.abs(value)/1e8).toFixed(2)+'亿':(Math.abs(value)/1e4).toFixed(0)+'万'}`;

export default function HomeSectorFlow({request,preview=false,embedded=false}:{request:Request;preview?:boolean;embedded?:boolean}){
 const [report,setReport]=useState<Report>({snapshot:null,running:false,error:'',source_url:url});
 const [kind,setKind]=useState<'industry'|'concept'>('industry');
 const [busy,setBusy]=useState(false),alive=useRef(true);
 const kindRef=useRef(kind);kindRef.current=kind;
 useEffect(()=>{alive.current=true;let active=true,running=false;setReport({snapshot:null,running:false,error:'',source_url:url});const load=async()=>{if(running)return;running=true;try{const data=await requestWithTimeout(request<Report>('sector_flow',{kind}));if(active)setReport(data);}catch{if(active)setReport(previous=>({...previous,stale:true,error:'板块资金连接暂时中断'}));}finally{running=false;}};void load();const timer=setInterval(load,5000);return()=>{active=false;clearInterval(timer);};},[request,kind]);
 useEffect(()=>()=>{alive.current=false;},[]);
 const refresh=async()=>{if(busy)return;const requestedKind=kind;setBusy(true);try{const deadline=Date.now()+60000;const job=await requestWithTimeout(request<{job:string}>('sector_flow_refresh',{kind:requestedKind}));for(;;){if(Date.now()>deadline)throw Error('板块刷新超时');const r=await requestWithTimeout(request<{status:string;result?:Report;error?:string}>('job',{job:job.job}));if(!alive.current||kindRef.current!==requestedKind)return;if(r.status==='failed')throw Error(r.error||'刷新失败');if(r.status==='done'){if(r.result)setReport(r.result);break;}await new Promise(resolve=>setTimeout(resolve,500));}}catch{if(alive.current&&kindRef.current===requestedKind)setReport(x=>({...x,error:'板块资金暂不可用'}));}finally{if(alive.current)setBusy(false);}};
 const candidate=report.snapshot||report.cached_snapshot,stamp=Date.parse(candidate?.collected_at||'');
 const data=candidate&&Number.isFinite(stamp)&&stamp<=Date.now()+5000?candidate:null;
 const delayed=!!report.stale||!!report.error;
 return <section className={'home-sector-flow'+(embedded?' embedded':'')} aria-label="行业资金观察">
  <div className="home-sector-heading"><strong>板块资金</strong><div className="sector-kind" role="group" aria-label="板块类型"><button type="button" aria-pressed={kind==='industry'} onClick={()=>setKind('industry')}>行业</button><button type="button" aria-pressed={kind==='concept'} onClick={()=>setKind('concept')}>概念</button></div>
   <span>{data?`${data.date} · ${data.collected_at.slice(11,19)}更新${preview?' · 静态预览':''}`:report.running?'更新中':'暂无数据'}</span>
   {data?.date_inferred&&<span className="data-status">日期推定</span>}{!!data?.excluded_count&&<span className="data-status partial">部分数据</span>}{delayed&&<span className="data-status delayed">更新延迟</span>}
   <div className="sector-actions">{!preview&&<button disabled={busy||report.running} onClick={()=>void refresh()}>刷新</button>}</div>
  </div>
  {data?<><div className="home-sector-columns">{([[`${data.date_inferred?'方向净流入':'大单净流入'}较多`,data.inflow,'up'],[`${data.date_inferred?'方向净流出':'大单净流出'}较多`,data.outflow,'down']] as const).map(([label,rows,color])=><div key={label}><span>{label}</span><div>{rows.length?rows.map(row=><span className="home-sector-item" key={row.code}><b>{row.name}</b><strong className={color}>{amount(row.net_yuan)}</strong><small>{row.change_percent>0?'+':''}{row.change_percent.toFixed(2)}%</small></span>):<small>暂无数据</small>}</div></div>)}</div>
   <InfoNote label="数据详情"><dl><dt>数据来源</dt><dd>{data.source}</dd><dt>数据日期</dt><dd>{data.date}{data.date_inferred?'（推定）':''}</dd><dt>采集时间</dt><dd>{data.collected_at.slice(0,19).replace('T',' ')}</dd>{data.verified_count!==undefined&&<><dt>板块覆盖</dt><dd>{data.verified_count} / {data.total}</dd></>}<dt>统计口径</dt><dd>{data.measure||(data.date_inferred?'买卖方向净额':'大单及超大单净额')}</dd>{delayed&&<><dt>更新状态</dt><dd>延迟，当前为上次快照</dd></>}{kind==='concept'&&<><dt>板块范围</dt><dd>概念之间可有重叠</dd></>}</dl></InfoNote>
  </>:<p>{report.running?'正在更新…':'暂无板块数据'}</p>}
 </section>;
}
