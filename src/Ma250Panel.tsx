import {Fragment,useCallback,useEffect,useMemo,useRef,useState} from 'react';
import StockChartPanel from './StockChartPanel';
import './ma250Panel.css';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Row={code:string;name:string;date:string;kind:'pullback'|'breakout'|'e2';strong:boolean;quality?:boolean;
 strong_reasons:string[];close:number;ma250:number;distance_pct:number;pullback_pct:number|null;
 touch_date:string|null;touch_low:number|null;atr20_pct:number|null;market_above:boolean|null;
 slope60_pct?:number|null;volume_ratio?:number|null;days_below?:number;source_date?:string;source_high?:number;confirmation_day?:number};
type DataIssue={code:string;name:string;state:string;bars:number;minimum_bars:number;reasons:string[];suggestion?:string;repair_ranges:{start:string;end:string;kind:string}[]};
type Scan={generated_at:string;universe:string;recent:number;trading_days:string[];scanned:number;codes:number;
 latest_day:string|null;market:{date:string|null;close:number|null;ma250:number|null;above:boolean|null;bars:number;error:string;stale?:boolean};
 rows:Row[];total:number;filtered_total?:number;strong_count?:number;breakout_count?:number;e2_count?:number;research_unavailable?:number;page?:number;pages?:number;data_issues?:DataIssue[];coverage?:{ready:number;insufficient:number;quality_blocked?:number;invalid:number}};
const REASON:Record<string,string>={market:'指数未站上年线或数据待补','broke-line':'回踩跌破年线',
 'no-higher-low':'低点未高于前低',extended:'距年线超过7%',macd:'MACD 未转正'};
const num=(value:number|null|undefined,digits=2)=>value==null||!Number.isFinite(value)?'—':value.toFixed(digits);
const signed=(value:number|null|undefined)=>value==null||!Number.isFinite(value)?'—':(value>=0?'+':'')+value.toFixed(1)+'%';
const rowKey=(row:Pick<Row,'code'|'date'|'kind'>)=>row.code+'-'+row.date+'-'+row.kind;
const confirmed=(row:Row)=>row.quality&&row.slope60_pct!=null&&row.slope60_pct>=0&&row.volume_ratio!=null&&row.volume_ratio>=1;
const label=(row:Row)=>row.kind==='e2'?'E2·研究参考':row.kind==='breakout'?(confirmed(row)?'突破·确认':'突破·观察'):(row.strong?'回踩·强':'回踩');

