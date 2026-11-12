import {Fragment,useCallback,useEffect,useMemo,useRef,useState} from 'react';
import './focusPool.css';
import StockSearch from './StockSearch';
import StockChartPanel from './StockChartPanel';
import {
  BACKTEST_EPISODE_OPTIONS,BACKTEST_PERCENT_OPTIONS,backtestAnchor,backtestCoverageText,backtestSources,backtestSummary,
  bucketByEpisodes,bucketByFirstDay,bucketByPercent,clockText,currentMatchOf,dayShort,entryTime,episodesOf,episodesTitle,filterBacktestRows,
  codeDigits,displayName,filterRows,fullStamp,groupEntries,groupFundText,HORIZONS,horizonCell,horizonTitle,horizonValue,isNum,layoutGroups,num2,pinGroups,poolAddedStamp,readPinnedGroups,selectionOf,writePinnedGroups,
  pctSigned,PERIOD_OPTIONS,planText,quantOf,readStoredTerminal,relatedTagsText,relatedTagsTitle,rowCounts,shortStamp,sortFromOption,
  sortOptionValue,SORT_OPTIONS,tagsOf,tagsTitle,toggleSort,windowExcessText,windowOf,windowReturnText,writeStoredTerminal,
  DEFAULT_BACKTEST_FILTER,DEFAULT_ROW_FILTER,
  type BacktestData,type BacktestFilter,type BacktestRow,type BucketStat,type Entry,type EntryGroup,type PoolData,type Request,
  type RowFilter,type RowPeriod,type SortKey,type SortState,
} from './poolTableModel';

const LIMIT=200;
const POLL_LIVE=6000;
const POLL_IDLE=30000;
const DETAIL_ID=(code:string)=>'pt-detail-'+code;

// 契约 §12.2：卡片内 10 列（名称完整显示 + ×N 徽标；代码去前缀；数值列右对齐，文本列左对齐）
const COLUMNS:{key?:SortKey;label:string;cls?:string;num?:boolean}[]=[
  {label:'代码',num:true},{label:'名称'},{label:'现价',num:true,cls:'pt-col-price'},{key:'added',label:'入选时间'},{key:'entry',label:'入选价格',num:true},
  {key:'since',label:'入选后涨幅',num:true},{key:'today',label:'今日涨幅',num:true},
  {key:'ratio',label:'量比',num:true},{key:'turnover',label:'换手(%)',num:true},{label:'相关概念·题材',cls:'pt-col-tags'},
];
const headClass=(column:{cls?:string;num?:boolean})=>[column.cls,column.num?'pt-head-num':''].filter(Boolean).join(' ')||undefined;

const readError=(cause:unknown)=>{
  if(cause instanceof Error){
    if(/failed to fetch|networkerror|load failed/i.test(cause.message))return '股票池读取失败，正在自动重试';
    return cause.message||'股票池读取失败';
  }
  return '股票池读取失败';
};
const tagsText=(tags:string[])=>tags.length?tags.slice(0,2).join(' / '):'—';

type FocusPoolProps={
  request:Request;preview:boolean;active:boolean;
  onOpenDaily:(code:string,name:string)=>void;
  onTrade:(payload:{code:string;name:string;side:'buy'|'sell'})=>void;
  watch:string[];
};

