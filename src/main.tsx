import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {enable,disable,isEnabled} from '@tauri-apps/plugin-autostart';
import {isPermissionGranted,requestPermission} from '@tauri-apps/plugin-notification';
import './style.css';
import Chart from './Chart';
import PaperTrading from './PaperTrading';
import type {VolumeFlow} from './models';
import type {PaperFillPoint} from './paperMarks';
import type {PaperPoint} from './PaperTrading';
import WatchlistCard from './WatchlistCard';
import WatchQuoteDetails from './watchQuote';
import type {WatchQuote} from './watchQuote';
import SourceCard from './SourceCard';
import ArchivePanel from './ArchivePanel';
import BuyResearch from './BuyResearch';
import type {BuyReport,BuySignal} from './BuyResearch';
import {EventsPanel,MessageCenter,DaySignals,shiftDay,today} from './Panels';
import type {Bar,Daily,Event,HistoryView,SourceInfo,MarketData} from './models';
import {sourceName} from './format';
type Watch={code:string;name:string;enabled:number;health:string;cache_health?:string;quote?:WatchQuote;candidates:{candidate_time:string;state:string}[]};
type Snapshot={watch:Watch[];events:Event[];instruments?:Record<string,string>;unread_messages?:number;config:{monitor?:boolean;phone_enabled?:boolean;sound?:boolean;provider?:string};market_open:boolean;now:string;data_dir:string;rule:string};
type Cached={day:string;data:{bars:Bar[];volume_unit?:string;source?:unknown}|Daily};
const preview=!isTauri();
async function api<T>(method:string,args:Record<string,unknown>={}):Promise<T>{
 if(preview){
  const d=await fetch('/preview.json').then(r=>r.json());
  if(method==='snapshot')return d.snapshot;
  if(method==='market')return {quotes:[],minute:null} as T;
  if(method==='volume_flow')return {code:args.code,day:args.day,status:'unavailable',minutes:[],message:'浏览器预览暂无分笔方向数据'} as T;
  if(method==='chart')return (args.kind==='daily'?d.daily[args.code as string]:d.minutes[args.code as string])||[];
  if(method==='history'){const h=d.history[args.code as string];return {...h,daily:h.daily.filter((r:Daily)=>String(args.start)<=r.date&&r.date<=String(args.end)),days:h.days.filter((r:{date:string})=>String(args.start)<=r.date&&r.date<=String(args.end)),events:h.events.filter((r:Event)=>String(args.start)<=r.trading_date&&r.trading_date<=String(args.end))};}
  if(method==='archive_status'){const h=d.history[args.code as string];const items=h.days.slice(-20).map((r:any)=>({date:r.date,status:r.has_minutes?'complete':'missing',source:r.has_minutes?'腾讯行情':undefined,rule_ready:r.status==='ready',rule_message:r.status==='missing_limit'?'缺少涨停参考价':''}));return {target:20,basis:'只读预览：依据本地日K已有日期',items,complete:items.filter((r:any)=>r.status==='complete').length,partial:0,missing:items.filter((r:any)=>r.status==='missing').length,requests:[]} as T;}
  if(method==='messages')return {items:[],total:0} as T;
  if(method==='events')return {items:[],total:0} as T;
  if(method==='sources')return d.history[args.code as string]?.source;
  throw Error('浏览器仅用于界面预览，请使用桌面客户端操作');
 }
 return invoke('rpc',{method,args});
}
function App(){
 const [paperAccount,setPaperAccount]=useState<{id:string;revision:number}|null>(null);
 const [paperChart,setPaperChart]=useState<{scope:string;points:PaperFillPoint[];minute_points?:PaperFillPoint[]}>({scope:'',points:[]});
 const [paperPoint,setPaperPoint]=useState<PaperPoint|null>(null);
 const [sidebarCollapsed,setSidebarCollapsed]=useState(()=>{try{return localStorage.getItem('stock-monitor-sidebar-collapsed')==='true';}catch{return false;}});
 const toggleSidebar=()=>setSidebarCollapsed(old=>{const next=!old;try{localStorage.setItem('stock-monitor-sidebar-collapsed',String(next));}catch{}return next;});
 const [autostart,setAutostart]=useState(false);
 const [buyReport,setBuyReport]=useState<BuyReport>();
 const [market,setMarket]=useState<MarketData>({quotes:[],minute:null});
 const [removeTarget,setRemoveTarget]=useState<Watch|null>(null);
 const [snapshot,setSnapshot]=useState<Snapshot>();const [code,setCode]=useState('sh603002');const [view,setView]=useState('minute');const [panel,setPanel]=useState('market');
 const [cache,setCache]=useState<Cached[]>([]);const [dayChoice,setDayChoice]=useState('');const [daily,setDaily]=useState<Daily[]>([]);
 const [input,setInput]=useState('');const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);const [secret,setSecret]=useState('');
 useEffect(()=>{if(!message)return;const timer=window.setTimeout(()=>setMessage(''),5000);return()=>window.clearTimeout(timer);},[message]);
 const [start,setStart]=useState('2026-10-01');const [end,setEnd]=useState(new Date().toLocaleDateString('sv-SE'));const [kind,setKind]=useState('minute');const [replayEvents,setReplayEvents]=useState<Event[]>([]);
 const [history,setHistory]=useState<HistoryView>();const [range,setRange]=useState({start:shiftDay(today(),-90),end:today()});
 const navigationBusy=useRef(false);const [,setNavigating]=useState(false);
 const [sourceInfo,setSourceInfo]=useState<SourceInfo>();
 const historyKey=useRef('');historyKey.current=code+'|'+range.start+'|'+range.end;const historySequence=useRef(0);
 const ensuredMinute=useRef(new Set<string>());
 const [minuteHint,setMinuteHint]=useState('');
 const [connectionError,setConnectionError]=useState('');
 const currentCode=useRef(code);currentCode.current=code;
 const loadSequence=useRef(0);const snapshotSequence=useRef(0);
 const day=dayChoice||(view==='daily'?history?.days.at(-1)?.date:cache.at(-1)?.day)||'';
 useEffect(()=>{let active=true;api<MarketData>('market',{day}).then(r=>{if(active)setMarket(r);}).catch(()=>{if(active)setMarket({quotes:[],minute:null,error:'指数暂时不可用'});});return()=>{active=false;};},[day,snapshot?.now]);
 const paperStart=view==='daily'?range.start:day,paperEnd=view==='daily'?range.end:day;
 const paperScope=[view,day,paperAccount?.id,paperAccount?.revision,code,paperStart,paperEnd].join('|');
 useEffect(()=>{let active=true;if(paperAccount&&code&&paperStart&&paperEnd)api<{points:PaperFillPoint[];minute_points?:PaperFillPoint[]}>('paper_chart',{account:paperAccount.id,code,start:paperStart,end:paperEnd,daily:view==='daily',day}).then(r=>{if(active)setPaperChart({scope:paperScope,points:r.points,minute_points:r.minute_points});}).catch(()=>{if(active)setPaperChart({scope:paperScope,points:[]});});return()=>{active=false;};},[paperScope]);
 const paperPoints=paperChart.scope===paperScope?paperChart.points:[];
 const paperMinutePoints=paperChart.scope===paperScope?(paperChart.minute_points||paperChart.points):[];
 const [flow,setFlow]=useState<VolumeFlow>();
 useEffect(()=>{
  let active=true,timer:ReturnType<typeof setTimeout>|undefined;
  if(!code||!day||panel!=='market')return;
  const update=async()=>{try{const result=await api<VolumeFlow>('volume_flow',{code,day});if(active){setFlow(result);timer=setTimeout(update,result.status==='loading'?2000:30000);}}catch{if(active){setFlow({code,day,status:'unavailable',minutes:[],message:'分笔方向暂不可用，按原总量显示'});timer=setTimeout(update,30000);}}};
  void update();return()=>{active=false;clearTimeout(timer);};
 },[code,day,panel,cache.some(row=>row.day===day)]);
 const selectedFlow=flow?.code===code&&flow.day===day?flow:undefined;
 const benchmark=market.minute?.date===day?market.minute:null;
 const stockBase=Number((cache.find(c=>c.day===day)?.data as {previous_close?:string})?.previous_close||((selectedQuote=>selectedQuote?.timestamp.slice(0,10)===day?selectedQuote.previous_close:undefined)(snapshot?.watch.find(w=>w.code===code)?.quote)));
 const indexCard=(indexCode:string,label:string)=>{const q=market.quotes.find(r=>r.code===indexCode);const stale=q&&((Date.parse(snapshot?.now||new Date().toISOString())-Date.parse(q.timestamp))>90000);return <div key={indexCode}><span>{label}</span>{q?<><strong className={'index-value '+(+q.change>=0?'up':'down')}>{Number(q.price).toFixed(2)}</strong><div className={'index-change '+(+q.change>=0?'up':'down')}>{+q.change>=0?'+':''}{Number(q.change).toFixed(2)}　{+q.change>0?'+':+q.change<0?'-':''}{Math.abs(Number(q.percent)).toFixed(2)}%</div><div className="index-time">{q.timestamp.slice(0,19).replace('T',' ')}{stale?' · 最近报价（非实时）':''}</div></>:<p className="index-unavailable">指数暂未取得</p>}</div>;};
 const refresh=async()=>{const seq=++snapshotSequence.current;try{const data=await api<Snapshot>('snapshot');if(seq===snapshotSequence.current){setSnapshot(data);setConnectionError('');}}catch(e){if(seq===snapshotSequence.current)setConnectionError(String(e));}};
 useEffect(()=>{if(!preview)isEnabled().then(setAutostart).catch(()=>{});refresh();const t=setInterval(refresh,3000);return()=>clearInterval(t);},[]);
 const load=async(target=code)=>{
  if(!target||currentCode.current!==target)return;
  const seq=++loadSequence.current;
  const [m,d]=await Promise.all([api<Cached[]>('chart',{code:target,kind:'minute'}),api<Cached[]>('chart',{code:target,kind:'daily'})]);
  if(currentCode.current!==target||seq!==loadSequence.current)return;
  setCache(m);setDaily(d.map(r=>r.data as Daily));
 };
 const loadHistory=async()=>{if(!code)return;const key=code+'|'+range.start+'|'+range.end,seq=++historySequence.current;const data=await api<HistoryView>('history',{code,...range});if(historyKey.current===key&&seq===historySequence.current){setHistory(data);setSourceInfo(data.source);}};
 useEffect(()=>{setHistory(undefined);loadHistory().catch(e=>setMessage(String(e)));},[code,range]);
 useEffect(()=>{if(snapshot)loadHistory().catch(()=>{});},[snapshot?.now]);
 useEffect(()=>{if(snapshot&&!snapshot.watch.some(w=>w.code===code)){setCode(snapshot.watch[0]?.code||'');setDayChoice('');}},[snapshot?.watch.map(w=>w.code).join(',')]);
 useEffect(()=>{setCache([]);setDaily([]);setReplayEvents([]);load().catch(e=>{if(currentCode.current===code)setMessage(String(e));});return()=>{loadSequence.current++;};},[code]);
 useEffect(()=>{if(!preview&&snapshot){load().catch(()=>{});}},[snapshot?.now]);
 async function waitJob<T>(method:string,args:Record<string,unknown>):Promise<T>{
  const task=await api<{job:string}>(method,args);
  for(;;){const state=await api<{status:string;error?:string;result?:T}>('job',{job:task.job});if(state.status==='failed')throw Error(state.error);if(state.status==='done')return state.result!;await new Promise(resolve=>setTimeout(resolve,500));}
 }
 useEffect(()=>{
  setMinuteHint('');if(preview||view!=='minute'||!day||cache.some(r=>r.day===day))return;
  const key=code+'|'+day;if(ensuredMinute.current.has(key))return;ensuredMinute.current.add(key);let active=true;
  setMinuteHint('正在优先检查本地缓存并按需补取…');
  waitJob<{message?:string}>('minute_ensure',{code,day}).then(async r=>{if(!active)return;setMinuteHint(r.message||'已检查可用分时');await load();await loadHistory();}).catch(e=>{if(active)setMinuteHint(String(e));});
  return()=>{active=false;};
 },[code,day,view,cache.length]);
 async function action(fn:()=>Promise<unknown>,success?:string){if(busy)return;setBusy(true);setMessage('');try{await fn();if(success)setMessage(success);await refresh();}catch(e){setMessage(String(e));}finally{setBusy(false);}}
 async function localTest(delay:number){if(preview)throw Error('请在桌面客户端测试');let allowed=await isPermissionGranted();if(!allowed)allowed=await requestPermission()==='granted';if(!allowed)throw Error('系统通知权限未开启');const result=await api<{message:string}>('test_local',{delay});setMessage(result.message);}
 const selected=snapshot?.watch.find(w=>w.code===code);const mdata=cache.find(c=>c.day===day)?.data as {bars?:Bar[]}|undefined;
 const minute=(mdata?.bars||[]).filter(b=>(b.time>='09:31'&&b.time<='11:30')||(b.time>='13:01'&&b.time<='15:00'));
 const events=[...(snapshot?.events||[]),...replayEvents,...(history?.events||[])].filter((e,i,a)=>a.findIndex(x=>x.key===e.key)===i);
 const onReplay=()=>action(async()=>{const r=await api<{matches:Record<string,unknown>[];candidates:unknown[]}>('replay',{code,day});setReplayEvents(r.matches.map(e=>({...e,symbol:code.slice(2),trading_date:day,mode:'replay'} as unknown as Event)));setMessage(`历史回放完成：${r.candidates.length} 个候选，${r.matches.length} 次触发。未发送通知。`);});
 const name=selected?.name||snapshot?.instruments?.[code]||events.find(e=>e.code===code)?.name||'选择股票';
 const selectDay=(date:string)=>{setDayChoice(date);setReplayEvents([]);if(date<range.start||date>range.end){const next={start:shiftDay(date,-30),end:date};setRange(next);}};
 const openBuy=(event:BuySignal)=>{setCode(event.code);selectDay(event.date);setView('minute');setPanel('market');};
 const buyMarks=(buyReport?.signals||[]).filter(e=>e.code===code&&e.date===day);
 const openEvent=(event:Event)=>{if(event.symbol==='TEST'){setPanel('messages');return;}setCode(event.code||((event.symbol[0]==='6'?'sh':'sz')+event.symbol));selectDay(event.trading_date);setView('minute');setPanel('market');};
 const openDay=(date:string)=>{selectDay(date);setView('minute');};
 const moveDay=async(direction:number)=>{
  if(navigationBusy.current)return;
  const rows=history?.daily||[];const index=rows.findIndex(r=>r.date===day);const next=index+direction;
  if(index>=0&&next>=0&&next<rows.length){selectDay(rows[next].date);return;}
  if(!rows.length)return;
  const edge=direction<0?rows[0].date:rows.at(-1)!.date;
  if(direction>0&&edge>=today()){setMessage('已到最新可用日期');return;}
  const target=direction<0?{start:shiftDay(edge,-365),end:shiftDay(edge,-1)}:{start:shiftDay(edge,1),end:today()};
  if(target.start>target.end){setMessage('已到最新可用日期');return;}
  navigationBusy.current=true;setNavigating(true);const stock=code;
  try{
   const query=()=>api<HistoryView>('history',{code:stock,...target});let data=await query();
   if(!data.daily.length&&!preview){await waitJob('daily_load',{code:stock,...target});data=await query();}
   if(currentCode.current!==stock)return;
   if(!data.daily.length){setMessage('来源暂无更多日K，已保留当前位置；不会连续重复请求。');return;}
   const chosen=direction<0?data.daily.at(-1)!.date:data.daily[0].date;
   setRange(r=>({start:direction<0?target.start:r.start,end:direction>0?target.end:r.end}));setDayChoice(chosen);setReplayEvents([]);
  }catch(e){setMessage(String(e));}finally{navigationBusy.current=false;setNavigating(false);}
 };
 const dayEvents=events.filter(e=>e.symbol===code.slice(2)&&e.trading_date===day&&e.mode!=='test');
 const daySignals=<DaySignals key={'signals-'+code+day} day={day} info={history?.days.find(d=>d.date===day)} events={dayEvents} busy={busy} onOpen={openEvent} onDownload={()=>action(async()=>{await waitJob('history_load',{code,start:day,end:day});await load();await loadHistory();},'已检查该日数据，未返回的历史分时仍显示缺失')} onReference={value=>action(async()=>{await api('history_reference',{code,day,limit_up:value});await loadHistory();},'历史参考价已保存，回放结果不推送')}/>;
 return <div className={'shell'+(sidebarCollapsed?' sidebar-collapsed':'')}>{removeTarget&&<div className="modal-overlay"><section className="card modal" role="dialog" aria-modal="true" aria-labelledby="remove-title"><h2 id="remove-title">移除自选股票</h2><p>确认移除 {removeTarget.name}（{removeTarget.code}）？</p><p className="muted">停止该股票监控，已有缓存和触发记录保留。</p><div className="form-row"><button disabled={busy} onClick={()=>setRemoveTarget(null)}>取消</button><button className="primary" disabled={busy} onClick={()=>action(async()=>{await api('remove',{code:removeTarget.code});setRemoveTarget(null);},'已移除自选，历史数据保留')}>确认移除</button></div></section></div>}<aside className="rail" id="primary-navigation" aria-label="主导航"><button className="rail-toggle" aria-label={sidebarCollapsed?'展开侧栏':'折叠侧栏'} title={sidebarCollapsed?'展开侧栏':'折叠侧栏'} aria-expanded={!sidebarCollapsed} aria-controls="primary-navigation" onClick={toggleSidebar}><span aria-hidden="true">{sidebarCollapsed?'›':'‹'}</span></button><div className="brand"><span className="logo">量</span><div>观量<small>STOCK MONITOR</small></div></div><p className="eyebrow">工作空间</p>
 {[['market','◈','自选监控'],['paper','▤','模拟交易'],['data','⇩','数据管理'],['settings','⚙','设置与通知']].map(([id,icon,name])=><button className={'nav '+(panel===id?'active':'')} key={id} aria-label={name} title={name} onClick={()=>setPanel(id)}><span aria-hidden="true">{icon}</span><span className="nav-label">{name}</span></button>)}
 <div className="rail-bottom" title={snapshot?.market_open?'交易时段':'非交易时段'}><i className={snapshot?.market_open?'dot':'dot idle'}/><span className="rail-state-label">{snapshot?.market_open?'交易时段':'非交易时段'}</span><p>本机独立监控<br/>仅提醒 · 手动交易</p><small>v0.5.0 · 规则 v1</small></div></aside>
 <div className="workspace"><header><div><span className="eyebrow">个人行情工作台</span><h1>{({market:'自选监控',paper:'模拟交易',buy:'买点历史研究',events:'触发记录',messages:'消息中心',data:'数据与缓存',settings:'设置与通知'} as Record<string,string>)[panel]}</h1></div><div className="header-right"><span className="chip">{preview?'只读界面预览':'本地运行'}</span><label className="switch"><input type="checkbox" checked={snapshot?.config.monitor||false} onChange={e=>action(()=>api('config',{monitor:e.target.checked}))}/>持续监控</label></div></header>
 {connectionError&&<div className="notice" role="alert">监控连接中断：{connectionError}。当前图表为缓存，请重启客户端恢复监控。</div>}
 {message&&<div className="toast" role="status">{message}<button onClick={()=>setMessage('')}>×</button></div>}
 {panel==='market'&&<><div className="summary"><div><span>监控股票</span><strong>{snapshot?.watch.filter(w=>w.enabled).length||0}<small> / {snapshot?.watch.length||0}</small></strong></div>{indexCard('sh000001','上证指数')}{indexCard('sz399001','深证成指')}{indexCard('sz399006','创业板指')}<div><span>当前状态</span><strong className="status-text">{connectionError?'连接中断':!snapshot?.config.monitor?'已暂停':snapshot?.market_open?'采样监控中':'休市 · 查看缓存'}</strong></div></div>
 {snapshot?.watch.length===0?<div className="card empty">自选池为空，请输入股票代码添加。<form className="add" onSubmit={e=>{e.preventDefault();action(async()=>{const added=await waitJob<{code:string}>('add_job',{code:input});setCode(added.code);setInput('');});}}><input aria-label="股票代码" value={input} onChange={e=>setInput(e.target.value)} placeholder="六位股票代码"/><button disabled={busy||!input}>＋</button></form></div>:<section className="market-grid"><WatchlistCard><div className="card-heading"><h2>我的自选</h2><span>{snapshot?.watch.length||0} 只</span></div><form className="add" onSubmit={e=>{e.preventDefault();action(async()=>{const added=await waitJob<{code:string;cache_warning?:string}>('add_job',{code:input});setCode(added.code);setDayChoice('');setInput('');if(added.cache_warning)setMessage(added.cache_warning);});}}><input aria-label="股票代码" placeholder="输入六位股票代码" value={input} onChange={e=>setInput(e.target.value)}/><button disabled={busy||!input}>＋</button></form><div className="stocks">{snapshot?.watch.map(w=><div key={w.code} className={'stock '+(code===w.code?'selected':'')} onClick={()=>{setCode(w.code);setDayChoice('');}}><div><strong>{w.name}</strong><small>{w.code.toUpperCase()}</small></div><div className="stock-right"><strong className={+(w.quote?.change||0)>=0?'up':'down'}>{w.quote?.price||'—'}</strong><small>{w.enabled?'监控开启':'已暂停'}</small></div><WatchQuoteDetails quote={w.quote}/></div>)}</div></WatchlistCard>
 <div className="card detail"><div className="detail-top"><div><h2>{name} <small>{code.toUpperCase()}</small></h2><p>{selected?.health} {selected?.cache_health} {selected?.quote&&`· 行情时间 ${selected.quote.timestamp.slice(0,19).replace('T',' ')}`}</p></div><div className="detail-actions"><button disabled={busy||!selected} onClick={()=>action(async()=>{await waitJob('refresh',{code});await load();},'行情刷新完成，请核对行情时间及状态')}>刷新行情</button><button disabled={busy||!selected} onClick={()=>action(()=>api('toggle',{code,enabled:!selected?.enabled}))}>{selected?.enabled?'暂停':'恢复'}</button><button disabled={busy||!selected} onClick={()=>setRemoveTarget(selected||null)}>移除</button></div></div>
 <div className="chart-toolbar"><div className="tabs"><button className={view==='minute'?'chosen':''} onClick={()=>setView('minute')}>分时</button><button className={view==='daily'?'chosen':''} onClick={()=>setView('daily')}>日K</button></div>{view==='minute'&&<div><select aria-label="交易日期" value={day} onChange={e=>selectDay(e.target.value)}>{day&&!cache.some(c=>c.day===day)&&<option value={day}>{day}（无缓存）</option>}{cache.map(c=><option key={c.day}>{c.day}</option>)}</select><button disabled={busy||!day} onClick={onReplay}>历史回放</button></div>}</div>
 <div className="chart-caption">{sourceName(view==='minute'?(mdata as {source?:unknown})?.source:(history?.daily[0]||daily[0])?.source)} · {view==='minute'?`${day||'暂无数据'} · 分钟量以手显示（1手＝100股）`:`${range.start} 至 ${range.end} · ${(history?.daily||[]).length} 根日K · 未复权 · 成交量（万股）`} <span>{view==='daily'?'本地缓存优先 · 收盘后按需增量更新':'历史缓存／实时状态以行情时间为准'}</span></div>
 {view==='minute'&&!minute.length?<div className="history-empty" role="status">{minuteHint||'该日没有本地分时缓存。'}<p>腾讯可用分时缓存：{cache[0]?.day||'暂无'} 至 {cache.at(-1)?.day||'暂无'}。日K历史范围比分钟接口更长，较早日期不一定有分时。数据管理中可查看最近20个交易日的完整性。</p>{!!cache.length&&<button onClick={()=>selectDay(cache.at(-1)!.day)}>查看最近可用分时</button>}</div>:<Chart volumeFlow={selectedFlow} paperFills={paperPoints} onPaperTrade={p=>{setPaperPoint({code,name,stamp:day+' '+p.time,origin:p.kind,side:p.side,price:p.price});if(!p.inChart)setPanel('paper');}} key={'chart-costs-v4-'+code} benchmark={benchmark} previousClose={stockBase} minute={minute} buySignals={buyMarks} daily={history?.daily||[]} view={view} events={view==='daily'?(history?.events||[]):dayEvents} selectedDay={day} onSelectDay={selectDay} onOpenDay={openDay} onMove={moveDay}/>}
 {view==='daily'&&<><div className="linked-minute"><h3>{day||'请选择交易日'} · 当日分时与分钟量</h3>{minute.length?<Chart volumeFlow={selectedFlow} paperFills={paperMinutePoints} onPaperTrade={p=>{setPaperPoint({code,name,stamp:day+' '+p.time,origin:p.kind,side:p.side,price:p.price});if(!p.inChart)setPanel('paper');}} key={code+day+'linked-costs-v4'} view="minute" selectedDay={day} buySignals={buyMarks} benchmark={benchmark} previousClose={stockBase} minute={minute} events={dayEvents} compact/>:<div className="history-empty">该日没有分时缓存。腾讯与新浪免费分钟接口均只提供近期数据；更早日期可能超出覆盖。可双击进入分时页查看覆盖说明，或尝试下载当天数据。</div>}</div></>}
 {(mdata as {source_note?:string})?.source_note&&<p className="notice">{(mdata as {source_note?:string}).source_note}</p>}{daySignals}<SourceCard info={sourceInfo} actual={(mdata as {source?:unknown})?.source}/>
 <div className="rule-strip"><span className="rule-icon">◎</span><div><strong>最大分钟量 → 后两分钟严格缩量 → 提醒</strong><p>确认时仍封涨停，等待首次开板。未结束分钟不参与确认。</p></div><span className="chip amber">卖点规则 v1</span></div>
 </div></section>}<div className="notice">关闭窗口后留在菜单栏／托盘继续监控。电脑睡眠、断网或完全退出期间监控会中断。公开行情为采样数据，短暂开板可能未被捕获。</div></>}
 {panel==='buy'&&<BuyResearch initialReport={buyReport} request={api} watch={snapshot?.watch||[]} onResult={setBuyReport} onOpen={openBuy}/>}
 {panel==='events'&&<EventsPanel request={api} onOpen={openEvent} onError={setMessage}/>}
 {panel==='messages'&&<MessageCenter request={api} onOpen={openEvent} onChange={refresh} onError={setMessage}/>}
 {panel==='data'&&<section className="card form-card"><h2>下载与本地缓存</h2><p>当前股票：{name} {code}。选择范围后获取来源实际可用的数据。</p><div className="form-row"><label>数据类型<select value={kind} onChange={e=>setKind(e.target.value)}><option value="minute">分钟数据</option><option value="daily">日线（未复权，本地缓存优先）</option></select></label><label>开始日期<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>结束日期<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><button className="primary" disabled={busy||!code} onClick={()=>action(async()=>{const result=await waitJob<{downloaded_days:string[];message:string}>('download',{code,start,end,kind});await load();setMessage(`已下载 ${result.downloaded_days.length} 个交易日：${result.downloaded_days.join('、')||'无'}。${result.message}`);})}>{busy?'下载中…':'下载并缓存'}</button></div><div className="notice">分钟接口通常只提供近期数日，指定更早日期可能没有结果。未返回的日期会保留为未知覆盖，不自动当作休市。后续每日运行可逐步积累本地历史。日K保存在本机，收盘15:15后按需补取；近期区间12小时、较早区间7天内复用请求结果，失败至少冷却1小时，日K网络请求串行且至少间隔1秒。</div><ArchivePanel code={code} request={api} busy={busy} onFill={()=>action(async()=>{await waitJob('archive_fill',{code});await load();await loadHistory();},'已检查来源实际可用历史；未返回日期仍列为缺失，不反复下载')} onOpen={date=>{selectDay(date);setView('minute');setPanel('market');}}/><h3>已有分钟缓存</h3><div className="coverage">{cache.map(c=><span className="chip" key={c.day}>{c.day}</span>)}</div><p>日线缓存：{daily[0]?.date||'无'} 至 {daily.at(-1)?.date||'无'}，共 {daily.length} 条。</p><button onClick={()=>action(async()=>{const r=await api<{path:string}>('backup');setMessage('备份已保存：'+r.path);})}>备份本地数据库</button><p className="muted">数据目录：{snapshot?.data_dir}</p><SourceCard info={sourceInfo}/></section>}
 {panel==='settings'&&<section className="card form-card"><h2>iPhone 锁屏通知</h2><p>在 iPhone 安装 Bark，开启锁屏通知，将应用内的设备密钥填入下方。电脑直接调用 Bark，无需搭建后端。</p><label className="secret-label">Bark 设备密钥（保存到系统凭据库）<div className="form-row"><input type="password" autoComplete="off" placeholder="只填写密钥，不填完整推送网址" value={secret} onChange={e=>setSecret(e.target.value)}/><button disabled={busy||!secret} onClick={()=>action(async()=>{await api('secret',{key:secret});setSecret('');},'密钥已保存到系统凭据库，不写入行情数据库')}>保存密钥</button></div></label><label className="setting"><span>启用手机推送<small>只发送此后新产生的实时事件</small></span><input type="checkbox" checked={snapshot?.config.phone_enabled||false} onChange={e=>action(()=>api('config',{phone_enabled:e.target.checked}))}/></label><button className="primary" disabled={busy} onClick={()=>action(async()=>{const r=await api<{message:string}>('test_push');setMessage(r.message);})}>发送测试通知</button><div className="notice">测试通知不是卖点信号。推送服务接受请求不代表手机已显示，请在锁屏上实际确认。网络、通知权限及专注模式可能影响到达。</div><h3>本机运行</h3><label className="setting"><span>登录电脑后自动启动<small>默认关闭，由你选择启用</small></span><input type="checkbox" checked={autostart} onChange={e=>{const checked=e.target.checked;action(async()=>{if(preview)throw Error('请在桌面客户端设置');await (checked?enable():disable());setAutostart(checked);});}}/></label><div className="form-row"><button disabled={busy} onClick={()=>action(()=>localTest(0))}>授权并测试本机通知</button><button disabled={busy} onClick={()=>action(()=>localTest(10))}>10秒后测试后台通知</button></div><label className="setting"><span>通知声音</span><input type="checkbox" checked={snapshot?.config.sound!==false} onChange={e=>action(()=>api('config',{sound:e.target.checked}))}/></label><p>关闭窗口保留后台监控；从菜单栏／托盘选择“退出并停止监控”才完全退出。</p><p className="muted">当前不做多设备同步。两台电脑同时运行时，可能分别推送相同股票的信号。</p><h3>行情数据来源</h3><p>实时主来源为腾讯；新浪已接入历史补充。按整日保存来源，不自动混合两家的分钟数据。</p><select aria-label="行情数据来源" value={snapshot?.config.provider||'tencent'} onChange={e=>action(()=>api('config',{provider:e.target.value}))}><option value="tencent">腾讯行情（已接入）</option><option value="sina" disabled>新浪行情（历史补充，实时不切换）</option></select><SourceCard info={sourceInfo}/><h3>规则与验证</h3><p>规则版本：{snapshot?.rule}。随附12只股票、19次历史触发核对样本。实时行情和涨停开板分支仍需交易日实测。</p></section>}
 <div hidden={panel!=='paper'}><PaperTrading onManageAccount={()=>setPanel('paper')} onOrderResult={text=>{if(panel!=='paper')setMessage(text);}} onAccountState={next=>setPaperAccount(old=>old?.id===next?.id&&old?.revision===next?.revision?old:next)} request={api} point={paperPoint} context={code&&day&&minute.some(b=>b.complete)?{code,name,stamp:day+' '+minute.filter(b=>b.complete).at(-1)?.time,origin:'手动分钟交易',side:'buy'}:undefined} onClosePoint={()=>setPaperPoint(null)} onOpenStock={(target,date)=>{setCode(target);if(date)selectDay(date);setView('minute');setPanel('market');}}/></div>
 <footer><span>观量 · 数据留在本机，交易由你决定</span><span>{busy?'正在处理…':snapshot? snapshot.now.slice(0,19).replace('T',' ')+' 中国标准时间':'正在连接本机监控…'}</span></footer></div></div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
