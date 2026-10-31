import React,{useEffect,useRef,useState} from 'react';
import {requestWithTimeout} from './requestTimeout';

type Sector={code:string;name:string;net_yuan:number;change_percent:number};
type Snapshot={date:string;source:string;source_url:string;quote_time:string|null;collected_at:string;measure?:string;date_inferred?:boolean;inflow:Sector[];outflow:Sector[]};
type Report={snapshot:Snapshot|null;running:boolean;error:string;source_url:string};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const url='https://data.eastmoney.com/bkzj/hy.html';
const amount=(value:number)=>`${value>0?'+':'−'}${Math.abs(value)>=1e8?(Math.abs(value)/1e8).toFixed(2)+'亿':(Math.abs(value)/1e4).toFixed(0)+'万'}`;

export default function HomeSectorFlow({request,preview=false,embedded=false}:{request:Request;preview?:boolean;embedded?:boolean}){
 const [report,setReport]=useState<Report>({snapshot:null,running:false,error:'',source_url:url});
 const [kind,setKind]=useState<'industry'|'concept'>('industry');
 const [busy,setBusy]=useState(false),alive=useRef(true);
 const kindRef=useRef(kind);kindRef.current=kind;
 useEffect(()=>{alive.current=true;let active=true,running=false;setReport({snapshot:null,running:false,error:'',source_url:url});const load=async()=>{if(running)return;running=true;try{const data=await requestWithTimeout(request<Report>('sector_flow',{kind}));if(active)setReport(data);}catch{if(active)setReport({snapshot:null,running:false,error:'板块资金暂不可用',source_url:url});}finally{running=false;}};void load();const timer=setInterval(load,5000);return()=>{active=false;clearInterval(timer);};},[request,kind]);
 useEffect(()=>()=>{alive.current=false;},[]);
 const refresh=async()=>{if(busy)return;const requestedKind=kind;setBusy(true);try{const job=await request<{job:string}>('sector_flow_refresh',{kind:requestedKind});for(;;){const r=await request<{status:string;result?:Report;error?:string}>('job',{job:job.job});if(!alive.current||kindRef.current!==requestedKind)return;if(r.status==='failed')throw Error(r.error||'刷新失败');if(r.status==='done'){if(r.result)setReport(r.result);break;}await new Promise(resolve=>setTimeout(resolve,500));}}catch{if(alive.current&&kindRef.current===requestedKind)setReport(x=>({...x,error:'板块资金暂不可用'}));}finally{if(alive.current)setBusy(false);}};
 const data=report.snapshot;
 return <section className={'home-sector-flow'+(embedded?' embedded':'')} aria-label="行业资金观察">
  <div className="home-sector-heading"><strong>板块资金</strong><div className="sector-kind" role="group" aria-label="板块类型"><button type="button" aria-pressed={kind==='industry'} onClick={()=>setKind('industry')}>行业</button><button type="button" aria-pressed={kind==='concept'} onClick={()=>setKind('concept')}>概念</button></div><span>{data?`${data.date}${data.date_inferred?' · 日期推定':` · ${data.quote_time?.slice(11,19)||'时间未提供'} 报价`} · ${data.source}${preview?' · 静态预览':''}`:(report.running?'正在获取':'暂无可靠数据')}</span><div className="sector-actions">{!preview&&<button disabled={busy||report.running} onClick={()=>void refresh()}>刷新</button>}<a href={data?.source.startsWith('新浪')?'https://vip.stock.finance.sina.com.cn/moneyflow/':url} target="_blank" rel="noreferrer">查看来源</a></div></div>
  {data?<>{report.error&&<p>更新未成功，显示仍在有效时段内的上次快照。</p>}<div className="home-sector-columns">{([[`${data.date_inferred?'方向净流入':'大单净流入'}较多`,data.inflow,'up'],[`${data.date_inferred?'方向净流出':'大单净流出'}较多`,data.outflow,'down']] as const).map(([label,rows,color])=><div key={label}><span>{label}</span><div>{rows.length?rows.map(row=><span className="home-sector-item" key={row.code}><b>{row.name}</b><strong className={color}>{amount(row.net_yuan)}</strong><small>{row.change_percent>0?'+':''}{row.change_percent.toFixed(2)}%</small></span>):<small>当前没有符合方向的板块</small>}</div></div>)}</div><p>{data.inflow.length?`可先观察${data.inflow[0].name}等净流入方向；`:''}{data.outflow.length?`持有${data.outflow[0].name}相关股票时，检查持仓风险和个股信号。`:''} {data.date_inferred?'新浪按买卖方向统计；日期由代表股行情推定，板块统计时间未提供。':'东财大单及超大单统计。'}{kind==='concept'?'概念板块可能重叠。':''}</p></>:<p>{report.running?'正在核对板块日期和资金数据。':'板块资金暂不可用；可通过来源查看板块排行。'}</p>}
 </section>;
}