export default function FocusPool({request,preview,active,onOpenDaily,onTrade,watch}:FocusPoolProps){
  const stored=useMemo(()=>readStoredTerminal(),[]);
  const [filter,setFilter]=useState<RowFilter>(stored.filter);
  const [sort,setSort]=useState<SortState>(stored.sort);
  useEffect(()=>{writeStoredTerminal({filter,sort});},[filter,sort]);
  const [data,setData]=useState<PoolData|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const [openCode,setOpenCode]=useState('');
  const [backtestOpen,setBacktestOpen]=useState(false);
  const [addOpen,setAddOpen]=useState(false);
  const [input,setInput]=useState('');
  const sequence=useRef(0);
  const refreshedAt=useRef(0);
  const tradingRef=useRef(false);
  const dataRef=useRef<PoolData|null>(null);
  dataRef.current=data;
  const fetchPool=useCallback(async()=>{
    const first=await request<PoolData>('pool',{limit:LIMIT,offset:0,include_archived:false});
    const entries=[...first.entries];
    let page=first;
    while(page.has_more){
      page=await request<PoolData>('pool',{limit:LIMIT,offset:entries.length,include_archived:false});
      if(!page.entries.length)throw Error('股票池分页读取未完成，请重试');
      entries.push(...page.entries);
    }
    return {...first,entries:[...new Map(entries.map(entry=>[entry.code,entry])).values()],has_more:false};
  },[request]);

  const read=useCallback(async(mode:'reset'|'refresh')=>{
    if(mode==='refresh'){
      if(typeof document!=='undefined'&&document.visibilityState==='hidden')return;
      // 休市降频：行情不变时 30 秒刷新一次，减少重复请求。
      if(!tradingRef.current&&Date.now()-refreshedAt.current<POLL_IDLE)return;
    }
    const seq=++sequence.current;
    if(mode==='reset')setLoading(true);
    try{
      const next=await fetchPool();
      if(seq!==sequence.current)return;
      refreshedAt.current=Date.now();
      tradingRef.current=Boolean(next.trading);
      setData(next);setError(next.error||'');
    }catch(cause){
      if(seq===sequence.current)setError(readError(cause));
    }finally{
      if(seq===sequence.current)setLoading(false);
    }
  },[fetchPool]);

  useEffect(()=>{
    if(!active)return;
    void read('reset');
    const timer=preview?undefined:setInterval(()=>void read('refresh'),POLL_LIVE);
    return ()=>{if(timer!==undefined)clearInterval(timer);};
  },[active,preview,read]);

  const entries=useMemo<Entry[]>(()=>data?.entries??[],[data]);
  const anchor=useMemo(()=>{
    if(data?.today&&data.today.length>=10)return data.today.slice(0,10);
    const raw=data?.quotes_time||data?.updated_at||'';
    if(raw.length>=10)return raw.slice(0,10);
    let latest='';
    for(const entry of entries)if(entry.added_day&&entry.added_day>latest)latest=entry.added_day;
    return latest||new Date().toLocaleDateString('sv-SE');
  },[data,entries]);
  const calendarToday=data?.calendar_today||anchor;
  // 筛选计数跟随时间范围和搜索。
  const visibleBase=useMemo(()=>filterRows(entries,{...filter,chip:'all'},anchor,calendarToday),[entries,filter.period,filter.search,anchor,calendarToday]);
  const counts=useMemo(()=>rowCounts(visibleBase,anchor,calendarToday),[visibleBase,anchor,calendarToday]);
  // 契约 §7：先筛选/搜索，再分组（排序作用于组内），空组自然消失。
  const filteredRows=useMemo(()=>filterRows(entries,filter,anchor,calendarToday),[entries,filter,anchor,calendarToday]);
  const groups=useMemo(()=>{
    const result=groupEntries(filteredRows,sort);
    if(filter.chip==='alert'&&sort.key==='added'){
      const direction=sort.dir==='desc'?-1:1;
      for(const group of result)group.entries.sort((a,b)=>poolAddedStamp(a).localeCompare(poolAddedStamp(b))*direction);
    }
    return result;
  },[filteredRows,sort,filter.chip]);
  // 用户第七轮：置顶组排最前（保持钉住先后顺序，不随资金排序移动；筛选后不存在的置顶组忽略）
  const [pinned,setPinned]=useState<string[]>(()=>readPinnedGroups());
  useEffect(()=>{writePinnedGroups(pinned);},[pinned]);
  const pinnedSet=useMemo(()=>new Set(pinned),[pinned]);
  const togglePin=(label:string)=>setPinned(current=>current.includes(label)?current.filter(item=>item!==label):[...current,label]);
  const orderedGroups=useMemo(()=>pinGroups(groups,pinned),[groups,pinned]);
  const [columnCount,setColumnCount]=useState(()=>typeof window!=='undefined'&&window.matchMedia('(min-width:1108px)').matches?2:1);
  useEffect(()=>{
    const query=window.matchMedia('(min-width:1108px)');
    const sync=()=>setColumnCount(query.matches?2:1);
    sync();
    query.addEventListener('change',sync);
    return ()=>query.removeEventListener('change',sync);
  },[]);
  const groupColumns=useMemo(()=>layoutGroups(orderedGroups,columnCount),[orderedGroups,columnCount]);
  const readOnly=preview;
  const watched=useMemo(()=>new Set((watch||[]).map(code=>String(code).toLowerCase())),[watch]);
  const isWatched=(code:string)=>watched.has(String(code).toLowerCase());
  const quoteClock=clockText(data?.quotes_time||data?.updated_at);
  const marketState=!data?'读取中':data.trading?'实时':(data.quotes_time?'快照':'—');

  const refetch=async()=>{
    try{
      const next=await fetchPool();
      setData(next);setError(next.error||'');
    }catch(cause){setError(readError(cause));}
  };
  const requireDesktop=()=>{
    if(readOnly){setMessage('浏览器只读预览：请在桌面客户端操作。');return false;}
    return true;
  };
  const pick=(entry:Entry,side:'buy'|'sell')=>{
    if(!requireDesktop())return;
    onTrade({code:entry.code,name:entry.name,side});
  };
  const addWatch=async(entry:Entry)=>{
    if(isWatched(entry.code)){setMessage(entry.name+' 已在自选监控中。');return;}
    if(!requireDesktop())return;
    setBusy(true);setError('');
    try{await request('add_job',{code:entry.code});setMessage('已请求加入自选：'+entry.name+'。');}
    catch(cause){setError(cause instanceof Error?cause.message:'加入自选失败');}
    finally{setBusy(false);}
  };
  const remove=async(entry:Entry)=>{
    if(!requireDesktop())return;
    if(!window.confirm('确定从股票池删除 '+entry.name+'（'+entry.code+'）？'))return;
    setBusy(true);setError('');
    try{
      await request('pool_remove',{code:entry.code});
      setMessage('已从股票池删除 '+entry.name);
      if(openCode===entry.code)setOpenCode('');
      await refetch();
    }catch(cause){setError(cause instanceof Error?cause.message:'删除失败');}
    finally{setBusy(false);}
  };
  const poolAdd=async(raw:string)=>{
    const code=raw.trim();
    if(!code)return;
    if(!requireDesktop())return;
    setBusy(true);setError('');
    try{await request('pool_add',{code});setInput('');setMessage('已添加 '+code+' 到股票池');await refetch();}
    catch(cause){setError(cause instanceof Error?cause.message:'添加失败');}
    finally{setBusy(false);}
  };
  const toggleRow=(code:string)=>setOpenCode(current=>current===code?'':code);
  const onSort=(key:SortKey)=>setSort(current=>toggleSort(current,key));
  const resetFilter=()=>setFilter({...DEFAULT_ROW_FILTER});

  return <section className="pool-terminal" aria-label="股票池" aria-busy={loading}>
    <div className="pt-titlebar">
      <span className="pt-title">股票池 - {entries.length}</span>
      <span className="pt-title-status">
        <span>行情 {quoteClock} · {marketState}</span>
        <span>·</span>
        <span>上涨 <b className="pt-up">{counts.up}</b> / 下跌 <b className="pt-down">{counts.down}</b></span>
        {readOnly&&<span className="pt-readonly">只读预览</span>}
      </span>
    </div>
    <div className="pt-toolbar" role="toolbar" aria-label="股票池工具栏">
      <div className="pt-chips" role="group" aria-label="入选筛选">
        <button type="button" aria-pressed={filter.chip==='all'} title="显示全部股票池标的" onClick={()=>setFilter(current=>({...current,chip:'all'}))}>全部 {counts.all}</button>
        <button type="button" aria-pressed={filter.chip==='today'} title="今天有新的有效入选事件（同一股票今天被研判选中；不要求今天是首次入选）" onClick={()=>setFilter(current=>({...current,chip:'today'}))}>今日入选 {counts.today}</button>
        <button type="button" aria-pressed={filter.chip==='multi'} title="历史累计有效入选天数 ≥2 天" onClick={()=>setFilter(current=>({...current,chip:'multi'}))}>多次入选 {counts.multi}</button>
        <button type="button" className="pt-alert-chip" aria-pressed={filter.chip==='alert'}
          title="只显示今天首次加入股票池的股票；历史股票今天再次入选不计入，也不依据系统通知"
          onClick={()=>setFilter(current=>({...current,chip:'alert',period:'all'}))}>今日提醒 {counts.alert}</button>
      </div>
      <label className="pt-field">时间范围<select aria-label="时间范围" value={filter.period} disabled={filter.chip==='alert'}
        title={filter.chip==='alert'?'今日提醒仅按今天首次加入股票池的日期筛选，与最近一次入选时间范围无关':'按最近一次有效入选日筛选'}
        onChange={event=>setFilter(current=>({...current,period:event.target.value as RowPeriod}))}>
        {PERIOD_OPTIONS.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}
      </select></label>
      <label className="pt-field">排序<select aria-label="排序" value={sortOptionValue(sort)} onChange={event=>setSort(sortFromOption(event.target.value))}>
        {SORT_OPTIONS.map(option=><option key={option.value} value={option.value}>{filter.chip==='alert'?option.label.replace('入选时间','入池时间'):option.label}</option>)}
      </select></label>
      <input className="pt-search" aria-label="搜索代码/名称/标签" placeholder="搜索 代码/名称/标签" value={filter.search}
        onChange={event=>setFilter(current=>({...current,search:event.target.value}))}/>
      {(filter.chip!=='all'||filter.period!=='all'||filter.search)&&<button type="button" className="pt-link" onClick={resetFilter}>清除筛选</button>}
      <span className="pt-toolbar-spacer"/>
      <button type="button" className={backtestOpen?'pt-toggle is-on':'pt-toggle'} aria-pressed={backtestOpen} aria-controls="pt-backtest"
        onClick={()=>setBacktestOpen(open=>!open)}>回测</button>
      <button type="button" className={addOpen?'pt-toggle is-on':'pt-toggle'} aria-expanded={addOpen} aria-controls="pt-add" disabled={readOnly}
        title={readOnly?'只读预览不可添加':'添加股票'} onClick={()=>setAddOpen(open=>!open)}>添加</button>
    </div>
    {addOpen&&!readOnly&&<div className="pt-add" id="pt-add">
      <form onSubmit={event=>{event.preventDefault();void poolAdd(input);}}>
        <StockSearch request={request} preview={preview} value={input} onChange={setInput} onSelect={stock=>{void poolAdd(stock.code);}}/>
        <button type="submit" disabled={busy||!input.trim()}>添加</button>
        <button type="button" onClick={()=>{setAddOpen(false);setInput('');}}>取消</button>
      </form>
    </div>}
    {error&&<p className="pt-error" role="alert">{error}<button type="button" onClick={()=>void read('reset')}>重试</button></p>}
    {message&&<p className="pt-notice" role="status">{message}</p>}
    {backtestOpen&&<BacktestPanel request={request} preview={preview}/>}
    {loading&&!data&&<p className="pt-empty">股票池读取中…</p>}
    {!loading&&!data&&!error&&<p className="pt-empty">股票池暂无数据。</p>}
    {data&&filteredRows.length===0&&<p className="pt-empty">{entries.length?'当前筛选条件下没有标的。点「清除筛选」恢复。':'股票池还没有标的。市场机会中可考虑建仓的标的、方向候选与题材启动信号会自动加入，也可点「添加」手动添加。'}</p>}
    {groups.length>0&&<div className="pt-groups">
      {groupColumns.map((column,index)=><div className="pt-group-col" key={'col-'+(index+1)}>
        {column.map(group=><GroupSection key={group.key} group={group} sort={sort} onSort={onSort} openCode={openCode} onToggle={toggleRow}
          readOnly={readOnly} busy={busy} request={request} live={active&&!preview} isWatched={isWatched}
          pinned={pinnedSet.has(group.label)} onTogglePin={togglePin} showAddedTime={filter.chip==='alert'}
          onPick={pick} onWatch={addWatch} onDelete={remove}/>)}
      </div>)}
    </div>}
    <div className="pt-footer">
      <span>显示 {filteredRows.length} / 共 {entries.length} 只 · {groups.length} 个方向 · {readOnly?'静态预览':'行情每 6 秒刷新（休市 30 秒）'} · 不自动下单</span>
      {data?.archived_count?<span>已归档 {data.archived_count} 只默认隐藏</span>:null}
    </div>
  </section>;
}

