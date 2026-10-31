import React,{useEffect,useRef,useState} from 'react';
import * as echarts from 'echarts';
import type {BreadthDay} from './MarketBreadth';
import type {MarketData} from './models';
import {breadthView,quoteView,marketObservation} from './marketOverview';
import HomeIndexTrend from './HomeIndexTrend';
import {requestWithTimeout} from './requestTimeout';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Row={code:string;name:string;change_percent:number;net_yuan:number};
type Report={snapshot:null|{date:string;source:string;date_inferred?:boolean;quote_time?:string|null;measure?:string;inflow:Row[];outflow:Row[];sectors?:Row[]};error:string};
type Point={time:string;change:number;net:number};
type Event={code:string;name:string;time:string;start:string;label:string;change:number;net:number};
type Constituent={date:string;first:string;last:string;collected_at:string;advance:number;decline:number;flat:number;covered:number;expected:number;average:number};
type ConstituentReport={data:Constituent|null;points:Constituent[];running:boolean;error:string};
type Intraday={date?:string;events:Event[];series:Record<string,{name:string;points:Point[]}>;status:string};
const empty:MarketData={quotes:[],minute:null,error:'行情暂不可用'};
const demoNames=['半导体','医药','白酒'];
const demoLabels=['启动观察','持续走强','转弱提醒'];
const demoTimes=['10:05','10:12','10:18'];
const demoSampleTimes=[['09:55','10:00','10:05'],['10:02','10:07','10:12'],['10:08','10:13','10:18']];
const demoSeries=demoNames.map((name,i)=>({key:`demo:${i}`,kind:'示例',name,points:[0,1,2].map((j)=>({time:`2026-10-30T${demoSampleTimes[i][j]}:00+08:00`,change:(i===2?-1:1)*j*0.35,net:(i===2?-1:1)*(j+1)*15000000}))}));
const amount=(x:number)=>`${x>0?'+':'−'}${(Math.abs(x)/1e8).toFixed(2)}亿`;

function SectorChart({points}:{points:Point[]}){
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null);
 useEffect(()=>{if(!ref.current)return;const c=echarts.init(ref.current,undefined,{renderer:'canvas'});chart.current=c;const o=new ResizeObserver(()=>c.resize());o.observe(ref.current);return()=>{o.disconnect();c.dispose();};},[]);
 useEffect(()=>{const c=chart.current;if(!c)return;const rows:({time:string;change:number|null;net:number|null})[]=[];points.forEach((p,i)=>{if(i&&Date.parse(p.time)-Date.parse(points[i-1].time)>8*60000)rows.push({time:p.time+'gap',change:null,net:null});rows.push(p);});c.setOption({animation:false,backgroundColor:'transparent',tooltip:{trigger:'axis'},grid:{left:44,right:46,top:14,bottom:30},legend:{data:['涨跌幅','大单净额'],textStyle:{color:'#aabbd3',fontSize:10},bottom:0},xAxis:{type:'category',data:rows.map(p=>p.time.endsWith('gap')?'':p.time.slice(11,16)),axisLabel:{color:'#91a6c2',fontSize:10}},yAxis:[{type:'value',scale:true,axisLabel:{color:'#91a6c2',formatter:'{value}%'}},{type:'value',scale:true,axisLabel:{color:'#91a6c2',formatter:(n:number)=>`${(n/1e8).toFixed(1)}亿`}}],series:[{name:'涨跌幅',type:'line',showSymbol:false,connectNulls:false,lineStyle:{color:'#85b6ff',width:1.5},data:rows.map(p=>p.change)},{name:'大单净额',type:'line',yAxisIndex:1,showSymbol:false,connectNulls:false,lineStyle:{color:'#e6b659',width:1.4},data:rows.map(p=>p.net)}]},true);},[points]);
 return <div className="panorama-sector-chart" ref={ref} role="img" aria-label="板块涨跌幅和资金采样走势"/>;
}