export default function Ma250Panel({request,active,watchCodes,onAddWatch,readOnly=false}:{request:Request;active:boolean;watchCodes:string[];onAddWatch:(code:string)=>Promise<void>;readOnly?:boolean}){
 const [scan,setScan]=useState<Scan|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const [universe,setUniverse]=useState('watch_pool'),[kind,setKind]=useState('all');
 const [strongOnly,setStrongOnly]=useState(false),[query,setQuery]=useState('');
 const [expanded,setExpanded]=useState<string|null>(null);
 const [page,setPage]=useState(1);
 const [recent,setRecent]=useState(5);
 const [adding,setAdding]=useState<Set<string>>(new Set()),[justAdded,setJustAdded]=useState<Set<string>>(new Set()),[addError,setAddError]=useState('');
 const pendingAdds=useRef(new Set<string>());
 const [repairing,setRepairing]=useState<string|null>(null),[repairMessage,setRepairMessage]=useState(''),[repairRevision,setRepairRevision]=useState(0);
 const pendingRepair=useRef(false);
 const watched=useMemo(()=>new Set(watchCodes),[watchCodes]);
 useEffect(()=>{setJustAdded(old=>{const remaining=new Set([...old].filter(code=>!watched.has(code)));return remaining.size===old.size?old:remaining;});},[watched]);
 const addWatch=async(row:Row)=>{
  if(readOnly||watched.has(row.code)||justAdded.has(row.code)||pendingAdds.current.has(row.code))return;
  pendingAdds.current.add(row.code);setAdding(new Set(pendingAdds.current));setAddError('');
  try{await onAddWatch(row.code);setJustAdded(old=>new Set(old).add(row.code));}
  catch(cause){setAddError(row.name+'：'+(cause instanceof Error?cause.message:String(cause)));}
  finally{pendingAdds.current.delete(row.code);setAdding(new Set(pendingAdds.current));}
 };
 const sequence=useRef(0);
 const load=useCallback(async(force=false)=>{
  const current=++sequence.current;
  setLoading(true);setError('');
  try{
   const response=await request<Scan|{job:string}>('ma250_scan_start',{universe,recent,kind,strong_only:strongOnly,query:query.trim(),page,page_size:100,force});
   let result:Scan|undefined;
   if('job' in response){
    for(let attempt=0;attempt<200;attempt++){
     if(current!==sequence.current)return;
     const job=await request<{status:string;result?:Scan;error?:string}>('job',{job:response.job});
     if(job.status==='failed')throw Error(job.error||'扫描失败');
     if(job.status==='done'){result=job.result;break;}
     await new Promise(resolve=>setTimeout(resolve,300));
    }
    if(!result)throw Error('扫描仍在进行，请稍后刷新');
   }else result=response;
   if(current===sequence.current)setScan(result);
  }catch(cause){if(current===sequence.current)setError(cause instanceof Error?cause.message:'年线信号扫描失败');}
  finally{if(current===sequence.current)setLoading(false);}
 },[request,universe,kind,strongOnly,query,page,recent]);
 useEffect(()=>{
  const timer=active?setTimeout(()=>void load(),150):undefined;
  return()=>{clearTimeout(timer);sequence.current++;};
 },[active,load,repairRevision]);
 const repairData=async(issue:DataIssue)=>{
  if(readOnly||pendingRepair.current||!issue.repair_ranges.length)return;
  pendingRepair.current=true;setRepairing(issue.code);setRepairMessage('');
  try{
   const dates=new Set<string>();
   for(const range of issue.repair_ranges){
    const task=await request<{job:string}>('daily_load',{code:issue.code,start:range.start,end:range.end});
    let done=false;
    for(let attempt=0;attempt<200;attempt++){
     const job=await request<{status:string;result?:string[];error?:string}>('job',{job:task.job});
     if(job.status==='failed')throw Error(job.error||'补充历史失败');
     if(job.status==='done'){for(const day of job.result||[])dates.add(day);done=true;break;}
     await new Promise(resolve=>setTimeout(resolve,300));
    }
    if(!done)throw Error('数据补充仍在进行，请稍后刷新扫描');
   }
   setRepairMessage(issue.name+(dates.size?'：补入'+dates.size+'根日线，正在重算扫描。':'：未新增日线；来源可能没有更早历史或停牌期间没有数据。'));
   setRepairRevision(value=>value+1);
  }catch(cause){setRepairMessage(issue.name+'：'+(cause instanceof Error?cause.message:'补充历史失败'));}
  finally{pendingRepair.current=false;setRepairing(null);}
 };
 const matchesScope=scan?.universe===universe;
 const source=useMemo(()=>matchesScope?scan.rows:[],[scan,matchesScope]);
 const rows=useMemo(()=>{
  const keyword=query.trim().toLowerCase();
  return source.filter(row=>(kind==='all'||row.kind===kind)&&(!strongOnly||(row.kind==='pullback'&&row.strong))
   &&(!keyword||row.code.toLowerCase().includes(keyword)||row.name.toLowerCase().includes(keyword)))
   ;
 },[source,kind,strongOnly,query]);
 useEffect(()=>{if(expanded&&!rows.some(row=>rowKey(row)===expanded))setExpanded(null);},[rows,expanded]);
 const market=scan?.market;
 const marketState=market?.stale?'待更新':market?.above===true?'年线上':market?.above===false?'年线下':'待更新';
 const strongCount=scan?.strong_count??source.filter(row=>row.kind==='pullback'&&row.strong).length;
 const breakoutCount=scan?.breakout_count??source.filter(row=>row.kind==='breakout').length;
 const e2Count=scan?.e2_count??source.filter(row=>row.kind==='e2').length;
 const days=matchesScope?scan.trading_days:[];
 const daysText=days.length?days[0]+' 至 '+days[days.length-1]:'等待交易日数据';
 const truncated=matchesScope&&scan.filtered_total===undefined&&scan.total>source.length;
 const toggle=(key:string)=>setExpanded(old=>old===key?null:key);
 return <div className="ma250-page">
  <section className="card ma250-desk" aria-label="年线信号概览">
   <div className="ma250-desk-head">
    <div className="ma250-title"><h2>年线信号台</h2><span className="ma250-period">最近 {days.length||recent} 个交易日</span><span className="ma250-date-range">{daysText}</span></div>
    <button type="button" className="ma250-refresh" disabled={loading} onClick={()=>void load(true)}>{loading?'扫描中…':'刷新扫描'}</button>
   </div>
   <div className="ma250-overview">
    <div className="ma250-market">
     <div className="ma250-market-main"><span>沪深300</span><strong>{num(market?.close)}</strong><span className={'ma250-market-state '+(market?.stale?'unknown':market?.above===true?'above':market?.above===false?'below':'unknown')}>{marketState}</span></div>
     <div className="ma250-market-meta"><span>MA250 <b>{num(market?.ma250)}</b></span><span>{market?.date||'指数数据待补'}</span>{market?.error&&<span className="ma250-data-warning" title={market.error}>更新异常</span>}</div>
    </div>
    <div className="ma250-counts" aria-label="区间信号统计">
     <div><span>强回踩</span><strong className="ma250-gold">{matchesScope?strongCount:'—'}</strong></div>
     <div><span>年线突破</span><strong className="ma250-blue">{matchesScope?breakoutCount:'—'}</strong></div>
     <div><span>{truncated?'已展示信号':'全部信号'}</span><strong>{matchesScope?scan.total:'—'}</strong></div>
     <div><span>E2研究参考</span><strong className="ma250-purple">{matchesScope?e2Count:'—'}</strong></div>
    </div>
   </div>
   <div className="ma250-toolbar" role="group" aria-label="年线信号筛选">
    <label><span>范围</span><select aria-label="扫描范围" value={universe} onChange={event=>{setUniverse(event.target.value);setExpanded(null);setPage(1);}}><option value="watch_pool">自选 + 股票池</option><option value="watch">仅自选</option><option value="all">全部本地日线</option></select></label>
    <label><span>类型</span><select aria-label="信号类型" value={kind} onChange={event=>{setKind(event.target.value);setPage(1);if(['breakout','e2'].includes(event.target.value))setStrongOnly(false);}}><option value="all">全部信号</option><option value="pullback">回踩年线</option><option value="breakout">突破年线</option><option value="e2">E2研究参考</option></select></label>
    <label><span>区间</span><select aria-label="信号时间范围" value={recent} onChange={event=>{setRecent(Number(event.target.value));setPage(1);setExpanded(null);}}>{[5,20,60,250].map(n=><option key={n} value={n}>最近{n}个交易日</option>)}</select></label>
    <label className="ma250-check"><input type="checkbox" checked={strongOnly} disabled={['breakout','e2'].includes(kind)} onChange={event=>{setStrongOnly(event.target.checked);setPage(1);}}/>只看强回踩</label>
    <label className="ma250-search"><span className="ma250-sr-only">搜索</span><input value={query} onChange={event=>{setQuery(event.target.value);setPage(1);}} placeholder="搜索代码 / 名称" aria-label="搜索年线信号"/></label>
   </div>
  </section>
  {error&&<div className="ma250-alert" role="alert">{error}{scan?' · 保留上次扫描结果':''}</div>}
  {addError&&<div className="ma250-alert" role="alert">加入自选失败 · {addError}</div>}
  {!!scan?.research_unavailable&&<div className="ma250-alert" role="status">E2研究参考：{scan.research_unavailable}只的日线或交易日数据待核实；请刷新后查看。</div>}
  {truncated&&<div className="ma250-alert" role="status">共 {scan.total} 条，当前展示 {source.length} 条；筛选与统计基于已展示信号，请缩小扫描范围查看。</div>}
  {matchesScope&&scan?.coverage&&(scan.coverage.insufficient>0||scan.coverage.invalid>0||(scan.coverage.quality_blocked||0)>0)&&<details className="ma250-coverage" key={universe}>
   <summary>数据检查：{scan.coverage.insufficient+(scan.coverage.quality_blocked||0)+scan.coverage.invalid}只待核<span>可检测 {scan.coverage.ready} / {scan.codes} 只 · 展开查看原因</span></summary>
   <div className="ma250-coverage-body">
    <p>可检测 {scan.coverage.ready} 只 · 历史不足 {scan.coverage.insufficient} 只 · 窗口不可用 {scan.coverage.quality_blocked||0} 只 · 数据异常 {scan.coverage.invalid} 只；缺失状态不等同于没有信号。</p>
    <p>刷新扫描只重算本地缓存。需要至少310根日线；当前及60根前的年线窗口均需通过检查。补齐日线会重算指标和历史信号，不更改检测或交易规则；不会自动切换复权。</p>
    {!!scan.data_issues?.length?<div className="ma250-data-items" role="list">{scan.data_issues.map(issue=><div className="ma250-data-item" role="listitem" key={issue.code}>
     <div><strong>{issue.name}</strong><small>{issue.code.toUpperCase()} · {issue.bars}/{issue.minimum_bars}根</small></div>
     <div><span>{issue.reasons.join('；')}</span>{issue.suggestion&&<small>{issue.suggestion}</small>}</div>
     {!!issue.repair_ranges.length&&<button type="button" disabled={readOnly||!!repairing} title={readOnly?'请在桌面客户端补充日线':'仅补所列缺失区间；补齐后指标和历史信号会重新计算'} onClick={()=>void repairData(issue)}>{repairing===issue.code?'补充中…':issue.repair_ranges.some(range=>range.kind==='gap')?'补缺口':'补历史'}</button>}
    </div>)}</div>:<p>逐股原因将在刷新扫描后显示；历史不足可能需要积累交易日，真实价格跳变不能靠重复刷新消除。</p>}
   </div>
  </details>}
  {repairMessage&&<div className="ma250-repair-status" role="status">{repairMessage}</div>}
  <section className="card ma250-list" aria-label="年线信号列表" aria-busy={loading}>
   <div className="ma250-list-head"><div><h3>信号列表</h3><span className="ma250-result-count" role="status">{scan?.filtered_total??rows.length} 条</span></div><span>{matchesScope?'已扫描 '+scan.scanned+' / '+scan.codes+' 只':'等待扫描'}<span className="ma250-list-hint"> · 点击行展开图表</span></span></div>
   {!rows.length?<div className="ma250-empty" role="status"><strong>{loading?'正在扫描本地日线…':error?'扫描暂不可用':query||kind!=='all'||strongOnly?'没有匹配的信号':`最近 ${recent} 个交易日暂无信号`}</strong><p>{loading?'扫描完成后显示收盘信号。':kind==='e2'?'可扩大时间区间查看历史E2确认；E2仅为研究参考，不进入提醒或自动交易。':query||kind!=='all'||strongOnly?'调整类型或搜索条件，查看其他信号。':'可切换扫描范围；日线或指数数据不足时，信号可能无法确认。'}</p>{(query||kind!=='all'||strongOnly)&&<button type="button" onClick={()=>{setKind('all');setStrongOnly(false);setQuery('');setPage(1);}}>清除筛选</button>}</div>:
   <div className="ma250-table-scroll"><table className="ma250-table"><thead><tr>{['股票','信号日','信号类型','收盘 / MA250','距年线','形态依据','ATR20','信号日环境','操作'].map((title,index)=><th key={index} scope="col">{title}</th>)}</tr></thead>
    <tbody>{rows.map(row=>{
     const key=rowKey(row),open=expanded===key,isBreakout=row.kind==='breakout',isE2=row.kind==='e2',inWatch=watched.has(row.code)||justAdded.has(row.code),isAdding=adding.has(row.code);
     const badgeClass=isE2?'research':isBreakout?(confirmed(row)?'breakout confirmed':'breakout'):(row.strong?'strong':'normal');
     const reason=isE2?'强信号后3个交易日内收盘突破信号日高点，且满足年线、MA5及指数条件；仅研究参考，不进入正式提醒或自动交易。':isBreakout?(row.volume_ratio==null?'量能数据缺失，突破质量待核实':'确认条件：年线60日斜率≥0，量比≥1'):
      ((row.strong_reasons||[]).map(item=>REASON[item]||item).join('、')||'指数在年线上，回踩未破年线、未破前低，距年线≤7%');
     return <Fragment key={key}>
      <tr className={'ma250-signal-row'+(open?' selected':'')} onClick={()=>toggle(key)}>
       <th scope="row"><span className="ma250-stock-name">{row.name}</span><span className="ma250-secondary ma250-code">{row.code.toUpperCase()}</span></th>
       <td className="ma250-date">{row.date}</td>
       <td><span className={'ma250-badge '+badgeClass} title={reason}>{label(row)}</span>{isBreakout&&row.volume_ratio==null&&<span className="ma250-secondary ma250-data-warning">量能待核</span>}</td>
       <td className="ma250-number"><strong>{num(row.close)}</strong><span className="ma250-secondary">{num(row.ma250)}</span></td>
       <td className={'ma250-number '+(row.distance_pct>=0?'up':'down')}>{signed(row.distance_pct)}</td>
       <td className="ma250-basis">{isE2?<><span>源强信号 {row.source_date}</span><span className="ma250-secondary">第{row.confirmation_day}日确认 · 突破 {num(row.source_high)}</span></>:isBreakout?<><span>斜率 {signed(row.slope60_pct)}</span><span className="ma250-secondary">量比 {row.volume_ratio==null?'—':num(row.volume_ratio)+'×'} · 线下 {row.days_below??'—'} 日</span></>:<><span>回撤 {row.pullback_pct==null?'—':num(row.pullback_pct,1)+'%'}</span><span className="ma250-secondary">低点 {num(row.touch_low)}{row.touch_date?' · '+row.touch_date.slice(5):''}</span></>}</td>
       <td className="ma250-number ma250-muted">{row.atr20_pct==null?'—':num(row.atr20_pct,1)+'%'}</td>
       <td><span className={'ma250-environment '+(row.market_above===true?'above':row.market_above===false?'below':'unknown')}>{row.market_above===true?'年线上':row.market_above===false?'年线下':'未知'}</span></td>
       <td><div className="ma250-row-actions"><button type="button" className="ma250-watch-action" disabled={inWatch||isAdding||readOnly} title={inWatch?'已在我的自选中':readOnly?'请在桌面客户端添加自选':'加入我的自选'} aria-label={row.name+(inWatch?' 已在自选':isAdding?' 正在加入自选':' 加入自选')} onClick={event=>{event.stopPropagation();void addWatch(row);}}>{inWatch?'已在自选':isAdding?'添加中…':'加入自选'}</button><button type="button" className="ma250-row-action" aria-expanded={open} aria-controls={'ma250-detail-'+key} aria-label={(open?'收起':'展开')+row.name+' '+row.date+' '+label(row)+'图表'} onClick={event=>{event.stopPropagation();toggle(key);}}>{open?'收起':'查看日K'}</button></div></td>
      </tr>
      {open&&<tr className="ma250-expand"><td colSpan={9}><div className="ma250-detail" id={'ma250-detail-'+key}><div className="ma250-detail-head"><span>信号日 {row.date}</span><span className="ma250-detail-note">{isE2?'源强信号 '+row.source_date+' · '+reason:isBreakout?reason:'回踩：'+(row.touch_date||'—')+' · '+reason}</span></div><StockChartPanel key={key} request={request} code={row.code} name={row.name} initialView="daily" initialDate={row.date} annualLineFocus/></div></td></tr>}
     </Fragment>;
    })}</tbody></table></div>}
   {(scan?.pages||1)>1&&<nav className="ma250-pagination" aria-label="信号分页"><button disabled={loading||(scan?.page||1)<=1} onClick={()=>setPage(value=>Math.max(1,value-1))}>上一页</button><span>第 {scan?.page||1} / {scan?.pages} 页 · 共 {scan?.filtered_total} 条</span><button disabled={loading||(scan?.page||1)>=(scan?.pages||1)} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>}
   <div className="ma250-footnote"><span>仅强回踩进入提醒 · E2仅研究参考，不进入提醒或自动交易</span><span>收盘信号 · 未复权日K{scan?.generated_at?' · 扫描 '+scan.generated_at.slice(11,16):''}</span></div>
  </section>
 </div>;
}