function GroupSection({group,sort,onSort,openCode,onToggle,readOnly,busy,request,live,isWatched,pinned,onTogglePin,showAddedTime,onPick,onWatch,onDelete}:{
  group:EntryGroup;sort:SortState;onSort:(key:SortKey)=>void;openCode:string;onToggle:(code:string)=>void;
  readOnly:boolean;busy:boolean;request:Request;live:boolean;isWatched:(code:string)=>boolean;pinned:boolean;onTogglePin:(label:string)=>void;showAddedTime:boolean;
  onPick:(entry:Entry,side:'buy'|'sell')=>void;
  onWatch:(entry:Entry)=>Promise<void>;
  onDelete:(entry:Entry)=>Promise<void>;
}){
  const {stats}=group;
  const columns=showAddedTime?COLUMNS.map(column=>column.key==='added'?{...column,label:'入池时间'}:column):COLUMNS;
  const fundTone=isNum(stats.fundYi)?(stats.fundYi>0?'pt-up':stats.fundYi<0?'pt-down':'pt-flat'):'pt-flat';
  return <section className="pt-group" aria-label={'分组 '+group.label}>
    <div className="pt-group-head">
      <span className="pt-group-title">{group.label} — {stats.rows} 只</span>
      <span className="pt-group-sep" aria-hidden="true">|</span>
      <span className="pt-group-stats">
        <span className="pt-group-stat">上涨 <b className="pt-up">{stats.up}</b>/下跌 <b className="pt-down">{stats.down}</b></span>
        <span className="pt-group-stat">资金净流入 <b className={fundTone}>{groupFundText(stats.fundYi)}</b></span>
      </span>
      <span className="pt-group-sep" aria-hidden="true">|</span>
      <span className="pt-group-driver" title={stats.driverText||undefined}>驱动：<span className="pt-driver-text">{stats.driverText||'—'}</span></span>
      <button type="button" className={'pt-pin'+(pinned?' is-pinned':'')} aria-label={(pinned?'取消置顶 ':'置顶 ')+group.label} aria-pressed={pinned}
        title={pinned?'取消置顶':'置顶该组'} onClick={event=>{event.preventDefault();event.stopPropagation();onTogglePin(group.label);}}>
        <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true" focusable="false"><path d="M16 9V4h1V2H7v2h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z"/></svg>
      </button>
    </div>
    <div className="pt-scroll">
      <div className="pt-table" role="table" aria-label={group.label+' 标的'}>
        <div className="pt-head" role="row">
          {columns.map(column=>column.key
            ?<span key={column.label} role="columnheader" className={headClass(column)} aria-sort={sort.key===column.key?(sort.dir==='desc'?'descending':'ascending'):'none'}>
              <button type="button" className={'pt-head-btn'+(sort.key===column.key?' is-sorted':'')} onClick={()=>onSort(column.key as SortKey)}
                aria-label={'按'+column.label+'排序'}>{column.label}{sort.key===column.key?(sort.dir==='desc'?'▾':'▴'):''}</button>
            </span>
            :<span key={column.label} role="columnheader" className={headClass(column)}>{column.label}</span>)}
        </div>
        {group.entries.map(entry=>{
          const expanded=openCode===entry.code;
          const episodes=episodesOf(entry);
          const selection=selectionOf(entry);
          const stamp=showAddedTime?poolAddedStamp(entry):selection.first_at||selection.first_day;
          const timeLabel=showAddedTime?'入池时间':'入选时间';
          const quant=quantOf(entry);
          const related=relatedTagsText(entry);
          return <Fragment key={entry.code}>
            <div data-pool-code={entry.code} className={'pt-row'+(expanded?' is-open':'')} role="row" tabIndex={0} aria-expanded={expanded} aria-controls={DETAIL_ID(entry.code)}
              onClick={()=>onToggle(entry.code)}
              onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onToggle(entry.code);}}}>
              <span className="pt-cell pt-code pt-num" role="cell" title={entry.code}>{codeDigits(entry.code)}</span>
              <span className="pt-cell pt-name" role="cell" title={entry.name} aria-label={entry.name}>
                <span className="pt-name-text">{displayName(entry.name)}</span>
                <span className="pt-count-badge" title={episodesTitle(entry)} aria-label={'入选 '+episodes.total+' 天'}>×{episodes.total}</span>
              </span>
              <span className="pt-cell pt-num pt-col-price" role="cell" title={entry.quote?'行情 '+clockText(entry.quote.time):'行情待取得'}>{entry.quote?num2(entry.quote.price):'—'}</span>
              <span className="pt-cell pt-time" role="cell" title={(showAddedTime?'入池 ':'入选 ')+fullStamp(stamp)} aria-label={timeLabel+' '+fullStamp(stamp)}>{showAddedTime?(stamp&&stamp.length===10?stamp.slice(5):shortStamp(stamp)):entryTime(entry)}</span>
              <span className="pt-cell pt-num" role="cell">{num2(entry.added_price)}</span>
              <span className={'pt-cell pt-num '+ (isNum(entry.since_add_percent)?(entry.since_add_percent>0?'pt-up':entry.since_add_percent<0?'pt-down':'pt-flat'):'')} role="cell" title="入选后涨幅（自入选价至今）">{pctSigned(entry.since_add_percent)}</span>
              <span className={'pt-cell pt-num '+ (isNum(entry.today_percent)?(entry.today_percent>0?'pt-up':entry.today_percent<0?'pt-down':'pt-flat'):'')} role="cell" title="今日涨幅">{pctSigned(entry.today_percent)}</span>
              <span className="pt-cell pt-num pt-yellow pt-col-ratio" role="cell" title="量比">{isNum(quant.volume_ratio)?quant.volume_ratio.toFixed(2):'—'}</span>
              <span className="pt-cell pt-num pt-yellow pt-col-turnover" role="cell" title="换手率(%)">{isNum(quant.turnover_rate)?quant.turnover_rate.toFixed(2):'—'}</span>
              <span className={'pt-cell pt-tag pt-col-tags'+(related==='—'?' is-empty':'')} role="cell" title={relatedTagsTitle(entry)}>{related}</span>
            </div>
            {expanded&&<DetailRow id={DETAIL_ID(entry.code)} entry={entry} readOnly={readOnly} busy={busy} watched={isWatched(entry.code)} request={request} live={live}
              onPick={onPick} onWatch={onWatch} onDelete={onDelete}/>}
          </Fragment>;
        })}
      </div>
    </div>
  </section>;
}