function ConstituentChart({points}:{points:Constituent[]}){
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null);
 useEffect(()=>{if(!ref.current)return;const c=echarts.init(ref.current,undefined,{renderer:'canvas'});chart.current=c;const o=new ResizeObserver(()=>c.resize());o.observe(ref.current);return()=>{o.disconnect();c.dispose();};},[]);
 useEffect(()=>{const c=chart.current;if(!c)return;const rows:({last:string;average:number|null})[]=[];points.forEach((p,i)=>{if(i&&Date.parse(p.last)-Date.parse(points[i-1].last)>8*60000)rows.push({last:'',average:null});rows.push(p);});c.setOption({animation:false,backgroundColor:'transparent',tooltip:{trigger:'axis'},grid:{left:40,right:15,top:10,bottom:22},xAxis:{type:'category',data:rows.map(p=>p.last.slice(11,16)),axisLabel:{color:'#91a6c2'}},yAxis:{type:'value',scale:true,axisLabel:{color:'#91a6c2',formatter:'{value}%'}},series:[{name:'成分股等权平均涨跌幅',type:'line',showSymbol:false,connectNulls:false,lineStyle:{color:'#85b6ff',width:1.5},data:rows.map(p=>p.average)}]},true);},[points]);
 return <div ref={ref} className="panorama-sector-chart" role="img" aria-label="成分股等权平均涨跌幅采样"/>;
}

