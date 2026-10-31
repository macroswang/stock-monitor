import React,{useEffect,useState} from 'react';
import {requestWithTimeout} from './requestTimeout';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Sector={code:string;name:string;net_yuan:number;change_percent:number};
type SectorSnapshot={date:string;source:string;measure?:string;date_inferred?:boolean;quote_time?:string|null;collected_at:string;inflow:Sector[];outflow:Sector[]};
type SectorReport={snapshot:SectorSnapshot|null;running:boolean;error:string};
type External={code:string;name:string;price:number;percent:number;source_time:string;time_basis:string};
type ExternalReport={snapshot:{source:string;source_url:string;collected_at:string;quotes:External[]}|null;running:boolean;error:string};
const emptySector:SectorReport={snapshot:null,running:false,error:''};
const emptyExternal:ExternalReport={snapshot:null,running:false,error:''};
const money=(n:number)=>`${n>0?'+':'−'}${Math.abs(n)>=1e8?(Math.abs(n)/1e8).toFixed(2)+'亿':(Math.abs(n)/1e4).toFixed(0)+'万'}`;
const signed=(n:number)=>`${n>0?'+':''}${n.toFixed(2)}%`;
const valid=(r:Sector)=>typeof r.name==='string'&&r.name.length>0&&Number.isFinite(r.net_yuan)&&Number.isFinite(r.change_percent);

function externalReference(name:string,quotes:External[]){
 // 仅作同类资产或宽泛科技行情对照，不参与筛选及收益判断。
 const code=/黄金|贵金属/.test(name)?'hf_GC':/石油|油气|原油/.test(name)?'hf_CL':/半导体|芯片|电子信息|计算机|软件|人工智能/.test(name)?'us.IXIC':null;
 return code?quotes.find(q=>q.code===code):undefined;
}
function FlowColumn({title,report,preview,quotes}:{title:string;report:SectorReport;preview:boolean;quotes:External[]}){
 const snap=report.snapshot;
 const inflow=snap?.inflow.filter(r=>valid(r)&&r.net_yuan>0)||[];
 const focus=inflow.filter(r=>r.change_percent>0);
 const outflow=snap?.outflow.filter(r=>valid(r)&&r.net_yuan<0)||[];
 const flowName=snap?.measure==='大单及超大单净额'?'大单净流入':'方向净流入';
 return <div className="opportunity-column">
  <div className="opportunity-column-title"><strong>{title}</strong><small>{snap?`${snap.date} · ${snap.date_inferred?'日期推定':snap.quote_time?.slice(11,19)||'时间未提供'} · ${snap.source}${preview?' · 静态预览':''}`:report.running?'正在获取':'暂无可用板块数据'}</small></div>
  {snap?<>{report.error&&<p className="opportunity-warning">更新失败，以下为上次快照。</p>}
   <div className="opportunity-label">流入前三且上涨 · 重点观察</div>
   {focus.length?<div className="opportunity-items">{focus.map(row=><div className="opportunity-item" key={row.code}><b>{row.name}</b>{/融资融券|重仓|央企50/.test(row.name)&&<small>宽泛分类</small>}<span className="up">{signed(row.change_percent)}</span><small>{flowName} <span className="up">{money(row.net_yuan)}</span></small>{externalReference(row.name,quotes)&&<small className="opportunity-reference">外围对照：{externalReference(row.name,quotes)!.name} {signed(externalReference(row.name,quotes)!.percent)}（{externalReference(row.name,quotes)!.source_time}）</small>}</div>)}</div>:<p>当前流入前三中暂无同时上涨的板块。</p>}
   {inflow.some(r=>r.change_percent<=0)&&<p>流入但未上涨：{inflow.filter(r=>r.change_percent<=0).map(r=>r.name).join('、')}。</p>}
   {outflow.length>0&&<p>流出较多：{outflow.map(r=>`${r.name} ${money(r.net_yuan)}`).join(' · ')}</p>}
  </>:<p>{report.running?'正在核对数据。':'等待板块资金数据。'}</p>}
 </div>;
}

export default function SectorOpportunities({request,preview=false}:{request:Request;preview?:boolean}){
 const [industry,setIndustry]=useState<SectorReport>(emptySector),[concept,setConcept]=useState<SectorReport>(emptySector),[external,setExternal]=useState<ExternalReport>(emptyExternal);
 useEffect(()=>{let alive=true,running=false;const load=async()=>{if(running)return;running=true;try{const results=await Promise.allSettled([requestWithTimeout(request<SectorReport>('sector_flow',{kind:'industry'})),requestWithTimeout(request<SectorReport>('sector_flow',{kind:'concept'})),requestWithTimeout(request<ExternalReport>('external_market'))]);if(!alive)return;
  setIndustry(results[0].status==='fulfilled'?results[0].value:{...emptySector,error:'板块资金暂不可用'});
  setConcept(results[1].status==='fulfilled'?results[1].value:{...emptySector,error:'板块资金暂不可用'});
  setExternal(results[2].status==='fulfilled'?results[2].value:{...emptyExternal,error:'外围行情暂不可用'});
 }finally{running=false;}};void load();const timer=setInterval(load,15000);return()=>{alive=false;clearInterval(timer);};},[request]);
 const quotes=(external.snapshot?.quotes||[]).filter(q=>typeof q.name==='string'&&Number.isFinite(q.price)&&Number.isFinite(q.percent)&&typeof q.source_time==='string');
 return <section className="sector-opportunities" aria-label="板块机会观察">
  <div className="opportunity-heading"><div><strong>行业与概念机会观察</strong><span>资金流入前三且板块上涨，列入观察；概念之间可能重叠。</span></div><small>{preview?'只读静态预览':'按来源时间更新'}</small></div>
  <div className="opportunity-columns"><FlowColumn title="行业" report={industry} preview={preview} quotes={quotes}/><FlowColumn title="概念" report={concept} preview={preview} quotes={quotes}/></div>
  <div className="opportunity-external"><div className="opportunity-external-heading"><strong>外围变化</strong><span>按报价涨跌观察；来源时间和延迟以各自数据为准。</span></div>
   {quotes.length?<div className="opportunity-external-list">{quotes.map(q=><div key={q.code}><span>{q.name}</span> <b className={q.percent>0?'up':q.percent<0?'down':''}>{signed(q.percent)}</b>{Math.abs(q.percent)>=2&&<em>波动较大</em>}<small>{q.source_time}</small></div>)}</div>:<p>{external.running?'正在获取外围行情。':'外围行情暂不可用。'}</p>}
   <small>{external.snapshot?`${external.snapshot.source} · 采集 ${external.snapshot.collected_at.slice(5,19).replace('T',' ')} · 来源时间的时区与延迟未核实${external.error?' · 更新失败':''}`:'暂无法核对外围报价。'}；外围与板块分别观察，时间未对齐时不合并判断。</small>
  </div>
  <p className="opportunity-note">以上为观察名单：流入金额是来源统计口径；重点查看个股走势和成交。新浪板块日期由代表股推定，板块统计时间未提供。</p>
 </section>;
}