function DetailRow({id,entry,readOnly,busy,watched,request,live,onPick,onWatch,onDelete}:{
  id:string;entry:Entry;readOnly:boolean;busy:boolean;watched:boolean;request:Request;live:boolean;
  onPick:(entry:Entry,side:'buy'|'sell')=>void;
  onWatch:(entry:Entry)=>Promise<void>;
  onDelete:(entry:Entry)=>Promise<void>;
}){
  const plan=entry.plan;
  const selection=selectionOf(entry);
  const tags=tagsOf(entry);
  const current=currentMatchOf(entry);
  return <section className="pt-detail" id={id} role="region" aria-label={'详情 '+entry.name}>
    <div className="pt-detail-chart">
      <StockChartPanel request={request} code={entry.code} name={entry.name} live={live}/>
    </div>
    <div className="pt-detail-grid">
      <div className="pt-detail-col">
        <h4>计划与关键价位</h4>
        <dl className="pt-kv">
          <div><dt>买区</dt><dd>{planText(plan,'buy')}</dd></div>
          <div><dt>不追</dt><dd>{planText(plan,'chase')}</dd></div>
          <div><dt>止损</dt><dd className="pt-stop">{planText(plan,'stop')}</dd></div>
          <div><dt>目标1</dt><dd className="pt-target">{planText(plan,'target1')}</dd></div>
          <div><dt>目标2</dt><dd>{planText(plan,'target2')}</dd></div>
          <div><dt>移动止损</dt><dd>{planText(plan,'trail')}</dd></div>
        </dl>
        {plan?.note?<p className="pt-muted">计划：{plan.note}</p>:null}
        {plan?.sell_note?<p className="pt-muted">离场：{plan.sell_note}</p>:null}
      </div>
      <div className="pt-detail-col">
        <h4>入选理由</h4>
        <p className="pt-detail-reason" title={entry.reason||undefined}>{entry.reason||'入选理由待取得'}</p>
        <p className="pt-detail-tags">概念 {tagsTitle(tags.concept)} · 题材 {tagsTitle(tags.theme)} · 事件 {tagsTitle(tags.event)}{tags.other.length?' · 其他 '+tagsTitle(tags.other):''}</p>
        <h4>入选统计</h4>
        <dl className="pt-kv">
          <div><dt>累计</dt><dd>{selection.days} 天 · 今日{selection.today > 0 ? '已入选' : '未入选'}</dd></div>
          <div><dt>首次</dt><dd>{fullStamp(selection.first_at)}</dd></div>
          <div><dt>最近</dt><dd>{fullStamp(selection.last_at)}</dd></div>
        </dl>
        <h4>当前状态</h4>
        <div className={'pt-current'+(current.ok?' is-match':'')}>
          <b>当前符合：{current.ok?'是':'否'}</b>
          <span>{current.ok?'zone 已进入买区、现价处于计划买区且未破止损，仍符合入选条件':current.reason}</span>
          <em>不代表买入建议</em>
        </div>
        <h4>窗口表现</h4>
        <div className="pt-win-badges">
          {HORIZONS.map(key=>{
            const window=windowOf(entry,key);
            const ret=window&&isNum(window.return_percent)?window.return_percent:null;
            const excess=window&&isNum(window.excess_percent)?window.excess_percent:null;
            return <span className="pt-win-badge" key={key} title={ret===null?key+' 尚未到期/待积累':key+' 收益 '+pctSigned(ret)+' · 超额 '+pctSigned(excess)}>
              <b>{key}</b>
              {ret===null?<em>待积累</em>:<span className={ret>0?'pt-up':ret<0?'pt-down':'pt-flat'}>{pctSigned(ret)}</span>}
              {excess!==null&&<i className={excess>0?'pt-up':excess<0?'pt-down':'pt-flat'}>超额 {pctSigned(excess)}</i>}
            </span>;
          })}
        </div>
        <h4>操作</h4>
        <div className="pt-ops">
          <button type="button" className="pt-primary" disabled={readOnly} title={readOnly?'只读预览不可交易':'打开本机人工委托票据'} onClick={()=>onPick(entry,'buy')}>买入</button>
          <button type="button" disabled={readOnly} title={readOnly?'只读预览不可交易':'打开本机人工委托票据'} onClick={()=>onPick(entry,'sell')}>卖出</button>
          <button type="button" disabled={readOnly||busy||watched} onClick={()=>void onWatch(entry)}>{watched?'已在自选':'加自选'}</button>
          <button type="button" className="pt-danger" disabled={readOnly||busy} onClick={()=>void onDelete(entry)}>删除</button>
          {readOnly&&<span className="pt-muted">只读预览：添加/删除/自选/交易请在桌面客户端操作。</span>}
        </div>
      </div>
    </div>
  </section>;
}