export default function MarketPanorama({request,preview=false,day,breadthError,watch=[],onOpenStock}:{request:Request;preview?:boolean;day?:BreadthDay;breadthError?:string;watch?:{code:string;name:string}[];onOpenStock?:(code:string)=>void}){
 const [demo,setDemo]=useState(false);
 const [indexes,setIndexes]=useState<MarketData[]>([empty,empty]);const [reports,setReports]=useState<Report[]>([]);const [intraday,setIntraday]=useState<Intraday[]>([]);const [selection,setSelection]=useState('');const [,clock]=useState(0);
 useEffect(()=>{let alive=true,busy=false;const load=async()=>{if(busy)return;busy=true;const calls:Promise<unknown>[]=[request<MarketData>('index_minute',{code:'sh000001'}),request<MarketData>('index_minute',{code:'sz399006'}),request<Report>('sector_flow',{kind:'industry'}),request<Report>('sector_flow',{kind:'concept'}),request<Intraday>('sector_intraday',{kind:'industry'}),request<Intraday>('sector_intraday',{kind:'concept'})];const results=await Promise.allSettled(calls.map(p=>requestWithTimeout(p)));if(alive){setIndexes([0,1].map(i=>results[i].status==='fulfilled'?results[i].value as MarketData:empty));setReports([2,3].map(i=>results[i].status==='fulfilled'?results[i].value as Report:{snapshot:null,error:'数据获取失败'}));setIntraday([4,5].map(i=>results[i].status==='fulfilled'?results[i].value as Intraday:{events:[],series:{},status:'板块数据暂不可用'}));clock(x=>x+1);}busy=false;};void load();const id=setInterval(load,15000);return()=>{alive=false;clearInterval(id);};},[request]);
 const [members,setMembers]=useState<{code:string;data:null|{collected_at:string;members:{code:string;name:string}[]};running:boolean;error:string}>({code:'',data:null,running:false,error:''});
 const now=Date.now(),a=quoteView(indexes[0].quotes[0],indexes[0].error,now),b=quoteView(indexes[1].quotes[0],indexes[1].error,now),breadth=breadthView(day,breadthError,now),summary=marketObservation(a,breadth);
 const realEvents=intraday.flatMap((d,i)=>d.events.map(e=>({...e,kind:i===0?'行业':'概念',key:`${i}:${e.code}`}))).sort((x,y)=>y.time.localeCompare(x.time));
 const events=demo?demoNames.map((name,i)=>({key:`demo:${i}`,code:`DEMO${i}`,name,time:`2026-10-30T${demoTimes[i]}:00+08:00`,start:`2026-10-30T${demoSampleTimes[i][1]}:00+08:00`,label:demoLabels[i],change:i===2?-.35:.35,net:i===2?-15000000:15000000,kind:'示例'})):realEvents;
 const series=intraday.flatMap((d,i)=>Object.entries(d.series).map(([code,v])=>({key:`${i}:${code}`,kind:i===0?'行业':'概念',...v})));
 const fallback=reports.flatMap((r,i)=>(r.snapshot?.sectors||r.snapshot?.inflow||[]).map(v=>({key:`${i}:${v.code}`,kind:i===0?'行业':'概念',name:v.name,points:[] as Point[]})));
 const realOptions=series.length?[...series,...fallback.filter(x=>!series.some(s=>s.key===x.key))]:fallback;const options=demo?demoSeries:realOptions;const selected=options.find(x=>x.key===selection)||options[0];
 const reportIndex=selected?.key.startsWith('1:')?1:0;const sectorSnapshot=reports[reportIndex]?.snapshot;const selectedQuote=sectorSnapshot?[...(sectorSnapshot.sectors||[]),...sectorSnapshot.inflow,...sectorSnapshot.outflow].find(r=>`${reportIndex}:${r.code}`===selected?.key):undefined;
 const sectorCode=demo?'':selected?.key.split(':').slice(1).join(':')||'';
 useEffect(()=>{let active=true;if(!sectorCode)return;const load=async()=>{try{const data=await requestWithTimeout(request<{data:null|{collected_at:string;members:{code:string;name:string}[]};running:boolean;error:string}>('sector_members',{code:sectorCode}));if(active)setMembers({code:sectorCode,...data});}catch{if(active)setMembers({code:sectorCode,data:null,running:false,error:'板块成分获取失败'});}};void load();const timer=setInterval(load,5000);return()=>{active=false;clearInterval(timer);};},[request,sectorCode]);
 const memberData=members.code===sectorCode?members.data:null;
 const [constituents,setConstituents]=useState<{code:string;result:ConstituentReport}>({code:'',result:{data:null,points:[],running:false,error:''}});
 useEffect(()=>{let active=true;if(!sectorCode||!memberData)return;const load=async()=>{try{const result=await requestWithTimeout(request<ConstituentReport>('sector_constituents',{code:sectorCode}));if(active)setConstituents({code:sectorCode,result});}catch{if(active)setConstituents({code:sectorCode,result:{data:null,points:[],running:false,error:'成分股行情暂不可用'}});}};void load();const timer=setInterval(load,5000);return()=>{active=false;clearInterval(timer);};},[request,sectorCode,!!memberData]);
 const c=constituents.code===sectorCode?constituents.result:null;const matches=memberData?watch.filter(w=>memberData.members.some(m=>m.code===w.code)):[];
 return <section className="market-panorama" aria-label="市场全景">
  <div className="panorama-title"><strong>市场全景</strong><small>{preview?'静态预览':'行情按来源采样'}</small><button type="button" className="panorama-demo-toggle" aria-pressed={demo} onClick={()=>{setDemo(v=>!v);setSelection('');}}>{demo?'返回真实数据':'查看效果示例'}</button></div>{demo&&<div className="panorama-demo-warning" role="status">以下板块异动和板块详情为虚构示例，仅展示布局与交互，不代表实际行情。</div>}
  <div className="panorama-indices"><HomeIndexTrend market={indexes[0]} index={a} now={now}/><HomeIndexTrend market={indexes[1]} index={b} now={now} name="创业板"/><div className="panorama-context"><strong>市场强弱</strong>{breadth?<><p>上涨 <b className="up">{breadth.day.advance}</b>　下跌 <b className="down">{breadth.day.decline}</b>　平盘 {breadth.day.flat}</p><p>TRIN（成交额） {breadth.trin?.toFixed(3)||'—'} · {breadth.day.date} {breadth.kind==='live'?'盘中采样':'收盘参考'}</p></>:<p>市场涨跌数据暂不可用</p>}<p>{summary}</p></div></div>
  <div className="panorama-lower"><section className="panorama-events" aria-label="板块异动"><strong>板块异动</strong><small>{demo?'虚构示例 · 非行情':'按发生时间 · 实验观察'}</small>{events.length?<div className="panorama-event-list">{events.map(e=><button key={e.key+e.time} onClick={()=>setSelection(e.key)}><span>{e.time.slice(11,16)}</span><b>{e.name}</b><em>{e.label}</em><small>{e.kind} · {e.start.slice(11,16)}起 涨跌幅变化 {e.change>0?'+':''}{e.change.toFixed(2)}百分点 · 大单净额变化 {amount(e.net)}</small></button>)}</div>:<p>暂无可核对的盘中异动。{intraday.map(x=>x.status).find(Boolean)||'正在获取数据。'}</p>}<small>对比同一来源约5—8分钟采样；变化超过0.3个百分点且资金方向一致。板块全量成分股涨跌尚未用于异动确认，不作为买卖信号。</small></section>
  <section className="panorama-detail" aria-label="板块详情"><div><strong>板块详情</strong><select aria-label="选择板块" value={selected?.key||''} onChange={e=>setSelection(e.target.value)}>{options.length?options.map(o=><option key={o.key} value={o.key}>{o.name} · {o.kind}</option>):<option value="">暂无板块</option>}</select></div>{!demo&&selectedQuote&&<p>涨跌 {selectedQuote.change_percent>0?'+':''}{selectedQuote.change_percent.toFixed(2)}% · {sectorSnapshot?.measure==='大单及超大单净额'?'大单净额':'方向净额'} {amount(selectedQuote.net_yuan)} · {sectorSnapshot?.date} {sectorSnapshot?.date_inferred?'日期推定':sectorSnapshot?.quote_time?.slice(11,19)||'时间未提供'} · {sectorSnapshot?.source}</p>}{selected?.points.length?<><p>{demo?'虚构示例':'数据日期'} {selected.points.at(-1)!.time.slice(0,10)} · {selected.points.length} 个采样点</p><SectorChart points={selected.points}/></>:<p>暂无可核对的板块资金走势；新浪快照未提供板块统计时间。</p>}{demo&&<p>示例成分股：上涨 18 · 下跌 6 · 平盘 1（虚构示例）</p>}{!demo&&c?.data&&<><p>成分股：上涨 <b className="up">{c.data.advance}</b> · 下跌 <b className="down">{c.data.decline}</b> · 平盘 {c.data.flat} · 覆盖 {c.data.covered}/{c.data.expected} · 等权平均 {c.data.average>0?'+':''}{c.data.average.toFixed(2)}%</p><p>腾讯报价 {c.data.date} {c.data.first.slice(11,19)}—{c.data.last.slice(11,19)} · 本次采集 {c.data.collected_at.slice(5,19).replace('T',' ')}</p>{c.points.length>1&&<ConstituentChart points={c.points}/>}</>}{!demo&&!c?.data&&memberData&&<p>{c?.running?'正在核对成分股报价':c?.error||'等待成分股报价'}</p>}<div className="panorama-matches">相关自选股：{demo?'示例模式不匹配真实自选股':memberData?(matches.length?matches.map(w=><button key={w.code} onClick={()=>onOpenStock?.(w.code)}>{w.name}</button>):'当前自选没有匹配项'):(members.code===sectorCode&&members.running?'正在核对板块成分':'板块成分暂无可用数据')} {!demo&&memberData&&<small>新浪 · 采集 {memberData.collected_at.slice(5,19).replace('T',' ')}，成分生效日期未提供</small>}</div></section></div>
  <small className="panorama-note">板块资金仅按来源口径显示；缺失时间、数据断档或来源切换时不生成异动。市场及板块采样可能延迟。</small>
 </section>;
}