function BacktestPanel({request,preview}:{request:Request;preview:boolean}){
  const [data,setData]=useState<BacktestData|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [filter,setFilter]=useState<BacktestFilter>({...DEFAULT_BACKTEST_FILTER});
  const sequence=useRef(0);
  const read=useCallback(async()=>{
    const seq=++sequence.current;
    setLoading(true);setError('');
    try{
      const next=await request<BacktestData>('pool_backtest');
      if(seq!==sequence.current)return;
      setData(next);setError(next.error||'');
    }catch(cause){
      if(seq===sequence.current)setError(cause instanceof Error?cause.message:'回测读取失败');
    }finally{
      if(seq===sequence.current)setLoading(false);
    }
  },[request]);
  useEffect(()=>{void read();},[read]);
  const allRows=useMemo<BacktestRow[]>(()=>data?.rows??[],[data]);
  const sources=useMemo(()=>backtestSources(allRows),[allRows]);
  const rows=useMemo(()=>filterBacktestRows(allRows,filter),[allRows,filter]);
  const summary=useMemo(()=>backtestSummary(rows),[rows]);
  const byEpisodes=useMemo(()=>bucketByEpisodes(rows),[rows]);
  const byPercent=useMemo(()=>bucketByPercent(rows),[rows]);
  const byDay=useMemo(()=>bucketByFirstDay(rows),[rows]);
  const coverage=data?.coverage??null;
  const anchor=backtestAnchor(allRows);
  const detailRows=useMemo(()=>[...rows].sort((left,right)=>
    String(right.first_day||'').localeCompare(String(left.first_day||''))
    || (right.episodes??0)-(left.episodes??0)
    || String(left.code).localeCompare(String(right.code))),[rows]);
  const patch=(next:Partial<BacktestFilter>)=>setFilter(current=>({...current,...next}));
  const summaryText=summary.rows
    ?'样本 '+summary.rows+' · 上涨占比（T+1·n='+summary.sample+'） '+(isNum(summary.upRate)?summary.upRate.toFixed(1)+'%':'—')
      +' · 平均收益 '+(isNum(summary.avgReturn)?pctSigned(summary.avgReturn):'—')
      +' · 平均超额 '+(isNum(summary.avgExcess)?pctSigned(summary.avgExcess):'—')
      +' · 已出结果 '+summary.done+' / 未到期 '+summary.pending+' / 缺数据 '+summary.missing
    :'筛选下无样本';
  const bucketTables:{title:string;buckets:BucketStat[]}[]=[
    {title:'按入选天数',buckets:byEpisodes},
    {title:'按入选涨幅',buckets:byPercent},
    {title:'按入选时间（最近10个入选日）',buckets:byDay},
  ];
  return <section className="pt-backtest" id="pt-backtest" aria-label="入选回测">
    <div className="pt-bt-head">
      <b>回测</b>
      {preview&&<span className="pt-bt-badge">回放/历史样本</span>}
      <span className="pt-bt-summary">{summaryText}</span>
      <span className="pt-spacer"/>
      <button type="button" className="pt-link" disabled={loading} onClick={()=>void read()}>{loading?'读取中…':'刷新'}</button>
    </div>
    {error&&<p className="pt-error" role="alert">{error}<button type="button" onClick={()=>void read()}>重试</button></p>}
    <div className="pt-bt-filters" role="group" aria-label="回测筛选">
      <label className="pt-field">入选时间<select aria-label="回测入选时间" value={filter.period} onChange={event=>patch({period:event.target.value as RowPeriod})}>
        {PERIOD_OPTIONS.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label className="pt-field">入选天数<select aria-label="回测入选天数" value={filter.episodes} onChange={event=>patch({episodes:event.target.value as BacktestFilter['episodes']})}>
        {BACKTEST_EPISODE_OPTIONS.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label className="pt-field">入选涨幅<select aria-label="回测入选涨幅" value={filter.percent} onChange={event=>patch({percent:event.target.value as BacktestFilter['percent']})}>
        {BACKTEST_PERCENT_OPTIONS.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label className="pt-field">来源<select aria-label="回测来源" value={filter.source} onChange={event=>patch({source:event.target.value})}>
        <option>全部</option>{sources.map(source=><option key={source}>{source}</option>)}</select></label>
      <button type="button" className="pt-link" onClick={()=>setFilter({...DEFAULT_BACKTEST_FILTER})}>重置</button>
      <span className="pt-muted">筛选后 {rows.length} / 全部 {allRows.length}{anchor?' · 样本区间至 '+dayShort(anchor):''}</span>
    </div>
    <div className="pt-bt-buckets">
      {bucketTables.map(table=><div className="pt-bt-block" key={table.title}>
        <h5>{table.title}</h5>
        <table className="pt-mini pt-bt-table"><thead><tr><th>分桶</th><th>条数</th><th>样本</th><th>上涨占比</th><th>平均收益</th><th>平均超额</th></tr></thead>
          <tbody>{table.buckets.map(bucket=><tr key={bucket.key}>
            <td>{bucket.label}</td><td>{bucket.rows}</td><td>{bucket.sample}</td>
            <td>{isNum(bucket.upRate)?bucket.upRate.toFixed(1)+'%':'—'}</td>
            <td className={isNum(bucket.avgReturn)?(bucket.avgReturn>0?'pt-up':bucket.avgReturn<0?'pt-down':'pt-flat'):''}>{isNum(bucket.avgReturn)?pctSigned(bucket.avgReturn):'—'}</td>
            <td className={isNum(bucket.avgExcess)?(bucket.avgExcess>0?'pt-up':bucket.avgExcess<0?'pt-down':'pt-flat'):''}>{isNum(bucket.avgExcess)?pctSigned(bucket.avgExcess):'—'}</td>
          </tr>)}</tbody></table>
      </div>)}
    </div>
    {rows.length?<div className="pt-scroll"><table className="pt-mini pt-bt-table pt-bt-detail">
      <thead><tr><th>代码</th><th>名称</th><th>首次入选</th><th>入选价格</th><th>入选天数</th><th>入选时涨幅</th><th>T+1</th><th>T+3</th><th>T+5</th></tr></thead>
      <tbody>{detailRows.map(row=><tr key={row.code}>
        <td className="pt-code">{row.code}</td><td>{row.name}</td><td>{row.first_day?dayShort(row.first_day):'—'}</td>
        <td>{num2(row.first_price)}</td><td className="pt-count">{row.episodes??1}</td>
        <td className={isNum(row.first_percent)?(row.first_percent>0?'pt-up':row.first_percent<0?'pt-down':'pt-flat'):''}>{pctSigned(row.first_percent)}</td>
        {HORIZONS.map(horizon=>{
          const cell=horizonCell(row,horizon);
          return <td key={horizon} className={'pt-hz pt-'+cell.tone} title={horizonTitle(row,horizon)}>{cell.text}</td>;
        })}
      </tr>)}</tbody></table></div>:<p className="pt-empty">筛选下没有回测样本。</p>}
    <p className="pt-muted pt-bt-note">口径：T+N = 首次入选日之后第 N 个交易日收盘 / 入选价格 − 1；基准 {coverage?.bench||'上证指数'}；超额 = 个股收益 − 基准收益。未到期/缺数据不按 0 计。{backtestCoverageText(coverage)}{coverage?.note?' '+coverage.note:''}回放/历史样本仅供研究，不构成投资建议；不自动下单。</p>
  </section>;
}
